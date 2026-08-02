"""Populate the local development database with ten ``[DEMO]`` initiatives.

Run once against a fresh local Postgres (after ``make dev`` or ``make migrate``):

    make seed-demo

The script drives the real application services end to end (no HTTP layer, no
fixtures) so every seeded state is one the platform can genuinely reach. It
aborts if any ``[DEMO]`` initiative already exists; rerunning against the same
database is not supported. Reset the local Postgres volume and re-migrate
before seeding again.

Known gap: ``EntityStatus.SUSPENDED`` is defined in ``governance_schemas`` but
is never assigned by any application service in this codebase (confirmed by a
repo-wide search) -- there is no reachable transition to seed, so it is
intentionally absent from the ten cases below. Coverage is otherwise 7 of 8
``EntityStatus`` values, all 4 ``RiskTier`` values, all 3 ``AssessmentKind``
values, and all 6 ``EvidenceKind`` values.
"""

import asyncio
import hashlib
import io
import sys
import traceback
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from ai_governance_api.adapters import (
    ClamAVScanner,
    S3ObjectStorage,
    SqlAlchemyAssessmentAudit,
    SqlAlchemyAssessmentStore,
    SqlAlchemyEvidenceAudit,
    SqlAlchemyEvidenceStore,
    SqlAlchemyTransaction,
)
from ai_governance_api.application import SaveAssessment, SubmitAssessment, UploadEvidence
from ai_governance_api.config import get_settings
from ai_governance_api.database import SessionFactory
from ai_governance_api.domain.assessments import (
    AIImpactAnswers,
    AssessmentActor,
    AssessmentAnswers,
    AssessmentKind,
    InternationalProcessingAnswers,
    RIPDAnswers,
    Subprocessor,
)
from ai_governance_api.domain.evidence import EvidenceActor, EvidenceKind
from ai_governance_api.domain.identity import Principal
from ai_governance_api.errors import ApplicationError, ErrorKind
from ai_governance_api.models import Agent, Assessment, Evidence, Initiative, ModelAsset
from ai_governance_api.schemas import (
    AgentCreate,
    AISystemCreate,
    ApprovalDecisionRequest,
    AssetReviewRequest,
    InitiativeCreate,
    InitiativeResubmissionRequest,
    InitiativeRevisionRequest,
    ModelAssetCreate,
    RetirementRequest,
    SubmissionRequest,
)
from ai_governance_api.services import InitiativeService, InventoryService
from governance_schemas import (
    ApprovalArea,
    ApprovalStatus,
    AutonomyLevel,
    DataClassification,
    DecisionImpact,
    HostingModel,
    RiskTier,
)
from policy_engine import GovernancePolicyEngine
from sqlalchemy import select

DEMO_PREFIX = "[DEMO] "
POLICY_EVALUATOR = GovernancePolicyEngine()
ADMIN = Principal(user_id="admin.governanca@demo.local", is_admin=True)


def _owner(slug: str) -> Principal:
    """Return a distinct owner principal for one demo initiative."""
    return Principal(user_id=f"owner.{slug}@demo.local")


def _reviewer(area: ApprovalArea) -> Principal:
    """Return the shared reviewer principal authorized for one approval area."""
    return Principal(user_id=f"reviewer.{area.value}@demo.local", approval_areas=frozenset({area}))


class _InMemoryUpload:
    """Minimal in-memory ``EvidenceSource`` used for the real upload pipeline."""

    def __init__(self, filename: str, content_type: str, content: bytes) -> None:
        """Wrap fixed bytes as an asynchronously readable upload source."""
        self.filename = filename
        self.content_type = content_type
        self._buffer = io.BytesIO(content)

    async def read(self, size: int) -> bytes:
        """Read at most ``size`` bytes from the wrapped buffer."""
        return self._buffer.read(size)


async def _demo_data_exists() -> bool:
    """Return whether a previous seeding already populated ``[DEMO]`` data."""
    async with SessionFactory() as session:
        existing = await session.scalar(
            select(Initiative.id).where(Initiative.name.like(f"{DEMO_PREFIX}%")).limit(1)
        )
    return existing is not None


async def _create_initiative(payload: InitiativeCreate, owner: Principal) -> Initiative:
    """Create one initiative through the real initiative service."""
    async with SessionFactory() as session:
        service = InitiativeService(session, POLICY_EVALUATOR)
        return await service.create(payload, owner)


async def _submit_initiative(
    initiative_id: str,
    owner: Principal,
    *,
    revision_summary: str | None = None,
) -> Initiative:
    """Submit a draft initiative and open its first or next review round."""
    async with SessionFactory() as session:
        service = InitiativeService(session, POLICY_EVALUATOR)
        initiative = await service.get(initiative_id)
        return await service.submit(
            initiative_id,
            SubmissionRequest(
                expected_version=initiative.version, revision_summary=revision_summary
            ),
            owner,
        )


