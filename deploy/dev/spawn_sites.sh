#!/usr/bin/env bash
# N simulated plants on the central stack of this machine (SITE_NETWORK_PLAN.md M9). Each one is
# registered, approved and given a kit through the platform's own services, then installed with
# deploy/sim/run_site.sh: the real site kit (agent, tunnel, Flower SuperNode) with NASA POWER data.
#
#   deploy/dev/spawn_sites.sh 20 wind
#   FEDWIND_TEST_POISON=nan deploy/dev/spawn_sites.sh 1 wind      # load test: one plant sends broken updates
#   deploy/dev/spawn_sites.sh --start deploy/dev/kits               # start kits made by spawn_sites.py
#   deploy/dev/stop_sites.sh                                        # stop them all
#
# Two ways to make the plants: this script asks the API container (CLI `sim-plants spawn`, no
# passwords involved); deploy/dev/spawn_sites.py goes through the website's HTTP API like people do
# (an admin login), also against a remote server, and leaves its kits for --start.
#
# Needs: deploy/central running (docker compose up), images fedwind-site-agent:0.3.0 and
# fedwind-flower:latest, and the GPT-2 cache in CENTRAL_DATA/hf-cache. Memory: every SuperNode loads
# GPT-2 (about 1-1.5 GB each), so 20 plants want a server with 32 GB+ of RAM.
# Test servers only. The central stack runs with ENV=production, where the API refuses to make
# simulated plants; SIM_ALLOW=1 confirms that this machine is a test deployment.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
START_DIR=""
if [[ "${1:-}" == "--start" ]]; then START_DIR="$(realpath "${2:?usage: spawn_sites.sh --start <kits folder>}")"; COUNT=0
else COUNT="${1:?usage: spawn_sites.sh <count> [wind|solar] | --start <kits folder>}"; fi
ENERGY="${2:-wind}"
CENTRAL="$REPO/deploy/central"
set -a; source "$CENTRAL/.env"; set +a
DC=(docker compose -f "$CENTRAL/docker-compose.yml")
[[ "${SIM_ALLOW:-}" == "1" ]] || { echo "Test deployments only: run with SIM_ALLOW=1 to confirm" >&2; exit 1; }

DATA="$(cd "$CENTRAL" && realpath -m "${CENTRAL_DATA:-./data}")"
KITS="$REPO/deploy/dev/kits"
mkdir -p "$KITS"; chmod 700 "$KITS"

# The gateway's certificate, so the plants trust it (the placeholder until Let's Encrypt has run)
export SITES_HOST
export SIM_GATEWAY_CERT="$REPO/deploy/dev/.gateway.crt"
"${DC[@]}" cp "gateway:/certs/live/$SITES_HOST/fullchain.pem" "$SIM_GATEWAY_CERT"

install() {   # install one kit zip as a simulated plant of the central stack
  SIM_SITE_API_URL="https://$SITES_HOST" SIM_EXTRA_COMPOSE="$REPO/deploy/dev/compose.central-sim.yml" \
    SIM_HF_CACHE="$DATA/hf-cache" "$REPO/deploy/sim/run_site.sh" "$1" >/dev/null
}

if [[ -n "$START_DIR" ]]; then
  for kit in "$START_DIR"/fedwind-site-*.zip; do
    [[ -f "$kit" ]] || continue
    install "$kit" && echo "  $(basename "$kit" .zip) started" && rm -f "$kit"
  done
  exit 0
fi

echo "registering $COUNT $ENERGY plants ..."
mapfile -t lines < <("${DC[@]}" exec -T -e ENV=test api python -m app.cli sim-plants spawn \
                       --count "$COUNT" --energy "$ENERGY" --out /data/sim-kits)
for line in "${lines[@]}"; do
  site_id="${line%%$'\t'*}"; kit="${line#*$'\t'}"
  "${DC[@]}" cp "api:$kit" "$KITS/"
  "${DC[@]}" exec -T api rm -f "$kit"
  install "$KITS/$(basename "$kit")"
  rm -f "$KITS/$(basename "$kit")"
  echo "  $site_id started${FEDWIND_TEST_POISON:+ (sends broken updates: $FEDWIND_TEST_POISON)}"
done
echo "done. Watch them: docker compose -f deploy/central/docker-compose.yml exec api python -m app.cli sim-plants status"
