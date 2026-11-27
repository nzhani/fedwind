#!/usr/bin/env bash
# Restore a backup made by backup.sh (SITE_NETWORK_PLAN.md M8). Replaces the database, the models and
# both CA keys with the backup's. Test it once per semester on a spare machine.
#
#   deploy/central/restore.sh deploy/central/backups/20261201T0223Z
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$(realpath "${1:?usage: restore.sh <backup folder>}")"
set -a; source "$HERE/.env"; set +a
DC=(docker compose -f "$HERE/docker-compose.yml")
PROJECT=arqauquat-central
DATA="$(cd "$HERE" && realpath -m "${CENTRAL_DATA:-./data}")"

(cd "$SRC" && sha256sum -c SHA256SUMS)
read -r -p "This replaces the live database, models and CA keys with $SRC. Type 'restore' to go on: " answer
[[ "$answer" == "restore" ]] || { echo "Nothing changed."; exit 1; }

WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
for f in postgres.dump files.tar.gz; do
  if [[ -f "$SRC/$f.enc" ]]; then
    : "${BACKUP_PASSPHRASE_FILE:?the backup is encrypted: set BACKUP_PASSPHRASE_FILE}"
    openssl enc -d -aes-256-cbc -pbkdf2 -pass "file:$BACKUP_PASSPHRASE_FILE" -in "$SRC/$f.enc" -out "$WORK/$f"
  else
    cp "$SRC/$f" "$WORK/$f"
  fi
done

"${DC[@]}" stop gateway web api
"${DC[@]}" up -d db
"${DC[@]}" exec -T db pg_restore -U fedwind -d fedwind --clean --if-exists < "$WORK/postgres.dump"
docker run --rm \
  -v "${PROJECT}_site-ca:/backup/site-ca" \
  -v "${PROJECT}_internal-ca:/backup/internal-ca" \
  -v "$DATA/models:/backup/models" \
  -v "$WORK:/in:ro" alpine:3.20 sh -c 'tar xzf /in/files.tar.gz -C /backup'
"${DC[@]}" up -d
echo "Restored from $SRC. Check Admin -> Health; plants reconnect by themselves."
