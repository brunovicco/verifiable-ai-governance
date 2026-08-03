# ADR 0024 - Executive metrics for the operational dashboard

## Status

Accepted.

## Date

2026-08-03.

## Context

The P2 backlog asked for "Executive metrics for coverage, SLA, residual risk, and
control effectiveness," extending the operational dashboard just delivered (ADR 0023).
The same honesty discipline applies: show only what is real.

- **Residual risk**: real, but not where the name suggested. `Assessment` has no
  dedicated `residual_risk` column - the value the owner reports in the structured
  response (`AIImpactAnswers.residual_risk`, etc., in `domain/assessments.py`) is
  already persisted into `Assessment.risk_tier` at submission time
  (`application/assessments.py`). Reusing that column avoids an easy mapping mistake
  (confirmed during implementation: `mypy` rejected the initial attempt to read a
  nonexistent `residual_risk` column).
- **SLA**: no declared target deadline exists anywhere in the code - only observed
  duration. `ReviewSubmission.submitted_at`/`.resolved_at` and
  `Incident.detected_at`/`.resolved_at` (both already present) give real cycle time.
  With no target to compare against, the metric is "average observed time," never "% within
  SLA" - the same choice already made for "cost" in ADR 0023.
- **Coverage**: `Initiative.required_documents` and `domain/assessments.py::
  AssessmentKind` use exactly the same string values
  (`"ai-impact-assessment"`, `"ripd"`, `"international-processing-assessment"`),
  confirmed by reading both definitions. This makes the intersection reliable without
  fragile text matching.
- **Control effectiveness**: no data exists. `ControlEvaluation` only records static
  applicability (`applicable: bool` + `reasons`), never whether the required evidence
  was actually verified or whether the control prevented anything.

## Decision

The three real metrics extend the same `DashboardSnapshot`/`GET /api/v1/dashboard` from
ADR 0023 - no new endpoint, no migration (every field used already exists).

Residual risk is aggregated by `RiskTier` from `Assessment.risk_tier` across non-draft
assessments. Coverage intersects each non-draft initiative's `required_documents` with
the three known `AssessmentKind` values, counting how many have a corresponding non-draft
`Assessment` - deliberately limited to the three structured assessments, not the
remaining evidence-based items in `required_documents` (`ai-system-card`,
`threat-model`, etc.); covering those would require heuristic matching against the free
text of `Evidence.kind`, a more fragile computation, recorded as a follow-up rather than
done unreliably. Cycle time is the average of observed hours between submission and
resolution of review rounds, and between detection and closure of incidents; when the
sample is empty, the result is `None` (not `0`), and the sample size always accompanies
the average so the panel's reader can judge the reliability of an average drawn from few
observations. Control effectiveness gets the same explicit-placeholder treatment as
"drift" in ADR 0023 (`control_effectiveness_available: false`).

## Alternatives considered

- **Define coverage against all `required_documents` items, including evidence-based
  ones:** rejected because it would require heuristic free-text matching against
  `Evidence.kind`, with a real risk of silent miscounting.
- **Expose "% within deadline" for cycle time:** rejected - this platform has no
  declared target deadline to compute compliance against.
- **Fabricate control effectiveness from a proxy (e.g., absence of incidents on systems
  where the control is applicable):** rejected - absence of an incident does not prove a
  control worked, and presenting it as "effectiveness" would mislead the panel's reader.

## Consequences

- no migration, no new endpoint - a pure extension of `DashboardSnapshot`;
- structured-assessment coverage is deliberately narrower than the full set of
  `required_documents`;
- cycle time may have a small or empty sample early in a portfolio's life; the panel
  shows the sample size so as not to suggest undue confidence.

## Security and privacy impact

Same surface as ADR 0023: only aggregated counts and averages, no end-user identifier,
prompt, or document content.

## Operational impact

No migration, no enablement flag - the extension is always on alongside the existing
endpoint.

## Follow-up

- cover coverage of evidence-based `required_documents` once there is a reliable way to
  link `Evidence.kind` to each item;
- control effectiveness once some real verification of evidence per control exists, not
  just declarative applicability;
- consider declaring explicit SLA targets on this platform, which would enable an honest
  compliance metric.
