from governance_schemas import (
    ApprovalArea,
    ApprovalRequirement,
    AutonomyLevel,
    DataClassification,
    DecisionImpact,
    HostingModel,
    PolicyContext,
    PolicyDecision,
    RiskBreakdown,
    RiskTier,
)


class GovernancePolicyEngine:
    """Deterministic baseline policy. Unknown or incomplete states fail closed upstream."""

    policy_id = "baseline-governance-policy"
    policy_version = "1.0.0"

    def evaluate(self, context: PolicyContext) -> PolicyDecision:
        breakdown = RiskBreakdown(
            impact=self._impact_score(context),
            data=self._data_score(context),
            autonomy=self._autonomy_score(context),
            exposure=10 if context.external_facing else 3,
            regulatory=10 if context.regulated_context else 0,
        )
        tier = self._tier(breakdown.total, context)
        return PolicyDecision(
            policy_id=self.policy_id,
            policy_version=self.policy_version,
            score=breakdown.total,
            tier=tier,
            breakdown=breakdown,
            approvals=self._approvals(context, tier),
            required_documents=self._documents(context, tier),
            blocked_reasons=self._blocked_reasons(context),
        )

    @staticmethod
    def _impact_score(context: PolicyContext) -> int:
        base = {
            DecisionImpact.INFORMATIONAL: 3,
            DecisionImpact.OPERATIONAL: 10,
            DecisionImpact.MATERIAL: 20,
            DecisionImpact.RIGHTS_OR_SAFETY: 30,
        }[context.decision_impact]
        return min(30, base + (5 if context.affects_rights else 0))

    @staticmethod
    def _data_score(context: PolicyContext) -> int:
        score = {
            DataClassification.PUBLIC: 0,
            DataClassification.INTERNAL: 5,
            DataClassification.CONFIDENTIAL: 12,
            DataClassification.RESTRICTED: 18,
        }[context.data_classification]
        if context.personal_data:
            score += 3
        if context.sensitive_data:
            score += 4
        if context.children_data:
            score += 3
        return min(25, score)

    @staticmethod
    def _autonomy_score(context: PolicyContext) -> int:
        score = {
            AutonomyLevel.A0_INFORMATION: 0,
            AutonomyLevel.A1_RECOMMENDATION: 4,
            AutonomyLevel.A2_PREPARE_FOR_APPROVAL: 8,
            AutonomyLevel.A3_REVERSIBLE_ACTIONS: 14,
            AutonomyLevel.A4_HIGH_IMPACT_ACTIONS: 21,
            AutonomyLevel.A5_HIGH_AUTONOMY: 25,
        }[context.autonomy_level]
        return min(25, score + (3 if context.uses_mcp else 0))

    @staticmethod
    def _tier(score: int, context: PolicyContext) -> RiskTier:
        if context.decision_impact is DecisionImpact.RIGHTS_OR_SAFETY or context.autonomy_level in {
            AutonomyLevel.A4_HIGH_IMPACT_ACTIONS,
            AutonomyLevel.A5_HIGH_AUTONOMY,
        }:
            return RiskTier.CRITICAL
        if score >= 60 or context.sensitive_data or context.affects_rights:
            return RiskTier.HIGH
        if score >= 30 or context.personal_data or context.executes_actions:
            return RiskTier.MEDIUM
        return RiskTier.LOW

    @staticmethod
    def _require(
        area: ApprovalArea, condition: bool, reason: str, fallback: str
    ) -> ApprovalRequirement:
        return ApprovalRequirement(
            area=area, required=condition, reason=reason if condition else fallback
        )

    def _approvals(self, context: PolicyContext, tier: RiskTier) -> list[ApprovalRequirement]:
        elevated = tier in {RiskTier.HIGH, RiskTier.CRITICAL}
        technical_change = any(
            (context.uses_agents, context.uses_rag, context.uses_mcp, context.uses_custom_model)
        )
        return [
            self._require(
                ApprovalArea.BUSINESS,
                True,
                "Owner de Negócio confirma finalidade, valor e accountability.",
                "",
            ),
            self._require(
                ApprovalArea.ARCHITECTURE,
                technical_change or tier is not RiskTier.LOW,
                "Arquitetura ou risco técnico exige validação de desenho e dependências.",
                "Solução de baixo risco sem componentes técnicos avançados.",
            ),
            self._require(
                ApprovalArea.SECURITY,
                elevated
                or context.executes_actions
                or context.uses_agents
                or context.uses_mcp
                or context.data_classification
                in {DataClassification.CONFIDENTIAL, DataClassification.RESTRICTED},
                "Dados, autonomia ou superfície de ataque exigem avaliação de Segurança.",
                "Sem gatilho material de segurança no assessment preliminar.",
            ),
            self._require(
                ApprovalArea.INFRASTRUCTURE,
                context.hosting_model in {HostingModel.SELF_HOSTED, HostingModel.HYBRID}
                or context.uses_custom_model
                or elevated,
                "Hospedagem, capacidade ou criticidade exige validação de Infraestrutura.",
                "Uso SaaS/cloud gerenciado de baixo ou médio risco.",
            ),
            self._require(
                ApprovalArea.DEVOPS,
                context.executes_actions
                or context.uses_agents
                or context.uses_mcp
                or context.uses_custom_model,
                "Implantação ou automação requer controles de entrega e operação.",
                "Não há automação ou componente operacional próprio no escopo informado.",
            ),
            self._require(
                ApprovalArea.PRIVACY,
                context.personal_data or context.sensitive_data or context.children_data,
                "Há tratamento de dados pessoais; avaliar necessidade de RIPD e salvaguardas.",
                "Nenhum dado pessoal foi declarado.",
            ),
            self._require(
                ApprovalArea.LEGAL,
                context.international_processing
                or context.affects_rights
                or context.external_facing,
                "Transferência, direitos ou exposição externa exige revisão Jurídica.",
                "Sem transferência internacional, impacto em direitos ou exposição externa.",
            ),
            self._require(
                ApprovalArea.COMPLIANCE,
                context.regulated_context or elevated,
                "Contexto regulado ou risco elevado exige validação de Compliance.",
                "Contexto não regulado e risco abaixo de alto.",
            ),
            self._require(
                ApprovalArea.DATA,
                context.uses_rag
                or context.uses_custom_model
                or context.personal_data
                or context.data_classification is not DataClassification.PUBLIC,
                "Fontes, qualidade, lineage ou classificação exigem validação de Dados.",
                "Somente dados públicos e nenhum RAG/treinamento próprio declarado.",
            ),
        ]

    @staticmethod
    def _documents(context: PolicyContext, tier: RiskTier) -> list[str]:
        documents = ["ai-system-card", "ai-impact-assessment"]
        if context.personal_data or context.sensitive_data or context.children_data:
            documents.append("ripd")
        if context.international_processing:
            documents.append("international-processing-assessment")
        if context.uses_agents or context.executes_actions:
            documents.extend(["agent-card", "human-oversight-plan"])
        if tier in {RiskTier.HIGH, RiskTier.CRITICAL}:
            documents.extend(["threat-model", "monitoring-plan"])
        return sorted(set(documents))

    @staticmethod
    def _blocked_reasons(context: PolicyContext) -> list[str]:
        reasons: list[str] = []
        if context.sensitive_data and context.data_classification is DataClassification.PUBLIC:
            reasons.append("Dados sensíveis não podem ser classificados como públicos.")
        if context.executes_actions and context.autonomy_level in {
            AutonomyLevel.A0_INFORMATION,
            AutonomyLevel.A1_RECOMMENDATION,
        }:
            reasons.append("A autonomia declarada é incompatível com execução de ações.")
        return reasons
