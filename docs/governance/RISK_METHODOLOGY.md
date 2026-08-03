# Risk methodology

- **Status:** Current baseline
- **Owner:** AI Governance and risk
- **Last reviewed:** 2026-08-03
- **Review trigger:** Policy-version change, new risk factor, sector overlay or incident learning

## Purpose

The preliminary risk score is a triage mechanism. It determines proportional governance
requirements and does not replace expert assessment, legal classification or approval.

## Current dimensions

The baseline score ranges from 0 to 100 and considers:

| Dimension | Maximum contribution |
|---|---:|
| Decision impact | 30 |
| Data sensitivity and privacy | 25 |
| Autonomy and action capability | 25 |
| Exposure and affected population | 10 |
| Regulated or high-control context | 10 |

The policy also applies elevation rules so that rights/safety impact or high autonomy
cannot be diluted by low values in unrelated dimensions.

## Risk tiers

| Tier | Governance interpretation |
|---|---|
| Low | Identifiable owner, system documentation and proportionate periodic review |
| Medium | Applicable technical gates, defined tests and monitoring expectations |
| High | Independent assurance, security analysis, stronger evidence and frequent review |
| Critical | Committee-level decision, reinforced human oversight, strict autonomy limits and stop criteria |

Exact score thresholds and elevation logic belong to the versioned policy engine and
should not be duplicated as an independent source of truth in this document.

## Inputs

Risk inputs should be normalized and explicit. Relevant facts include:

- purpose and intended users;
- decision impact;
- personal, sensitive or children's data;
- data classification;
- autonomy and ability to execute actions;
- external exposure;
- regulated context;
- international processing;
- RAG, agents, MCP and custom models;
- hosting and provider context;
- reversibility, human oversight and affected rights where captured.

Unknown or missing material facts should not be interpreted as low risk.

## Inherent and residual risk

### Inherent risk

Risk before considering implemented controls and evidence. The preliminary policy score
primarily supports this view.

### Residual risk

Risk remaining after considering controls, design choices, human oversight, test results
and operational limitations. Structured assessments may record a residual-risk tier,
but its acceptance remains a governance decision rather than an automatic score result.

## Overrides

A reviewer may need to raise the risk tier based on evidence or context not represented
in the baseline inputs. An override should record:

- original policy result;
- requested and final tier;
- reviewer identity and area;
- justification;
- supporting evidence;
- policy and entity version;
- review or expiry condition.

A reduction should require stronger evidence and explicit authority because it decreases
governance requirements.

## Change triggers

Reassessment is required when a material fact changes, including:

- purpose or affected population;
- decision impact or autonomy;
- data class or processing location;
- provider, model version or routing group;
- tool, MCP or external integration;
- human-approval condition;
- cost, latency or operational limits when they affect safe behavior;
- evidence of incident, drift or control failure.

Old approvals must not be reused solely because a new scope appears similar.

## Validation of the methodology

The risk policy should be tested for:

- determinism;
- monotonicity for clearly increasing risk factors;
- elevation-rule behavior;
- boundary conditions around tier changes;
- missing and contradictory facts;
- representative low, medium, high and critical scenarios;
- regressions after a policy-version change;
- sector-overlay conflicts.

## Governance of policy changes

Every material change should include:

1. semantic policy version update;
2. rationale and affected risk scenarios;
3. positive and negative tests;
4. migration or re-evaluation plan for existing initiatives;
5. approval by the policy owner;
6. communication of changed obligations;
7. monitoring for unintended portfolio effects.

## Limitations

The score cannot fully represent organizational culture, legal interpretation, malicious
intent, emergent model behavior or all sector-specific harms. It is a reproducible entry
point for review, not a substitute for multidisciplinary judgment.
