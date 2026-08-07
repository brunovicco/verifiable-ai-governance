"""Validate checked-in runtime authorization schema and example."""

import json
import sys
from pathlib import Path

from governance_schemas.runtime_authorization import SignedRuntimeAuthorization


def main() -> int:
    """Validate the example and ensure JSON Schema matches the Pydantic model."""
    root = Path(__file__).resolve().parents[1]
    example_path = root / "contracts/runtime-authorization/examples/credit-pj-v1.json"
    schema_path = root / "contracts/runtime-authorization/v1.schema.json"

    example = json.loads(example_path.read_text(encoding="utf-8"))
    parsed = SignedRuntimeAuthorization.model_validate(example)

    expected_schema = SignedRuntimeAuthorization.model_json_schema()
    stored_schema = json.loads(schema_path.read_text(encoding="utf-8"))
    if stored_schema != expected_schema:
        print(
            "[runtime-authorization] schema drift: regenerate v1.schema.json",
            file=sys.stderr,
        )
        return 2

    print(
        "[runtime-authorization] valid "
        f"id={parsed.claims.authorization_id} "
        f"signing_sha256={parsed.signing_digest()}"
    )
    print(
        "[runtime-authorization] note: P1.1 validates contract shape only; "
        "signature trust begins in P1.2"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
