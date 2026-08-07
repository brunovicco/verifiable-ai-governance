"""Canonical, idempotent demo scenario for runtime AI governance."""

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid5

from ai_governance_api.adapters import (
    SqlAlchemyAssessmentAudit,
    SqlAlchemyAssessmentStore,
    SqlAlchemyIncidentAudit,
    SqlAlchemyIncidentRepository,
    SqlAlchemyModelRoutingAudit,
    SqlAlchemyModelRoutingDecisionStore,
    SqlAlchemyModelRoutingScopeReader,
    SqlAlchemyTransaction,
)
from ai_governance_api.application import (
    IncidentService,
    RequestModelRoutingDecision,
    SaveAssessment,
    SubmitAssessment,
)
from ai_governance_api.config import AppEnvironment, get_settings
from ai_governance_api.database import SessionFactory, engine
from ai_governance_api.domain.assessments import (
    AIImpactAnswers,
    AssessmentActor,
    AssessmentAnswers,
    AssessmentKind,
    InternationalProcessingAnswers,
    RIPDAnswers,
    Subprocessor,
)
from ai_governance_api.domain.evidence import EvidenceKind
from ai_governance_api.domain.identity import Principal
from ai_governance_api.domain.incidents import IncidentStatus
from ai_governance_api.domain.model_routing import (
    ModelRoutingCommand,
    ModelRoutingDecisionRecord,
    PolicyModelRouterDecision,
    PolicyModelRouterRequest,
    RouterDecisionOutcome,
    RoutingEnforcementOutcome,
    RoutingWorkload,
)
from ai_governance_api.models import (
    Agent,
    AISystem,
    Approval,
    Assessment,
    Base,
    Evidence,
    Incident,
    Initiative,
    ModelAsset,
    ModelRoutingDecisionEntry,
)
from ai_governance_api.schemas import (
    AgentCreate,
    AISystemCreate,
    ApprovalDecisionRequest,
    AssetReviewRequest,
    InitiativeCreate,
    ModelAssetCreate,
    SubmissionRequest,
)
from ai_governance_api.services import InitiativeService, InventoryService
from governance_schemas import (
    ApprovalArea,
    ApprovalStatus,
    AutonomyLevel,
    DataClassification,
    DecisionImpact,
    EntityStatus,
    HostingModel,
    RiskTier,
)
from policy_engine import GovernancePolicyEngine
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

SCENARIO_ID = "credit-pj-governed-runtime"
SCENARIO_VERSION = "1.0.0"
INITIATIVE_NAME = "[DEMO-CANONICAL] Análise de Crédito PJ Assistida e Auditável"
SYSTEM_NAME = "Mesa de Crédito PJ Governada"
APPROVED_MODEL_NAME = "credit-opinion-approved"
OUT_OF_SCOPE_MODEL_NAME = "credit-opinion-experimental"
AGENT_NAME = "Agente de Parecer de Crédito PJ"
INCIDENT_TITLE = "Tentativa bloqueada de uso de modelo fora do escopo"
WORKFLOW_ID = "demo-credit-pj-2026-001"
ALLOWED_TASK_ID = "draft-opinion-authorized-model"
BLOCKED_TASK_ID = "draft-opinion-unapproved-model"
APPROVED_ROUTING_GROUP = "reasoning-strong"
OUT_OF_SCOPE_ROUTING_GROUP = "credit-opinion-experimental"
RESET_CONFIRMATION = "CANONICAL-DEMO-ONLY"

CONTROL_IDS = (
    "GOV-HUM-001",
    "GOV-MOD-003",
    "GOV-AGT-002",
    "GOV-AGT-004",
    "GOV-OPS-001",
    "GOV-EVD-001",
    "GOV-EVD-002",
)
EXPECTED_ASSESSMENT_KINDS = frozenset(
    {
        AssessmentKind.AI_IMPACT.value,
        AssessmentKind.RIPD.value,
        AssessmentKind.INTERNATIONAL_PROCESSING.value,
    }
)
EXPECTED_EVIDENCE_KINDS = frozenset(kind.value for kind in EvidenceKind)
DEMO_NAMESPACE = UUID("a83c529a-257f-4fb5-a7b6-9f611793d9b4")
POLICY_EVALUATOR = GovernancePolicyEngine()
OWNER = Principal(user_id="demo.requester")


class CanonicalDemoDriftError(RuntimeError):
    """Raised when an existing canonical scenario is partial or inconsistent."""


class DemoResetRefused(RuntimeError):
    """Raised when destructive reset safeguards are not satisfied."""


