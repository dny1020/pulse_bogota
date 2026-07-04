#!/usr/bin/env bash
# pulse restore — restore a snapshot created by backup.sh.
#   usage: restore.sh <backup-dir>   (e.g. /mnt/ssd/pulse_bogota/backups/20260618-033000)
set -euo pipefail

SRC="${1:?usage: restore.sh <backup-dir>}"
COMPOSE="${PULSE_COMPOSE:-/opt/pulse_bogota/compose.yaml}"

[ -f "$SRC/pulse.sql.gz" ] || { echo "no $SRC/pulse.sql.gz found" >&2; exit 1; }

echo "This OVERWRITES the database with the backup from $SRC."
read -r -p "Continue? [y/N] " ans
case "$ans" in y|Y) ;; *) echo "cancelled"; exit 1 ;; esac

# Stop the API so nothing writes during the restore.
docker compose -f "$COMPOSE" stop api

# Wipe the current schema, then replay the dump.
docker compose -f "$COMPOSE" exec -T db psql -U pulse -d pulse \
    -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
gunzip -c "$SRC/pulse.sql.gz" | docker compose -f "$COMPOSE" exec -T db psql -U pulse -d pulse

docker compose -f "$COMPOSE" start api
echo "restored from $SRC"
