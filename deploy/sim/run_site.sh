#!/usr/bin/env bash
# Simulate a plant on this computer with a site kit downloaded from the website
# (DEMO_SIMULATION_PLAN.md §4). It installs the kit exactly as a plant would, with two settings
# changed:
#   DATA_SOURCE=nasa_power   the plant's "measurements" are NASA POWER weather at its coordinates
#   SITE_API_URL             how the container reaches the API on this computer
#
#   deploy/sim/run_site.sh ~/Downloads/fedwind-site-<id>.zip
#   deploy/sim/stop_site.sh <id> [--forget]
#
# Optional (deploy/dev/spawn_sites.sh sets these for plants of the central stack):
#   SIM_SITE_API_URL     where the plant reaches the site API (default: this computer's lab API)
#   SIM_EXTRA_COMPOSE    one more compose file layered on top (gateway trust, test switches)
#   SIM_HF_CACHE         GPT-2 cache folder for the kit's Flower SuperNode
#   SIM_INBOX            a prepared hourly export (deploy/sim/make_export.py) used as the plant data
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
ZIP="${1:?usage: run_site.sh <fedwind-site-<id>.zip>}"
SIM_DIR="$REPO/deploy/sim/sites"
API_URL="${SIM_SITE_API_URL:-http://host.docker.internal:8001}"
IMAGE="fedwind-site-agent:0.3.0"

[[ -f "$ZIP" ]] || { echo "No such file: $ZIP" >&2; exit 1; }
root="$(unzip -Z1 "$ZIP" | head -1 | cut -d/ -f1)"
[[ "$root" =~ ^fedwind-site-[a-z][a-z0-9-]+$ ]] || { echo "Not a FedWind site kit: $ZIP" >&2; exit 1; }
# Every entry must stay inside the kit folder
if unzip -Z1 "$ZIP" | grep -qvE "^${root}/" || unzip -Z1 "$ZIP" | grep -q '\.\.'; then
  echo "Refusing a kit with paths outside $root/" >&2; exit 1
fi
site_id="${root#fedwind-site-}"
dest="$SIM_DIR/$site_id"
[[ -e "$dest" ]] && { echo "Already simulated at $dest (run stop_site.sh $site_id --forget first)" >&2; exit 1; }

mkdir -p "$SIM_DIR"
tmp="$(mktemp -d "$SIM_DIR/.unzip-XXXXXX")"
unzip -q "$ZIP" -d "$tmp"
mv "$tmp/$root" "$dest"
rmdir "$tmp"

# Data: a prepared hourly export (SIM_INBOX, like a real plant's SCADA export) or NASA POWER downloads
if [[ -n "${SIM_INBOX:-}" ]]; then
  [[ -f "$SIM_INBOX" ]] || { echo "No such export: $SIM_INBOX" >&2; exit 1; }
  mkdir -p "$dest/data/inbox" && cp "$SIM_INBOX" "$dest/data/inbox/"
  data_source=csv_inbox
else
  data_source=nasa_power
fi
# Certificate kits (central server) keep their gateway address; development kits talk to the API here
if grep -q '^SITE_AUTH_MODE=mtls' "$dest/.env" && [[ -z "${SIM_SITE_API_URL:-}" ]]; then
  sed -i -e "s|^DATA_SOURCE=.*|DATA_SOURCE=$data_source|" "$dest/.env"
else
  sed -i \
    -e "s|^DATA_SOURCE=.*|DATA_SOURCE=$data_source|" \
    -e "s|^SITE_API_URL=.*|SITE_API_URL=$API_URL|" \
    "$dest/.env"
fi
[[ -n "${SIM_HF_CACHE:-}" ]] && sed -i "s|^HF_CACHE=.*|HF_CACHE=$SIM_HF_CACHE|" "$dest/.env"
printf '\n# Changed by deploy/sim/run_site.sh: simulated plant (NASA POWER data), API on this computer\n' >> "$dest/.env"

# NASA POWER data kept by demo_reset.sh for these coordinates: the plant works offline too
kv() { grep -E "^$1=" "$dest/.env" | tail -1 | cut -d= -f2-; }
cache="$REPO/deploy/sim/nasa-cache/$(kv ENERGY_TYPE)_$(kv LAT)_$(kv LON).json"
if [[ -f "$cache" ]]; then
  mkdir -p "$dest/data/store"
  cp "$cache" "$dest/data/store/nasa_power.json"
  echo "Using cached NASA POWER data for these coordinates"
fi

docker image inspect "$IMAGE" >/dev/null 2>&1 \
  || docker build -q -f "$REPO/site_agent/Dockerfile" -t "$IMAGE" "$REPO" >/dev/null

files=(-f "$dest/docker-compose.yml" -f "$REPO/deploy/sim/compose.sim.yml")
[[ -n "${SIM_EXTRA_COMPOSE:-}" ]] && files+=(-f "$SIM_EXTRA_COMPOSE")
SIM_UID="$(id -u)" SIM_GID="$(id -g)" docker compose "${files[@]}" up -d
echo
echo "Simulated plant '$site_id' is starting; its page turns Online within a minute."
echo "Logs: docker compose -f $dest/docker-compose.yml logs -f agent"
echo "Stop: deploy/sim/stop_site.sh $site_id"