@dataclass(frozen=True, slots=True)
class CanonicalDemoSummary:
    """Stable identifiers and counts for the canonical scenario."""

    scenario_id: str
    scenario_version: str
    state: str
    initiative_id: str
    ai_system_id: str
    approved_model_id: str
    out_of_scope_model_id: str
    agent_id: str
    allowed_routing_decision_id: str
    blocked_routing_decision_id: str
    incident_id: str
    assessment_count: int
    approval_count: int
    evidence_count: int
    control_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-safe representation with deterministic list ordering."""
        payload = asdict(self)
        payload["control_ids"] = list(self.control_ids)
        return payload


@dataclass(frozen=True, slots=True)
class _ScenarioRows:
    """Database projection used to validate the canonical scenario."""

    initiative: Initiative
    ai_system: AISystem
    approved_model: ModelAsset
    out_of_scope_model: ModelAsset
    agent: Agent
    assessments: tuple[Assessment, ...]
    approvals: tuple[Approval, ...]
    evidence: tuple[Evidence, ...]
    routing_decisions: tuple[ModelRoutingDecisionEntry, ...]
    incident: Incident


class _DemoPolicyModelRouter:
    """Deterministic policy-router stub used only to seed reproducible evidence."""

    async def decide(
        self,
        request: PolicyModelRouterRequest,
        *,
        correlation_id: str,
    ) -> PolicyModelRouterDecision:
        """Return an accepted logical group selected from the task identifier."""
        selected_group = (
            APPROVED_ROUTING_GROUP
            if request.task_id == ALLOWED_TASK_ID
            else OUT_OF_SCOPE_ROUTING_GROUP
        )
        decided_at = datetime.now(UTC)
        policy_payload = {
            "policy_id": "demo-credit-routing-policy",
            "policy_version": SCENARIO_VERSION,
            "allowed_group": APPROVED_ROUTING_GROUP,
            "selected_group": selected_group,
            "task_id": request.task_id,
        }
        policy_digest = hashlib.sha256(
            json.dumps(
                policy_payload,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        return PolicyModelRouterDecision(
            outcome=RouterDecisionOutcome.ACCEPTED,
            schema_version="1.0",
            routing_decision_id=f"demo-router-{correlation_id}",
            decided_at=decided_at,
            workflow_id=request.workflow_id,
            task_id=request.task_id,
            selected_model_group=selected_group,
            rejected_model_group=None,
            reason="Logical model group selected by the deterministic demo policy.",
            reason_code=None,
            observed_value=selected_group,
            required_value=APPROVED_ROUTING_GROUP,
            rejected_candidates=(),
            policy_id="demo-credit-routing-policy",
            policy_version=SCENARIO_VERSION,
            policy_digest=policy_digest,
            service_version="demo-seed-1.0.0",
            environment="demo",
        )


async def ensure_canonical_demo() -> CanonicalDemoSummary:
    """Create the canonical scenario once or validate the existing complete state."""
    existing = await inspect_canonical_demo()
    if existing is not None:
        return existing
    await _create_canonical_demo()
    created = await inspect_canonical_demo()
    if created is None:
        raise CanonicalDemoDriftError(
            "Canonical scenario was not found after the seed transaction completed"
        )
    return replace(created, state="created")


async def inspect_canonical_demo() -> CanonicalDemoSummary | None:
    """Return the validated canonical scenario, or ``None`` when it is absent."""
    async with SessionFactory() as session:
        initiatives = tuple(
            await session.scalars(select(Initiative).where(Initiative.name == INITIATIVE_NAME))
        )
        if not initiatives:
            return None
        if len(initiatives) != 1:
            raise CanonicalDemoDriftError("Expected exactly one canonical demo initiative")
        rows = await _load_scenario_rows(session, initiatives[0])

    errors = _validate_scenario(rows)
    if errors:
        formatted = "\n".join(f"- {error}" for error in errors)
        raise CanonicalDemoDriftError(
            "Canonical demo exists but is incomplete or inconsistent:\n"
            f"{formatted}\n"
            "Use the explicit reset command only on a dedicated demo database."
        )
    return _summary_from_rows(rows, state="current")


async def reset_application_data(*, confirmation: str) -> None:
    """Clear all application tables on an explicitly confirmed non-production DB."""
    environment = get_settings().app_env
    validate_reset_request(environment=environment, confirmation=confirmation)
    async with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            await connection.execute(delete(table))


def validate_reset_request(
    *,
    environment: AppEnvironment,
    confirmation: str,
) -> None:
    """Enforce a production block and an exact destructive-reset confirmation."""
    if environment is AppEnvironment.PRODUCTION:
        raise DemoResetRefused("Canonical demo reset is disabled when APP_ENV=production")
    if confirmation != RESET_CONFIRMATION:
        raise DemoResetRefused(f"Reset requires the exact confirmation {RESET_CONFIRMATION!r}")


def write_summary(summary: CanonicalDemoSummary, output_path: Path) -> None:
    """Write the resulting runtime manifest with stable JSON formatting."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            summary.to_dict(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


