from pathlib import Path

import pytest
from governance_schemas import ControlCatalog, ControlDefinition, CrosswalkFramework
from policy_engine import (
    ControlCrosswalkError,
    GovernanceControlCatalog,
    GovernanceControlCrosswalk,
)


def test_packaged_crosswalk_maps_every_baseline_control_and_declares_iso_pending() -> None:
    catalog = GovernanceControlCatalog.from_package().catalog
    crosswalk = GovernanceControlCrosswalk.from_package(catalog).crosswalk

    control_ids = {control.control_id for control in catalog.controls}
    entry_ids = {entry.control_id for entry in crosswalk.entries}

    assert entry_ids == control_ids
    assert CrosswalkFramework.ISO_IEC_42001 in crosswalk.frameworks_pending
    assert CrosswalkFramework.ISO_IEC_42001 not in crosswalk.frameworks_covered
    assert CrosswalkFramework.MITRE_ATLAS in crosswalk.frameworks_covered
    assert CrosswalkFramework.OWASP_AGENTIC_TOP10 in crosswalk.frameworks_covered
    assert all(
        reference.framework != CrosswalkFramework.ISO_IEC_42001
        for entry in crosswalk.entries
        for reference in entry.references
    )


def _single_control_catalog() -> ControlCatalog:
    return ControlCatalog(
        catalog_id="test-catalog",
        version="1.0.0",
        controls=(
            ControlDefinition(
                control_id="GOV-ORG-001",
                title="Owner definido",
                domain="organization",
                objective="Garantir accountability explícita por toda iniciativa.",
                control_type="preventive",
                owner="AI Governance",
                review_frequency="semestral",
                requirements=("Toda iniciativa deve possuir owner.",),
                evidence=("Registro da iniciativa com owner",),
                applicability={"always": True},
            ),
        ),
    )


def test_crosswalk_entry_referencing_unknown_control_id_fails_closed(tmp_path: Path) -> None:
    broken = tmp_path / "broken-crosswalk.yaml"
    broken.write_text(
        """
crosswalk_id: test
version: "1.0.0"
frameworks_covered: [nist_ai_rmf]
frameworks_pending: []
disclaimer: "Referência de apoio, sem valor de conformidade."
entries:
  - control_id: GOV-ZZZ-999
    references:
      - framework: nist_ai_rmf
        reference: "GOVERN 1"
        title: Policies
""",
        encoding="utf-8",
    )

    with pytest.raises(ControlCrosswalkError, match="unknown control IDs"):
        GovernanceControlCrosswalk.from_path(broken, _single_control_catalog())


def test_malformed_crosswalk_fails_closed(tmp_path: Path) -> None:
    catalog = GovernanceControlCatalog.from_package().catalog
    invalid = tmp_path / "invalid.yaml"
    invalid.write_text("crosswalk_id: broken\nversion: nope\nentries: []\n", encoding="utf-8")

    with pytest.raises(ControlCrosswalkError, match="validation failed"):
        GovernanceControlCrosswalk.from_path(invalid, catalog)


def test_missing_configured_crosswalk_does_not_fall_back(tmp_path: Path) -> None:
    catalog = GovernanceControlCatalog.from_package().catalog

    with pytest.raises(ControlCrosswalkError, match="could not be read"):
        GovernanceControlCrosswalk.from_path(tmp_path / "missing.yaml", catalog)
