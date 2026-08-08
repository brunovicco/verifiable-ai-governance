"""Backfill trusted runtime-control snapshots before Router-side enforcement is enabled."""

import argparse
import asyncio

from sqlalchemy import select

from ai_governance_api.adapters.runtime_control_persistence import (
    SqlAlchemyRuntimeControlStateReader,
)
from ai_governance_api.application.runtime_control import RuntimeControlGate
from ai_governance_api.config import get_settings
from ai_governance_api.database import SessionFactory, engine
from ai_governance_api.dependencies import get_runtime_control_projection
from ai_governance_api.models import Agent


async def bootstrap_runtime_control(*, batch_size: int) -> int:
    """Project every durable Agent state using bounded keyset pagination."""
    if not 1 <= batch_size <= 1000:
        raise ValueError("batch_size must be between 1 and 1000")
    settings = get_settings()
    if not settings.runtime_control_enabled:
        raise RuntimeError("RUNTIME_CONTROL_ENABLED must be true for distributed bootstrap")

    projection = get_runtime_control_projection()
    reader = SqlAlchemyRuntimeControlStateReader(SessionFactory)
    gate = RuntimeControlGate(reader, projection)
    await projection.ping()

    projected = 0
    after_agent_id: str | None = None
    try:
        while True:
            async with SessionFactory() as session:
                statement = select(Agent.id).order_by(Agent.id).limit(batch_size)
                if after_agent_id is not None:
                    statement = statement.where(Agent.id > after_agent_id)
                agent_ids = list(await session.scalars(statement))
            if not agent_ids:
                break
            for agent_id in agent_ids:
                await gate.state_for(agent_id)
                projected += 1
            after_agent_id = agent_ids[-1]
        return projected
    finally:
        await projection.close()
        get_runtime_control_projection.cache_clear()
        await engine.dispose()


def main() -> int:
    """Run the bounded bootstrap and report only aggregate progress."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=250)
    args = parser.parse_args()
    try:
        projected = asyncio.run(bootstrap_runtime_control(batch_size=args.batch_size))
    except Exception as exc:
        print(f"Runtime-control bootstrap failed: {type(exc).__name__}")
        return 1
    print(f"Runtime-control bootstrap projected {projected} agents")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