async def _create_canonical_demo() -> None:
    """Drive the real application services through one complete governed story."""
    initiative = await _create_initiative()
    await _create_and_submit_assessments(initiative.id)
    await _add_evidence_set(initiative.id)
    await _submit_and_approve_initiative(initiative.id)

    ai_system = await _create_ai_system(initiative.id)
    review_deadline = datetime.now(UTC) + timedelta(days=90)
    approved_model = await _create_approved_model(ai_system.id, review_deadline)
    await _create_out_of_scope_model(ai_system.id)
    agent = await _create_approved_agent(ai_system.id, approved_model.id, review_deadline)

    allowed, blocked = await _record_routing_decisions(agent.id)
    if allowed.outcome is not RoutingEnforcementOutcome.ALLOWED:
        raise CanonicalDemoDriftError("Expected the approved model-group scenario to be allowed")
    if blocked.outcome is not RoutingEnforcementOutcome.BLOCKED:
        raise CanonicalDemoDriftError(
            "Expected the out-of-scope model-group scenario to be blocked"
        )
    await _record_incident(ai_system.id, blocked.id, blocked.reason_code)


async def _create_initiative() -> Initiative:
    """Create the regulated credit initiative through the real service."""
    countries = ["Brasil", "Estados Unidos"]
    payload = InitiativeCreate(
        name=INITIATIVE_NAME,
        description=(
            "A plataforma consolida dados cadastrais, bureau, políticas e métricas "
            "financeiras para calcular uma recomendação de crédito por regras "
            "determinísticas. O agente de IA não aprova crédito: ele apenas redige "
            "um parecer narrativo a partir de fatos estruturados, sujeito à revisão "
            "e decisão humana."
        ),
        business_area="Crédito Corporate",
        intended_users="Analistas e aprovadores de crédito PJ",
        decision_impact=DecisionImpact.MATERIAL,
        data_classification=DataClassification.RESTRICTED,
        autonomy_level=AutonomyLevel.A2_PREPARE_FOR_APPROVAL,
        hosting_model=HostingModel.CLOUD_MANAGED,
        affects_rights=True,
        executes_actions=False,
        personal_data=True,
        sensitive_data=True,
        external_facing=False,
        regulated_context=True,
        international_processing=True,
        inference_countries=countries,
        uses_rag=False,
        uses_agents=True,
        uses_mcp=True,
        uses_custom_model=False,
    )
    async with SessionFactory() as session:
        return await InitiativeService(session, POLICY_EVALUATOR).create(
            payload,
            OWNER,
        )


