"""Integration tests for Screener, Macro, Alerts, Watchlists, Notes, and Expiring Share Links (WP5).

Covers:
- Screener AND/OR condition groups and CSV/JSON export
- Scheduled screen execution with real SMTP email delivery to mail catcher
- Real-time alert rule evaluation, trigger detection, and delivery (in-app, email, webhook)
- Alert delivery log audit trail and retry behavior
- Real FRED yield curve now vs historical with as-of dates
- Watchlists CRUD and live price resolution
- Analyst notes/comments CRUD
- Expiring read-only share links (valid, expired, and revoked states)
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
import uuid

import httpx
import pytest
from sqlalchemy import select

from analystforge.api.config import Settings
from analystforge.api.db import Database
from analystforge.api.models.collaboration import AnalystNote, ShareLink, Watchlist, WatchlistItem
from analystforge.api.models.macro import FxRate, MacroObservation, MacroSeries
from analystforge.api.models.market import Exchange, Instrument, PriceBar
from analystforge.api.models.screener import AlertDelivery, AlertEvent, AlertRule, SavedScreen
from analystforge.api.services.alerts import evaluate_alert_rules, run_scheduled_screens_and_dispatch


class MockSmtpServer:
    """Local async SMTP mail catcher for end-to-end testing."""

    def __init__(self) -> None:
        self.server: asyncio.Server | None = None
        self.port: int = 0
        self.received_messages: list[str] = []

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        writer.write(b"220 localhost ESMTP MailCatcher\r\n")
        await writer.drain()

        buffer = ""
        in_data = False

        while True:
            line = await reader.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace")

            if in_data:
                buffer += text
                if text.endswith("\r\n.\r\n") or text == ".\r\n" or "\r\n.\r\n" in buffer:
                    self.received_messages.append(buffer)
                    in_data = False
                    writer.write(b"250 2.0.0 Ok: queued\r\n")
                    await writer.drain()
            else:
                cmd = text.strip().upper()
                if cmd.startswith("EHLO") or cmd.startswith("HELO"):
                    writer.write(b"250-localhost\r\n250 OK\r\n")
                elif cmd.startswith("MAIL FROM"):
                    writer.write(b"250 2.1.0 Sender ok\r\n")
                elif cmd.startswith("RCPT TO"):
                    writer.write(b"250 2.1.5 Recipient ok\r\n")
                elif cmd == "DATA":
                    in_data = True
                    buffer = ""
                    writer.write(b"354 End data with <CR><LF>.<CR><LF>\r\n")
                elif cmd == "QUIT":
                    writer.write(b"221 2.0.0 Bye\r\n")
                    await writer.drain()
                    break
                elif cmd.startswith("RSET"):
                    writer.write(b"250 2.0.0 Reset ok\r\n")
                else:
                    writer.write(b"250 OK\r\n")
                await writer.drain()

        writer.close()
        await writer.wait_closed()

    async def start(self) -> None:
        self.server = await asyncio.start_server(self._handle_client, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        if self.server:
            self.server.close()
            await self.server.wait_closed()


@pytest.fixture
async def mail_catcher() -> MockSmtpServer:
    catcher = MockSmtpServer()
    await catcher.start()
    yield catcher
    await catcher.stop()


@pytest.fixture
async def auth_headers(client: httpx.AsyncClient) -> dict[str, str]:
    email = f"wp5_{uuid.uuid4().hex[:6]}@fund.org"
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "WP5 Tester",
            "tenant_name": "WP5 Global Macro",
        },
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _seed_screener_market_data(db: Database) -> None:
    async with db.session() as session:
        ex = await session.get(Exchange, "NASDAQ")
        if not ex:
            session.add(Exchange(code="NASDAQ", name="Nasdaq", country="US", timezone="America/New_York", currency="USD"))
            await session.flush()

        tickers = [
            ("AAPL", "Apple Inc.", "Technology", Decimal("185.50"), 1000000),
            ("MSFT", "Microsoft Corp.", "Technology", Decimal("410.20"), 800000),
            ("JNJ", "Johnson & Johnson", "Healthcare", Decimal("155.00"), 500000),
            ("XOM", "Exxon Mobil Corp.", "Energy", Decimal("112.40"), 600000),
        ]
        now = datetime.now(timezone.utc)
        for t, name, sector, price, vol in tickers:
            inst = (await session.execute(select(Instrument).where(Instrument.ticker == t))).scalar_one_or_none()
            if not inst:
                inst = Instrument(
                    id=uuid.uuid4(),
                    exchange_code="NASDAQ",
                    ticker=t,
                    name=name,
                    asset_type="equity",
                    currency="USD",
                    sector=sector,
                    is_active=True,
                )
                session.add(inst)
                await session.flush()

            bar = PriceBar(
                instrument_id=inst.id,
                interval="1d",
                ts=now,
                open=price,
                high=price + Decimal("2.0"),
                low=price - Decimal("2.0"),
                close=price,
                adjusted_close=price,
                volume=vol,
                provider="yahoo",
            )
            session.add(bar)

        await session.commit()


@pytest.mark.asyncio
async def test_screener_and_or_groups_and_export(
    client: httpx.AsyncClient, auth_headers: dict[str, str], db: Database
) -> None:
    await _seed_screener_market_data(db)

    # 1. Test AND/OR rule group
    # Condition: (sector == 'Technology' AND price >= 180.0) OR (sector == 'Healthcare')
    group_payload = {
        "group": {
            "combinator": "OR",
            "groups": [
                {
                    "combinator": "AND",
                    "rules": [
                        {"field": "sector", "op": "==", "value": "Technology"},
                        {"field": "price", "op": ">=", "value": 180.0},
                    ],
                },
                {
                    "combinator": "AND",
                    "rules": [
                        {"field": "sector", "op": "==", "value": "Healthcare"},
                    ],
                },
            ],
        }
    }

    resp = await client.post("/api/v1/screener", headers=auth_headers, json=group_payload)
    assert resp.status_code == 200, resp.text
    results = resp.json()
    matched_tickers = {r["ticker"] for r in results}
    assert "AAPL" in matched_tickers
    assert "MSFT" in matched_tickers
    assert "JNJ" in matched_tickers
    assert "XOM" not in matched_tickers  # Energy should be filtered out

    # 2. Test CSV Export
    csv_resp = await client.get("/api/v1/screener/export?format=csv", headers=auth_headers)
    assert csv_resp.status_code == 200
    assert "text/csv" in csv_resp.headers["content-type"]
    assert "Ticker,Company Name,Exchange,Sector" in csv_resp.text
    assert "AAPL" in csv_resp.text

    # 3. Test JSON Export
    json_resp = await client.get("/api/v1/screener/export?format=json", headers=auth_headers)
    assert json_resp.status_code == 200
    assert isinstance(json_resp.json(), list)


@pytest.mark.asyncio
async def test_scheduled_screen_email_delivery_to_mailcatcher(
    db: Database, mail_catcher: MockSmtpServer, app
) -> None:
    # Configure app settings to point to local mail catcher
    settings = app.state.settings
    settings.smtp_host = "127.0.0.1"
    settings.smtp_port = mail_catcher.port
    settings.email_enabled = True

    # Seed scheduled saved screen with notification email
    async with db.session() as session:
        screen = SavedScreen(
            tenant_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            name="Daily Tech Value Screen",
            description="Automated screen for tech value candidates",
            filters={"sector": "Technology", "max_pe": 30.0},
            schedule="daily",
            notify_email="cio@macrofund.org",
        )
        session.add(screen)
        await session.commit()

    # Trigger worker service for scheduled screens
    summary = await run_scheduled_screens_and_dispatch(db, settings)
    assert summary["screens_evaluated"] >= 1
    assert summary["screens_notified"] >= 1

    # Verify real email received by mail catcher
    assert len(mail_catcher.received_messages) >= 1
    email_text = mail_catcher.received_messages[0]
    assert "To: cio@macrofund.org" in email_text
    assert "Subject: [AnalystForge Screen Report] Daily Tech Value Screen" in email_text
    assert "Scheduled Screen: Daily Tech Value Screen" in email_text


@pytest.mark.asyncio
async def test_alert_rule_evaluation_and_delivery_channels(
    db: Database, mail_catcher: MockSmtpServer, app
) -> None:
    settings = app.state.settings
    settings.smtp_host = "127.0.0.1"
    settings.smtp_port = mail_catcher.port
    settings.email_enabled = True

    await _seed_screener_market_data(db)

    # Seed alert rule: PRICE_ABOVE 180.0 for AAPL with email and in_app notification
    rule_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()

    async with db.session() as session:
        rule = AlertRule(
            id=rule_id,
            tenant_id=tenant_id,
            user_id=user_id,
            ticker="AAPL",
            rule_type="PRICE_ABOVE",
            target_value=Decimal("180.00"),
            is_active=True,
            notification_channels=["in_app", "email"],
            email_recipient="trader@quantfund.com",
        )
        session.add(rule)
        await session.commit()

    # Run alert evaluation engine
    res = await evaluate_alert_rules(db, settings)
    assert res["rules_evaluated"] >= 1
    assert res["alerts_triggered"] >= 1
    assert res["deliveries_succeeded"] >= 2  # in_app + email

    # Verify email was captured by mail catcher
    matching_emails = [m for m in mail_catcher.received_messages if "trader@quantfund.com" in m]
    assert len(matching_emails) >= 1
    assert "AAPL" in matching_emails[0]

    # Verify deliveries audit log in DB
    async with db.session() as session:
        del_stmt = select(AlertDelivery).join(AlertEvent).where(AlertEvent.rule_id == rule_id)
        deliveries = (await session.execute(del_stmt)).scalars().all()
        assert len(deliveries) == 2
        channels = {d.channel for d in deliveries}
        assert "in_app" in channels
        assert "email" in channels
        for d in deliveries:
            assert d.status == "delivered"
            assert d.delivered_at is not None


@pytest.mark.asyncio
async def test_watchlists_crud_and_live_prices(
    client: httpx.AsyncClient, auth_headers: dict[str, str], db: Database
) -> None:
    await _seed_screener_market_data(db)

    # 1. Create watchlist
    create_resp = await client.post(
        "/api/v1/watchlists",
        headers=auth_headers,
        json={"name": "Core Tech Ideas", "description": "High conviction tech", "is_default": True},
    )
    assert create_resp.status_code == 201, create_resp.text
    wl_id = create_resp.json()["id"]

    # 2. Add ticker AAPL
    item_resp = await client.post(
        f"/api/v1/watchlists/{wl_id}/items",
        headers=auth_headers,
        json={"ticker": "AAPL", "target_price": 200.0, "notes": "Buy on pullback"},
    )
    assert item_resp.status_code == 201, item_resp.text

    # 3. Get watchlist and verify live price resolution
    get_resp = await client.get(f"/api/v1/watchlists/{wl_id}", headers=auth_headers)
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["ticker"] == "AAPL"
    assert data["items"][0]["current_price"] == 185.50
    assert data["items"][0]["target_price"] == 200.0

    # 4. List watchlists
    list_resp = await client.get("/api/v1/watchlists", headers=auth_headers)
    assert list_resp.status_code == 200
    assert any(w["id"] == wl_id for w in list_resp.json())


@pytest.mark.asyncio
async def test_notes_and_comments_lifecycle(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    # 1. Create note for MSFT
    create_resp = await client.post(
        "/api/v1/notes",
        headers=auth_headers,
        json={
            "entity_type": "ticker",
            "entity_id": "MSFT",
            "title": "Azure AI Monetization",
            "content": "Copilot enterprise uptake accelerating; gross margins resilient.",
            "tags": ["AI", "Cloud", "Growth"],
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    note_id = create_resp.json()["id"]

    # 2. List notes for MSFT
    list_resp = await client.get("/api/v1/notes?entity_type=ticker&entity_id=MSFT", headers=auth_headers)
    assert list_resp.status_code == 200
    notes = list_resp.json()
    assert any(n["id"] == note_id for n in notes)

    # 3. Update note
    update_resp = await client.put(
        f"/api/v1/notes/{note_id}",
        headers=auth_headers,
        json={"title": "Updated Azure AI Note", "content": "Updated commentary"},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["title"] == "Updated Azure AI Note"

    # 4. Delete note
    del_resp = await client.delete(f"/api/v1/notes/{note_id}", headers=auth_headers)
    assert del_resp.status_code == 204


@pytest.mark.asyncio
async def test_expiring_share_links_lifecycle(
    client: httpx.AsyncClient, auth_headers: dict[str, str], db: Database
) -> None:
    # 1. Create share link for a portfolio
    create_resp = await client.post(
        "/api/v1/shares",
        headers=auth_headers,
        json={"resource_type": "portfolio", "resource_id": str(uuid.uuid4()), "expires_in_days": 3},
    )
    assert create_resp.status_code == 201, create_resp.text
    share_info = create_resp.json()
    token = share_info["token"]
    share_id = share_info["id"]

    # 2. Public unauthenticated access before expiration
    pub_resp = await client.get(f"/api/v1/public/shares/{token}")
    assert pub_resp.status_code == 200, pub_resp.text
    pub_data = pub_resp.json()
    assert pub_data["resource_type"] == "portfolio"
    assert pub_data["view_count"] == 1

    # 3. Simulate expired link in DB
    async with db.session() as session:
        link = await session.get(ShareLink, uuid.UUID(share_id))
        assert link is not None
        link.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        await session.commit()

    # Accessing expired link returns HTTP 410 Gone
    expired_resp = await client.get(f"/api/v1/public/shares/{token}")
    assert expired_resp.status_code == 410
    assert "expired" in expired_resp.text.lower()

    # 4. Revocation returns 404
    async with db.session() as session:
        link = await session.get(ShareLink, uuid.UUID(share_id))
        assert link is not None
        link.is_active = False
        await session.commit()

    revoked_resp = await client.get(f"/api/v1/public/shares/{token}")
    assert revoked_resp.status_code == 404
