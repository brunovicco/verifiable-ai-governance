from pathlib import Path

import pytest
from governance_schemas import (
    AutonomyLevel,
    ControlContext,
    DataClassification,
    DecisionImpact,
    HostingModel,
    RiskTier,
)
from policy_engine import ControlCatalogError, GovernanceControlCatalog


def context(**changes: object) -> ControlContext:
    values: dict[str, object] = {
        "decision_impact": DecisionImpact.INFORMATIONAL,
        "data_classification": DataClassification.PUBLIC,
        "autonomy_level": AutonomyLevel.A0_INFORMATION,
        "hosting_model": HostingModel.SAAS,
        "risk_tier": RiskTier.LOW,
    }
    values.update(changes)
    return ControlContext.model_validate(values)


def test_packaged_catalog_has_25_unique_versioned_controls() -> None:
    catalog = GovernanceControlCatalog.from_package().catalog

    assert catalog.catalog_id == "verifiable-ai-governance-baseline"
    assert catalog.version == "1.0.0"
    assert len(catalog.controls) == 25
    assert len({control.control_id for control in catalog.controls}) == 25
    assert all(control.requirements and control.evidence for control in catalog.controls)


def test_low_risk_context_only_receives_baseline_controls() -> None:
    evaluations = GovernanceControlCatalog.from_package().evaluate(context())
    applicable = {item.control.control_id for item in evaluations if item.applicable}

    assert "GOV-ORG-001" in applicable
    assert "GOV-RSK-001" in applicable
    assert "GOV-MOD-003" in applicable
    assert "GOV-AGT-001" not in applicable
    assert "GOV-DAT-004" not in applicable
    assert all(item.reasons for item in evaluations)


def test_high_risk_agent_context_explains_specialized_controls() -> None:
    evaluations = GovernanceControlCatalog.from_package().evaluate(
        context(
            decision_impact=DecisionImpact.RIGHTS_OR_SAFETY,
            data_classification=DataClassification.RESTRICTED,
            autonomy_level=AutonomyLevel.A4_HIGH_IMPACT_ACTIONS,
            hosting_model=HostingModel.HYBRID,
            risk_tier=RiskTier.CRITICAL,
            affects_rights=True,
            executes_actions=True,
            personal_data=True,
            sensitive_data=True,
            international_processing=True,
            uses_rag=True,
            uses_agents=True,
            uses_mcp=True,
        )
    )
    by_id = {item.control.control_id: item for item in evaluations}

    assert all(by_id[control_id].applicable for control_id in by_id)
    assert "international_processing" in " ".join(by_id["GOV-DAT-004"].reasons)
    assert "uses_agents" in " ".join(by_id["GOV-AGT-001"].reasons)


def test_invalid_or_incomplete_catalog_fails_closed(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.yaml"
    invalid.write_text("catalog_id: broken\nversion: nope\ncontrols: []\n", encoding="utf-8")

    with pytest.raises(ControlCatalogError, match="validation failed"):
        GovernanceControlCatalog.from_path(invalid)


def test_missing_configured_catalog_does_not_fall_back(tmp_path: Path) -> None:
    with pytest.raises(ControlCatalogError, match="could not be read"):
        GovernanceControlCatalog.from_path(tmp_path / "missing.yaml")
