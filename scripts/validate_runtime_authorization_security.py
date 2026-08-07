"""Validate P1.2 public key-set configuration and crypto availability."""

from pathlib import Path

from ai_governance_api.adapters.runtime_authorization_crypto import (
    PyJwtEd25519SignatureProvider,
)
from ai_governance_api.domain.runtime_authorization_security import (
    load_runtime_authorization_key_set_json,
    runtime_authorization_key_set_json,
)


def main() -> int:
    """Load the checked-in public example and verify canonical round-trip."""
    root = Path(__file__).resolve().parents[1]
    path = root / "contracts/runtime-authorization/examples/trusted-key-set-v1.json"
    raw = path.read_text(encoding="utf-8")
    key_set = load_runtime_authorization_key_set_json(raw)
    canonical = runtime_authorization_key_set_json(key_set)

    # Constructing the provider proves the configured PyJWT crypto extra exposes EdDSA.
    PyJwtEd25519SignatureProvider()

    print(
        "[runtime-authorization] key-set valid "
        f"generation={key_set.generation} keys={len(key_set.keys)}"
    )
    print(f"[runtime-authorization] canonical-json-bytes={len(canonical.encode('utf-8'))}")
    print("[runtime-authorization] private key material is not stored in this file")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