async def _resubmit_initiative(
    initiative_id: str,
    owner: Principal,
    *,
    revision_summary: str,
) -> Initiative:
    """Open a new review round for an initiative with requested changes."""
    async with SessionFactory() as session:
        service = InitiativeService(session, POLICY_EVALUATOR)
        initiative = await service.get(initiative_id)
        return await service.resubmit(
            initiative_id,
            InitiativeResubmissionRequest(
                expected_version=initiative.version,
                revision_summary=revision_summary,
            ),
            owner,
        )


async def _revise_initiative(
    initiative_id: str,
    owner: Principal,
    *,
    change_reason: str,
    description: str,
) -> Initiative:
    """Save corrected proposal facts without opening a new review round."""
    async with SessionFactory() as session:
        service = InitiativeService(session, POLICY_EVALUATOR)
        initiative = await service.get(initiative_id)
        return await service.revise(
            initiative_id,
            InitiativeRevisionRequest(
                expected_version=initiative.version,
                change_reason=change_reason,
                description=description,
            ),
            owner,
        )


async def _decide_one(
    initiative_id: str,
    *,
    area: ApprovalArea,
    decision: ApprovalStatus,
    reviewer: Principal,
) -> Initiative:
    """Decide the current round's pending gate for one approval area."""
    async with SessionFactory() as session:
        service = InitiativeService(session, POLICY_EVALUATOR)
        initiative = await service.get(initiative_id)
        gate = next(
            item
            for item in initiative.approvals
            if item.area == area
            and item.status == ApprovalStatus.PENDING
            and item.review_round == initiative.current_review_round
        )
        return await service.decide_approval(
            initiative_id,
            gate.id,
            ApprovalDecisionRequest(
                decision=decision,
                comments=f"Decisão de {area.value} registrada com evidências e justificativa.",
                evidence_uri=f"urn:demo:{initiative_id}:{area.value}",
                expected_version=gate.version,
            ),
            reviewer,
        )


async def _decide_all_pending(
    initiative_id: str,
    reviewer_for_area: Callable[[ApprovalArea], Principal],
) -> None:
    """Approve every gate still pending in the current review round."""
    async with SessionFactory() as session:
        service = InitiativeService(session, POLICY_EVALUATOR)
        initiative = await service.get(initiative_id)
    areas = [
        item.area
        for item in initiative.approvals
        if item.status == ApprovalStatus.PENDING
        and item.review_round == initiative.current_review_round
    ]
    for area in areas:
        await _decide_one(
            initiative_id,
            area=area,
            decision=ApprovalStatus.APPROVED,
            reviewer=reviewer_for_area(area),
        )


async def _current_assessment_version(initiative_id: str, kind: AssessmentKind) -> int | None:
    """Return the current version of one assessment definition, if it exists."""
    async with SessionFactory() as session:
        assessment = await session.scalar(
            select(Assessment).where(
                Assessment.initiative_id == initiative_id,
                Assessment.assessment_type == kind.value,
            )
        )
    return assessment.version if assessment is not None else None


async def _save_assessment(
    initiative_id: str,
    *,
    kind: AssessmentKind,
    answers: AssessmentAnswers,
    actor: Principal,
    expected_version: int | None = None,
) -> tuple[str, int]:
    """Save one structured assessment draft (create or update) and return id and version."""
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
            actor=AssessmentActor(user_id=actor.user_id),
            expected_version=expected_version,
        )
    return record.id, record.version


async def _submit_assessment(assessment_id: str, expected_version: int, actor: Principal) -> None:
    """Submit a complete draft assessment for independent review."""
    async with SessionFactory() as session:
        submit = SubmitAssessment(
            SqlAlchemyAssessmentStore(session),
            SqlAlchemyAssessmentAudit(session),
            SqlAlchemyTransaction(session),
        )
        await submit.execute(
            assessment_id=assessment_id,
            expected_version=expected_version,
            actor=AssessmentActor(user_id=actor.user_id),
        )


async def _save_and_submit_assessment(
    initiative_id: str,
    *,
    kind: AssessmentKind,
    answers: AssessmentAnswers,
    actor: Principal,
) -> None:
    """Save a structured assessment draft and immediately submit it for review."""
    assessment_id, version = await _save_assessment(
        initiative_id, kind=kind, answers=answers, actor=actor
    )
    await _submit_assessment(assessment_id, version, actor)


async def _add_reference_evidence(
    initiative_id: str,
    *,
    kind: EvidenceKind,
    uri: str,
    supplied_by: str,
) -> None:
    """Insert a human-entered evidence reference, mirroring the approval-attestation pattern."""
    async with SessionFactory() as session:
        session.add(
            Evidence(
                initiative_id=initiative_id,
                approval_id=None,
                kind=kind.value,
                uri=uri,
                sha256=hashlib.sha256(uri.encode()).hexdigest(),
                supplied_by=supplied_by,
                trusted_source=False,
                metadata_json={"origin": "seed-demo-data"},
            )
        )
        await session.commit()


