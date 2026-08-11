import ast
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_CONFIG = REPOSITORY_ROOT / "apps" / "api" / "alembic.ini"
MIGRATION_DIRECTORY = REPOSITORY_ROOT / "apps" / "api" / "alembic" / "versions"
EXPECTED_REVISIONS = tuple(f"{number:04d}" for number in range(1, 20))
INITIAL_TABLES = {
    "agents",
    "ai_systems",
    "approvals",
    "assessments",
    "audit_events",
    "evidence",
    "incidents",
    "initiatives",
    "international_processing",
    "model_assets",
}


def _script_directory() -> ScriptDirectory:
    config = Config(str(ALEMBIC_CONFIG))
    return ScriptDirectory.from_config(config)


def _attribute_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return None


def _literal_create_tables(tree: ast.AST) -> set[str]:
    tables: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _attribute_name(node.func) != "create_table" or not node.args:
            continue
        table_name = node.args[0]
        if isinstance(table_name, ast.Constant) and isinstance(table_name.value, str):
            tables.add(table_name.value)
    return tables


def test_migration_chain_is_single_linear_history_through_0019() -> None:
    scripts = _script_directory()

    assert scripts.get_bases() == ["0001"]
    assert scripts.get_heads() == ["0019"]

    revisions = list(scripts.walk_revisions(base="base", head="heads"))
    ordered = tuple(revision.revision for revision in reversed(revisions))
    assert ordered == EXPECTED_REVISIONS

    previous: str | None = None
    for revision_id in ordered:
        revision = scripts.get_revision(revision_id)
        assert revision is not None
        assert revision.down_revision == previous
        previous = revision_id


def test_migrations_do_not_bootstrap_schema_from_application_metadata() -> None:
    violations: list[str] = []

    for migration in sorted(MIGRATION_DIRECTORY.glob("*.py")):
        tree = ast.parse(migration.read_text(encoding="utf-8"), filename=str(migration))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module == "ai_governance_api.models" or module.startswith(
                    "ai_governance_api.models."
                ):
                    violations.append(f"{migration.name}: imports {module}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "ai_governance_api.models" or alias.name.startswith(
                        "ai_governance_api.models."
                    ):
                        violations.append(f"{migration.name}: imports {alias.name}")
            elif isinstance(node, ast.Call) and _attribute_name(node.func) in {
                "create_all",
                "drop_all",
            }:
                violations.append(
                    f"{migration.name}: calls {_attribute_name(node.func)} instead of Alembic ops"
                )

    assert violations == []


def test_initial_revision_is_explicit_historical_contract() -> None:
    migration = MIGRATION_DIRECTORY / "0001_initial_schema.py"
    source = migration.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(migration))

    assert _literal_create_tables(tree) == INITIAL_TABLES
    assert "Base.metadata" not in source
    assert "runtime_telemetry_events" not in source
    assert "review_submissions" not in source
    assert "model_routing_decisions" not in source


def test_existing_0019_database_remains_at_the_current_head() -> None:
    scripts = _script_directory()
    revision = scripts.get_revision("0019")

    assert revision is not None
    assert revision.is_head
    assert scripts.get_heads() == ["0019"]
