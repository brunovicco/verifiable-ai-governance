# Control crosswalk

- **Status:** Reference mapping; not a compliance statement
- **Owner:** AI Governance and compliance
- **Last reviewed:** 2026-08-03
- **Review trigger:** Standard revision, regulatory change or catalog-version change

## Purpose

This document maps platform capability areas to commonly used AI governance and security
references. It supports gap analysis and evidence planning. It does not certify the
platform or an adopting organization.

The official text, current edition, jurisdictional interpretation and organizational
scope remain authoritative.

## Reference set

- NIST AI Risk Management Framework (AI RMF 1.0), including Govern, Map, Measure and
  Manage. NIST has indicated that an update is in progress.
- NIST AI 600-1, Generative AI Profile.
- ISO/IEC 42001:2023, Artificial Intelligence Management System.
- ISO/IEC 23894, AI risk-management guidance.
- OWASP Top 10 for LLM Applications 2025.
- OWASP Agentic AI threats and mitigation guidance.
- Regulation (EU) 2024/1689, the EU Artificial Intelligence Act, where applicable.

Official reference pages:

- https://airc.nist.gov/airmf-resources/airmf/
- https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence
- https://www.iso.org/standard/42001
- https://genai.owasp.org/resource/owasp-top-10-for-llm-applications-2025/
- https://genai.owasp.org/resource/agentic-ai-threats-and-mitigations/
- https://eur-lex.europa.eu/eli/reg/2024/1689/oj

## Capability-level crosswalk

| Platform capability | NIST AI RMF | ISO/IEC 42001 themes | GenAI / agent security | EU AI Act support area |
|---|---|---|---|---|
| Identifiable owner and RACI | Govern | Leadership, roles and accountability | Governance and ownership | Provider/deployer responsibilities |
| AI inventory | Govern, Map | AI system inventory and lifecycle processes | Asset and dependency awareness | System classification and documentation |
| Deterministic risk classification | Map, Measure | Risk assessment and treatment planning | Threat/risk prioritization | Risk-management process support |
| Structured impact assessments | Map, Measure | AI impact and risk assessment | Harm and misuse analysis | Fundamental-rights and impact documentation support |
| Versioned control catalog | Govern, Manage | Control objectives and operational planning | Mitigation traceability | Technical and organizational measures |
| Independent approval gates | Govern, Manage | Responsibility, review and change control | Human authorization and separation of duties | Human oversight and governance support |
| Evidence and review history | Govern, Measure | Documented information, monitoring and internal audit | Test and assurance evidence | Technical documentation and record support |
| Model and agent registry | Map, Manage | Lifecycle and supplier/system control | Model, tool and agent dependency control | System and component documentation |
| Runtime approved-scope enforcement | Manage | Operational control | Excessive agency, tool misuse and model substitution mitigation | Human/technical oversight support |
| Logging and monitoring design | Measure, Manage | Performance evaluation and monitoring | Detection of unsafe behavior and abuse | Logging/monitoring support where applicable |
| Incident and kill switch | Manage | Nonconformity, corrective action and continuity | Containment and remediation | Serious-incident and corrective-action support |
| Temporary exceptions | Govern, Manage | Risk treatment, approvals and review | Compensating controls | Controlled derogation governance, subject to law |
| Backup and restore assurance | Govern, Manage | Continuity and documented information protection | Resilience | Operational resilience support |

## NIST AI RMF interpretation

### Govern

Supported by ownership, RACI, policy versioning, authorization provenance, control
catalog governance, exceptions and audit.

### Map

Supported by business context, affected users, data, autonomy, regions, models, agents,
tools and processing context.

### Measure

Supported by structured assessments, evidence, test references, risk breakdown and
portfolio metrics. Real drift and control-effectiveness measures remain planned.

### Manage

Supported by conditional gates, risk treatment, independent approval, runtime blocking,
incidents, remediation, kill switch and review expiry.

## ISO/IEC 42001 interpretation

The project can provide implementation examples and evidence for an organizational AI
management system, particularly inventory, risk assessment, documented controls,
operational governance, monitoring and corrective action.

It cannot establish an AIMS by itself. Certification depends on the organization's
scope, leadership, policies, competencies, operating processes, internal audit and
continual improvement, among other requirements.

## OWASP interpretation

Relevant platform controls include:

- limiting models, tools and MCP integrations to approved scope;
- separating authorization from model output;
- requiring human approval where configured;
- minimizing data sent to external routers;
- blocking excessive cost, data-class or autonomy conditions;
- preserving routing and blocked-action evidence;
- planning sanitized agent telemetry and incident response.

Runtime-specific protections such as prompt-injection detection, secure tool execution,
output encoding and sandboxing remain responsibilities of the integrated AI runtime.

## EU AI Act interpretation

The platform can support inventory, classification context, technical documentation,
risk management, human oversight, logging, post-market monitoring and incident evidence.

Applicability, actor role, risk classification, required conformity activities and legal
obligations must be assessed against the current official regulation, amendments,
implementing measures and jurisdiction-specific guidance.

## Crosswalk governance

Each future control-level mapping should include:

- catalog and control version;
- reference name, edition and clause/category;
- mapping strength: direct, supporting or contextual;
- expected evidence;
- limitations and organizational dependencies;
- reviewer and review date.

Do not use terms such as “compliant”, “certified” or “meets all requirements” solely from
this crosswalk.
