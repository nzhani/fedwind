#!/usr/bin/env bash
# Stop a simulated plant started with run_site.sh. The website shows it Offline after
# 3 missed heartbeats. --forget also deletes its folder (site key included), e.g. before
# installing a re-issued kit.
#
#   deploy/sim/stop_site.sh <site-id> [--forget]
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
site_id="${1:?usage: stop_site.sh <site-id> [--forget]}"
[[ "$site_id" =~ ^[a-z][a-z0-9-]+$ ]] || { echo "Not a site id: $site_id" >&2; exit 1; }
dest="$REPO/deploy/sim/sites/$site_id"
[[ -d "$dest" ]] || { echo "No simulated plant at $dest" >&2; exit 1; }

docker compose -f "$dest/docker-compose.yml" -f "$REPO/deploy/sim/compose.sim.yml" down
if [[ "${2:-}" == "--forget" ]]; then
  # Plants started before the agent ran as your user left root-owned files: remove those in a container
  rm -rf "$dest" 2>/dev/null || {
    docker run --rm -v "$dest":/site --entrypoint sh fedwind-site-agent:0.3.0 -c 'rm -rf /site/* /site/.[!.]*'
    rm -rf "$dest"
  }
  echo "Removed $dest"
fi
