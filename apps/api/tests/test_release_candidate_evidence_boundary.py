from pathlib import Path

_CORE = Path("scripts/release_candidate_evidence.py")
_CAPTURE = Path("scripts/capture_clean_install_release_evidence.py")
_GENERATOR = Path("scripts/generate_release_candidate_evidence_index.py")
_VERIFIER = Path("scripts/verify_release_candidate_evidence_index.py")
_REFRESH = Path("scripts/refresh_release_build_provenance.py")
_PACKAGE = Path("scripts/__init__.py")
_SEED_CLI = Path("scripts/seed_canonical_demo.py")


def test_scripts_package_has_no_global_application_import_side_effect() -> None:
    source = _PACKAGE.read_text(encoding="utf-8")
    assert "canonical_demo_identity" not in source
    assert "sqlalchemy" not in source.lower()
    assert "ai_governance_api" not in source


def test_canonical_identity_listener_is_scoped_to_seed_cli() -> None:
    source = _SEED_CLI.read_text(encoding="utf-8")
    assert "install_canonical_demo_identity_listener" in source
    assert "install_canonical_demo_identity_listener()" in source


def test_release_tooling_uses_pure_canonical_identity_contract() -> None:
    for path in (_GENERATOR, _VERIFIER):
        source = path.read_text(encoding="utf-8")
        assert "canonical_demo_contract" in source
        assert "canonical_demo_identity" not in source


def test_release_evidence_core_and_offline_verifier_do_not_execute_network_operations() -> None:
    for path in (_CORE, _VERIFIER):
        source = path.read_text(encoding="utf-8").lower()
        for forbidden in ("httpx", "requests.", "urllib", "socket."):
            assert forbidden not in source


def test_final_index_generator_does_not_run_scanners_or_live_benchmarks() -> None:
    source = _GENERATOR.read_text(encoding="utf-8").lower()
    for forbidden in (
        "trivy",
        "pip-audit",
        "npm audit",
        "docker build",
        "routing-decisions",
        "runtime-assurance-evaluations",
    ):
        assert forbidden not in source


def test_clean_install_capture_uses_frozen_archive_and_bounded_p2e1_script() -> None:
    source = _CAPTURE.read_text(encoding="utf-8").lower()
    assert '"git", "archive"' in source
    assert "clean_install_script" in source
    assert "p2e1_compose_project_name" in source
    for forbidden in (
        "git reset",
        "git clean",
        "git checkout",
        "alembic stamp",
        "docker volume rm",
        "docker system prune",
    ):
        assert forbidden not in source


def test_provenance_refresh_replaces_only_known_generated_directory() -> None:
    source = _REFRESH.read_text(encoding="utf-8")
    assert '_PROVENANCE_RELATIVE = Path("artifacts/release/provenance")' in source
    assert "require_clean_worktree(repo)" in source
    assert "_replace_directory(output, repo / _PROVENANCE_RELATIVE)" in source
    assert "git reset" not in source
    assert "git clean" not in source
