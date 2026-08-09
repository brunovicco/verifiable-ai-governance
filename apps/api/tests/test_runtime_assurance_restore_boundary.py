import ast
import inspect
from pathlib import Path

from ai_governance_api.application.runtime_assurance_restore import (
    RuntimeAssuranceRestoreDecisionService,
    RuntimeAssuranceRestoreExecutionService,
    RuntimeAssuranceRestoreRequestService,
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


def test_restore_request_and_decision_services_have_no_runtime_control_actuator() -> None:
    request_signature = inspect.signature(RuntimeAssuranceRestoreRequestService.__init__)
    decision_signature = inspect.signature(RuntimeAssuranceRestoreDecisionService.__init__)
    assert "runtime_control" not in request_signature.parameters
    assert "runtime_control" not in decision_signature.parameters


def test_restore_execution_is_bounded_to_deactivate_only() -> None:
    signature = inspect.signature(RuntimeAssuranceRestoreExecutionService.__init__)
    assert "runtime_control" in signature.parameters
    module_path = Path(inspect.getfile(RuntimeAssuranceRestoreExecutionService))
    source = module_path.read_text(encoding="utf-8")
    assert "._runtime_control.deactivate(" in source
    assert "._runtime_control.activate(" not in source
    assert "PolicyModelRouter" not in source
    assert "policy_model_router" not in source
    assert _imported_module_roots(source).isdisjoint({"httpx", "requests"})


def test_restore_persistence_has_no_router_or_http_dependency() -> None:
    service_path = Path(inspect.getfile(RuntimeAssuranceRestoreExecutionService))
    adapter_path = (
        service_path.parent.parent / "adapters" / "runtime_assurance_restore_persistence.py"
    )
    source = adapter_path.read_text(encoding="utf-8")
    assert "PolicyModelRouter" not in source
    assert "policy_model_router" not in source
    assert _imported_module_roots(source).isdisjoint({"httpx", "requests"})
