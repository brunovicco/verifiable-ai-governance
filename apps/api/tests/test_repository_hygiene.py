from pathlib import Path

from scripts.validate_repository_hygiene import (
    REQUIRED_DOCKERIGNORE_ENTRIES,
    REQUIRED_GITIGNORE_ENTRIES,
    tracked_path_violation,
    validate_ignore_entries,
    validate_repository,
    validate_tracked_paths,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_normal_product_paths_are_allowed() -> None:
    paths = (
        "apps/api/src/ai_governance_api/domain/agents.py",
        "docs/architecture/ARCHITECTURE.md",
        "scripts/seed_canonical_demo.py",
        ".env.example",
    )
    assert validate_tracked_paths(paths) == []


def test_local_tooling_and_generated_state_are_rejected() -> None:
    paths = (
        ".agents/reviewer.md",
        ".claude/settings.json",
        ".codex/config.toml",
        ".harness.json",
        "AGENTS.md",
        "CLAUDE.md",
        ".idea/workspace.xml",
        ".vscode/settings.local.json",
        "nested/__pycache__/module.pyc",
        ".env.local",
    )
    violations = validate_tracked_paths(paths)
    assert [violation.split(":", maxsplit=1)[0] for violation in violations] == sorted(paths)


def test_ignore_files_cover_public_hygiene_policy() -> None:
    assert validate_ignore_entries(REPO_ROOT / ".gitignore", REQUIRED_GITIGNORE_ENTRIES) == []
    assert (
        validate_ignore_entries(
            REPO_ROOT / ".dockerignore",
            REQUIRED_DOCKERIGNORE_ENTRIES,
        )
        == []
    )


def test_repository_current_tracked_tree_is_clean() -> None:
    assert validate_repository(REPO_ROOT) == []


def test_direct_path_matcher_preserves_tool_agnostic_agent_code() -> None:
    assert tracked_path_violation("packages/governance-schemas/src/agent_contract.py") is None
    assert tracked_path_violation(".claude/rules/security.md") is not None
    assert tracked_path_violation(".vscode/settings.json") is None
    assert tracked_path_violation(".vscode/settings.local.json") is not None