async def _upload_real_evidence(
    initiative_id: str,
    *,
    kind: EvidenceKind,
    filename: str,
    text: str,
    actor: Principal,
) -> None:
    """Run the real scan-and-store evidence pipeline, skipping it if unreachable."""
    settings = get_settings()
    async with SessionFactory() as session:
        upload = UploadEvidence(
            SqlAlchemyEvidenceStore(session),
            ClamAVScanner(
                host=settings.malware_scanner_host,
                port=settings.malware_scanner_port,
                connect_timeout_seconds=settings.malware_scanner_connect_timeout_seconds,
                scan_timeout_seconds=settings.malware_scanner_scan_timeout_seconds,
            ),
            S3ObjectStorage(
                bucket=settings.object_storage_bucket,
                region=settings.object_storage_region,
                endpoint_url=settings.object_storage_endpoint_url,
                access_key=settings.object_storage_access_key,
                secret_key=settings.object_storage_secret_key,
                auto_create_bucket=settings.object_storage_auto_create_bucket,
                server_side_encryption=settings.object_storage_server_side_encryption,
                connect_timeout_seconds=settings.object_storage_connect_timeout_seconds,
                read_timeout_seconds=settings.object_storage_read_timeout_seconds,
            ),
            SqlAlchemyEvidenceAudit(session),
            SqlAlchemyTransaction(session),
            max_bytes=settings.evidence_max_bytes,
            allowed_content_types=settings.evidence_allowed_content_type_set,
        )
        try:
            await upload.execute(
                initiative_id=initiative_id,
                kind=kind,
                source=_InMemoryUpload(filename, "text/plain", text.encode("utf-8")),
                actor=EvidenceActor(user_id=actor.user_id),
            )
        except ApplicationError as exc:
            if exc.kind is not ErrorKind.DEPENDENCY_UNAVAILABLE:
                raise
            print(
                f"[seed]   aviso: pipeline real de evidência indisponível ({exc}); "
                f"pulando evidência {kind.value} (suba ClamAV/MinIO com 'make dev' para incluí-la)"
            )


async def _create_system(
    initiative_id: str,
    owner: Principal,
    *,
    name: str,
    purpose: str,
    production: bool,
) -> str:
    """Create an AI system under an approved initiative and return its id."""
    async with SessionFactory() as session:
        service = InventoryService(session)
        system = await service.create_system(
            initiative_id,
            AISystemCreate(name=name, purpose=purpose, production=production),
            owner,
        )
        return system.id


async def _retire_system(system_id: str, owner: Principal, *, reason: str) -> None:
    """Retire an AI system and its dependent inventory."""
    async with SessionFactory() as session:
        service = InventoryService(session)
        system = await service.get_system(system_id)
        await service.retire_system(
            system_id,
            RetirementRequest(expected_version=system.version, reason=reason),
            owner,
        )


async def _create_model(system_id: str, owner: Principal, **fields: object) -> str:
    """Register a model asset under a mutable AI system and return its id."""
    async with SessionFactory() as session:
        service = InventoryService(session)
        model = await service.create_model(system_id, ModelAssetCreate(**fields), owner)
        return model.id


async def _review_model(model_id: str, reviewer: Principal, *, reference: str, days: int) -> None:
    """Approve a model scope through an independent architecture review."""
    async with SessionFactory() as session:
        service = InventoryService(session)
        model = await session.get(ModelAsset, model_id)
        assert model is not None, f"model {model_id} was not found"
        await service.review_model(
            model_id,
            AssetReviewRequest(
                expected_version=model.version,
                next_review_at=datetime.now(UTC) + timedelta(days=days),
                reference=reference,
            ),
            reviewer,
        )


async def _create_agent(system_id: str, owner: Principal, **fields: object) -> str:
    """Register a governed agent under a mutable AI system and return its id."""
    async with SessionFactory() as session:
        service = InventoryService(session)
        agent = await service.create_agent(system_id, AgentCreate(**fields), owner)
        return agent.id


async def _review_agent(agent_id: str, reviewer: Principal, *, reference: str, days: int) -> None:
    """Approve an agent scope through an independent security review."""
    async with SessionFactory() as session:
        service = InventoryService(session)
        agent = await session.get(Agent, agent_id)
        assert agent is not None, f"agent {agent_id} was not found"
        await service.review_agent(
            agent_id,
            AssetReviewRequest(
                expected_version=agent.version,
                next_review_at=datetime.now(UTC) + timedelta(days=days),
                reference=reference,
            ),
            reviewer,
        )


def _ai_impact(
    *,
    intended_benefits: str,
    residual_risk: str,
) -> AIImpactAnswers:
    """Build a complete AI impact assessment answer set."""
    return AIImpactAnswers(
        affected_groups=("usuários finais", "equipe operadora"),
        intended_benefits=intended_benefits,
        potential_harms=("recomendação incorreta", "viés não identificado"),
        human_oversight="Um responsável humano revisa e pode reverter toda decisão relevante.",
        contestability="Usuários podem contestar o resultado junto à área responsável.",
        mitigation_measures=("revisão humana", "amostragem de qualidade", "monitoramento contínuo"),
        residual_risk=RiskTier(residual_risk),
    )


