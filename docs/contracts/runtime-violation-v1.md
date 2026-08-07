# Runtime violation contract v1

`RuntimeViolationEnvelope` is the cross-service evidence format emitted by Policy Model Router when
signed runtime authorization is denied and consumed by Verifiable AI Governance.

The event is intentionally content-minimized. It contains request identity, bounded reason codes,
authorization identifiers/digests and the selected logical model group only when model-scope
enforcement reached that stage. Prompts, model responses, documents, headers and credentials are
out of contract.

The envelope carries `event_digest`, SHA-256 over canonical UTF-8 JSON of `event`. Governance must
validate both the digest and request/authorization binding before treating a 403 as a trusted
violation.

Authorization state semantics:

- `absent`: no signed authorization was supplied;
- `present`: a structurally valid envelope was supplied, but P1.3 verification did not complete;
- `verified`: P1.3 verification completed; required for model-scope violations.

A valid violation is enforcement evidence, not an incident severity decision. Incident handling and
kill-switch action are separate governance workflows.
