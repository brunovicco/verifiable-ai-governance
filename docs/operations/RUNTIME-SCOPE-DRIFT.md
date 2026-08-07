# Runtime scope-digest drift

P0.4 makes model and agent review digests executable runtime controls.

## What is checked

Every routing request loads fresh registry facts and recomputes canonical scope for:

- the governed agent;
- every registered model considered by that agent.

The recomputed digest is compared with the digest persisted by independent review.

## Failure modes

| Reason code | Meaning | Router called? |
| --- | --- | --- |
| `agent_scope_drifted` | Material agent facts changed after approval. | No |
| `model_scope_drifted` | Allowed approved model scope no longer matches review. | No |
| `agent_review_not_current` | Agent review is missing or expired. | No |
| `approved_model_unavailable` | No current approved/reviewed model is usable. | No |
| `registry_scope_changed` | Registry changed while router decision was in flight. | Possibly, but inference remains blocked. |

## Material model scope

The digest binds provider, model/version, routing group, region, approved/prohibited
use cases, allowed data classes, evaluation baseline and deprecation date.

## Material agent scope

The digest binds name, purpose, owner, version, region, autonomy, allowed models,
tools, permissions, cost/runtime limits, human approval points and kill-switch
availability.

## Recovery

Do not repair drift by editing `approved_scope_digest`.

1. inspect current asset state and audit trail;
2. determine whether changed facts are intended;
3. restore unintended facts through an authorized path, or submit intended changes
   for a new independent review;
4. for model changes, re-review dependent agents after model approval;
5. repeat the blocked runtime scenario and confirm the drift reason disappears.

## Validation

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy apps/api/src packages/governance-schemas/src packages/policy-engine/src
uv run pytest apps/api/tests/test_asset_registry_domain.py
uv run pytest apps/api/tests/test_model_routing_domain.py
uv run pytest apps/api/tests/test_model_routing_application.py
uv run pytest apps/api/tests/test_scope_digest_enforcement.py
uv run pytest
```

The P0.4 integration tests intentionally mutate model and agent fields through
SQLAlchemy without using `InventoryService`. This simulates a bypassed write path and
proves runtime execution still fails closed.