def _ripd(
    *,
    processing_purpose: str,
    residual_risk: str,
) -> RIPDAnswers:
    """Build a complete RIPD (privacy impact) assessment answer set."""
    return RIPDAnswers(
        controller_area="Governança de Dados",
        processing_purpose=processing_purpose,
        personal_data_categories=("dados cadastrais", "dados de uso"),
        data_subjects=("clientes", "colaboradores"),
        legal_basis="Execução de contrato e legítimo interesse, com avaliação de balanceamento.",
        necessity_assessment=(
            "O tratamento é limitado ao mínimo necessário para a finalidade declarada."
        ),
        risk_scenarios=("acesso indevido", "retenção além do necessário"),
        safeguards=("controle de acesso por papel", "retenção limitada", "criptografia em repouso"),
        residual_risk=RiskTier(residual_risk),
    )


def _international_processing(
    *,
    inference_countries: tuple[str, ...],
    residual_risk: str,
) -> InternationalProcessingAnswers:
    """Build a complete international processing assessment answer set."""
    return InternationalProcessingAnswers(
        data_categories=("dados cadastrais", "conteúdo da interação"),
        source_country="Brasil",
        inference_countries=inference_countries,
        storage_regions=inference_countries,
        log_regions=("Brasil",),
        subprocessors=(
            Subprocessor(
                name="Provedor de inferência em nuvem",
                countries=inference_countries,
                purpose="Execução do modelo de linguagem contratado",
            ),
        ),
        transfer_mechanism="Cláusulas contratuais padrão com o subprocessador internacional.",
        legal_basis="Execução de contrato com salvaguardas contratuais internacionais.",
        safeguards=("cláusulas contratuais padrão", "minimização de dados antes do envio"),
        residual_risk=RiskTier(residual_risk),
    )


async def seed_case_01() -> None:
    """Caso 1: rascunho nunca submetido, avaliação de impacto ainda em andamento."""
    owner = _owner("triagem-ti")
    initiative = await _create_initiative(
        InitiativeCreate(
            name=f"{DEMO_PREFIX}Assistente de triagem de tickets de TI",
            description=(
                "Classifica e prioriza tickets de suporte de TI a partir do texto enviado "
                "pelo usuário, sem executar ações automatizadas sobre os sistemas."
            ),
            business_area="Tecnologia da Informação",
            intended_users="Equipe de service desk interno",
            decision_impact=DecisionImpact.INFORMATIONAL,
            data_classification=DataClassification.INTERNAL,
            autonomy_level=AutonomyLevel.A1_RECOMMENDATION,
            hosting_model=HostingModel.SAAS,
        ),
        owner,
    )
    await _save_assessment(
        initiative.id,
        kind=AssessmentKind.AI_IMPACT,
        answers=_ai_impact(
            intended_benefits="Reduzir o tempo de triagem inicial dos chamados de TI.",
            residual_risk="low",
        ),
        actor=owner,
    )


async def seed_case_02() -> None:
    """Caso 2: primeira rodada em revisão, gate de negócio ainda pendente."""
    owner = _owner("resumos-reunioes")
    initiative = await _create_initiative(
        InitiativeCreate(
            name=f"{DEMO_PREFIX}Gerador de resumos de reuniões",
            description=(
                "Produz resumos e itens de ação a partir de transcrições de reuniões internas "
                "já autorizadas para gravação."
            ),
            business_area="Produtividade Corporativa",
            intended_users="Colaboradores em geral",
            decision_impact=DecisionImpact.INFORMATIONAL,
            data_classification=DataClassification.PUBLIC,
            autonomy_level=AutonomyLevel.A0_INFORMATION,
            hosting_model=HostingModel.SAAS,
        ),
        owner,
    )
    await _save_and_submit_assessment(
        initiative.id,
        kind=AssessmentKind.AI_IMPACT,
        answers=_ai_impact(
            intended_benefits="Reduzir o tempo gasto documentando reuniões internas.",
            residual_risk="low",
        ),
        actor=owner,
    )
    await _submit_initiative(initiative.id, owner)
    await _add_reference_evidence(
        initiative.id,
        kind=EvidenceKind.OTHER,
        uri="urn:demo:resumos-reunioes:nota-produto",
        supplied_by=owner.user_id,
    )


