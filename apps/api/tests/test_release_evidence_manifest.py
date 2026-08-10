from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts.release_evidence_manifest import (
    ReleaseManifestError,
    build_release_manifest,
    canonical_json_bytes,
    seal_manifest,
    verify_release_manifest,
)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _init_repo(path: Path, remote: str, *, name: str, version: str, a2a: str | None) -> None:
    path.mkdir(parents=True)
    _git(path, "init", "-b", "main")
    _git(path, "config", "user.name", "P2 Test")
    _git(path, "config", "user.email", "p2@example.invalid")
    _git(path, "remote", "add", "origin", remote)
    dependency = f'    "a2a-otel-kit{a2a}",\n' if a2a else ""
    (path / "pyproject.toml").write_text(
        "[project]\n"
        f'name = "{name}"\n'
        f'version = "{version}"\n'
        'requires-python = ">=3.13"\n'
        "dependencies = [\n"
        f"{dependency}"
        "]\n",
        encoding="utf-8",
    )
    (path / "uv.lock").write_text("version = 1\nrevision = 3\n", encoding="utf-8")
    _git(path, "add", ".")
    _git(path, "commit", "-m", "initial")


def _write_governance_inputs(governance: Path) -> str:
    policy = governance / "packages/policy-engine/src/policy_engine"
    policy.mkdir(parents=True)
    (policy / "engine.py").write_text("POLICY = 'v1'\n", encoding="utf-8")
    (policy / "control_catalog.yaml").write_text("controls: []\n", encoding="utf-8")
    (policy / "control_crosswalk.yaml").write_text("mappings: []\n", encoding="utf-8")
    migrations = governance / "apps/api/alembic/versions"
    migrations.mkdir(parents=True)
    (migrations / "0001_initial.py").write_text(
        'revision: str = "0001"\ndown_revision: str | None = None\n',
        encoding="utf-8",
    )
    e2e = governance / "artifacts/e2e"
    e2e.mkdir(parents=True)
    for name in (
        "p1.7-cross-repo-telemetry-live-report.json",
        "p1.8-cross-repo-assurance-live-report.json",
    ):
        (e2e / name).write_text(json.dumps({"schema_version": "1.0"}) + "\n", encoding="utf-8")
    _git(governance, "add", ".")
    _git(governance, "commit", "-m", "governance inputs")
    return _git(governance, "rev-parse", "HEAD")


def _fixture_repos(tmp_path: Path) -> dict[str, Path]:
    governance = tmp_path / "governance"
    router = tmp_path / "router"
    credit = tmp_path / "credit"
    a2a = tmp_path / "a2a"
    _init_repo(
        governance,
        "https://github.com/brunovicco/verifiable-ai-governance.git",
        name="verifiable-ai-governance-workspace",
        version="0.1.0",
        a2a=None,
    )
    _init_repo(
        router,
        "git@github.com:brunovicco/policy-model-router.git",
        name="policy-model-router",
        version="0.4.0",
        a2a="==0.4.2",
    )
    _init_repo(
        credit,
        "https://github.com/brunovicco/multi-agent-credit-desk",
        name="multi-agent-credit-desk",
        version="0.1.0",
        a2a="==0.5.0",
    )
    _init_repo(
        a2a,
        "https://github.com/brunovicco/a2a-otel-kit.git",
        name="a2a-otel-kit",
        version="0.5.0",
        a2a=None,
    )
    _git(a2a, "tag", "v0.5.0")
    (a2a / "pyproject.toml").write_text(
        "[project]\n"
        'name = "a2a-otel-kit"\n'
        'version = "0.6.0"\n'
        'requires-python = ">=3.13"\n'
        "dependencies = []\n",
        encoding="utf-8",
    )
    _git(a2a, "add", "pyproject.toml")
    _git(a2a, "commit", "-m", "prepare 0.6")
    governance_evidence_head = _write_governance_inputs(governance)
    credit_head = _git(credit, "rev-parse", "HEAD")
    report = {
        "schema_version": "1.0",
        "result": "passed",
        "baselines": {
            "governance_head": governance_evidence_head,
            "required_governance_baseline": governance_evidence_head,
            "credit_desk_head": credit_head,
            "a2a_otel_kit_runtime_version": "0.5.0",
        },
    }
    p19 = governance / "artifacts/e2e/p1.9-governed-actuation-live-report.json"
    p19.write_text(json.dumps(report, sort_keys=True) + "\n", encoding="utf-8")
    _git(governance, "add", str(p19.relative_to(governance)))
    _git(governance, "commit", "-m", "record p1.9 evidence")
    return {
        "governance": governance,
        "policy_model_router": router,
        "multi_agent_credit_desk": credit,
        "a2a_otel_kit": a2a,
    }


def test_manifest_is_deterministic_and_verifiable(tmp_path: Path) -> None:
    repos = _fixture_repos(tmp_path)
    first = build_release_manifest(release_version="0.2.0-rc1", repos=repos)
    second = build_release_manifest(release_version="0.2.0-rc1", repos=repos)
    assert canonical_json_bytes(first) == canonical_json_bytes(second)
    assert first["manifest_digest"] == second["manifest_digest"]
    verify_release_manifest(first, repos=repos)


