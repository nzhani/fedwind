#!/usr/bin/env bash
# Stop every simulated plant made by spawn_sites.sh ("Sim ..." names); --forget also deletes their folders.
#   deploy/dev/stop_sites.sh [--forget]
set -uo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
for env in "$REPO"/deploy/sim/sites/*/.env; do
  [[ -f "$env" ]] || continue
  grep -q '^SITE_NAME=Sim ' "$env" || continue
  site_id="$(grep '^SITE_ID=' "$env" | cut -d= -f2)"
  "$REPO/deploy/sim/stop_site.sh" "$site_id" "$@"
done
