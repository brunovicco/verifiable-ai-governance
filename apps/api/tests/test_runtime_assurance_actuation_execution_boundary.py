import ast
import inspect
from pathlib import Path

from ai_governance_api.application.runtime_assurance_actuation_executions import (
    RuntimeAssuranceActuationExecutionService,
)


def _imported_module_roots(source: str) -> set[str]:
    tree = ast.parse(source)
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", maxsplit=1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", maxsplit=1)[0])
    return roots


def _called_attributes(source: str) -> list[str]:
    tree = ast.parse(source)
    return [
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]


def test_p1_9c_service_has_one_exactly_bounded_runtime_actuator() -> None:
    signature = inspect.signature(RuntimeAssuranceActuationExecutionService.__init__)
    assert tuple(signature.parameters) == (
        "self",
        "repository",
        "runtime_control",
        "audit",
        "transaction",
        "id_factory",
    )

    module_path = Path(inspect.getfile(RuntimeAssuranceActuationExecutionService))
    source = module_path.read_text(encoding="utf-8")
    calls = _called_attributes(source)

    assert calls.count("activate") == 1
    assert "deactivate" not in calls
    assert "restore_kill_switch" not in calls
    assert "PolicyModelRouter" not in source
    assert "policy_model_router" not in source
    assert _imported_module_roots(source).isdisjoint({"httpx", "requests"})


def test_p1_9c_persistence_does_not_mutate_agent_or_call_external_actuators() -> None:
    service_path = Path(inspect.getfile(RuntimeAssuranceActuationExecutionService))
    adapter_path = (
        service_path.parent.parent
        / "adapters"
        / "runtime_assurance_actuation_execution_persistence.py"
    )
    source = adapter_path.read_text(encoding="utf-8")
    calls = _called_attributes(source)

    assert "activate" not in calls
    assert "deactivate" not in calls
    assert "apply_agent_state" not in calls
    assert "PolicyModelRouter" not in source
    assert "policy_model_router" not in source
    assert _imported_module_roots(source).isdisjoint({"httpx", "requests"})