def test_manifest_verification_uses_declared_commit_not_future_checkout(tmp_path: Path) -> None:
    repos = _fixture_repos(tmp_path)
    manifest = build_release_manifest(release_version="0.2.0-rc1", repos=repos)
    governance = repos["governance"]
    (governance / "README.future").write_text("future\n", encoding="utf-8")
    _git(governance, "add", "README.future")
    _git(governance, "commit", "-m", "future manifest commit")
    verify_release_manifest(manifest, repos=repos)


def test_tampered_evidence_hash_fails_even_with_resealed_manifest(tmp_path: Path) -> None:
    repos = _fixture_repos(tmp_path)
    manifest = build_release_manifest(release_version="0.2.0-rc1", repos=repos)
    evidence = dict(manifest["evidence"])  # type: ignore[arg-type]
    p19 = dict(evidence["p1_9_governed_actuation"])  # type: ignore[arg-type]
    p19["sha256"] = "0" * 64
    evidence["p1_9_governed_actuation"] = p19
    tampered = dict(manifest)
    tampered["evidence"] = evidence
    tampered = seal_manifest(tampered)
    with pytest.raises(ReleaseManifestError, match="does not match re-derived"):
        verify_release_manifest(tampered, repos=repos)


def test_generator_rejects_dirty_input_repository(tmp_path: Path) -> None:
    repos = _fixture_repos(tmp_path)
    (repos["policy_model_router"] / "dirty.txt").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(ReleaseManifestError, match="must be clean"):
        build_release_manifest(release_version="0.2.0-rc1", repos=repos)


def _squash_fixture_repos(tmp_path: Path) -> dict[str, Path]:
    governance = tmp_path / "governance"
    router = tmp_path / "router"
    credit = tmp_path / "credit"
    a2a = tmp_path / "a2a"
    _init_repo(
        governance,
        "https://github.com/brunovicco/verifiable-ai-governance.git",
        name="verifiable-ai-governance-workspace",
        version="0.1.0",
        a2a=None,
    )
    _init_repo(
        router,
        "git@github.com:brunovicco/policy-model-router.git",
        name="policy-model-router",
        version="0.4.0",
        a2a="==0.4.2",
    )
    _init_repo(
        credit,
        "https://github.com/brunovicco/multi-agent-credit-desk",
        name="multi-agent-credit-desk",
        version="0.1.0",
        a2a="==0.5.0",
    )
    _init_repo(
        a2a,
        "https://github.com/brunovicco/a2a-otel-kit.git",
        name="a2a-otel-kit",
        version="0.5.0",
        a2a=None,
    )
    _git(a2a, "tag", "v0.5.0")
    (a2a / "pyproject.toml").write_text(
        "[project]\n"
        'name = "a2a-otel-kit"\n'
        'version = "0.6.0"\n'
        'requires-python = ">=3.13"\n'
        "dependencies = []\n",
        encoding="utf-8",
    )
    _git(a2a, "add", "pyproject.toml")
    _git(a2a, "commit", "-m", "prepare 0.6")

    _git(governance, "switch", "-c", "feature/p1.9e")
    governance_evidence_head = _write_governance_inputs(governance)
    credit_head = _git(credit, "rev-parse", "HEAD")
    report = {
        "schema_version": "1.0",
        "result": "passed",
        "baselines": {
            "governance_head": governance_evidence_head,
            "required_governance_baseline": governance_evidence_head,
            "credit_desk_head": credit_head,
            "a2a_otel_kit_runtime_version": "0.5.0",
        },
    }
    p19 = governance / "artifacts/e2e/p1.9-governed-actuation-live-report.json"
    p19.write_text(json.dumps(report, sort_keys=True) + "\n", encoding="utf-8")
    _git(governance, "add", str(p19.relative_to(governance)))
    _git(governance, "commit", "-m", "record p1.9 evidence")

    _git(governance, "switch", "main")
    _git(governance, "merge", "--squash", "feature/p1.9e")
    _git(governance, "commit", "-m", "squash merge p1.9e")
    (governance / "P2.txt").write_text("later release tooling\n", encoding="utf-8")
    _git(governance, "add", "P2.txt")
    _git(governance, "commit", "-m", "later release tooling")
    return {
        "governance": governance,
        "policy_model_router": router,
        "multi_agent_credit_desk": credit,
        "a2a_otel_kit": a2a,
    }


def test_manifest_accepts_content_equivalent_squash_merge(tmp_path: Path) -> None:
    repos = _squash_fixture_repos(tmp_path)
    manifest = build_release_manifest(release_version="0.2.0-rc1", repos=repos)
    compatibility = manifest["compatibility"]
    assert isinstance(compatibility, dict)
    governance = compatibility["governance"]
    assert isinstance(governance, dict)
    assert governance["relation"] == "squash_equivalent"
    assert isinstance(governance["attested_path_count"], int)
    assert governance["attested_path_count"] > 0
    assert isinstance(governance["attested_paths_digest"], str)
    verify_release_manifest(manifest, repos=repos)


def test_manifest_rejects_squash_when_attested_content_drifted(tmp_path: Path) -> None:
    repos = _squash_fixture_repos(tmp_path)
    governance = repos["governance"]
    engine = governance / "packages/policy-engine/src/policy_engine/engine.py"
    engine.write_text("POLICY = 'tampered-after-evidence'\n", encoding="utf-8")
    _git(governance, "add", str(engine.relative_to(governance)))
    _git(governance, "commit", "-m", "change evidence-bound content")
    with pytest.raises(ReleaseManifestError, match="neither descends from nor preserves"):
        build_release_manifest(release_version="0.2.0-rc1", repos=repos)