async def seed_case_03() -> None:
    """Caso 3: mudanças solicitadas por Privacidade, reabrindo os assessments."""
    owner = _owner("treinamento")
    initiative = await _create_initiative(
        InitiativeCreate(
            name=f"{DEMO_PREFIX}Recomendador de conteúdo de treinamento",
            description=(
                "Sugere trilhas de capacitação personalizadas com base no histórico funcional "
                "e nas lacunas de competência de cada colaborador."
            ),
            business_area="Recursos Humanos",
            intended_users="Colaboradores e gestores de equipe",
            decision_impact=DecisionImpact.OPERATIONAL,
            data_classification=DataClassification.INTERNAL,
            autonomy_level=AutonomyLevel.A2_PREPARE_FOR_APPROVAL,
            hosting_model=HostingModel.SAAS,
            personal_data=True,
        ),
        owner,
    )
    await _save_and_submit_assessment(
        initiative.id,
        kind=AssessmentKind.AI_IMPACT,
        answers=_ai_impact(
            intended_benefits="Aumentar a relevância das trilhas de capacitação recomendadas.",
            residual_risk="medium",
        ),
        actor=owner,
    )
    await _save_and_submit_assessment(
        initiative.id,
        kind=AssessmentKind.RIPD,
        answers=_ripd(
            processing_purpose="Personalizar recomendações de capacitação por colaborador.",
            residual_risk="medium",
        ),
        actor=owner,
    )
    await _submit_initiative(initiative.id, owner)
    await _decide_one(
        initiative.id,
        area=ApprovalArea.PRIVACY,
        decision=ApprovalStatus.CHANGES_REQUESTED,
        reviewer=_reviewer(ApprovalArea.PRIVACY),
    )


async def seed_case_04() -> None:
    """Caso 4: segunda rodada em revisão, exercitando revise() e resubmit()."""
    owner = _owner("notas-fiscais")
    initiative = await _create_initiative(
        InitiativeCreate(
            name=f"{DEMO_PREFIX}Extrator de dados de notas fiscais",
            description=(
                "Extrai campos estruturados de notas fiscais recebidas e lança os valores "
                "automaticamente no sistema financeiro interno."
            ),
            business_area="Financeiro",
            intended_users="Equipe de contas a pagar",
            decision_impact=DecisionImpact.OPERATIONAL,
            data_classification=DataClassification.CONFIDENTIAL,
            autonomy_level=AutonomyLevel.A2_PREPARE_FOR_APPROVAL,
            hosting_model=HostingModel.SAAS,
            executes_actions=True,
        ),
        owner,
    )
    await _save_and_submit_assessment(
        initiative.id,
        kind=AssessmentKind.AI_IMPACT,
        answers=_ai_impact(
            intended_benefits="Reduzir o retrabalho manual de lançamento de notas fiscais.",
            residual_risk="medium",
        ),
        actor=owner,
    )
    await _submit_initiative(initiative.id, owner)
    await _decide_one(
        initiative.id,
        area=ApprovalArea.BUSINESS,
        decision=ApprovalStatus.CHANGES_REQUESTED,
        reviewer=_reviewer(ApprovalArea.BUSINESS),
    )
    await _revise_initiative(
        initiative.id,
        owner,
        change_reason="Detalhar os limites de valor para lançamento automático.",
        description=(
            "Extrai campos estruturados de notas fiscais recebidas e lança automaticamente no "
            "sistema financeiro apenas valores abaixo do limite de alçada operacional definido."
        ),
    )
    reopened_version = await _current_assessment_version(initiative.id, AssessmentKind.AI_IMPACT)
    assessment_id, version = await _save_assessment(
        initiative.id,
        kind=AssessmentKind.AI_IMPACT,
        answers=_ai_impact(
            intended_benefits="Reduzir o retrabalho manual dentro de um limite de alçada seguro.",
            residual_risk="medium",
        ),
        actor=owner,
        expected_version=reopened_version,
    )
    await _submit_assessment(assessment_id, version, owner)
    await _resubmit_initiative(
        initiative.id,
        owner,
        revision_summary="Lançamento automático agora limitado por alçada de valor.",
    )


async def seed_case_05() -> None:
    """Caso 5: rejeitado por Compliance, encerrando os demais gates pendentes."""
    owner = _owner("compliance-contratos")
    initiative = await _create_initiative(
        InitiativeCreate(
            name=f"{DEMO_PREFIX}Verificador automático de compliance de contratos",
            description=(
                "Avalia cláusulas contratuais frente a políticas internas e executa o "
                "encaminhamento automático para assinatura quando aprovadas."
            ),
            business_area="Jurídico",
            intended_users="Equipe de contratos",
            decision_impact=DecisionImpact.MATERIAL,
            data_classification=DataClassification.RESTRICTED,
            autonomy_level=AutonomyLevel.A3_REVERSIBLE_ACTIONS,
            hosting_model=HostingModel.CLOUD_MANAGED,
            executes_actions=True,
            personal_data=True,
            sensitive_data=True,
            regulated_context=True,
        ),
        owner,
    )
    await _save_and_submit_assessment(
        initiative.id,
        kind=AssessmentKind.AI_IMPACT,
        answers=_ai_impact(
            intended_benefits="Acelerar a checagem de conformidade contratual.",
            residual_risk="high",
        ),
        actor=owner,
    )
    await _save_and_submit_assessment(
        initiative.id,
        kind=AssessmentKind.RIPD,
        answers=_ripd(
            processing_purpose="Analisar dados pessoais presentes em cláusulas contratuais.",
            residual_risk="high",
        ),
        actor=owner,
    )
    await _upload_real_evidence(
        initiative.id,
        kind=EvidenceKind.SECURITY_TEST,
        filename="teste-seguranca-compliance.txt",
        text=(
            "Relatório de teste de segurança: varredura de vulnerabilidades concluída sem "
            "achados críticos. Escopo: pipeline de análise contratual e integração de assinatura."
        ),
        actor=owner,
    )
    await _submit_initiative(initiative.id, owner)
    await _decide_one(
        initiative.id,
        area=ApprovalArea.COMPLIANCE,
        decision=ApprovalStatus.REJECTED,
        reviewer=_reviewer(ApprovalArea.COMPLIANCE),
    )