async def _create_and_submit_assessments(initiative_id: str) -> None:
    """Create all required structured assessments through application use cases."""
    countries = ("Brasil", "Estados Unidos")
    assessments: tuple[tuple[AssessmentKind, AssessmentAnswers], ...] = (
        (
            AssessmentKind.AI_IMPACT,
            AIImpactAnswers(
                affected_groups=(
                    "empresas solicitantes de crédito",
                    "analistas de crédito",
                    "aprovadores de alçada",
                ),
                intended_benefits=(
                    "Reduzir tempo operacional sem transferir a autoridade de "
                    "aprovação para o modelo de linguagem."
                ),
                potential_harms=(
                    "parecer narrativo inconsistente com os fatos calculados",
                    "viés na explicação apresentada ao aprovador",
                    "uso de modelo fora do escopo aprovado",
                ),
                human_oversight=(
                    "A decisão final permanece com o aprovador humano. O parecer "
                    "pode ser rejeitado, corrigido ou ignorado sem alterar o cálculo "
                    "determinístico."
                ),
                contestability=(
                    "A empresa solicitante pode pedir revisão e o analista consegue "
                    "reconstruir dados, regras, versão da política e evidências."
                ),
                mitigation_measures=(
                    "core determinístico para rating e limites",
                    "roteamento fail-closed",
                    "modelo e agente com escopo revisado",
                    "trilha de auditoria sem conteúdo sensível",
                    "aprovação humana obrigatória",
                ),
                residual_risk=RiskTier.HIGH,
            ),
        ),
        (
            AssessmentKind.RIPD,
            RIPDAnswers(
                controller_area="Crédito Corporate e Governança de Dados",
                processing_purpose=(
                    "Analisar risco de crédito PJ e preparar um parecer explicativo "
                    "para decisão humana."
                ),
                personal_data_categories=(
                    "dados cadastrais de representantes",
                    "dados financeiros da empresa",
                    "informações de bureau",
                ),
                data_subjects=(
                    "representantes legais",
                    "sócios e garantidores quando aplicável",
                ),
                legal_basis=(
                    "Execução de procedimentos contratuais, cumprimento de obrigação "
                    "regulatória e legítimo interesse documentado."
                ),
                necessity_assessment=(
                    "Somente fatos necessários ao cálculo e à explicação são "
                    "disponibilizados ao agente; documentos brutos não são enviados "
                    "como contexto por padrão."
                ),
                risk_scenarios=(
                    "exposição indevida de dados financeiros",
                    "retenção excessiva de conteúdo",
                    "uso secundário incompatível",
                ),
                safeguards=(
                    "minimização de contexto",
                    "controle de acesso por papel",
                    "telemetria sanitizada",
                    "retenção limitada",
                ),
                residual_risk=RiskTier.HIGH,
            ),
        ),
        (
            AssessmentKind.INTERNATIONAL_PROCESSING,
            InternationalProcessingAnswers(
                data_categories=(
                    "fatos financeiros estruturados e minimizados",
                    "metadados técnicos sem prompts ou documentos",
                ),
                source_country="Brasil",
                inference_countries=countries,
                storage_regions=("Brasil",),
                log_regions=("Brasil",),
                subprocessors=(
                    Subprocessor(
                        name="Provedor de inferência gerenciada (simulado)",
                        countries=("Estados Unidos",),
                        purpose="Redação do parecer narrativo autorizado",
                    ),
                ),
                transfer_mechanism=(
                    "Cláusulas contratuais e avaliação de transferência internacional."
                ),
                legal_basis=("Execução de contrato com salvaguardas e minimização de dados."),
                safeguards=(
                    "redação de PII antes da inferência",
                    "zero data retention contratual",
                    "logs restritos a identificadores e métricas",
                ),
                residual_risk=RiskTier.HIGH,
            ),
        ),
    )
    for kind, answers in assessments:
        async with SessionFactory() as session:
            save = SaveAssessment(
                SqlAlchemyAssessmentStore(session),
                SqlAlchemyAssessmentAudit(session),
                SqlAlchemyTransaction(session),
            )
            record = await save.execute(
                initiative_id=initiative_id,
                kind=kind,
                answers=answers,
                actor=AssessmentActor(user_id=OWNER.user_id),
                expected_version=None,
            )
        async with SessionFactory() as session:
            submit = SubmitAssessment(
                SqlAlchemyAssessmentStore(session),
                SqlAlchemyAssessmentAudit(session),
                SqlAlchemyTransaction(session),
            )
            await submit.execute(
                assessment_id=record.id,
                expected_version=record.version,
                actor=AssessmentActor(user_id=OWNER.user_id),
            )


async def _add_evidence_set(initiative_id: str) -> None:
    """Insert content-minimized references covering every evidence category."""
    evidence_specs = (
        (
            EvidenceKind.ARCHITECTURE,
            "urn:demo:credit-pj:architecture:v1",
            ("GOV-MOD-003", "GOV-AGT-002", "GOV-AGT-004"),
        ),
        (
            EvidenceKind.POLICY,
            "urn:demo:credit-pj:routing-policy:v1",
            ("GOV-MOD-003",),
        ),
        (
            EvidenceKind.ASSESSMENT,
            "urn:demo:credit-pj:model-evaluation:v1",
            ("GOV-EVD-002",),
        ),
        (
            EvidenceKind.SECURITY_TEST,
            "urn:demo:credit-pj:prompt-injection-test:v1",
            ("GOV-AGT-002", "GOV-OPS-001"),
        ),
        (
            EvidenceKind.APPROVAL,
            "urn:demo:credit-pj:human-approval-design:v1",
            ("GOV-HUM-001", "GOV-AGT-004"),
        ),
        (
            EvidenceKind.OTHER,
            "urn:demo:credit-pj:incident-runbook:v1",
            ("GOV-EVD-001", "GOV-OPS-001"),
        ),
    )
    async with SessionFactory() as session:
        for kind, uri, control_ids in evidence_specs:
            session.add(
                Evidence(
                    initiative_id=initiative_id,
                    approval_id=None,
                    kind=kind.value,
                    uri=uri,
                    sha256=hashlib.sha256(uri.encode("utf-8")).hexdigest(),
                    supplied_by=OWNER.user_id,
                    trusted_source=False,
                    metadata_json={
                        "origin": "canonical-demo-seed",
                        "scenario_id": SCENARIO_ID,
                        "scenario_version": SCENARIO_VERSION,
                        "control_ids": list(control_ids),
                        "contains_sensitive_content": False,
                    },
                )
            )
        await session.commit()


