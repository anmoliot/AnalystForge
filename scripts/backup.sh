#!/usr/bin/env sh
# Dump the running PostgreSQL database to var/backups with a checksum.
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ ! -f .env ]; then
  echo "Missing .env; run 'make env' first." >&2
  exit 1
fi

# shellcheck disable=SC1091
set -a
. ./.env
set +a

BACKUP_DIR="$ROOT/var/backups"
mkdir -p "$BACKUP_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
FILE="$BACKUP_DIR/analystforge-$STAMP.sql.gz"

docker compose exec -T postgres pg_dump \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  --format=plain --no-owner --no-privileges | gzip -9 > "$FILE"

sha256sum "$FILE" > "$FILE.sha256"
echo "Backup written: $FILE"
echo "Checksum: $(cat "$FILE.sha256")"
