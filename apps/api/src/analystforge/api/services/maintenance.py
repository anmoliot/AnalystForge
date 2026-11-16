"""Database and operational maintenance tasks for AnalystForge."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select, update

from analystforge.api.db import Database
from analystforge.api.logging import get_logger
from analystforge.api.models.collaboration import ShareLink
from analystforge.api.models.core import RefreshToken
from analystforge.api.models.ops import ProviderHealthRecord

logger = get_logger("maintenance")


async def run_operational_cleanup(db: Database) -> dict[str, int]:
    """Purges expired tokens, deactivates expired share links, and rotates stale health logs."""
    now = datetime.now(UTC)
    results = {
        "expired_shares_deactivated": 0,
        "revoked_tokens_purged": 0,
        "stale_health_records_purged": 0,
    }

    async with db.session() as session:
        # 1. Deactivate expired share links
        stmt_shares = (
            update(ShareLink)
            .where(ShareLink.is_active.is_(True), ShareLink.expires_at < now)
            .values(is_active=False)
        )
        share_res = await session.execute(stmt_shares)
        results["expired_shares_deactivated"] = share_res.rowcount or 0

        # 2. Purge expired or revoked refresh tokens older than 7 days past expiry
        token_cutoff = now - timedelta(days=7)
        stmt_tokens = delete(RefreshToken).where(
            (RefreshToken.expires_at < token_cutoff) | (RefreshToken.is_revoked.is_(True))
        )
        token_res = await session.execute(stmt_tokens)
        results["revoked_tokens_purged"] = token_res.rowcount or 0

        # 3. Clean up provider health records older than 30 days
        health_cutoff = now - timedelta(days=30)
        stmt_health = delete(ProviderHealthRecord).where(
            ProviderHealthRecord.checked_at < health_cutoff
        )
        health_res = await session.execute(stmt_health)
        results["stale_health_records_purged"] = health_res.rowcount or 0

        await session.commit()

    logger.info(
        "maintenance.cleanup_completed",
        **results,
    )
    return results