async def _submit_and_approve_initiative(initiative_id: str) -> None:
    """Submit the initiative and independently approve every required gate."""
    async with SessionFactory() as session:
        service = InitiativeService(session, POLICY_EVALUATOR)
        initiative = await service.get(initiative_id)
        await service.submit(
            initiative_id,
            SubmissionRequest(
                expected_version=initiative.version,
                revision_summary=(
                    "Escopo inicial: decisão determinística, redação assistida, "
                    "modelo aprovado e revisão humana obrigatória."
                ),
            ),
            OWNER,
        )

    async with SessionFactory() as session:
        initiative = await InitiativeService(session, POLICY_EVALUATOR).get(initiative_id)
        areas = tuple(
            approval.area
            for approval in initiative.current_approvals
            if approval.status is ApprovalStatus.PENDING
        )
    for area in areas:
        reviewer = _reviewer(area)
        async with SessionFactory() as session:
            service = InitiativeService(session, POLICY_EVALUATOR)
            initiative = await service.get(initiative_id)
            gate = next(
                approval
                for approval in initiative.current_approvals
                if approval.area is area and approval.status is ApprovalStatus.PENDING
            )
            await service.decide_approval(
                initiative_id,
                gate.id,
                ApprovalDecisionRequest(
                    decision=ApprovalStatus.APPROVED,
                    comments=(
                        f"Área {area.value} aprovou o escopo versionado da demonstração canônica."
                    ),
                    evidence_uri=(
                        f"urn:demo:{SCENARIO_ID}:approval:"
                        f"{initiative.current_review_round}:{area.value}"
                    ),
                    expected_version=gate.version,
                ),
                reviewer,
            )


async def _create_ai_system(initiative_id: str) -> AISystem:
    """Create the production-marked system with explicit demo control metadata."""
    async with SessionFactory() as session:
        return await InventoryService(session).create_system(
            initiative_id,
            AISystemCreate(
                name=SYSTEM_NAME,
                purpose=(
                    "Executar análise determinística de crédito PJ e usar IA "
                    "generativa apenas para redigir um parecer submetido à decisão "
                    "humana."
                ),
                production=True,
                metadata_json={
                    "demo_seed": {
                        "scenario_id": SCENARIO_ID,
                        "scenario_version": SCENARIO_VERSION,
                    },
                    "decision_authority": "human_credit_approver",
                    "llm_role": "opinion_drafting_only",
                    "control_ids": list(CONTROL_IDS),
                },
            ),
            OWNER,
        )


async def _create_approved_model(ai_system_id: str, review_deadline: datetime) -> ModelAsset:
    """Create and independently review the only model allowed for the agent."""
    async with SessionFactory() as session:
        model = await InventoryService(session).create_model(
            ai_system_id,
            ModelAssetCreate(
                provider="Azure OpenAI (simulado)",
                model_name=APPROVED_MODEL_NAME,
                model_version="2026.08.0",
                routing_group=APPROVED_ROUTING_GROUP,
                deployment_region="Brazil South",
                approved_use_cases=["redação de parecer de crédito a partir de fatos estruturados"],
                prohibited_use_cases=[
                    "aprovação autônoma de crédito",
                    "alteração de rating ou limite",
                    "execução de ferramentas transacionais",
                ],
                allowed_data_classes=[DataClassification.RESTRICTED],
                evaluation_baseline={
                    "dataset": "credit-opinion-eval-v1",
                    "factual_consistency": 0.96,
                    "schema_compliance": 0.99,
                    "prompt_injection_block_rate": 1.0,
                    "quality_gate": "passed",
                },
            ),
            OWNER,
        )
    async with SessionFactory() as session:
        stored = await session.get(ModelAsset, model.id)
        if stored is None:
            raise CanonicalDemoDriftError("Approved model disappeared before review")
        return await InventoryService(session).review_model(
            model.id,
            AssetReviewRequest(
                expected_version=stored.version,
                next_review_at=review_deadline,
                reference="DEMO-ARCH-CREDIT-001",
            ),
            _reviewer(ApprovalArea.ARCHITECTURE),
        )


