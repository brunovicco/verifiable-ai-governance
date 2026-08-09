import ast
import inspect
from pathlib import Path

from ai_governance_api.application.runtime_assurance_actuation import (
    RuntimeAssuranceActuationRequestService,
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


def test_p1_9a_service_has_no_runtime_actuation_boundary() -> None:
    signature = inspect.signature(RuntimeAssuranceActuationRequestService.__init__)
    assert tuple(signature.parameters) == (
        "self",
        "repository",
        "audit",
        "transaction",
        "clock",
        "id_factory",
    )

    module_path = Path(inspect.getfile(RuntimeAssuranceActuationRequestService))
    source = module_path.read_text(encoding="utf-8")

    forbidden = (
        "RuntimeControlService",
        "RuntimeControlEntry",
        ".activate(",
        ".deactivate(",
        "PolicyModelRouter",
        "policy_model_router",
    )

    assert all(token not in source for token in forbidden)
    assert _imported_module_roots(source).isdisjoint({"httpx", "requests"})


def test_p1_9a_persistence_has_no_runtime_control_or_router_dependency() -> None:
    service_path = Path(inspect.getfile(RuntimeAssuranceActuationRequestService))
    adapter_path = (
        service_path.parent.parent / "adapters" / "runtime_assurance_actuation_persistence.py"
    )
    source = adapter_path.read_text(encoding="utf-8")

    forbidden = (
        "runtime_control",
        "RuntimeControlEntry",
        "PolicyModelRouter",
        "policy_model_router",
    )

    assert all(token not in source for token in forbidden)
    assert _imported_module_roots(source).isdisjoint({"httpx", "requests"})
