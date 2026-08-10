from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_WORKFLOW = _ROOT / ".github/workflows/release-provenance.yml"
_GENERATOR = _ROOT / "scripts/generate_release_build_provenance.py"
_CORE = _ROOT / "scripts/release_build_provenance.py"


def test_attestation_workflow_is_manual_and_least_privilege() -> None:
    source = _WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in source
    assert "pull_request:" not in source
    assert "push:" not in source
    assert "schedule:" not in source
    assert "contents: read" in source
    assert "id-token: write" in source
    assert "attestations: write" in source
    assert "artifact-metadata: write" in source
    assert "packages: write" not in source


def test_workflow_uses_current_attest_action_and_checksum_subjects() -> None:
    source = _WORKFLOW.read_text(encoding="utf-8")
    assert "uses: actions/attest@v4" in source
    assert "subject-checksums: artifacts/release/provenance/release-subjects.sha256" in source
    assert "attest-build-provenance" not in source
    assert "gh attestation verify" in source
    assert "id: attest" in source
    assert "steps.attest.outputs.bundle-path" in source
    release_check = "".join(
        (
            'test "${{ inputs.release_version }}" = ',
            '"${{ steps.roots.outputs.release_version }}"',
        )
    )
    assert release_check in source


def test_p2_0c_does_not_publish_packages_or_images() -> None:
    source = _WORKFLOW.read_text(encoding="utf-8")
    forbidden = (
        "docker push",
        "push-to-registry: true",
        "ghcr.io/",
        "docker/build-push-action",
        "packages: write",
    )
    for token in forbidden:
        assert token not in source


def test_generator_has_no_network_fallback() -> None:
    source = _GENERATOR.read_text(encoding="utf-8") + _CORE.read_text(encoding="utf-8")
    forbidden = (
        "git clone",
        "git fetch",
        "curl ",
        "httpx",
        "requests",
        "urllib.request",
        "gh api",
    )
    for token in forbidden:
        assert token not in source


def test_recipe_binds_the_attestation_workflow() -> None:
    source = _CORE.read_text(encoding="utf-8")
    assert '".github/workflows/release-provenance.yml"' in source
    assert 'ATTESTATION_ACTION = "actions/attest@v4"' in source
    assert 'ATTESTATION_PREDICATE = "https://slsa.dev/provenance/v1"' in source
