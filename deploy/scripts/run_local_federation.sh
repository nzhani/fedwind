#!/usr/bin/env bash
# Run the federation as plain processes: 1 SuperLink + 1 SuperNode per site.
# Same wiring as deploy/docker-compose.yml, for a machine without Docker or for a
# quick laptop test. Ctrl+C stops everything.
#
#   deploy/scripts/run_local_federation.sh                 # all five sites
#   SITES="almaty aktau" deploy/scripts/run_local_federation.sh
#
# Then, from Long-term_Forecasting/flower_app:
#   flwr run . local-deployment --run-config <file.toml> --stream
#
# Env: PYTHON_BIN (default Long-term_Forecasting/.venv/bin), DATA_DIR (deploy/data),
#      LOG_DIR (deploy/data/federation-logs), CUDA_VISIBLE_DEVICES per process via GPU_<SITE>.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
BIN="${PYTHON_BIN:-$REPO/Long-term_Forecasting/.venv/bin}"
DATA_DIR="${DATA_DIR:-$REPO/deploy/data}"
LOG_DIR="${LOG_DIR:-$DATA_DIR/federation-logs}"
SITES=(${SITES:-almaty zhezkazgan aktau taraz aktobe})
ALL_SITES=(almaty zhezkazgan aktau taraz aktobe)   # partition-id order (deploy/seed/sites.json)

export PATH="$BIN:$PATH"   # SuperLink/SuperNode start flower-superexec by name
export FEDWIND_ML_ROOT="$REPO/Long-term_Forecasting"
export PYTHONPATH="$FEDWIND_ML_ROOT:$FEDWIND_ML_ROOT/flower_app${PYTHONPATH:+:$PYTHONPATH}"
export HF_HOME="${HF_HOME:-$DATA_DIR/hf-cache}"
export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"
export FLWR_HOME="${FLWR_HOME:-$DATA_DIR/flwr-home}"
# CPU runs: keep torch from starting one thread per core in every client process
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-2}"
mkdir -p "$LOG_DIR" "$FLWR_HOME" "$DATA_DIR/runs"

pids=()
cleanup() { kill "${pids[@]}" 2>/dev/null || true; wait 2>/dev/null || true; }
trap cleanup EXIT INT TERM

"$BIN/flower-superlink" --insecure \
  --serverappio-api-address 127.0.0.1:9091 \
  --fleet-api-address 127.0.0.1:9092 \
  --control-api-address 127.0.0.1:9093 \
  > "$LOG_DIR/superlink.log" 2>&1 &
pids+=($!)

# Wait for the fleet API before starting clients
for _ in $(seq 1 60); do
  (exec 3<>/dev/tcp/127.0.0.1/9092) 2>/dev/null && break
  sleep 0.5
done

for site in "${SITES[@]}"; do
  pid=-1
  for i in "${!ALL_SITES[@]}"; do [[ "${ALL_SITES[$i]}" == "$site" ]] && pid=$i; done
  [[ $pid -ge 0 ]] || { echo "unknown site $site" >&2; exit 1; }
  gpu_var="GPU_${site^^}"
  mkdir -p "$DATA_DIR/outputs/$site"
  CUDA_VISIBLE_DEVICES="${!gpu_var:-${CUDA_VISIBLE_DEVICES:-}}" FLOWER_EXP_DIR="$DATA_DIR/outputs/$site" \
  "$BIN/flower-supernode" --insecure \
    --superlink 127.0.0.1:9092 \
    --clientappio-api-address "127.0.0.1:$((9100 + pid))" \
    --node-config "partition-id=$pid num-partitions=${#ALL_SITES[@]} site=\"$site\" data-root=\"$DATA_DIR/sites/$site\"" \
    > "$LOG_DIR/supernode-$site.log" 2>&1 &
  pids+=($!)
done

echo "SuperLink on 127.0.0.1:9093 (control), ${#SITES[@]} SuperNodes: ${SITES[*]}. Logs: $LOG_DIR"
wait
