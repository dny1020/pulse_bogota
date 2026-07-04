#!/usr/bin/env bash
# pulse backup — consistent PostgreSQL snapshot via pg_dump.
# pg_dump takes a consistent snapshot on its own, so the API keeps running.
set -euo pipefail

BACKUP_DIR="${PULSE_BACKUP_DIR:-/mnt/ssd/pulse_bogota/backups}"
KEEP="${PULSE_BACKUP_KEEP:-7}"
COMPOSE="${PULSE_COMPOSE:-/opt/pulse_bogota/compose.yaml}"

ts="$(date +%Y%m%d-%H%M%S)"
dest="$BACKUP_DIR/$ts"
mkdir -p "$dest"

docker compose -f "$COMPOSE" exec -T db pg_dump -U pulse -d pulse | gzip > "$dest/pulse.sql.gz"

echo "pulse backup -> $dest/pulse.sql.gz"

# Rotation: keep the last $KEEP snapshots.
ls -1dt "$BACKUP_DIR"/*/ 2>/dev/null | tail -n "+$((KEEP + 1))" | xargs -r rm -rf
