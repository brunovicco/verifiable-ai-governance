"""Validate checked-in runtime violation schema and example against Pydantic."""

import json
from pathlib import Path

from governance_schemas import RuntimeViolationEnvelope

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "contracts/runtime-violation/v1.schema.json"
EXAMPLE = ROOT / "contracts/runtime-violation/credit-pj-model-scope-v1.json"


def main() -> int:
    """Fail when generated schema or example diverges from the Python contract."""
    expected_schema = RuntimeViolationEnvelope.model_json_schema()
    checked_schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    if checked_schema != expected_schema:
        raise SystemExit("runtime violation JSON Schema is stale")
    payload = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    envelope = RuntimeViolationEnvelope.model_validate(payload)
    if envelope.event_digest != envelope.event.digest():
        raise SystemExit("runtime violation example digest is invalid")
    print("runtime violation contract OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
