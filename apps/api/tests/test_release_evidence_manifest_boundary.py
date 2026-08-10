from pathlib import Path

_FILES = (
    Path("scripts/release_evidence_manifest.py"),
    Path("scripts/generate_release_evidence_manifest.py"),
    Path("scripts/verify_release_evidence_manifest.py"),
)


def test_release_manifest_tooling_has_no_network_clients_or_secret_material() -> None:
    source = "\n".join(path.read_text(encoding="utf-8") for path in _FILES)
    forbidden = (
        "import httpx",
        "import requests",
        "urllib.request",
        "socket.create_connection",
        "BEGIN PRIVATE KEY",
        "RUNTIME_AUTHORIZATION_PRIVATE_KEY",
        "API_KEY",
    )
    for fragment in forbidden:
        assert fragment not in source


def test_release_manifest_tooling_does_not_mutate_repository_history() -> None:
    source = Path("scripts/release_evidence_manifest.py").read_text(encoding="utf-8")
    forbidden = (
        '_git(repo, "checkout"',
        '_git(repo, "switch"',
        '_git(repo, "reset"',
        '_git(repo, "clean"',
        '_git(repo, "commit"',
        '_git(repo, "tag"',
        '_git(repo, "push"',
    )
    for fragment in forbidden:
        assert fragment not in source


def test_schema_is_closed_and_manifest_is_self_hashed() -> None:
    schema = Path("schemas/release-evidence-manifest.schema.json").read_text(encoding="utf-8")
    source = Path("scripts/release_evidence_manifest.py").read_text(encoding="utf-8")
    assert '"additionalProperties": false' in schema
    assert '"manifest_digest"' in schema
    assert "manifest_digest(document)" in source
    assert "git_file_bytes" in source
    assert "merge-base" in source
    assert "squash_equivalent" in source
    assert "attested_paths_digest" in source
