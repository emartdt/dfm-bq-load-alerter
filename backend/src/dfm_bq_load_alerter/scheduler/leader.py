"""PG advisory-lock leader-election (rev 2 P4).

Ensures **exactly one** Pod runs APScheduler cron jobs even when
`replicaCount > 1` or rolling update produces a transient overlap.

Mechanism:
- Each Pod opens a dedicated PG session and calls `pg_try_advisory_lock(K)`
  where K = crc32('dfm-alert-scheduler').
- The first caller acquires K → "leader". All subsequent callers see false
  → "standby" (API still serves; scheduler is dormant).
- When the leader Pod's session terminates (kill / OOM / network), PG
  releases the lock automatically — no orphaned locks. Standby Pods
  detect the release on their next heartbeat ping and one of them is
  promoted to leader.

This module is intentionally session-scoped. The lock is held for the
lifetime of `Leader._connection`. Closing the connection releases the
lock. Hold the connection open for as long as the Pod intends to be
leader.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import zlib
from collections.abc import Awaitable, Callable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

log = logging.getLogger(__name__)

LOCK_NAME = b"dfm-alert-scheduler"


def build_lock_key(name: bytes = LOCK_NAME) -> int:
    """Stable 32-bit integer key for pg_try_advisory_lock."""
    return zlib.crc32(name) & 0x7FFFFFFF


class Leader:
    """Run-time leader-election state for the scheduler.

    Lifecycle:
        leader = Leader(engine)
        await leader.try_acquire()          # one-shot at startup
        await leader.run_forever(...)       # background ping task
        await leader.release()              # on shutdown
    """

    def __init__(
        self,
        engine: AsyncEngine,
        *,
        ping_seconds: int = 30,
        lock_key: int | None = None,
    ) -> None:
        self._engine = engine
        self._ping = ping_seconds
        self._key = lock_key if lock_key is not None else build_lock_key()
        self._connection: AsyncConnection | None = None
        self._is_leader = False

    @property
    def is_leader(self) -> bool:
        return self._is_leader

    @property
    def lock_key(self) -> int:
        return self._key

    async def try_acquire(self) -> bool:
        """Attempt to take leadership. Idempotent when already leader."""
        if self._is_leader:
            return True
        connection = await self._engine.connect()
        try:
            result = await connection.execute(
                text("SELECT pg_try_advisory_lock(:k)"), {"k": self._key}
            )
            acquired = bool(result.scalar_one())
        except Exception:
            await connection.close()
            raise
        if not acquired:
            await connection.close()
            return False
        self._connection = connection
        self._is_leader = True
        log.info("leader acquired (lock_key=%s)", self._key)
        return True

    async def release(self) -> None:
        """Release the lock and close the dedicated connection."""
        if self._connection is None:
            self._is_leader = False
            return
        try:
            await self._connection.execute(
                text("SELECT pg_advisory_unlock(:k)"), {"k": self._key}
            )
        except Exception:  # noqa: BLE001 — best-effort on shutdown
            log.exception("advisory unlock failed; PG will release on session close")
        finally:
            await self._connection.close()
            self._connection = None
            self._is_leader = False
            log.info("leader released (lock_key=%s)", self._key)

    async def _verify_leader(self) -> bool:
        """Ping the lock connection — if it died, we lost leadership."""
        if self._connection is None:
            return False
        try:
            await self._connection.execute(text("SELECT 1"))
            return True
        except Exception:  # noqa: BLE001 — connection-level failure ⇒ not leader
            log.warning("leader connection ping failed; demoting to standby")
            with contextlib.suppress(Exception):
                await self._connection.close()
            self._connection = None
            self._is_leader = False
            return False

    async def run_forever(
        self,
        *,
        on_acquired: Callable[[], Awaitable[None]] | None = None,
        on_lost: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        """Heartbeat loop. Maintains leadership and triggers callbacks on transitions.

        - As leader: pings the lock connection every `ping_seconds`. If the
          ping fails, calls `on_lost` and tries to acquire again.
        - As standby: tries to acquire the lock. On success calls `on_acquired`.
        """
        while True:
            try:
                if self._is_leader:
                    if not await self._verify_leader() and on_lost is not None:
                        await on_lost()
                else:
                    if await self.try_acquire() and on_acquired is not None:
                        await on_acquired()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 — heartbeat loop must never die
                log.exception("leader heartbeat error")
            await asyncio.sleep(self._ping)
