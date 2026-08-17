# Governance Finding Contract v1

GI-0 defines a portable envelope for conclusions and recommendations produced by future Governance
Intelligence adapters. Every finding is **advisory**, **untrusted** and **non-authoritative**.

The contract expresses the invariant:

```text
Agents reason.
Governed systems decide.
Runtime evidence proves.
```

## Wire shape

```json
{
  "schema_version": "1.0",
  "candidate": {
    "finding_id": "11111111-1111-4111-8111-111111111111",
    "finding_type": "risk_candidate",
    "statement": "The policy language may require an additional human review gate.",
    "confidence": 0.91,
    "sources": [
      {
        "artifact_id": "policy:acceptable-ai-use",
        "version": "3.1",
        "node_id": "clause:4.2.3",
        "section": "4.2.3",
        "content_digest": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
      }
    ],
    "external_taxonomy_references": [
      {
        "provider": "nist",
        "taxonomy": "ai-rmf",
        "identifier": "GOVERN-1.2",
        "version": "1.0",
        "reference_uri": "https://airc.nist.gov/AI_RMF_Knowledge_Base/Playbook"
      }
    ],
    "provenance": {
      "agent_run_id": "22222222-2222-4222-8222-222222222222",
      "agent_name": "risk_mapper",
      "provider": "provider-neutral",
      "model": "governance-analysis-model",
      "model_version": "2026.08",
      "prompt_config_version": "risk-mapping-v1",
      "retrieval_query_reference": "query:4de78b5f",
      "retrieved_sources": [],
      "tool_call_references": ["tool-call:resolve-policy"],
      "created_at": "2026-08-16T18:30:00Z",
      "correlation_id": "corr:gi-0-example"
    },
    "trust_level": "untrusted",
    "advisory_only": true
  }
}
```

The Python implementation follows the repository digest convention: lowercase SHA-256 hex with 64
characters and no `sha256:` prefix.

## Finding types

Version 1.0 starts with a deliberately small taxonomy:

- `policy_interpretation`;
- `risk_candidate`;
- `control_candidate`;
- `evidence_gap`;
- `evidence_interpretation`;
- `intake_suggestion`.

These values describe recommendations, not governed lifecycle states. Approval, authorization,
compliance, release, runtime-control and restoration outcomes are outside this contract.

## Validation and review flow

```text
LLM output / external finding / retrieved content / uploaded document / tool output
  → GovernanceFindingEnvelope schema validation
  → source validation and reference resolution
  → artifact-version digest verification
  → GovernanceFindingCandidate (still advisory and untrusted)
  → human or deterministic review
  → governed decision through an authoritative use case
```

Pydantic validation closes every model with `extra="forbid"`. Payloads containing fields such as
`approved`, `authorized`, `compliant`, `approval_status`, `runtime_authorized` or
`control_approved` are invalid. A confidence value of `1.0` remains only a recommendation.

Schema validity proves only that a payload matches the contract. It does not prove that a source
exists, that its digest matches resolved bytes, that the source is authentic, that the
interpretation is correct or that a governance decision is valid.

## Source and taxonomy references

`GovernanceSourceReference` carries an artifact ID, version, optional node/section and content
digest. It never carries the full document. Consumers resolve the reference through an authorized
source adapter and verify the version and digest before review.

`ExternalTaxonomyReference` is generic by design and accepts an optional HTTP(S) or URN locator.
NIST, OWASP, MITRE, EU, ASAGO, GRC and internal taxonomies can be referenced without making any of
them a core dependency or source of governance authority.

AI-generated interpretation is not evidence. The original resolved artifact may be evidence; the
finding is a derived representation.

## Provenance and minimization

`AgentRunProvenance` records stable run, agent, model/configuration, source, tool-call, time and
correlation references needed for review and audit. The schema has no field for chain-of-thought,
full prompts, document bodies or complete model responses, and rejects those unexpected fields.

## Checked-in implementation

- Python models: `packages/governance-schemas/src/governance_schemas/governance_intelligence.py`;
- application port: `apps/api/src/ai_governance_api/application/governance_intelligence.py`;
- contract tests: `apps/api/tests/test_governance_intelligence_contract.py`;
- architecture tests: `apps/api/tests/test_architecture.py`;
- architectural decision: `docs/adr/0054-governance-intelligence-trust-boundary.md`.
