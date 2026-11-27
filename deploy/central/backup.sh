#!/usr/bin/env bash
# Daily backup of the central server (SITE_NETWORK_PLAN.md M8): the database, the promoted and earlier
# models, the site CA key and the internal CA key. Restore with deploy/central/restore.sh.
#
#   deploy/central/backup.sh                 into BACKUP_DIR (default deploy/central/backups)
#   cron:  23 2 * * *  /path/to/deploy/central/backup.sh >> /var/log/arqauquat-backup.log 2>&1
#
# The backup holds private CA keys. Set BACKUP_PASSPHRASE_FILE (a file with a long random passphrase,
# kept off this server too) to encrypt it with AES-256; copy backups to a second place you control.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
set -a; source "$HERE/.env"; set +a
DC=(docker compose -f "$HERE/docker-compose.yml")
PROJECT=arqauquat-central
DATA="$(cd "$HERE" && realpath -m "${CENTRAL_DATA:-./data}")"
ROOT="${BACKUP_DIR:-$HERE/backups}"
STAMP="$(date -u +%Y%m%dT%H%MZ)"
DEST="$ROOT/$STAMP"
mkdir -p "$DEST"
chmod 700 "$ROOT" "$DEST"

echo "database ..."
"${DC[@]}" exec -T db pg_dump -U fedwind -Fc fedwind > "$DEST/postgres.dump"

echo "models and CA keys ..."
docker run --rm \
  -v "${PROJECT}_site-ca:/backup/site-ca:ro" \
  -v "${PROJECT}_internal-ca:/backup/internal-ca:ro" \
  -v "$DATA/models:/backup/models:ro" \
  -v "$DEST:/out" alpine:3.20 tar czf /out/files.tar.gz -C /backup .

encrypted=false
if [[ -n "${BACKUP_PASSPHRASE_FILE:-}" ]]; then
  for f in postgres.dump files.tar.gz; do
    openssl enc -aes-256-cbc -pbkdf2 -salt -pass "file:$BACKUP_PASSPHRASE_FILE" -in "$DEST/$f" -out "$DEST/$f.enc"
    rm "$DEST/$f"
  done
  encrypted=true
else
  echo "WARNING: not encrypted (set BACKUP_PASSPHRASE_FILE); this backup contains private CA keys" >&2
fi
(cd "$DEST" && sha256sum ./* > SHA256SUMS)

size=$(du -sb "$DEST" | cut -f1)
printf '{"finished_at": "%s", "dest": "%s", "size_bytes": %s, "encrypted": %s}\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$DEST" "$size" "$encrypted" > "$DATA/backups-status.json"

# Keep BACKUP_KEEP_DAYS (14) days
find "$ROOT" -mindepth 1 -maxdepth 1 -type d -mtime "+${BACKUP_KEEP_DAYS:-14}" -exec rm -rf {} +
echo "backup done: $DEST ($((size / 1000000)) MB)"
