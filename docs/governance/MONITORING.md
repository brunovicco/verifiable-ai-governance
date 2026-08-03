# Monitoring of models and agents

## Three levels

1. **Operation:** availability, latency, error, timeout, throughput, tokens, cost,
   retries, fallback and rate limit.
2. **Model:** quality, groundedness, refusal, safety, structured output, regression,
   drift, version, region and out-of-scope use.
3. **Agent:** goal, plan, model, tools, sanitized arguments, permissions, loops,
   delegations, approvals, blocked actions, cost, time and state change.

## Events that must block or interrupt

- unapproved model, agent, tool or MCP;
- data class incompatible with the destination;
- absence of mandatory human approval;
- cost, time, steps or permissions above the limit;
- plan change after approval;
- irreversible action or action outside the tenant;
- regression below the promotion threshold;
- required telemetry or evidence unavailable.

## Minimization

Operational telemetry should prefer IDs, digests, categories, timestamps and
outcomes. Prompts, documents, credentials and responses are not collected by
default. Exceptions require explicit purpose, access, retention and approval.
