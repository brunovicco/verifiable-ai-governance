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

GI-1 resolves each reference through an actor- and subject-bound application authorization port,
requires the resolver to return the exact artifact identity and version, and calculates SHA-256
over bounded source bytes. Only `VerifiedGovernanceKnowledgeSource` values may enter the
`GovernanceIntelligencePort`; raw references are insufficient. Digest verification binds bytes to
the reference but does not prove authenticity, applicability, evidentiary sufficiency or the truth
of a generated interpretation.

The first concrete mapping is GI-1A verified uploaded evidence:
`artifact_id="evidence:<canonical UUID>"`, the decimal evidence record version and its persisted
SHA-256 digest, without node/section selectors or storage coordinates. Eligibility and access are
adapter rules, not new fields in the Governance Finding `1.0` wire contract.

GI-2 orchestrates the first application-owned consumption boundary. It records purpose and source
access before analysis, supplies only verified source wrappers to one explicit advisory method,
then revalidates every candidate. Candidate citations must be a subset of the verified input;
provenance `retrieved_sources` must equal the complete verified input; provenance correlation must
match the authenticated request. Findings are returned only after a content-minimized completion
audit is committed. These are application invariants and do not change the `1.0` wire schema.

GI-3 adds a consumer-owned review boundary without changing this wire contract. It reconstructs
the envelope through the closed schema, requires provenance correlation to match authenticated
review context, authorizes the reviewer through a content-free port and records a digest-bound
minimized receipt. `accepted_for_consideration`, `rejected` and `deferred` describe review of the
advisory finding only. None represents a governed approval, authorization, compliance conclusion
or subject lifecycle transition. Finding content remains ephemeral; the audit receipt stores only
identities, disposition, trace facts and the SHA-256 envelope digest.

GI-3B adds a separate consumer-side receipt contract for durable replay. A caller-supplied
`request_id` is bound to the complete review command and to an immutable receipt digest. Exact
replays return the original receipt after current authorization; divergent reuse fails with a
conflict. The minimized receipt table and audit event remain outside Governance Finding `1.0` and
store no statement, confidence, source reference, prompt, provider or model content.

## Provenance and minimization

`AgentRunProvenance` records stable run, agent, model/configuration, source, tool-call, time and
correlation references needed for review and audit. The schema has no field for chain-of-thought,
full prompts, document bodies or complete model responses, and rejects those unexpected fields.

## Version and evolution policy

Governance Finding wire versions use `MAJOR.MINOR` independently from the Python package version.
Generic ingestion must call `parse_governance_finding`, which requires an explicit supported
`schema_version` and fails closed for missing or unknown versions.

Version `1.0` is immutable. Its generated schema is checked in at
`contracts/governance-intelligence/v1.schema.json` and bound by SHA-256 in
`contracts/governance-intelligence/compatibility-policy.json`.

Within a major, a newer consumer must retain and dispatch every earlier supported minor model.
Older consumers are not expected to accept newer minor payloads. Changes to existing meaning,
required fields or accepted data require a new major. No version increment permits authority state
or weakens `trust_level="untrusted"` and `advisory_only=true`.

See ADR 0056 and the PH-2 contract-evolution runbook for the complete lifecycle and change process.

## Checked-in implementation

- Python models: `packages/governance-schemas/src/governance_schemas/governance_intelligence.py`;
- application port: `apps/api/src/ai_governance_api/application/governance_intelligence.py`;
- governed analysis tests: `apps/api/tests/test_governance_intelligence_application.py`;
- portable example: `contracts/governance-intelligence/examples/risk-candidate-v1.json`;
- contract tests: `apps/api/tests/test_governance_intelligence_contract.py`;
- cross-repository compatibility gate:
  `scripts/verify_governance_intelligence_compatibility.py`;
- version-evolution gate:
  `scripts/verify_governance_intelligence_contract_evolution.py`;
- version-evolution tests:
  `apps/api/tests/test_governance_intelligence_contract_evolution.py`;
- architecture tests: `apps/api/tests/test_architecture.py`;
- architectural decisions: `docs/adr/0054-governance-intelligence-trust-boundary.md`,
  `docs/adr/0055-governance-intelligence-cross-repository-compatibility-gate.md` and
  `docs/adr/0056-governance-intelligence-versioned-contract-evolution.md`, plus the downstream
  source/orchestration/review decisions in ADRs 0057 through 0062.

The PH-1 gate builds and installs the wheel into an ephemeral target, then validates this fixture
from isolated Python processes rooted in current external consumer checkouts. PH-2 separately
protects immutable version artifacts, public dispatch and evolution rules.
