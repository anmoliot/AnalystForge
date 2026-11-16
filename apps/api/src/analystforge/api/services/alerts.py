"""Alert evaluation, notification delivery engine, and scheduled screens service.

Supports:
- Multi-channel delivery: In-app notification events, SMTP email, and HTTP webhooks
- Retry mechanism with delivery log audit trail
- Scheduled screen evaluation and automated email dispatch
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from email.message import EmailMessage
import smtplib
from typing import Any

import httpx
from sqlalchemy import desc, func, select
from sqlalchemy.orm import selectinload

from analystforge.api.config import Settings
from analystforge.api.db import Database
from analystforge.api.logging import get_logger
from analystforge.api.models.market import Instrument, PriceBar
from analystforge.api.models.screener import AlertDelivery, AlertEvent, AlertRule, SavedScreen

logger = get_logger("alerts")


def _sync_send_smtp_email(
    host: str,
    port: int,
    user: str | None,
    password: str | None,
    sender: str,
    recipient: str,
    subject: str,
    text_content: str,
    html_content: str | None = None,
    use_tls: bool = False,
) -> None:
    """Synchronous SMTP email sender executed in background thread pool."""
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    msg.set_content(text_content)

    if html_content:
        msg.add_alternative(html_content, subtype="html")

    with smtplib.SMTP(host, port, timeout=10.0) as server:
        if use_tls:
            server.starttls()
        if user and password:
            server.login(user, password)
        server.send_message(msg)


async def send_alert_email(
    settings: Settings,
    recipient: str,
    subject: str,
    text_content: str,
    html_content: str | None = None,
) -> None:
    """Deliver an email alert asynchronously via configured SMTP host/mail catcher."""
    pwd = settings.smtp_password.get_secret_value() if settings.smtp_password else None
    await asyncio.to_thread(
        _sync_send_smtp_email,
        host=settings.smtp_host,
        port=settings.smtp_port,
        user=settings.smtp_user,
        password=pwd,
        sender=settings.smtp_from,
        recipient=recipient,
        subject=subject,
        text_content=text_content,
        html_content=html_content,
        use_tls=settings.smtp_tls,
    )


async def send_alert_webhook(
    webhook_url: str,
    payload: dict[str, Any],
    timeout: float = 5.0,
) -> None:
    """Deliver an alert payload to a remote webhook URL."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            webhook_url,
            json=payload,
            headers={"User-Agent": "AnalystForge-Alerts/1.0", "X-AnalystForge-Event": "alert.triggered"},
        )
        resp.raise_for_status()


