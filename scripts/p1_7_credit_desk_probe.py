"""A2A probe used by the P1.7d live runtime-telemetry verification harness."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

import httpx
from a2a.client import ClientConfig, create_client
from a2a.helpers.proto_helpers import new_text_message
from a2a.types import Role, SendMessageRequest, Task, TaskState

_HEALTHY_INPUT = json.dumps(
    {
        "annual_revenue": "1000000",
        "total_debt": "300000",
        "monthly_debt_service": "10000",
        "monthly_operating_cash_flow": "25000",
        "bureau_score": "850",
        "years_in_operation": 12,
        "requested_amount": "30000",
        "critical_flags": [],
    }
)
_INVALID_INPUT = "not valid json"


def _task_text(task: Task) -> str:
    """Return the terminal JSON text without exposing it in the probe report."""
    if task.status.state == TaskState.TASK_STATE_COMPLETED:
        if not task.artifacts:
            raise RuntimeError("completed Credit Desk task returned no artifact")
        parts = task.artifacts[0].parts
    else:
        if task.status.message is None:
            raise RuntimeError("failed Credit Desk task returned no status message")
        parts = task.status.message.parts
    return "".join(part.text for part in parts)


async def _send(client: Any, text: str) -> Task:
    """Send one JSON text message and require one terminal task."""
    message = new_text_message(text, media_type="application/json", role=Role.ROLE_USER)
    task: Task | None = None
    async for response in client.send_message(SendMessageRequest(message=message)):
        task = response.task
    if task is None:
        raise RuntimeError("Credit Desk A2A request returned no task")
    return task


async def probe(base_url: str) -> dict[str, object]:
    """Exercise one successful and one failed terminal evaluation."""
    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as httpx_client:
        client = await create_client(
            base_url,
            client_config=ClientConfig(streaming=False, httpx_client=httpx_client),
            relative_card_path="/.well-known/agent-card.json",
        )
        try:
            success_task = await _send(client, _HEALTHY_INPUT)
            if success_task.status.state != TaskState.TASK_STATE_COMPLETED:
                raise RuntimeError("healthy Credit Desk task did not complete")
            success_payload = json.loads(_task_text(success_task))
            if not isinstance(success_payload, dict):
                raise RuntimeError("healthy Credit Desk opinion is not a JSON object")
            if success_payload.get("decision") != "APPROVAL_RECOMMENDED":
                raise RuntimeError("healthy Credit Desk decision is unexpected")

            failed_task = await _send(client, _INVALID_INPUT)
            if failed_task.status.state != TaskState.TASK_STATE_FAILED:
                raise RuntimeError("invalid Credit Desk task did not fail")
            failed_payload = json.loads(_task_text(failed_task))
            if not isinstance(failed_payload, dict):
                raise RuntimeError("failed Credit Desk envelope is not a JSON object")
            if failed_payload.get("code") != "INVALID_INPUT":
                raise RuntimeError("invalid Credit Desk task returned an unexpected error code")

            return {
                "success": {
                    "context_id": success_task.context_id,
                    "task_id": success_task.id,
                    "state": "completed",
                    "decision": "APPROVAL_RECOMMENDED",
                },
                "failure": {
                    "context_id": failed_task.context_id,
                    "task_id": failed_task.id,
                    "state": "failed",
                    "error_code": "INVALID_INPUT",
                },
            }
        finally:
            await client.close()


def main() -> int:
    """Run the structural A2A probe and print one compact JSON document."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    args = parser.parse_args()
    try:
        result = asyncio.run(probe(args.url.rstrip("/")))
    except Exception as exc:
        print(f"credit desk telemetry probe failed: {type(exc).__name__}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