async def seed_case_06() -> None:
    """Caso 6: aprovado por sete revisores independentes; sistema de IA criado."""
    owner = _owner("precificacao")
    initiative = await _create_initiative(
        InitiativeCreate(
            name=f"{DEMO_PREFIX}Painel de precificação dinâmica orientado por IA",
            description=(
                "Recomenda ajustes de preço em tempo real com base em demanda e concorrência, "
                "exibindo a sugestão para aprovação comercial antes da publicação."
            ),
            business_area="Comercial",
            intended_users="Equipe de pricing e canais digitais",
            decision_impact=DecisionImpact.MATERIAL,
            data_classification=DataClassification.RESTRICTED,
            autonomy_level=AutonomyLevel.A3_REVERSIBLE_ACTIONS,
            hosting_model=HostingModel.SELF_HOSTED,
            external_facing=True,
            regulated_context=True,
        ),
        owner,
    )
    await _save_and_submit_assessment(
        initiative.id,
        kind=AssessmentKind.AI_IMPACT,
        answers=_ai_impact(
            intended_benefits=(
                "Melhorar a competitividade de preços sem intervenção manual constante."
            ),
            residual_risk="high",
        ),
        actor=owner,
    )
    await _add_reference_evidence(
        initiative.id,
        kind=EvidenceKind.ARCHITECTURE,
        uri="urn:demo:precificacao:diagrama-arquitetura",
        supplied_by=owner.user_id,
    )
    await _submit_initiative(initiative.id, owner)
    await _decide_all_pending(initiative.id, _reviewer)
    await _create_system(
        initiative.id,
        owner,
        name="Painel de Precificação Dinâmica",
        purpose="Recomendar ajustes de preço em tempo real para aprovação comercial.",
        production=False,
    )


async def seed_case_07() -> None:
    """Caso 7: crítico, aprovado, com sistema ativo, modelo e agente aprovados."""
    owner = _owner("atendimento-financeiro")
    countries = ("Brasil", "Estados Unidos")
    initiative = await _create_initiative(
        InitiativeCreate(
            name=(
                f"{DEMO_PREFIX}Copiloto autônomo de atendimento ao cliente com ações financeiras"
            ),
            description=(
                "Atende clientes de ponta a ponta e executa ações financeiras reversíveis, como "
                "estornos dentro de um limite pré-aprovado, sem intervenção humana prévia."
            ),
            business_area="Atendimento ao Cliente",
            intended_users="Clientes finais",
            decision_impact=DecisionImpact.RIGHTS_OR_SAFETY,
            data_classification=DataClassification.RESTRICTED,
            autonomy_level=AutonomyLevel.A4_HIGH_IMPACT_ACTIONS,
            hosting_model=HostingModel.SELF_HOSTED,
            affects_rights=True,
            executes_actions=True,
            personal_data=True,
            sensitive_data=True,
            external_facing=True,
            regulated_context=True,
            international_processing=True,
            inference_countries=list(countries),
            uses_rag=True,
            uses_agents=True,
            uses_mcp=True,
            uses_custom_model=True,
        ),
        owner,
    )
    await _save_and_submit_assessment(
        initiative.id,
        kind=AssessmentKind.AI_IMPACT,
        answers=_ai_impact(
            intended_benefits="Reduzir o tempo de resposta ao cliente em solicitações financeiras.",
            residual_risk="critical",
        ),
        actor=owner,
    )
    await _save_and_submit_assessment(
        initiative.id,
        kind=AssessmentKind.RIPD,
        answers=_ripd(
            processing_purpose=(
                "Processar dados financeiros e pessoais para atendimento automatizado."
            ),
            residual_risk="critical",
        ),
        actor=owner,
    )
    await _save_and_submit_assessment(
        initiative.id,
        kind=AssessmentKind.INTERNATIONAL_PROCESSING,
        answers=_international_processing(
            inference_countries=countries,
            residual_risk="critical",
        ),
        actor=owner,
    )
    await _upload_real_evidence(
        initiative.id,
        kind=EvidenceKind.POLICY,
        filename="politica-limites-acao-copiloto.txt",
        text=(
            "Política interna: o copiloto pode executar estornos financeiros reversíveis até o "
            "limite operacional definido, com trilha de auditoria completa e kill switch ativo."
        ),
        actor=owner,
    )
    await _add_reference_evidence(
        initiative.id,
        kind=EvidenceKind.APPROVAL,
        uri="urn:demo:atendimento-financeiro:ata-comite-risco",
        supplied_by=owner.user_id,
    )
    await _submit_initiative(initiative.id, owner)
    await _decide_all_pending(initiative.id, _reviewer)

    system_id = await _create_system(
        initiative.id,
        owner,
        name="Copiloto de Atendimento Financeiro",
        purpose="Atender clientes e executar ações financeiras reversíveis autorizadas.",
        production=True,
    )
    model_id = await _create_model(
        system_id,
        owner,
        provider="Fornecedor de Modelo Próprio",
        model_name="copiloto-financeiro-v1",
        model_version="2026.08.0",
        routing_group="atendimento-financeiro",
        deployment_region="Brasil",
        approved_use_cases=["atendimento financeiro assistido"],
        prohibited_use_cases=["decisões de crédito automatizadas"],
        allowed_data_classes=[DataClassification.CONFIDENTIAL, DataClassification.RESTRICTED],
        evaluation_baseline={"dataset": "atendimento-financeiro-eval-v1", "acuracia": 0.94},
    )
    await _review_model(
        model_id,
        _reviewer(ApprovalArea.ARCHITECTURE),
        reference="ARCH-2026-107",
        days=25,
    )
    agent_id = await _create_agent(
        system_id,
        owner,
        name="Agente de estorno financeiro",
        purpose="Executar estornos financeiros reversíveis dentro do limite pré-aprovado.",
        owner_id=owner.user_id,
        agent_version="1.0.0",
        deployment_region="Brasil",
        autonomy_level=AutonomyLevel.A3_REVERSIBLE_ACTIONS,
        allowed_models=[model_id],
        tools=["sistema-financeiro-interno"],
        permissions=["financeiro:estorno:executar"],
        max_cost=50.0,
        max_runtime_seconds=60,
        human_approval_points=["estorno acima de limite de exceção"],
        kill_switch_enabled=True,
    )
    await _review_agent(
        agent_id,
        _reviewer(ApprovalArea.SECURITY),
        reference="SEC-2026-107",
        days=20,
    )


