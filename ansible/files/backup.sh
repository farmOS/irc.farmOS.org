#!/usr/bin/env bash
#
# Weekly backup of the ircjournal PostgreSQL database.
# Invoked by cron. Keeps only the most recent 3 dumps.
#
set -euo pipefail

# Define constants.
CONTAINER="db"
DB="ircj"
USER="ircj"
BACKUP_DIR="/opt/irc.farmOS.org/backups"
KEEP=3

# Ensure the backup directory exists.
mkdir -p "$BACKUP_DIR"

# Wait for the database to become ready (up to 10 minutes).
for i in $(seq 20); do
  if docker exec "$CONTAINER" pg_isready -U "$USER" -d "$DB" >/dev/null; then
    break
  fi
  sleep 30
done

# Fail if the database is not ready.
docker exec "$CONTAINER" pg_isready -U "$USER" -d "$DB" >/dev/null

# Dump the database and compress it to a temporary file.
STAMP="$(date +%Y-%m-%d_%H-%M-%S)"
TMP="$BACKUP_DIR/.ircj-$STAMP.sql.gz.tmp"
trap 'rm -f "$TMP"' EXIT
docker exec "$CONTAINER" pg_dump -U "$USER" "$DB" | gzip > "$TMP"

# Move the dump into place.
mv "$TMP" "$BACKUP_DIR/ircj-$STAMP.sql.gz"

# Delete old backups, keeping only the newest $KEEP.
ls -1t "$BACKUP_DIR"/ircj-*.sql.gz | tail -n +$((KEEP + 1)) | xargs -r rm -f
