import copy
import json
import subprocess
from pathlib import Path

import pytest

from scripts.canonical_demo_contract import (
    CANONICAL_DEMO_AGENT_ID,
    CANONICAL_DEMO_SCENARIO_ID,
    canonical_demo_release_record,
)
from scripts.release_candidate_evidence import (
    FROZEN_COMPONENT_COMMITS,
    RELEASE_INDEX,
    ReleaseCandidateEvidenceError,
    build_clean_install_evidence,
    build_release_candidate_index,
    build_release_candidate_subjects,
    clean_install_checks,
    self_digest,
    verify_clean_install_evidence,
    verify_release_candidate_index,
)


def _manifest(governance_commit: str) -> dict[str, object]:
    return {
        "release": {"version": "0.2.0-rc2"},
        "components": {
            "governance": {"commit": governance_commit},
            **{name: {"commit": commit} for name, commit in FROZEN_COMPONENT_COMMITS.items()},
        },
        "manifest_digest": "a" * 64,
    }


def _passing_log() -> str:
    return "\n".join(
        (
            "P2.0e.1 isolated Compose project: vag-p2e1-test",
            "--- first alembic upgrade head ---",
            "0019 (head)",
            "0019 (head)",
            '{"checks": {"database": "ok", "runtime_control": "ok", "schema": "ok"}, '
            '"status": "ok"}',
            "P2.0e.1 fresh-install E2E: PASS",
        )
    )


def _git_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    script = repo / "scripts/test_fresh_install_migrations.sh"
    script.parent.mkdir(parents=True)
    script.write_text("#!/usr/bin/env bash\necho test\n", encoding="utf-8")
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Release Test",
            "-c",
            "user.email=release@example.invalid",
            "commit",
            "-m",
            "source",
        ],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return repo, commit


def test_canonical_release_identity_is_stable() -> None:
    assert CANONICAL_DEMO_SCENARIO_ID == "credit-pj-governed-runtime"
    assert CANONICAL_DEMO_AGENT_ID == "565aa2b9-ead9-59e6-89a9-18920cced7ce"


def test_clean_install_log_requires_two_upgrades_and_readiness() -> None:
    checks = clean_install_checks(_passing_log())
    assert all(checks.values())

    incomplete = clean_install_checks(_passing_log().replace("0019 (head)\n", "", 1))
    assert incomplete["second_upgrade_reached_head"] is False


def test_clean_install_evidence_rederives_from_frozen_source(tmp_path: Path) -> None:
    repo, commit = _git_repo(tmp_path)
    manifest = _manifest(commit)
    manifest_path = repo / "artifacts/release/release-manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    log_path = repo / "artifacts/release/clean-install/clean-install-e2e.log"
    log_path.parent.mkdir(parents=True)
    log_path.write_text(_passing_log(), encoding="utf-8")

    evidence = build_clean_install_evidence(
        manifest=manifest,
        governance_repo=repo,
        log_path=log_path,
        generated_at="2026-08-10T23:00:00Z",
        environment={
            "system": "TestOS",
            "system_release": "1",
            "machine": "test",
            "docker": "Docker version test",
            "docker_compose": "Docker Compose version test",
        },
    )
    evidence_path = repo / "artifacts/release/clean-install/clean-install-evidence.json"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    verified = verify_clean_install_evidence(
        evidence_path=evidence_path,
        log_path=log_path,
        release_manifest_path=manifest_path,
        governance_repo=repo,
    )
    assert verified["verdict"] == "pass"

    log_path.write_text(_passing_log() + "\ntampered\n", encoding="utf-8")
    with pytest.raises(ReleaseCandidateEvidenceError, match="digest or size mismatch"):
        verify_clean_install_evidence(
            evidence_path=evidence_path,
            log_path=log_path,
            release_manifest_path=manifest_path,
            governance_repo=repo,
        )


def test_rc2_rejects_unplanned_sibling_source_drift() -> None:
    manifest = _manifest("1" * 40)
    components = manifest["components"]
    assert isinstance(components, dict)
    router = components["policy_model_router"]
    assert isinstance(router, dict)
    router["commit"] = "2" * 40

    with pytest.raises(ReleaseCandidateEvidenceError, match="component binding changed"):
        build_release_candidate_index(
            manifest=manifest,
            security={},
            provenance={},
            benchmark={},
            clean_install={},
            canonical_demo=canonical_demo_release_record(),
        )


def test_release_candidate_index_binds_all_pass_roots() -> None:
    commit = "1" * 40
    manifest = _manifest(commit)
    security = {
        "release_version": "0.2.0-rc2",
        "release_manifest_digest": "a" * 64,
        "bundle_digest": "b" * 64,
        "verdict": "pass",
    }
    provenance = {
        "release_version": "0.2.0-rc2",
        "provenance_digest": "c" * 64,
    }
    benchmark = {
        "release_version": "0.2.0-rc2",
        "bundle_digest": "d" * 64,
        "verdict": "pass",
    }
    clean_install = {
        "release_version": "0.2.0-rc2",
        "source": {"governance_commit": commit},
        "evidence_digest": "e" * 64,
        "verdict": "pass",
    }
    index = build_release_candidate_index(
        manifest=manifest,
        security=security,
        provenance=provenance,
        benchmark=benchmark,
        clean_install=clean_install,
        canonical_demo=canonical_demo_release_record(),
    )

    assert index["verdict"] == "pass"
    roots = index["roots"]
    assert isinstance(roots, dict)
    assert set(roots) == {
        "release_manifest",
        "security_evidence",
        "build_provenance",
        "runtime_benchmark",
        "clean_install",
    }
    assert (
        verify_release_candidate_index(
            index=index,
            manifest=manifest,
            security=security,
            provenance=provenance,
            benchmark=benchmark,
            clean_install=clean_install,
            canonical_demo=canonical_demo_release_record(),
        )
        == index["index_digest"]
    )

    tampered = copy.deepcopy(index)
    tampered["canonical_demo"]["agent_id"] = "0" * 36
    tampered["index_digest"] = self_digest(tampered, "index_digest")
    with pytest.raises(ReleaseCandidateEvidenceError, match="does not re-derive"):
        verify_release_candidate_index(
            index=tampered,
            manifest=manifest,
            security=security,
            provenance=provenance,
            benchmark=benchmark,
            clean_install=clean_install,
            canonical_demo=canonical_demo_release_record(),
        )


def test_release_candidate_subject_is_only_final_index(tmp_path: Path) -> None:
    root = tmp_path
    path = root / RELEASE_INDEX
    path.parent.mkdir(parents=True)
    path.write_text("{}\n", encoding="utf-8")
    row = build_release_candidate_subjects(path, root)
    assert row.endswith(f"  {RELEASE_INDEX}\n")
    assert len(row.split()[0]) == 64


def test_release_candidate_schemas_are_closed() -> None:
    clean_schema = json.loads(
        Path("schemas/release-clean-install-evidence.schema.json").read_text(encoding="utf-8")
    )
    index_schema = json.loads(
        Path("schemas/release-candidate-evidence-index.schema.json").read_text(encoding="utf-8")
    )
    assert clean_schema["additionalProperties"] is False
    assert index_schema["additionalProperties"] is False
    assert "evidence_digest" in clean_schema["required"]
    assert "index_digest" in index_schema["required"]
