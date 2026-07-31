from governance_schemas import (
    ApprovalArea,
    AutonomyLevel,
    DataClassification,
    DecisionImpact,
    HostingModel,
    PolicyContext,
    RiskTier,
)
from policy_engine import GovernancePolicyEngine


def test_low_risk_information_use_requires_only_business() -> None:
    decision = GovernancePolicyEngine().evaluate(
        PolicyContext(
            decision_impact=DecisionImpact.INFORMATIONAL,
            data_classification=DataClassification.PUBLIC,
            autonomy_level=AutonomyLevel.A0_INFORMATION,
            hosting_model=HostingModel.SAAS,
        )
    )

    assert decision.tier is RiskTier.LOW
    assert {item.area for item in decision.approvals if item.required} == {ApprovalArea.BUSINESS}


def test_sensitive_agent_requires_cross_functional_review() -> None:
    decision = GovernancePolicyEngine().evaluate(
        PolicyContext(
            decision_impact=DecisionImpact.MATERIAL,
            data_classification=DataClassification.RESTRICTED,
            autonomy_level=AutonomyLevel.A3_REVERSIBLE_ACTIONS,
            hosting_model=HostingModel.HYBRID,
            personal_data=True,
            sensitive_data=True,
            international_processing=True,
            executes_actions=True,
            uses_agents=True,
            uses_mcp=True,
            regulated_context=True,
        )
    )

    assert decision.tier in {RiskTier.HIGH, RiskTier.CRITICAL}
    assert all(item.required for item in decision.approvals)
    assert "ripd" in decision.required_documents
    assert "international-processing-assessment" in decision.required_documents


def test_inconsistent_action_claim_fails_closed() -> None:
    decision = GovernancePolicyEngine().evaluate(
        PolicyContext(
            decision_impact=DecisionImpact.OPERATIONAL,
            data_classification=DataClassification.INTERNAL,
            autonomy_level=AutonomyLevel.A1_RECOMMENDATION,
            hosting_model=HostingModel.CLOUD_MANAGED,
            executes_actions=True,
        )
    )

    assert not decision.can_submit
    assert decision.blocked_reasons
