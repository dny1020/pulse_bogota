#!/usr/bin/env bash
# pulse backup — snapshot consistente de la base SQLite.
# Para la app momentáneamente para copiar la DB sin riesgo de corrupción.
set -euo pipefail

BACKUP_DIR="${PULSE_BACKUP_DIR:-/mnt/ssd/pulse-backups}"
KEEP="${PULSE_BACKUP_KEEP:-7}"
COMPOSE="${PULSE_COMPOSE:-/opt/pulse/compose.yaml}"

ts="$(date +%Y%m%d-%H%M%S)"
dest="$BACKUP_DIR/$ts"
mkdir -p "$dest"

# Parar la app para un snapshot consistente, copiar, reiniciar.
docker compose -f "$COMPOSE" stop api

container_id=$(docker compose -f "$COMPOSE" ps -q api)
docker cp "$container_id:/data/pulse_bogota.db" "$dest/pulse_bogota.db"

docker compose -f "$COMPOSE" start api

echo "pulse backup -> $dest/pulse_bogota.db"

# Rotación: conservar los últimos $KEEP snapshots.
ls -1dt "$BACKUP_DIR"/*/ 2>/dev/null | tail -n "+$((KEEP + 1))" | xargs -r rm -rf