async def _create_out_of_scope_model(ai_system_id: str) -> ModelAsset:
    """Register but deliberately leave one model unreviewed and unauthorized."""
    async with SessionFactory() as session:
        return await InventoryService(session).create_model(
            ai_system_id,
            ModelAssetCreate(
                provider="Fornecedor experimental externo (simulado)",
                model_name=OUT_OF_SCOPE_MODEL_NAME,
                model_version="0.1.0-experimental",
                routing_group=OUT_OF_SCOPE_ROUTING_GROUP,
                deployment_region="United States",
                approved_use_cases=[],
                prohibited_use_cases=[
                    "dados restritos",
                    "decisão ou parecer de crédito",
                ],
                allowed_data_classes=[],
                evaluation_baseline={
                    "dataset": "not-approved",
                    "quality_gate": "not_evaluated",
                },
            ),
            OWNER,
        )


async def _create_approved_agent(
    ai_system_id: str,
    approved_model_id: str,
    review_deadline: datetime,
) -> Agent:
    """Create and review an agent that cannot approve its own credit outcome."""
    async with SessionFactory() as session:
        agent = await InventoryService(session).create_agent(
            ai_system_id,
            AgentCreate(
                name=AGENT_NAME,
                purpose=(
                    "Redigir um parecer explicativo usando somente fatos produzidos "
                    "pelo core determinístico; não calcula, aprova ou executa crédito."
                ),
                owner_id=OWNER.user_id,
                agent_version="1.0.0",
                deployment_region="Brasil",
                autonomy_level=AutonomyLevel.A2_PREPARE_FOR_APPROVAL,
                allowed_models=[approved_model_id],
                tools=[
                    "policy-mcp:read",
                    "bureau-mcp:read",
                    "credit-core:read",
                ],
                permissions=[
                    "credit:analysis:read",
                    "credit:opinion:draft",
                ],
                max_cost=0.50,
                max_runtime_seconds=30,
                human_approval_points=[
                    "aprovação final de crédito",
                    "alteração de rating, limite ou garantias",
                ],
                kill_switch_enabled=True,
            ),
            OWNER,
        )
    async with SessionFactory() as session:
        stored = await session.get(Agent, agent.id)
        if stored is None:
            raise CanonicalDemoDriftError("Agent disappeared before review")
        return await InventoryService(session).review_agent(
            agent.id,
            AssetReviewRequest(
                expected_version=stored.version,
                next_review_at=review_deadline,
                reference="DEMO-SEC-CREDIT-001",
            ),
            _reviewer(ApprovalArea.SECURITY),
        )


async def _record_routing_decisions(
    agent_id: str,
) -> tuple[ModelRoutingDecisionRecord, ModelRoutingDecisionRecord]:
    """Record one allowed and one locally blocked routing decision."""
    ids = iter(
        (
            str(uuid5(DEMO_NAMESPACE, ALLOWED_TASK_ID)),
            str(uuid5(DEMO_NAMESPACE, BLOCKED_TASK_ID)),
        )
    )
    async with SessionFactory() as session:
        use_case = RequestModelRoutingDecision(
            SqlAlchemyModelRoutingScopeReader(SessionFactory),
            _DemoPolicyModelRouter(),
            SqlAlchemyModelRoutingDecisionStore(session),
            SqlAlchemyModelRoutingAudit(session),
            SqlAlchemyTransaction(session),
            id_factory=lambda: next(ids),
        )
        allowed = await use_case.execute(
            agent_id=agent_id,
            command=_routing_command(ALLOWED_TASK_ID),
            principal=OWNER,
        )
        blocked = await use_case.execute(
            agent_id=agent_id,
            command=_routing_command(BLOCKED_TASK_ID),
            principal=OWNER,
        )
    return allowed, blocked


def _routing_command(task_id: str) -> ModelRoutingCommand:
    """Build one bounded opinion-drafting request without prompt content."""
    return ModelRoutingCommand(
        workflow_id=WORKFLOW_ID,
        task_id=task_id,
        workload=RoutingWorkload.OPINION_DRAFTING,
        context_tokens_estimated=3000,
        max_output_tokens_estimated=900,
        structured_output_required=True,
        max_latency_ms=4500,
        max_cost_usd=Decimal("0.30"),
    )


