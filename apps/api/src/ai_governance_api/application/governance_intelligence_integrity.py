"""Canonical integrity helpers shared across Governance Intelligence boundaries."""

import hashlib
import json

from governance_schemas import GovernanceFindingEnvelope


def governance_finding_envelope_digest(finding: GovernanceFindingEnvelope) -> str:
    """Return lowercase SHA-256 over one complete canonical finding envelope."""
    canonical = json.dumps(
        finding.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(canonical).hexdigest()