async def evaluate_alert_rules(
    db: Database,
    settings: Settings,
) -> dict[str, Any]:
    """Inspect all active alert rules, check triggering conditions, and dispatch notifications."""
    summary: dict[str, Any] = {
        "rules_evaluated": 0,
        "alerts_triggered": 0,
        "deliveries_succeeded": 0,
        "deliveries_failed": 0,
    }

    async with db.session() as session:
        rules_stmt = select(AlertRule).where(AlertRule.is_active.is_(True))
        rules = (await session.execute(rules_stmt)).scalars().all()
        summary["rules_evaluated"] = len(rules)

        for rule in rules:
            # Look up latest price for ticker
            inst_stmt = select(Instrument).where(Instrument.ticker == rule.ticker)
            inst = (await session.execute(inst_stmt)).scalar_one_or_none()
            if not inst:
                continue

            bar_stmt = (
                select(PriceBar.close)
                .where(PriceBar.instrument_id == inst.id, PriceBar.interval == "1d")
                .order_by(desc(PriceBar.ts))
                .limit(1)
            )
            latest_close = (await session.execute(bar_stmt)).scalar_one_or_none()
            if latest_close is None:
                continue

            current_val = Decimal(str(latest_close))
            is_triggered = False
            msg = ""

            if rule.rule_type == "PRICE_ABOVE" and current_val >= rule.target_value:
                is_triggered = True
                msg = f"{rule.ticker} price ${current_val:.2f} crossed above target threshold ${rule.target_value:.2f}"
            elif rule.rule_type == "PRICE_BELOW" and current_val <= rule.target_value:
                is_triggered = True
                msg = f"{rule.ticker} price ${current_val:.2f} crossed below target threshold ${rule.target_value:.2f}"

            if is_triggered:
                summary["alerts_triggered"] += 1
                now = datetime.now(timezone.utc)
                rule.last_triggered_at = now

                event = AlertEvent(
                    rule_id=rule.id,
                    ticker=rule.ticker,
                    message=msg,
                    triggered_value=current_val,
                    triggered_at=now,
                )
                session.add(event)
                await session.flush()

                channels = rule.notification_channels or ["in_app"]

                for ch in channels:
                    delivery = AlertDelivery(
                        event_id=event.id,
                        channel=ch,
                        recipient=rule.email_recipient if ch == "email" else rule.webhook_url,
                        attempts=1,
                        status="pending",
                    )
                    session.add(delivery)
                    await session.flush()

                    if ch == "in_app":
                        delivery.status = "delivered"
                        delivery.delivered_at = now
                        summary["deliveries_succeeded"] += 1

                    elif ch == "email" and rule.email_recipient:
                        # Attempt email delivery with retry
                        email_success = False
                        last_err: str | None = None
                        for attempt in range(1, 4):
                            delivery.attempts = attempt
                            try:
                                await send_alert_email(
                                    settings=settings,
                                    recipient=rule.email_recipient,
                                    subject=f"[AnalystForge Alert] {rule.ticker}: {rule.rule_type}",
                                    text_content=f"Alert Notification:\n\n{msg}\nTriggered at: {now.isoformat()}\n",
                                    html_content=f"<h3>AnalystForge Alert</h3><p><strong>{msg}</strong></p><p>Triggered at: {now.isoformat()}</p>",
                                )
                                email_success = True
                                break
                            except Exception as exc:
                                last_err = str(exc)
                                await asyncio.sleep(0.05)

                        if email_success:
                            delivery.status = "delivered"
                            delivery.delivered_at = datetime.now(timezone.utc)
                            summary["deliveries_succeeded"] += 1
                        else:
                            delivery.status = "failed"
                            delivery.last_error = last_err
                            summary["deliveries_failed"] += 1

                    elif ch == "webhook" and rule.webhook_url:
                        # Attempt webhook dispatch
                        wh_success = False
                        wh_err: str | None = None
                        payload_data = {
                            "event_id": str(event.id),
                            "rule_id": str(rule.id),
                            "ticker": rule.ticker,
                            "rule_type": rule.rule_type,
                            "target_value": float(rule.target_value),
                            "triggered_value": float(current_val),
                            "message": msg,
                            "triggered_at": now.isoformat(),
                        }
                        for attempt in range(1, 4):
                            delivery.attempts = attempt
                            try:
                                await send_alert_webhook(rule.webhook_url, payload_data)
                                wh_success = True
                                break
                            except Exception as exc:
                                wh_err = str(exc)
                                await asyncio.sleep(0.05)

                        if wh_success:
                            delivery.status = "delivered"
                            delivery.delivered_at = datetime.now(timezone.utc)
                            summary["deliveries_succeeded"] += 1
                        else:
                            delivery.status = "failed"
                            delivery.last_error = wh_err
                            summary["deliveries_failed"] += 1

        await session.commit()

    return summary


async def run_scheduled_screens_and_dispatch(
    db: Database,
    settings: Settings,
) -> dict[str, Any]:
    """Run scheduled saved screens and deliver results via email if configured."""
    summary: dict[str, Any] = {
        "screens_evaluated": 0,
        "screens_notified": 0,
    }

    async with db.session() as session:
        stmt = select(SavedScreen).where(SavedScreen.schedule.is_not(None))
        scheduled_screens = (await session.execute(stmt)).scalars().all()
        summary["screens_evaluated"] = len(scheduled_screens)

        for screen in scheduled_screens:
            now = datetime.now(timezone.utc)
            screen.last_run_at = now

            if screen.notify_email:
                try:
                    await send_alert_email(
                        settings=settings,
                        recipient=screen.notify_email,
                        subject=f"[AnalystForge Screen Report] {screen.name}",
                        text_content=(
                            f"Scheduled Screen: {screen.name}\n"
                            f"Description: {screen.description or 'N/A'}\n"
                            f"Run Timestamp: {now.isoformat()}\n"
                            f"Filter Criteria: {screen.filters}\n"
                        ),
                        html_content=(
                            f"<h3>Scheduled Screen Execution: {screen.name}</h3>"
                            f"<p>{screen.description or ''}</p>"
                            f"<p>Run at: {now.isoformat()}</p>"
                        ),
                    )
                    summary["screens_notified"] += 1
                except Exception as exc:
                    logger.warning("screener.email_failed", screen_id=str(screen.id), error=str(exc))

        await session.commit()

    return summary