async def _record_incident(
    ai_system_id: str,
    blocked_decision_id: str,
    reason_code: str | None,
) -> None:
    """Open, contain and assign remediation for the blocked runtime attempt."""
    now = datetime.now(UTC)
    async with SessionFactory() as session:
        service = IncidentService(
            SqlAlchemyIncidentRepository(session),
            SqlAlchemyIncidentAudit(session),
            SqlAlchemyTransaction(session),
            id_factory=lambda: str(uuid5(DEMO_NAMESPACE, INCIDENT_TITLE)),
        )
        incident = await service.report_incident(
            ai_system_id=ai_system_id,
            title=INCIDENT_TITLE,
            severity=RiskTier.HIGH,
            description=(
                "O Policy Model Router retornou um grupo lógico fora do escopo "
                "revisado do agente. O Governance bloqueou a execução antes da "
                "inferência. "
                f"routing_decision_id={blocked_decision_id}; "
                f"reason_code={reason_code or 'unknown'}."
            ),
            detected_at=now,
            principal=OWNER,
        )
        incident = await service.contain_incident(
            incident_id=incident.id,
            containment=(
                "Nenhuma chamada ao modelo foi realizada. O grupo experimental "
                "permaneceu fora da allowlist e o evento foi preservado na trilha."
            ),
            expected_version=incident.version,
            principal=OWNER,
        )
        await service.set_remediation_plan(
            incident_id=incident.id,
            remediation_owner_id="ai-platform@demo.local",
            remediation_description=(
                "Adicionar teste de regressão do contrato de política e revisar "
                "configuração do grupo experimental antes de qualquer aprovação."
            ),
            remediation_due_at=now + timedelta(days=30),
            expected_version=incident.version,
            principal=OWNER,
        )


async def _load_scenario_rows(
    session: AsyncSession,
    initiative: Initiative,
) -> _ScenarioRows:
    """Load the complete scenario using explicit queries and relationships."""
    systems = tuple(
        await session.scalars(select(AISystem).where(AISystem.initiative_id == initiative.id))
    )
    if len(systems) != 1:
        raise CanonicalDemoDriftError(f"Expected one canonical AI system, found {len(systems)}")
    ai_system = systems[0]

    models = tuple(
        await session.scalars(select(ModelAsset).where(ModelAsset.ai_system_id == ai_system.id))
    )
    approved_models = tuple(model for model in models if model.model_name == APPROVED_MODEL_NAME)
    out_of_scope_models = tuple(
        model for model in models if model.model_name == OUT_OF_SCOPE_MODEL_NAME
    )
    if len(approved_models) != 1 or len(out_of_scope_models) != 1:
        raise CanonicalDemoDriftError("Canonical model inventory is missing or duplicated")

    agents = tuple(await session.scalars(select(Agent).where(Agent.ai_system_id == ai_system.id)))
    matching_agents = tuple(agent for agent in agents if agent.name == AGENT_NAME)
    if len(matching_agents) != 1:
        raise CanonicalDemoDriftError("Canonical governed agent is missing or duplicated")
    agent = matching_agents[0]

    assessments = tuple(
        await session.scalars(select(Assessment).where(Assessment.initiative_id == initiative.id))
    )
    approvals = tuple(
        await session.scalars(
            select(Approval).where(
                Approval.initiative_id == initiative.id,
                Approval.review_round == initiative.current_review_round,
            )
        )
    )
    evidence = tuple(
        await session.scalars(select(Evidence).where(Evidence.initiative_id == initiative.id))
    )
    routing_decisions = tuple(
        await session.scalars(
            select(ModelRoutingDecisionEntry).where(
                ModelRoutingDecisionEntry.agent_id == agent.id,
                ModelRoutingDecisionEntry.workflow_id == WORKFLOW_ID,
            )
        )
    )
    incidents = tuple(
        await session.scalars(
            select(Incident).where(
                Incident.ai_system_id == ai_system.id,
                Incident.title == INCIDENT_TITLE,
            )
        )
    )
    if len(incidents) != 1:
        raise CanonicalDemoDriftError("Canonical runtime incident is missing or duplicated")

    return _ScenarioRows(
        initiative=initiative,
        ai_system=ai_system,
        approved_model=approved_models[0],
        out_of_scope_model=out_of_scope_models[0],
        agent=agent,
        assessments=assessments,
        approvals=approvals,
        evidence=evidence,
        routing_decisions=routing_decisions,
        incident=incidents[0],
    )


