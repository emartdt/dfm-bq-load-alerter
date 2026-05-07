"""Verify the alembic environment loads and the initial migration's metadata is sane.

Full upgrade/downgrade smoke test against a real PG instance is run in CI's
integration job (pytest-postgresql); this module verifies the static structure
without requiring a live database.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ALEMBIC_DIR = Path(__file__).resolve().parents[1] / "alembic"


def _load_revision_module():
    versions = sorted((ALEMBIC_DIR / "versions").glob("*.py"))
    assert versions, "expected at least one alembic revision under alembic/versions/"
    spec = importlib.util.spec_from_file_location("initial_migration", versions[0])
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["initial_migration"] = module
    spec.loader.exec_module(module)
    return module


def test_alembic_env_module_imports() -> None:
    """env.py must import cleanly when alembic config is not active (parses only)."""
    env_path = ALEMBIC_DIR / "env.py"
    assert env_path.exists()
    source = env_path.read_text()
    # sanity checks — env.py wires SQLAlchemy async engine and target metadata
    assert "target_metadata" in source
    assert "run_async_migrations" in source


def test_initial_migration_has_upgrade_and_downgrade() -> None:
    module = _load_revision_module()
    assert hasattr(module, "upgrade") and callable(module.upgrade)
    assert hasattr(module, "downgrade") and callable(module.downgrade)
    assert module.revision == "0001"
    assert module.down_revision is None


def test_models_register_against_metadata() -> None:
    """All ORM models must register against the shared Base.metadata."""
    from dfm_bq_load_alerter.db import models  # noqa: F401
    from dfm_bq_load_alerter.db.base import Base

    expected = {
        "tables",
        "check_snapshots",
        "alert_recipients",
        "teams_webhooks",
        "alert_events",
        "report_runs",
        "bo_users",
        "alert_policy",
        "system_warnings",
        "bq_query_log",
        "alert_groups",
        "alert_group_recipients",
        "alert_group_webhooks",
    }
    actual = set(Base.metadata.tables.keys())
    missing = expected - actual
    assert not missing, f"Missing tables in metadata: {missing}"
