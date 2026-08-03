# Stage gates

| Gate | Entry | Mandatory exit | Typical blockers |
|---|---|---|---|
| G0 Intake | objective and owner | registration and ID | missing owner/purpose |
| G1 Triage | completed questionnaire | risk tier, documents and gates | inconsistent answers |
| G2 Assessment | system card and AIA | proposed risks and treatments | missing RIPD/transfer |
| G3 Design | architecture and vendors | conditional technical approvals | threat, region or access without a control |
| G4 Validation | candidate version and test plan | evaluation report and limits | metric below threshold |
| G5 Go-live | approved gates and evidence | versioned decision, rollback and operational owner | any pending/rejected gate |
| G6 Operation | telemetry and baseline | reviews, alerts and handled incidents | drift, violation or unapproved model |
| G7 Change/Retire | change assessment or exit plan | new decision or discontinuation evidence | material change without reassessment |

## Material changes

Switching model/version, a new country, a new data category, a new tool or
permission, increased autonomy, a change of purpose, a new affected audience and a
threshold change must reopen the assessment. The system will not reuse a prior
approval by implicit similarity.

A change request in G2-G5 closes the current round, preserves the evaluated snapshot
and reopens the existing assessments as versioned drafts. After corrections, the
owner provides a summary, resubmits the assessments and creates a new round with
recalculated policy and gates. A definitive rejection cannot be converted into a
resubmission without a new formal process.
