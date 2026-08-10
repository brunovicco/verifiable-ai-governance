from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts.generate_release_build_provenance import generate
from scripts.release_build_provenance import (
    BuildProvenanceError,
    build_checksums,
    canonical_json_bytes,
    deterministic_files_bundle,
    deterministic_git_archive,
    parse_checksums,
    safe_relative_path,
    self_digest,
    sha256_bytes,
    verify_self_digest,
)
from scripts.verify_release_build_provenance import verify


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()


def _source_repo(tmp_path: Path, name: str, remote: str) -> tuple[Path, str]:
    repo = tmp_path / name
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "tests@example.invalid")
    _git(repo, "config", "user.name", "P2.0c Tests")
    _git(repo, "remote", "add", "origin", f"https://github.com/{remote}.git")
    (repo / "README.md").write_text(f"# {name}\n", encoding="utf-8")
    (repo / "uv.lock").write_text(f"lock-{name}\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "source")
    return repo, _git(repo, "rev-parse", "HEAD")


def _write_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _fixture(tmp_path: Path) -> dict[str, object]:
    sources: dict[str, tuple[Path, str, str]] = {}
    metadata = {
        "governance": "brunovicco/verifiable-ai-governance",
        "policy_model_router": "brunovicco/policy-model-router",
        "multi_agent_credit_desk": "brunovicco/multi-agent-credit-desk",
        "a2a_otel_kit": "brunovicco/a2a-otel-kit",
    }
    for key, remote in metadata.items():
        repo, commit = _source_repo(tmp_path, f"source-{key}", remote)
        sources[key] = (repo, commit, remote)

    root = tmp_path / "tooling"
    root.mkdir()
    _git(root, "init", "-b", "feat/p2.0c-build-provenance-attestation")
    _git(root, "config", "user.email", "tests@example.invalid")
    _git(root, "config", "user.name", "P2.0c Tests")
    _git(
        root,
        "remote",
        "add",
        "origin",
        "https://github.com/brunovicco/verifiable-ai-governance.git",
    )

    recipe_files = (
        ".github/workflows/release-provenance.yml",
        "schemas/release-build-provenance.schema.json",
        "scripts/release_build_provenance.py",
        "scripts/generate_release_build_provenance.py",
        "scripts/verify_release_build_provenance.py",
    )
    for recipe in recipe_files:
        path = root / recipe
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"recipe:{recipe}\n", encoding="utf-8")

    components: dict[str, object] = {}
    for key, (_, commit, remote) in sources.items():
        components[key] = {
            "commit": commit,
            "lockfile": {"sha256": "a" * 64},
            "repository": remote,
        }

    manifest: dict[str, object] = {
        "canonicalization": "json-sort-keys-compact-v1",
        "components": components,
        "kind": "verifiable-ai-governance/release-evidence-manifest",
        "manifest_digest": "",
        "release": {
            "source_date": "2026-08-09T23:13:31-03:00",
            "version": "0.2.0-rc1",
        },
    }
    manifest["manifest_digest"] = self_digest(manifest, "manifest_digest")
    manifest_path = root / "artifacts/release/release-manifest.json"
    _write_json(manifest_path, manifest)

    security: dict[str, object] = {
        "bundle_digest": "",
        "kind": "verifiable-ai-governance/release-security-evidence",
        "policy_digest": "b" * 64,
        "release_manifest_digest": manifest["manifest_digest"],
        "verdict": "pass",
    }
    security["bundle_digest"] = self_digest(security, "bundle_digest")
    security_path = root / "artifacts/release/security/security-evidence-bundle.json"
    _write_json(security_path, security)
    raw = root / "artifacts/release/security/vulnerabilities/raw.json"
    _write_json(raw, {"findings": []})

    _git(root, "add", ".")
    _git(root, "commit", "-m", "tooling")

    return {
        "root": root,
        "manifest": manifest_path,
        "security": security_path,
        "sources": sources,
    }


def test_canonical_json_is_order_independent() -> None:
    assert canonical_json_bytes({"b": 2, "a": 1}) == canonical_json_bytes({"a": 1, "b": 2})


def test_safe_relative_path_rejects_traversal() -> None:
    with pytest.raises(BuildProvenanceError):
        safe_relative_path("../escape")


def test_self_digest_detects_tamper() -> None:
    document: dict[str, object] = {"value": 1, "digest": ""}
    document["digest"] = self_digest(document, "digest")
    verify_self_digest(document, "digest")
    document["value"] = 2
    with pytest.raises(BuildProvenanceError):
        verify_self_digest(document, "digest")


def test_files_bundle_is_deterministic() -> None:
    entries = [("b.txt", b"b"), ("a.txt", b"a")]
    left = deterministic_files_bundle(entries, source_date="2026-08-09T00:00:00+00:00")
    right = deterministic_files_bundle(reversed(entries), source_date="2026-08-09T00:00:00+00:00")
    assert left == right


def test_git_archive_is_deterministic(tmp_path: Path) -> None:
    repo, commit = _source_repo(tmp_path, "archive", "brunovicco/archive")
    left = deterministic_git_archive(repo, commit, "archive")
    right = deterministic_git_archive(repo, commit, "archive")
    assert left == right


