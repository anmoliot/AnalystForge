#!/usr/bin/env sh
# Restore a gzipped plain SQL dump produced by scripts/backup.sh.
# Usage: ./scripts/restore.sh var/backups/analystforge-....sql.gz
# Requires explicit CONFIRM_RESTORE=yes to avoid accidental data loss.
set -eu

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 <backup.sql.gz>" >&2
  exit 2
fi

FILE="$1"
if [ ! -f "$FILE" ]; then
  echo "Backup not found: $FILE" >&2
  exit 1
fi

if [ "${CONFIRM_RESTORE:-}" != "yes" ]; then
  echo "Refusing to overwrite the database. Re-run with CONFIRM_RESTORE=yes." >&2
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# shellcheck disable=SC1091
set -a
. ./.env
set +a

if [ -f "$FILE.sha256" ]; then
  sha256sum -c "$FILE.sha256"
fi

echo "Restoring $FILE into database $POSTGRES_DB ..."
gzip -dc "$FILE" | docker compose exec -T postgres psql \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  --set ON_ERROR_STOP=on
echo "Restore complete. Run readiness checks before serving traffic."
