from pathlib import Path

_CORE = Path("scripts/release_security_evidence.py")
_GENERATOR = Path("scripts/generate_release_security_evidence.py")
_VERIFIER = Path("scripts/verify_release_security_evidence.py")


def test_offline_verifier_has_no_network_or_scanner_execution() -> None:
    source = _VERIFIER.read_text(encoding="utf-8") + _CORE.read_text(encoding="utf-8")
    forbidden = (
        "import httpx",
        "import requests",
        "import urllib.request",
        "import subprocess",
        "subprocess.run(",
        "subprocess.Popen(",
    )
    for fragment in forbidden:
        assert fragment not in source


def test_generator_scans_declared_commits_not_worktree_head() -> None:
    source = _GENERATOR.read_text(encoding="utf-8")
    assert "git_blob(repo, commit, path)" in source
    assert '["git", "archive", "--format=tar", commit]' in source
    assert 'components[name]["commit"]' in source
    assert "git checkout" not in source
    assert "git switch" not in source
    assert "git reset" not in source


def test_container_builds_are_bound_to_release_commit() -> None:
    source = _GENERATOR.read_text(encoding="utf-8")
    assert 'release_commit = str(components["governance"]["commit"])' in source
    assert "NEXT_PUBLIC_GIT_SHA" in source
    assert '"apps/api/Dockerfile"' in source
    assert '"apps/web/Dockerfile"' in source


def test_required_scanner_boundaries_are_explicit() -> None:
    source = _GENERATOR.read_text(encoding="utf-8")
    for fragment in (
        '"uvx",\n            "pip-audit"',
        '"npm",\n            "sbom"',
        '["npm", "audit"',
        '["trivy", "image"',
        '["docker", "build"',
    ):
        assert fragment in source


def test_generator_does_not_modify_release_manifest_or_policy() -> None:
    source = _GENERATOR.read_text(encoding="utf-8")
    forbidden = (
        "release_manifest.write_text",
        "args.release_manifest.write_text",
        "args.policy.write_text",
        "git commit",
        "git push",
    )
    for fragment in forbidden:
        assert fragment not in source