async def seed_case_08() -> None:
    """Caso 8: aprovado, ativado e então aposentado."""
    owner = _owner("legado-produtos")
    initiative = await _create_initiative(
        InitiativeCreate(
            name=f"{DEMO_PREFIX}Sistema legado de recomendação de produtos (descontinuado)",
            description=(
                "Recomendava produtos com base em navegação recente do cliente, substituído por "
                "um mecanismo de busca semântica mais recente."
            ),
            business_area="E-commerce",
            intended_users="Clientes da loja online",
            decision_impact=DecisionImpact.INFORMATIONAL,
            data_classification=DataClassification.PUBLIC,
            autonomy_level=AutonomyLevel.A0_INFORMATION,
            hosting_model=HostingModel.SAAS,
        ),
        owner,
    )
    await _save_and_submit_assessment(
        initiative.id,
        kind=AssessmentKind.AI_IMPACT,
        answers=_ai_impact(
            intended_benefits="Aumentar a relevância das recomendações de produto exibidas.",
            residual_risk="low",
        ),
        actor=owner,
    )
    await _add_reference_evidence(
        initiative.id,
        kind=EvidenceKind.ASSESSMENT,
        uri="urn:demo:legado-produtos:relatorio-avaliacao-inicial",
        supplied_by=owner.user_id,
    )
    await _submit_initiative(initiative.id, owner)
    await _decide_all_pending(initiative.id, _reviewer)
    system_id = await _create_system(
        initiative.id,
        owner,
        name="Recomendador de Produtos (legado)",
        purpose="Recomendar produtos com base na navegação recente do cliente.",
        production=True,
    )
    await _retire_system(
        system_id,
        owner,
        reason="Substituído por um mecanismo de recomendação mais recente com melhor cobertura.",
    )


async def seed_case_09() -> None:
    """Caso 9: mudanças solicitadas por Jurídico, reabrindo os três assessments."""
    owner = _owner("juridico-internacional")
    countries = ("Portugal",)
    initiative = await _create_initiative(
        InitiativeCreate(
            name=f"{DEMO_PREFIX}Assistente jurídico de triagem de contratos internacionais",
            description=(
                "Realiza a triagem inicial de contratos internacionais recebidos, identificando "
                "cláusulas de risco antes da revisão humana pela equipe jurídica."
            ),
            business_area="Jurídico",
            intended_users="Equipe jurídica internacional",
            decision_impact=DecisionImpact.MATERIAL,
            data_classification=DataClassification.RESTRICTED,
            autonomy_level=AutonomyLevel.A3_REVERSIBLE_ACTIONS,
            hosting_model=HostingModel.CLOUD_MANAGED,
            personal_data=True,
            external_facing=True,
            regulated_context=True,
            international_processing=True,
            inference_countries=list(countries),
        ),
        owner,
    )
    await _save_and_submit_assessment(
        initiative.id,
        kind=AssessmentKind.AI_IMPACT,
        answers=_ai_impact(
            intended_benefits="Acelerar a triagem inicial de contratos internacionais recebidos.",
            residual_risk="high",
        ),
        actor=owner,
    )
    await _save_and_submit_assessment(
        initiative.id,
        kind=AssessmentKind.RIPD,
        answers=_ripd(
            processing_purpose="Analisar dados pessoais presentes em contratos internacionais.",
            residual_risk="high",
        ),
        actor=owner,
    )
    await _save_and_submit_assessment(
        initiative.id,
        kind=AssessmentKind.INTERNATIONAL_PROCESSING,
        answers=_international_processing(
            inference_countries=countries,
            residual_risk="high",
        ),
        actor=owner,
    )
    await _submit_initiative(initiative.id, owner)
    await _decide_one(
        initiative.id,
        area=ApprovalArea.LEGAL,
        decision=ApprovalStatus.CHANGES_REQUESTED,
        reviewer=_reviewer(ApprovalArea.LEGAL),
    )


