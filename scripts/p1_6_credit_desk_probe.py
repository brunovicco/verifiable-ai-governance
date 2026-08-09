"""A2A probe executed with the Credit Desk workspace environment during P1.6d."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

import httpx
from a2a.client import ClientConfig, create_client
from a2a.helpers.proto_helpers import new_text_message
from a2a.types import Role, SendMessageRequest, TaskState

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


async def probe(base_url: str) -> dict[str, object]:
    """Send one healthy application and return the completed deterministic opinion."""
    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as httpx_client:
        client = await create_client(
            base_url,
            client_config=ClientConfig(streaming=False, httpx_client=httpx_client),
            relative_card_path="/.well-known/agent-card.json",
        )
        try:
            message = new_text_message(
                _HEALTHY_INPUT,
                media_type="application/json",
                role=Role.ROLE_USER,
            )
            task = None
            async for response in client.send_message(SendMessageRequest(message=message)):
                task = response.task
            if task is None or task.status.state != TaskState.TASK_STATE_COMPLETED:
                raise RuntimeError("Credit Desk A2A task did not complete")
            if not task.artifacts:
                raise RuntimeError("Credit Desk A2A task returned no artifact")
            body = "".join(part.text for part in task.artifacts[0].parts)
            payload = json.loads(body)
            if not isinstance(payload, dict):
                raise RuntimeError("Credit Desk opinion is not a JSON object")
            return payload
        finally:
            await client.close()


def main() -> int:
    """Parse the target URL and print one compact JSON result."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    args = parser.parse_args()
    try:
        payload = asyncio.run(probe(args.url.rstrip("/")))
    except Exception as exc:
        print(f"credit desk probe failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