def test_checksums_include_provenance_and_are_sorted(tmp_path: Path) -> None:
    root = tmp_path
    first = root / "z.bin"
    second = root / "a.bin"
    provenance = root / "p.json"
    first.write_bytes(b"z")
    second.write_bytes(b"a")
    provenance.write_bytes(b"{}")
    records = [
        {"path": "z.bin", "sha256": sha256_bytes(b"z")},
        {"path": "a.bin", "sha256": sha256_bytes(b"a")},
    ]
    value = build_checksums(records, provenance, root)
    paths = [path for path, _ in parse_checksums(value)]
    assert paths == ["a.bin", "p.json", "z.bin"]


def test_full_generation_and_verification(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    root = fixture["root"]
    assert isinstance(root, Path)
    sources = fixture["sources"]
    assert isinstance(sources, dict)

    output = root / "artifacts/release/provenance"
    generate(
        repo_root=root,
        release_manifest_path=fixture["manifest"],
        security_bundle_path=fixture["security"],
        governance_source_repo=sources["governance"][0],
        policy_model_router_repo=sources["policy_model_router"][0],
        credit_desk_repo=sources["multi_agent_credit_desk"][0],
        a2a_otel_kit_repo=sources["a2a_otel_kit"][0],
        output_dir=output,
        expected_release_version="0.2.0-rc1",
    )
    provenance = verify(
        repo_root=root,
        provenance_path=output / "release-build-provenance.json",
        release_manifest_path=fixture["manifest"],
        security_bundle_path=fixture["security"],
        governance_source_repo=sources["governance"][0],
        policy_model_router_repo=sources["policy_model_router"][0],
        credit_desk_repo=sources["multi_agent_credit_desk"][0],
        a2a_otel_kit_repo=sources["a2a_otel_kit"][0],
    )
    assert provenance["release_version"] == "0.2.0-rc1"
    assert len(provenance["subjects"]) == 6
    assert len(parse_checksums((output / "release-subjects.sha256").read_text())) == 7


def test_generation_rejects_wrong_release_version(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    root = fixture["root"]
    sources = fixture["sources"]
    with pytest.raises(BuildProvenanceError, match="Release version mismatch"):
        generate(
            repo_root=root,
            release_manifest_path=fixture["manifest"],
            security_bundle_path=fixture["security"],
            governance_source_repo=sources["governance"][0],
            policy_model_router_repo=sources["policy_model_router"][0],
            credit_desk_repo=sources["multi_agent_credit_desk"][0],
            a2a_otel_kit_repo=sources["a2a_otel_kit"][0],
            output_dir=root / "artifacts/release/provenance",
            expected_release_version="0.2.0",
        )


def test_generation_rejects_nonpassing_security(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    security_path = fixture["security"]
    security = json.loads(security_path.read_text())
    security["verdict"] = "fail"
    security["bundle_digest"] = self_digest(security, "bundle_digest")
    _write_json(security_path, security)
    _git(fixture["root"], "add", ".")
    _git(fixture["root"], "commit", "-m", "failed security")
    sources = fixture["sources"]
    with pytest.raises(BuildProvenanceError, match="verdict must be pass"):
        generate(
            repo_root=fixture["root"],
            release_manifest_path=fixture["manifest"],
            security_bundle_path=security_path,
            governance_source_repo=sources["governance"][0],
            policy_model_router_repo=sources["policy_model_router"][0],
            credit_desk_repo=sources["multi_agent_credit_desk"][0],
            a2a_otel_kit_repo=sources["a2a_otel_kit"][0],
            output_dir=fixture["root"] / "artifacts/release/provenance",
            expected_release_version="0.2.0-rc1",
        )


def test_verifier_rejects_subject_tamper(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    root = fixture["root"]
    sources = fixture["sources"]
    output = root / "artifacts/release/provenance"
    provenance = generate(
        repo_root=root,
        release_manifest_path=fixture["manifest"],
        security_bundle_path=fixture["security"],
        governance_source_repo=sources["governance"][0],
        policy_model_router_repo=sources["policy_model_router"][0],
        credit_desk_repo=sources["multi_agent_credit_desk"][0],
        a2a_otel_kit_repo=sources["a2a_otel_kit"][0],
        output_dir=output,
        expected_release_version="0.2.0-rc1",
    )
    first_subject = provenance["subjects"][0]
    path = root / first_subject["path"]
    path.write_bytes(path.read_bytes() + b"tamper")
    with pytest.raises(BuildProvenanceError, match="digest/size mismatch"):
        verify(
            repo_root=root,
            provenance_path=output / "release-build-provenance.json",
            release_manifest_path=fixture["manifest"],
            security_bundle_path=fixture["security"],
            governance_source_repo=sources["governance"][0],
            policy_model_router_repo=sources["policy_model_router"][0],
            credit_desk_repo=sources["multi_agent_credit_desk"][0],
            a2a_otel_kit_repo=sources["a2a_otel_kit"][0],
        )
