"""Tests for WP9: Worker operations, cron schedules, and database cleanup."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from analystforge.api.db import Database
from analystforge.api.models.collaboration import ShareLink
from analystforge.api.models.core import RefreshToken, Tenant, User
from analystforge.api.models.ops import ProviderHealthRecord
from analystforge.api.services.maintenance import run_operational_cleanup
from analystforge.worker.main import (
    WorkerSettings,
    ping,
)


def test_worker_settings_cron_jobs_and_functions():
    """Verify worker function registry and cron schedules."""
    function_names = {f.__name__ for f in WorkerSettings.functions}
    assert "ping" in function_names
    assert "ingest_all" in function_names
    assert "check_alerts" in function_names
    assert "check_scheduled_screens" in function_names
    assert "cleanup_database" in function_names
    assert "update_prices" in function_names
    assert "update_macro" in function_names

    # Check cron definitions exist
    cron_jobs = WorkerSettings.cron_jobs
    assert len(cron_jobs) >= 8


@pytest.mark.asyncio
async def test_worker_ping():
    ctx = {}
    res = await ping(ctx)
    assert res == "pong"


@pytest.mark.asyncio
async def test_operational_cleanup(db: Database):
    """Exit criteria: Database cleanup deactivates expired shares and purges revoked tokens."""
    now = datetime.now(UTC)

    async with db.session() as session:
        # 1. Setup tenant & user
        t = Tenant(name="Ops Tenant", slug=f"ops-{uuid.uuid4().hex[:6]}")
        session.add(t)
        await session.flush()

        u = User(
            tenant_id=t.id,
            email=f"worker_{uuid.uuid4().hex[:6]}@test.com",
            password_hash="argon2id$mockhash",
            full_name="Worker Test User",
            role="ANALYST",
        )
        session.add(u)
        await session.flush()

        # 2. Add an expired share link and an active unexpired share link
        expired_share = ShareLink(
            tenant_id=t.id,
            user_id=u.id,
            token=f"exp_{uuid.uuid4().hex[:16]}",
            resource_type="portfolio",
            resource_id="port_1",
            expires_at=now - timedelta(hours=2),
            is_active=True,
        )
        active_share = ShareLink(
            tenant_id=t.id,
            user_id=u.id,
            token=f"act_{uuid.uuid4().hex[:16]}",
            resource_type="portfolio",
            resource_id="port_2",
            expires_at=now + timedelta(days=2),
            is_active=True,
        )
        session.add_all([expired_share, active_share])

        # 3. Add revoked/expired tokens and an active valid token
        revoked_token = RefreshToken(
            user_id=u.id,
            token_hash=f"hash_{uuid.uuid4().hex[:16]}",
            family="fam_1",
            is_revoked=True,
            expires_at=now - timedelta(days=10),
        )
        valid_token = RefreshToken(
            user_id=u.id,
            token_hash=f"hash_{uuid.uuid4().hex[:16]}",
            family="fam_2",
            is_revoked=False,
            expires_at=now + timedelta(days=20),
        )
        session.add_all([revoked_token, valid_token])

        # 4. Add old health record
        old_health = ProviderHealthRecord(
            provider="yahoo",
            capability="prices",
            status="ok",
            checked_at=now - timedelta(days=45),
        )
        recent_health = ProviderHealthRecord(
            provider="yahoo",
            capability="prices",
            status="ok",
            checked_at=now - timedelta(hours=1),
        )
        session.add_all([old_health, recent_health])

        await session.commit()

        expired_share_id = expired_share.id
        active_share_id = active_share.id
        revoked_token_id = revoked_token.id
        valid_token_id = valid_token.id

    # Execute cleanup
    cleanup_counts = await run_operational_cleanup(db)
    assert cleanup_counts["expired_shares_deactivated"] >= 1
    assert cleanup_counts["revoked_tokens_purged"] >= 1
    assert cleanup_counts["stale_health_records_purged"] >= 1

    # Verify database state after cleanup
    async with db.session() as session:
        exp_s = await session.get(ShareLink, expired_share_id)
        assert exp_s is not None
        assert not exp_s.is_active  # Expired share is now deactivated

        act_s = await session.get(ShareLink, active_share_id)
        assert act_s is not None
        assert act_s.is_active  # Valid share remains active

        rev_t = await session.get(RefreshToken, revoked_token_id)
        assert rev_t is None  # Revoked token purged

        val_t = await session.get(RefreshToken, valid_token_id)
        assert val_t is not None  # Active token remains preserved
