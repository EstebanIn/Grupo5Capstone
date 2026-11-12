#!/usr/bin/env bash
set -euo pipefail
umask 077
: "${EDUGESTOR_ROOT:?Directorio absoluto de Edugestor}"
: "${RESTIC_REPOSITORY:?Repositorio remoto configurado}"
: "${RESTIC_PASSWORD_FILE:?Archivo privado con la contraseña restic}"
case "$RESTIC_REPOSITORY" in s3:https://*.compat.objectstorage.*.oraclecloud.com/*) ;; *) echo 'Se requiere el bucket OCI autorizado fuera de la VM.' >&2; exit 1;; esac
cd "$EDUGESTOR_ROOT"
exec 9>/run/lock/edugestor-backup.lock
flock -n 9 || exit 0
stage=$(mktemp -d /var/tmp/edugestor-backup.XXXXXXXX)
cleanup() { case "$stage" in /var/tmp/edugestor-backup.*) rm -rf -- "$stage";; esac; }
trap cleanup EXIT
compose=(docker compose --env-file deploy/.env.production -f deploy/compose.production.yml)
"${compose[@]}" exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$stage/database.dump"
"${compose[@]}" exec -T web tar -C /state -cf - credentials > "$stage/credentials.tar"
"${compose[@]}" exec -T web tar -C /app/knowledge -cf - procesados > "$stage/indices.tar"
cp deploy/.env.production "$stage/environment.env"
git rev-parse HEAD > "$stage/commit.txt"
# Margen conservador frente al cupo de 20 GB compartido de OCI. Comprobar
# también uso ajeno y peticiones en la consola: restic no ve otros buckets.
restic stats --mode raw-data --json > "$stage/stats.json"
python3 - "$stage" <<'PY'
import json, pathlib, sys
p=pathlib.Path(sys.argv[1]); used=json.loads((p/'stats.json').read_text())['total_size']
incoming=sum(f.stat().st_size for f in p.iterdir())
if used+incoming > 9_000_000_000:
    raise SystemExit('Respaldo detenido: supera el límite local conservador de 9 GB.')
PY
restic backup "$stage" --tag edugestor --host edugestor-demo --exclude stats.json
restic forget --tag edugestor --keep-daily 7 --keep-weekly 4 --prune
restic check
