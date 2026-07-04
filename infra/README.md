# Deploy en la Raspberry Pi (pull-based desde GHCR)

GitHub Actions construye y publica `ghcr.io/dny1020/pulse_bogota` en cada push a `main`.
La Pi hace pull cada 5 minutos vía systemd timer — sin puertos expuestos, sin runners.

## Setup (una sola vez)

```bash
# 1. copiar artefactos
scp infra/compose.yaml infra/deploy.sh rpi:/opt/pulse_bogota/
scp infra/pulse-deploy.* rpi:/tmp/

ssh rpi
chmod +x /opt/pulse_bogota/deploy.sh
# /opt/pulse_bogota/.env debe tener:
#   POSTGRES_PASSWORD=...   (obligatorio — genera uno: openssl rand -hex 24)
#   TOMTOM_API_KEY=..., etc. según los collectors que quieras activar

# 2. instalar el timer
sudo mv /tmp/pulse-deploy.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now pulse-deploy.timer

# 3. primer deploy + verificación
sudo systemctl start pulse-deploy.service
journalctl -u pulse-deploy -n 20
```

## Operación

```bash
systemctl list-timers pulse-deploy.timer   # próxima ejecución
journalctl -u pulse-deploy -f              # logs de deploys
sudo systemctl start pulse-deploy.service  # forzar deploy ahora
docker logs pulse                           # logs de la app
```

## Rollback

```bash
# pin a una versión anterior publicada en GHCR
sed -i 's|pulse_bogota:latest|pulse_bogota:0.7|' /opt/pulse_bogota/compose.yaml
sudo systemctl start pulse-deploy.service
# (revertir el pin después de arreglar main)
```

## Backups

El estado vive en el SSD de la Pi: PostgreSQL en `/mnt/ssd/pulse_bogota/postgres`
(bind mount de `compose.yaml`). `backup.sh`
hace un `pg_dump` comprimido sin parar la API (pg_dump toma un snapshot
consistente por sí solo). Conserva los últimos `PULSE_BACKUP_KEEP` snapshots
(7 por defecto).

```bash
# setup (una sola vez)
scp infra/backup.sh infra/restore.sh rpi:/opt/pulse_bogota/
scp infra/pulse-backup.* rpi:/tmp/
ssh rpi
chmod +x /opt/pulse_bogota/backup.sh /opt/pulse_bogota/restore.sh
sudo mv /tmp/pulse-backup.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now pulse-backup.timer   # diario 03:30

# a mano
sudo /opt/pulse_bogota/backup.sh                        # snapshot ahora
ls /mnt/ssd/pulse_bogota/backups                         # snapshots disponibles
```

Variables: `PULSE_BACKUP_DIR` (def. `/mnt/ssd/pulse_bogota/backups`), `PULSE_BACKUP_KEEP`
(def. `7`), `PULSE_COMPOSE` (def. `/opt/pulse_bogota/compose.yaml`).

## Restore

```bash
# para la API, limpia el esquema, restaura el dump y la vuelve a levantar
# (pide confirmación)
sudo /opt/pulse_bogota/restore.sh /mnt/ssd/pulse_bogota/backups/20260618-033000
```

## Logs

La app escribe a stdout y a `/mnt/ssd/pulse_bogota/logs/pulse_bogota.log`
(bind mount; sobrevive reinicios del contenedor). También: `docker logs pulse`.
