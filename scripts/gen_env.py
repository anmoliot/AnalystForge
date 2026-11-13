#!/usr/bin/env python
"""Generate a development .env with cryptographically random secrets.

Never overwrites an existing .env. Safe to run from any working directory.
"""

from __future__ import annotations

import base64
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / ".env.example"
TARGET = ROOT / ".env"


def main() -> int:
    if TARGET.exists():
        print(f".env already exists at {TARGET}; leaving it untouched.")
        return 0
    if not TEMPLATE.exists():
        print("Missing .env.example; cannot generate configuration.", file=sys.stderr)
        return 1

    content = TEMPLATE.read_text(encoding="utf-8")
    secret_key = secrets.token_hex(32)
    encryption_key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
    db_password = secrets.token_urlsafe(24)

    replacements = {
        "SECRET_KEY=\n": f"SECRET_KEY={secret_key}\n",
        "ENCRYPTION_KEY=\n": f"ENCRYPTION_KEY={encryption_key}\n",
        "POSTGRES_PASSWORD=CHANGE_ME\n": f"POSTGRES_PASSWORD={db_password}\n",
        "CHANGE_ME@localhost": f"{db_password}@localhost",
    }
    for old, new in replacements.items():
        content = content.replace(old, new)

    if "CHANGE_ME" in content:
        print("Template still contains CHANGE_ME placeholders.", file=sys.stderr)
        return 1

    TARGET.write_text(content, encoding="utf-8")
    print(f"Wrote {TARGET} with generated secrets (git-ignored).")
    print("Development database credentials are in POSTGRES_* and DATABASE_URL.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
