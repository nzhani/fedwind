#!/usr/bin/env bash
# Back to the start of the demo (DEMO_DAY_PLAN.md §2 F), on THIS computer's stack only:
#   1. stops every simulated plant (deploy/sim/sites/*); its NASA POWER data is kept in
#      deploy/sim/nasa-cache/ so a plant registered again at the same coordinates works offline
#   2. removes the registered plants, their organizations and every non-admin account
#      (python -m app.cli demo-reset, which refuses when the API runs with ENV=production)
#   3. promotes the demo's starting models again: wind run A, solar run C
# Kept: admin accounts, the lab sites, every training run, the audit log, and the example plants in
# DEMO_KEEP_PLANTS (with their organization, accounts and running simulated agent).
# Shows what would go and asks before changing anything.
#
#   cp deploy/sim/demo.env.example deploy/sim/demo.env   # once: data folder + run ids
#   deploy/sim/demo_reset.sh
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
SIM="$REPO/deploy/sim"
[[ -f "$SIM/demo.env" ]] && source "$SIM/demo.env"
: "${FEDWIND_DATA:?Set FEDWIND_DATA in deploy/sim/demo.env (the data folder of the stack)}"
export FEDWIND_DATA
dc=(docker compose -f "$REPO/deploy/docker-compose.yml")

promote=()
for run in "${DEMO_WIND_RUN:-}" "${DEMO_SOLAR_RUN:-}"; do
  [[ -n "$run" ]] && promote+=(--promote "$run")
done
keep=()
for id in ${DEMO_KEEP_PLANTS:-}; do keep+=(--keep "$id"); done
kept() { [[ " ${DEMO_KEEP_PLANTS:-} " == *" $1 "* ]]; }

echo "== Local FedWind demo reset =="
"${dc[@]}" exec -T api python -m app.cli demo-reset "${keep[@]}"   # dry run: lists what would go
shopt -s nullglob
sims=("$SIM"/sites/*/)
names=""
for s in "${sims[@]}"; do kept "$(basename "$s")" || names+="$(basename "$s") "; done
echo "simulated:     $names(stopped)"
echo "promote again: ${promote[*]:-nothing}"
echo
read -r -p "Type 'reset' to remove the above from the local demo: " answer
[[ "$answer" == "reset" ]] || { echo "Nothing changed."; exit 1; }

mkdir -p "$SIM/nasa-cache"
for dir in "${sims[@]}"; do
  id="$(basename "$dir")"
  kept "$id" && continue
  kv() { grep -E "^$1=" "$dir/.env" | tail -1 | cut -d= -f2-; }
  if [[ -f "$dir/data/store/nasa_power.json" ]]; then
    cp "$dir/data/store/nasa_power.json" "$SIM/nasa-cache/$(kv ENERGY_TYPE)_$(kv LAT)_$(kv LON).json"
  fi
  "$SIM/stop_site.sh" "$id" --forget
done

"${dc[@]}" exec -T api python -m app.cli demo-reset --yes "${keep[@]}" "${promote[@]}"
echo
echo "Done. Next: log in as admin in a private window; register the plant in a normal window."