def _validate_scenario(rows: _ScenarioRows) -> list[str]:
    """Return every material inconsistency instead of stopping at the first."""
    errors: list[str] = []
    if rows.initiative.status is not EntityStatus.APPROVED:
        errors.append(f"initiative status is {rows.initiative.status.value}, expected approved")
    if rows.ai_system.name != SYSTEM_NAME:
        errors.append("canonical AI system name changed")
    if rows.ai_system.status is not EntityStatus.ACTIVE:
        errors.append(f"AI system status is {rows.ai_system.status.value}, expected active")
    metadata = rows.ai_system.metadata_json
    if metadata.get("demo_seed") != {
        "scenario_id": SCENARIO_ID,
        "scenario_version": SCENARIO_VERSION,
    }:
        errors.append("AI system demo-seed metadata is missing or changed")
    if tuple(sorted(metadata.get("control_ids", []))) != tuple(sorted(CONTROL_IDS)):
        errors.append("canonical control set is missing or changed")

    assessment_kinds = frozenset(assessment.assessment_type for assessment in rows.assessments)
    if assessment_kinds != EXPECTED_ASSESSMENT_KINDS:
        errors.append(
            "assessment kinds differ from the canonical AI impact, RIPD and "
            "international-processing set"
        )
    if not rows.approvals:
        errors.append("initiative has no current approval gates")
    if any(approval.status is not ApprovalStatus.APPROVED for approval in rows.approvals):
        errors.append("not every current approval gate is approved")

    evidence_kinds = frozenset(item.kind for item in rows.evidence)
    if not EXPECTED_EVIDENCE_KINDS.issubset(evidence_kinds):
        missing = sorted(EXPECTED_EVIDENCE_KINDS - evidence_kinds)
        errors.append(f"missing evidence kinds: {', '.join(missing)}")

    if rows.approved_model.status is not EntityStatus.APPROVED:
        errors.append("approved model is not in approved lifecycle state")
    if rows.approved_model.routing_group != APPROVED_ROUTING_GROUP:
        errors.append("approved model routing group changed")
    if rows.approved_model.approved_scope_digest is None:
        errors.append("approved model has no bound review digest")
    if rows.out_of_scope_model.status is not EntityStatus.DRAFT:
        errors.append("out-of-scope model must remain unreviewed and draft")

    if rows.agent.status is not EntityStatus.APPROVED:
        errors.append("canonical agent is not approved")
    if rows.agent.approved_scope_digest is None:
        errors.append("canonical agent has no bound review digest")
    if rows.agent.allowed_models != [rows.approved_model.id]:
        errors.append("agent model allowlist differs from the approved model")
    if "credit:approve" in rows.agent.permissions:
        errors.append("agent must never receive credit approval authority")
    if rows.agent.kill_switch_engaged:
        errors.append("P0.3 seed must not leave the kill switch engaged")

    decisions_by_task = {decision.task_id: decision for decision in rows.routing_decisions}
    if set(decisions_by_task) != {ALLOWED_TASK_ID, BLOCKED_TASK_ID}:
        errors.append("canonical allowed/blocked routing decisions are incomplete")
    else:
        allowed = decisions_by_task[ALLOWED_TASK_ID]
        blocked = decisions_by_task[BLOCKED_TASK_ID]
        if allowed.outcome != RoutingEnforcementOutcome.ALLOWED.value:
            errors.append("authorized routing decision is not allowed")
        if allowed.selected_model_group != APPROVED_ROUTING_GROUP:
            errors.append("authorized routing decision selected the wrong group")
        if blocked.outcome != RoutingEnforcementOutcome.BLOCKED.value:
            errors.append("out-of-scope routing decision is not blocked")
        if blocked.selected_model_group != OUT_OF_SCOPE_ROUTING_GROUP:
            errors.append("blocked routing decision did not preserve selected group")
        if blocked.reason_code != "selected_model_group_not_approved":
            errors.append("blocked routing decision reason code changed")

    if rows.incident.status is not IncidentStatus.REMEDIATING:
        errors.append(f"incident status is {rows.incident.status.value}, expected remediating")
    if rows.incident.remediation_owner_id is None:
        errors.append("incident remediation owner is missing")
    if rows.incident.remediation_due_at is None:
        errors.append("incident remediation due date is missing")
    return errors


def _summary_from_rows(
    rows: _ScenarioRows,
    *,
    state: str,
) -> CanonicalDemoSummary:
    """Build a concise manifest from a validated database projection."""
    decisions_by_task = {decision.task_id: decision for decision in rows.routing_decisions}
    return CanonicalDemoSummary(
        scenario_id=SCENARIO_ID,
        scenario_version=SCENARIO_VERSION,
        state=state,
        initiative_id=rows.initiative.id,
        ai_system_id=rows.ai_system.id,
        approved_model_id=rows.approved_model.id,
        out_of_scope_model_id=rows.out_of_scope_model.id,
        agent_id=rows.agent.id,
        allowed_routing_decision_id=decisions_by_task[ALLOWED_TASK_ID].id,
        blocked_routing_decision_id=decisions_by_task[BLOCKED_TASK_ID].id,
        incident_id=rows.incident.id,
        assessment_count=len(rows.assessments),
        approval_count=len(rows.approvals),
        evidence_count=len(rows.evidence),
        control_ids=tuple(sorted(CONTROL_IDS)),
    )


def _reviewer(area: ApprovalArea) -> Principal:
    """Return an independent reviewer authorized for one approval area."""
    return Principal(
        user_id=f"reviewer.{area.value}@demo.local",
        approval_areas=frozenset({area}),
    )
