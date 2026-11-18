"""Verify the application's SMTP sender against a loopback Mailpit instance."""

import argparse
import asyncio
import json
import secrets
import uuid
from email import policy
from email.parser import BytesParser

import httpx

from analystforge.api.config import Settings
from analystforge.api.services.alerts import send_alert_email


async def verify(smtp_port: int, http_port: int) -> dict[str, object]:
    subject = "AnalystForge delivery verification " + uuid.uuid4().hex
    recipient = "verification@example.invalid"
    settings = Settings(
        _env_file=None,
        environment="test",
        secret_key=secrets.token_hex(32),
        database_url="sqlite+aiosqlite://",
        email_enabled=True,
        smtp_host="127.0.0.1",
        smtp_port=smtp_port,
        smtp_from="AnalystForge verification <sender@example.invalid>",
        smtp_user=None,
        smtp_password=None,
        smtp_tls=False,
    )
    await send_alert_email(
        settings,
        recipient,
        subject,
        "Local SMTP delivery verification.",
        html_content="<p>Local SMTP delivery verification.</p>",
        attachment=("verification.txt", b"AnalystForge attachment verification\n", "text/plain"),
    )
    async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{http_port}", timeout=10) as client:
        response = await client.get("/api/v1/messages")
        response.raise_for_status()
        matches = [item for item in response.json()["messages"] if item["Subject"] == subject]
        if len(matches) != 1:
            raise RuntimeError("Mailpit did not capture exactly one matching verification message.")
        response = await client.get(f"/api/v1/message/{matches[0]['ID']}/raw")
        response.raise_for_status()
        message = BytesParser(policy=policy.default).parsebytes(response.content)
    if message["To"] != recipient or message["Subject"] != subject:
        raise RuntimeError("Captured recipient or subject differs from the sent message.")
    plain = message.get_body(preferencelist=("plain",))
    html = message.get_body(preferencelist=("html",))
    attachments = list(message.iter_attachments())
    if plain is None or "Local SMTP delivery verification." not in plain.get_content():
        raise RuntimeError("Plain-text body was not delivered.")
    if html is None or "<p>Local SMTP delivery verification.</p>" not in html.get_content():
        raise RuntimeError("HTML body was not delivered.")
    if len(attachments) != 1 or attachments[0].get_filename() != "verification.txt":
        raise RuntimeError("Attachment metadata was not delivered.")
    if attachments[0].get_payload(decode=True) != b"AnalystForge attachment verification\n":
        raise RuntimeError("Attachment bytes differ from the sent payload.")
    return {
        "status": "passed",
        "smtp_port": smtp_port,
        "http_port": http_port,
        "plain_text": True,
        "html": True,
        "attachment": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smtp-port", type=int, default=11025)
    parser.add_argument("--http-port", type=int, default=18025)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(verify(args.smtp_port, args.http_port))))


if __name__ == "__main__":
    main()
