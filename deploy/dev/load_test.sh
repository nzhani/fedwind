#!/usr/bin/env bash
# M9 load test (SITE_NETWORK_PLAN.md §11): 20 simulated plants on the central stack of this machine
# train together for 3 rounds; one plant is stopped during the run (must show as dropped) and one
# sends broken updates (must show as rejected). Writes deploy/dev/results/load_test_<time>.json.
#
#   SIM_ALLOW=1 deploy/dev/load_test.sh                 # 20 wind plants, 3 rounds
#   SIM_ALLOW=1 PLANTS=10 ROUNDS=2 deploy/dev/load_test.sh
#   deploy/dev/stop_sites.sh --forget                    # clean up afterwards
#
# Needs a test server, not a laptop: 20 SuperNodes load GPT-2 (32 GB+ RAM; a GPU helps). The central
# stack must be up, with TRAIN_MIN_HOURS low enough for the simulated history (default 2160 h needs
# SIM_HISTORY_YEARS >= 1; the plants fetch NASA POWER history on first start, which takes a while).
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
PLANTS="${PLANTS:-20}"
ROUNDS="${ROUNDS:-3}"
ENERGY="${ENERGY:-wind}"
WAIT_MIN="${WAIT_MIN:-90}"            # how long plants may take to become eligible
CENTRAL="$REPO/deploy/central"
DC=(docker compose -f "$CENTRAL/docker-compose.yml")
cli() { "${DC[@]}" exec -T api python -m app.cli "$@"; }
log() { printf '%s  %s\n' "$(date +%H:%M:%S)" "$*"; }
[[ "${SIM_ALLOW:-}" == "1" ]] || { echo "Test deployments only: run with SIM_ALLOW=1" >&2; exit 1; }

log "spawning $((PLANTS - 1)) plants and 1 that sends broken updates"
"$REPO/deploy/dev/spawn_sites.sh" "$((PLANTS - 1))" "$ENERGY"
FEDWIND_TEST_POISON=nan "$REPO/deploy/dev/spawn_sites.sh" 1 "$ENERGY"
# Simulated plants of this energy type, newest first (the last one spawned sends broken updates)
sim_sites() { for d in $(ls -td "$REPO"/deploy/sim/sites/*/); do
                grep -q "^SITE_NAME=Sim $ENERGY " "$d/.env" 2>/dev/null && basename "$d"; done; }
poisoned="$(sim_sites | head -1)"

log "waiting until $PLANTS plants can train (up to $WAIT_MIN min)"
deadline=$(( $(date +%s) + WAIT_MIN * 60 ))
while :; do
  ready="$(cli sim-plants status | tail -1 | awk '{print $1}')"
  log "  $ready of $PLANTS can train"
  (( ready >= PLANTS )) && break
  (( $(date +%s) > deadline )) && { cli sim-plants status; echo "plants not ready in time" >&2; exit 1; }
  sleep 60
done

log "starting $ROUNDS rounds"
run_id="$(cli start-run --energy "$ENERGY" --rounds "$ROUNDS" --horizon 1 --data-percent 5 \
          --min-clients "$(( PLANTS * 3 / 4 ))" --round-timeout 900 | tail -1)"
log "run $run_id"

# Stop one healthy plant's SuperNode after round 1: it must show as dropped from round 2 on
dropped=""
while :; do
  status="$(cli run-status "$run_id" --json)"
  state="$(python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["status"], d["round"])' <<<"$status")"
  if [[ -z "$dropped" && "${state#* }" -ge 1 ]]; then
    dropped="$(sim_sites | grep -v "^$poisoned$" | head -1)"
    log "round 1 done: stopping the SuperNode of $dropped"
    docker compose -p "fedwind-site-$dropped" stop supernode >/dev/null
  fi
  [[ "${state% *}" == "done" || "${state% *}" == "failed" || "${state% *}" == "stopped" ]] && break
  sleep 30
done

mkdir -p "$REPO/deploy/dev/results"
out="$REPO/deploy/dev/results/load_test_$(date -u +%Y%m%dT%H%MZ).json"
python3 - "$status" "$dropped" "$poisoned" "$PLANTS" "$ROUNDS" "$out" <<'EOF'
import json, sys
run, dropped, poisoned, plants, rounds, out = json.loads(sys.argv[1]), *sys.argv[2:4], int(sys.argv[4]), int(sys.argv[5]), sys.argv[6]
checks = {
    "run finished": run["status"] == "done",
    f"{rounds} rounds": len(run["rounds"]) == rounds,
    f"at least {plants} sites in the run": run["sites"] >= plants,
    "stopped plant shown as dropped": any(dropped in r["dropped_sites"] for r in run["rounds"][1:]),
    "broken updates rejected": any(poisoned in r["rejected_sites"] for r in run["rounds"]),
}
json.dump({"run": run, "dropped_plant": dropped, "poisoned_plant": poisoned, "checks": checks}, open(out, "w"), indent=2)
for name, ok in checks.items():
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
print(f"written {out}")
sys.exit(0 if all(checks.values()) else 1)
EOF