async def seed_case_10() -> None:
    """Caso 10: aprovado por um único administrador; modelo registrado sem revisão."""
    owner = _owner("busca-semantica")
    initiative = await _create_initiative(
        InitiativeCreate(
            name=f"{DEMO_PREFIX}Motor de busca semântica de currículos com modelo próprio (RAG)",
            description=(
                "Permite busca semântica de currículos internos usando um modelo próprio com "
                "recuperação aumentada por contexto (RAG) sobre a base de talentos."
            ),
            business_area="Recursos Humanos",
            intended_users="Equipe de recrutamento",
            decision_impact=DecisionImpact.OPERATIONAL,
            data_classification=DataClassification.CONFIDENTIAL,
            autonomy_level=AutonomyLevel.A2_PREPARE_FOR_APPROVAL,
            hosting_model=HostingModel.CLOUD_MANAGED,
            personal_data=True,
            uses_rag=True,
            uses_custom_model=True,
        ),
        owner,
    )
    await _save_and_submit_assessment(
        initiative.id,
        kind=AssessmentKind.AI_IMPACT,
        answers=_ai_impact(
            intended_benefits="Reduzir o tempo de busca por currículos aderentes às vagas abertas.",
            residual_risk="medium",
        ),
        actor=owner,
    )
    await _save_and_submit_assessment(
        initiative.id,
        kind=AssessmentKind.RIPD,
        answers=_ripd(
            processing_purpose="Indexar e buscar dados pessoais presentes em currículos internos.",
            residual_risk="medium",
        ),
        actor=owner,
    )
    await _submit_initiative(initiative.id, owner)
    await _decide_all_pending(initiative.id, lambda _area: ADMIN)
    system_id = await _create_system(
        initiative.id,
        owner,
        name="Busca Semântica de Currículos",
        purpose="Buscar currículos internos por similaridade semântica com a vaga aberta.",
        production=True,
    )
    await _create_model(
        system_id,
        owner,
        provider="Modelo Próprio Interno",
        model_name="busca-curriculos-embeddings",
        model_version="2026.08.0",
        routing_group="busca-semantica-rh",
        deployment_region="Brasil",
        approved_use_cases=["busca semântica de currículos internos"],
        allowed_data_classes=[DataClassification.CONFIDENTIAL],
        evaluation_baseline={"dataset": "busca-curriculos-eval-v1", "recall_top10": 0.88},
    )


CASES: list[tuple[int, str, Callable[[], Awaitable[None]]]] = [
    (1, "Assistente de triagem de tickets de TI", seed_case_01),
    (2, "Gerador de resumos de reuniões", seed_case_02),
    (3, "Recomendador de conteúdo de treinamento", seed_case_03),
    (4, "Extrator de dados de notas fiscais", seed_case_04),
    (5, "Verificador automático de compliance de contratos", seed_case_05),
    (6, "Painel de precificação dinâmica orientado por IA", seed_case_06),
    (7, "Copiloto autônomo de atendimento ao cliente com ações financeiras", seed_case_07),
    (8, "Sistema legado de recomendação de produtos (descontinuado)", seed_case_08),
    (9, "Assistente jurídico de triagem de contratos internacionais", seed_case_09),
    (10, "Motor de busca semântica de currículos com modelo próprio (RAG)", seed_case_10),
]


async def main() -> int:
    """Seed the ten demo cases sequentially, failing fast on the first error."""
    if await _demo_data_exists():
        print(
            "[seed] já existem iniciativas [DEMO] neste banco. Rodar novamente não é suportado; "
            "reinicie o Postgres local (docker compose down -v && make dev && make migrate) "
            "antes de semear de novo."
        )
        return 1

    for number, name, case in CASES:
        print(f"[seed] caso {number}: {name}")
        try:
            await case()
        except Exception:
            print(f"[seed] falhou no caso {number} ({name}):")
            traceback.print_exc()
            return 1

    print("[seed] concluído: 10 iniciativas [DEMO] criadas com sucesso.")
    print(
        "[seed] nota: EntityStatus.SUSPENDED não é alcançável por nenhum serviço de aplicação "
        "hoje (ver docstring do módulo) e não foi semeado."
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
