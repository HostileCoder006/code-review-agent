"""Create database tables for native Windows / local development."""
from __future__ import annotations

import asyncio
import sys

from app.core.database import Base, engine
from app.models import Installation, Repository, Review, Finding, TimelineEvent  # noqa: F401


async def main() -> int:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    print("Tables created successfully.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to create tables: {exc}", file=sys.stderr)
        raise SystemExit(1)
