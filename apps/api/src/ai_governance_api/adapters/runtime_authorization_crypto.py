"""Ed25519 signature adapter for canonical runtime authorization bytes."""

import base64
import binascii

from jwt.algorithms import Algorithm, get_default_algorithms
from jwt.exceptions import InvalidKeyError

from ai_governance_api.domain.runtime_authorization_security import (
    RuntimeAuthorizationSecurityError,
)


class PyJwtEd25519SignatureProvider:
    """Sign and verify raw bytes using PyJWT's EdDSA cryptographic primitive."""

    def __init__(self) -> None:
        """Resolve the EdDSA primitive from the already-declared PyJWT crypto stack."""
        self._algorithm: Algorithm = get_default_algorithms()["EdDSA"]

    def sign(self, payload: bytes, private_key_pem: str) -> str:
        """Return an unpadded base64url Ed25519 signature for arbitrary bytes."""
        try:
            key = self._algorithm.prepare_key(private_key_pem)
            signature = self._algorithm.sign(payload, key)
        except (InvalidKeyError, TypeError, ValueError) as exc:
            raise RuntimeAuthorizationSecurityError(
                "invalid_private_key",
                "Runtime authorization signing key is invalid",
            ) from exc
        if len(signature) != 64:
            raise RuntimeAuthorizationSecurityError(
                "unsupported_eddsa_key",
                "Runtime authorization v1 requires Ed25519 rather than another EdDSA curve",
            )
        return base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")

    def verify(self, payload: bytes, public_jwk: str, signature: str) -> bool:
        """Verify an Ed25519 signature against one exact trusted public JWK."""
        try:
            raw_signature = _decode_signature(signature)
            public_key = self._algorithm.from_jwk(public_jwk)
            return bool(self._algorithm.verify(payload, public_key, raw_signature))
        except (InvalidKeyError, TypeError, ValueError, binascii.Error):
            return False


def _decode_signature(value: str) -> bytes:
    """Decode strict unpadded base64url and require Ed25519's 64-byte signature."""
    if len(value) != 86:
        raise ValueError("Ed25519 signature must be 86 base64url characters")
    encoded = value.encode("ascii")
    padding = b"=" * ((4 - len(encoded) % 4) % 4)
    decoded = base64.b64decode(
        encoded + padding,
        altchars=b"-_",
        validate=True,
    )
    if len(decoded) != 64:
        raise ValueError("Ed25519 signature must decode to 64 bytes")
    return decoded
