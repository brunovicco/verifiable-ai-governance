# Control catalog

The baseline catalog connects initiative characteristics to verifiable controls. It
is an operational reference and does not constitute certification or an automatic
declaration of compliance.

## Structure of a control

| Field | Purpose |
|---|---|
| `control_id` | Stable identifier used in evidence and integrations |
| `domain` | Domain responsible for organizing the catalog |
| `objective` | Risk or outcome the control is intended to address |
| `control_type` | Preventive, detective or corrective |
| `owner` | Role responsible for design and follow-up |
| `review_frequency` | Minimum cadence or review-triggering event |
| `requirements` | Verifiable implementation conditions |
| `evidence` | Evidence expected for assurance |
| `implementation_reference` | Optional technical implementation from the portfolio |
| `applicability` | Declarative rule evaluated against the initiative |

## Applicability semantics

`always: true` identifies baseline controls. The others can select risk tiers, flags,
impacts, data classifications, autonomy and hosting. `match: any` applies the control
when any configured group matches; `match: all` requires all groups. An empty rule, or
one that combines `always` with selectors, is rejected.

The report records both matches and unmet conditions. The interface shows applicable
controls by default and allows browsing the full catalog.

## File governance

- any change must update the catalog's semantic version;
- existing IDs must not be reused for different objectives;
- requirements and evidence must be testable and understandable;
- rule changes must include positive and negative scenarios;
- sector overlays will be added without silently changing the baseline.

## Supporting crosswalk with external frameworks

`packages/policy-engine/src/policy_engine/control_crosswalk.yaml` maps each control to
references from the NIST AI RMF (NIST AI 100-1), NIST AI 600-1 (Generative AI
Profile), the OWASP Top 10 for LLM Applications & Generative AI, the OWASP Top 10 for
Agentic Applications and MITRE ATLAS. It is its own file, versioned separately from
the baseline catalog - it does not change `applicability` or any policy decision.

The citations were built from a direct reading of the official source texts: NIST AI
100-1 (AI RMF 1.0, Jan/2023), NIST AI 600-1 (Generative AI Profile, Jul/2024), OWASP
Top 10 for LLM Applications & Generative AI 2025 (Nov/2024), OWASP Top 10 for Agentic
Applications 2026 (Dec/2025), and MITRE ATLAS, cross-checked against the MITRE
SAFE-AI report (Apr/2025) and the cross-references OWASP's own Top 10 makes to ATLAS
technique IDs. Even so, the crosswalk does not constitute legal opinion, certification
or a declaration of compliance - it should be reviewed by legal/compliance before
formal use, and each reference can be reconfirmed against the corresponding
framework's official text. `agent`-domain controls (GOV-AGT-*) use the OWASP Agentic
Top 10 (codes ASI01-ASI10) as the primary reference for risks specific to
multi-agent systems, complementing the OWASP LLM Top 10.

NIST AI RMF citations use named function/category (e.g., "GOVERN 2") as the default
granularity; a numbered subcategory (e.g., "GOVERN 1.6") only appears in the few cases
where it maps directly and unambiguously to the control - a deliberate editorial
choice, not a source-access limitation. The concept note "NIST AI RMF: Trustworthy
Use of AI in Critical Infrastructure Profile" (Apr/2026) does not yet define citable
risk categories (it is a planning document, not a published profile) and is therefore
not referenced; it will be assessed once a complete profile is published.

ISO/IEC 42001 is listed as pending (`frameworks_pending`) because it is a licensed
standard; no reference is cited against it until the official text is accessible. The
loader (`GovernanceControlCrosswalk`) fails closed if an entry references a
`control_id` that does not exist in the loaded catalog, and can be overridden via
`CONTROL_CROSSWALK_PATH`, following the same pattern as `CONTROL_CATALOG_PATH`.
