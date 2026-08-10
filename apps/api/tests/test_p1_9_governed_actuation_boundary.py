from pathlib import Path

_HARNESS = Path("scripts/verify_p1_9_governed_actuation_e2e.py")


def test_live_harness_uses_only_governed_p1_9_actuation_endpoints() -> None:
    source = _HARNESS.read_text(encoding="utf-8")
    required = (
        "/actuation-request",
        "/runtime-assurance-actuation-requests/",
        "/runtime-assurance-actuation-decisions/",
        "/restore-request",
        "/runtime-assurance-restore-requests/",
        "/runtime-assurance-restore-decisions/",
    )
    for fragment in required:
        assert fragment in source

    forbidden = (
        "/runtime-control/activate",
        "/runtime-control/deactivate",
        "/kill-switch/engage",
        "/kill-switch/restore",
        "RuntimeControlService(",
        ".activate(",
        ".deactivate(",
    )
    for fragment in forbidden:
        assert fragment not in source


def test_live_harness_requires_independent_security_principal() -> None:
    source = _HARNESS.read_text(encoding="utf-8")
    assert '"X-User-Areas": "security"' in source
    assert "owner and Security approver must be different principals" in source
    assert "self-approval" in source


def test_live_harness_proves_runtime_enforcement_and_recovery() -> None:
    source = _HARNESS.read_text(encoding="utf-8")
    assert '"kill_switch_engaged"' in source
    assert '"policy_model_router"' in source
    assert '"governance_registry"' in source
    assert '"inactive"' in source
    assert '"active"' in source
