from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_builder_copies_workspace_local_dependencies_before_web_sources() -> None:
    """Keep non-hoisted workspace packages available to the Next.js builder."""
    dockerfile = (ROOT / "apps/web/Dockerfile").read_text(encoding="utf-8")
    dependency_copy = (
        "COPY --from=dependencies /workspace/apps/web/node_modules "
        "./apps/web/node_modules"
    )
    source_copy = "COPY apps/web ./apps/web"

    assert dependency_copy in dockerfile
    assert dockerfile.index(dependency_copy) < dockerfile.index(source_copy)
