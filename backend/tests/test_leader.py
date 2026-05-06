"""Unit tests for the PG advisory-lock Leader implementation.

The PG side is mocked with an AsyncMock connection so tests run in any
environment without a real PostgreSQL.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from dfm_bq_load_alerter.scheduler.leader import Leader, build_lock_key


def _build_engine(*, lock_returns: list[bool], ping_raises: bool = False) -> MagicMock:
    """Engine whose connect() returns a connection scripted to return lock_returns."""
    engine = MagicMock()

    def make_connection() -> MagicMock:
        conn = MagicMock()
        conn.execute = AsyncMock()
        conn.close = AsyncMock()

        scripted = list(lock_returns)

        async def execute_side_effect(stmt, _params=None):
            text = str(stmt)
            if "pg_try_advisory_lock" in text:
                value = scripted.pop(0) if scripted else False
                result = MagicMock()
                result.scalar_one.return_value = value
                return result
            if "pg_advisory_unlock" in text:
                result = MagicMock()
                result.scalar_one.return_value = True
                return result
            if "SELECT 1" in text:
                if ping_raises:
                    raise RuntimeError("connection lost")
                return MagicMock()
            return MagicMock()

        conn.execute.side_effect = execute_side_effect
        return conn

    async def connect() -> MagicMock:
        return make_connection()

    engine.connect = AsyncMock(side_effect=connect)
    return engine


def test_lock_key_is_stable() -> None:
    assert build_lock_key() == build_lock_key()
    assert build_lock_key() == build_lock_key(b"dfm-alert-scheduler")
    assert 0 <= build_lock_key() < 2**31


@pytest.mark.asyncio
async def test_try_acquire_returns_true_when_lock_available() -> None:
    engine = _build_engine(lock_returns=[True])
    leader = Leader(engine)
    assert await leader.try_acquire() is True
    assert leader.is_leader is True


@pytest.mark.asyncio
async def test_try_acquire_returns_false_when_lock_held() -> None:
    engine = _build_engine(lock_returns=[False])
    leader = Leader(engine)
    assert await leader.try_acquire() is False
    assert leader.is_leader is False


@pytest.mark.asyncio
async def test_try_acquire_is_idempotent_when_already_leader() -> None:
    engine = _build_engine(lock_returns=[True])
    leader = Leader(engine)
    await leader.try_acquire()
    # second call should not re-execute the lock query
    engine.connect.reset_mock()
    assert await leader.try_acquire() is True
    engine.connect.assert_not_called()


@pytest.mark.asyncio
async def test_release_closes_connection_and_resets_state() -> None:
    engine = _build_engine(lock_returns=[True])
    leader = Leader(engine)
    await leader.try_acquire()
    held_connection = leader._connection  # noqa: SLF001
    assert held_connection is not None

    await leader.release()
    held_connection.close.assert_awaited()
    assert leader.is_leader is False
    assert leader._connection is None  # noqa: SLF001


@pytest.mark.asyncio
async def test_release_when_not_leader_is_noop() -> None:
    engine = _build_engine(lock_returns=[False])
    leader = Leader(engine)
    await leader.try_acquire()
    # should not raise
    await leader.release()
    assert leader.is_leader is False


@pytest.mark.asyncio
async def test_verify_leader_demotes_when_ping_fails() -> None:
    engine = _build_engine(lock_returns=[True], ping_raises=True)
    leader = Leader(engine)
    await leader.try_acquire()
    assert leader.is_leader is True

    ok = await leader._verify_leader()  # noqa: SLF001
    assert ok is False
    assert leader.is_leader is False
    assert leader._connection is None  # noqa: SLF001
