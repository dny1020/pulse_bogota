#!/usr/bin/env bash
# pulse restore — restaura un snapshot creado por backup.sh.
#   uso: restore.sh <dir-de-backup>   (p.ej. /mnt/ssd/pulse-backups/20260618-033000)
set -euo pipefail

SRC="${1:?uso: restore.sh <dir-de-backup>}"
COMPOSE="${PULSE_COMPOSE:-/opt/pulse/compose.yaml}"

[ -f "$SRC/pulse_bogota.db" ] || { echo "no se encontró $SRC/pulse_bogota.db" >&2; exit 1; }

echo "Esto SOBRESCRIBE la base de datos con el backup de $SRC."
read -r -p "¿Continuar? [y/N] " ans
case "$ans" in y|Y) ;; *) echo "cancelado"; exit 1 ;; esac

# Parar la app para que nadie escriba durante la restauración.
docker compose -f "$COMPOSE" stop api

container_id=$(docker compose -f "$COMPOSE" ps -q api)
docker cp "$SRC/pulse_bogota.db" "$container_id:/data/pulse_bogota.db"

docker compose -f "$COMPOSE" start api
echo "restaurado desde $SRC"
