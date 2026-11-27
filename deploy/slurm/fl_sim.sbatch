#!/usr/bin/env bash
#SBATCH --job-name=fedwind-fl
#SBATCH --gres=gpu:2
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=12:00:00
#SBATCH --output=deploy/slurm/logs/%x-%j.out
# One federated run in Flower's simulation mode (one job, N virtual clients sharing the GPUs) that
# writes the website's run folder, so it can be imported with `python -m app.cli import-run`.
#   ENERGY=wind HORIZON=72 ROUNDS=20 sbatch -p <partition> deploy/slurm/fl_sim.sbatch
#   CLIENTS_PER_GPU=4 (default 2): how many virtual clients share one GPU
# Clients are the lab sites of the dataset registry (5 wind: KZMET, 5 solar: KZSOLAR).
set -euo pipefail
source deploy/slurm/common.sh
ENERGY="${ENERGY:-wind}"; HORIZON="${HORIZON:-72}"; ROUNDS="${ROUNDS:-20}"; EPOCHS="${EPOCHS:-2}"
STRATEGY="${STRATEGY:-fedavg}"; SEED="${SEED:-2021}"; DATA_PERCENT="${DATA_PERCENT:-100}"
CLIENTS="${CLIENTS:-5}"; CLIENTS_PER_GPU="${CLIENTS_PER_GPU:-2}"
if [[ "$ENERGY" == "solar" ]]; then DATASET=KZSOLAR; TARGET=KSTAR; else DATASET=KZMET; TARGET=WS50M; fi
RUN_ID="${RUN_ID:-$ENERGY-$STRATEGY-h$HORIZON-$(date -u +%Y%m%dT%H%M%SZ)-irgetas}"
OUT="$FEDWIND_DATA/runs"
gpu_share="$(python -c "print(round(1 / $CLIENTS_PER_GPU, 3))")"

# The same model settings as runs started from the website's Experiments page (ExperimentConfig)
RC="energy-type=\"$ENERGY\" dataset-name=\"$DATASET\" target-column=\"$TARGET\" pred-len=$HORIZON seq-len=336"
RC+=" num-server-rounds=$ROUNDS local-epochs=$EPOCHS strategy=\"$STRATEGY\" random-seed=$SEED"
RC+=" model=\"gpt4ts_linear\" llm-layers=2 is-pretrained=true data-percent=$DATA_PERCENT"
RC+=" fraction-train=1.0 min-train-clients=$CLIENTS save-predictions=false"
RC+=" runs-dir=\"$OUT\" run-id=\"$RUN_ID\""
[[ "$ENERGY" == "solar" ]] && RC+=" solar-target=\"kstar\" daylight-mask=true"

cd "$FEDWIND_ML_ROOT/flower_app"
flwr run . local-simulation-5 --stream --run-config "$RC" \
  --federation-config "options.num-supernodes=$CLIENTS options.backend.client-resources.num-gpus=$gpu_share options.backend.client-resources.num-cpus=2"

# For import-run: the run config next to the results
printf '%s\n' $RC | sed 's/=/ = /' > "$OUT/$RUN_ID/run_config.toml"
echo
echo "run folder: $OUT/$RUN_ID"
echo "to show it on the website: copy that folder into <website data>/import/ and run"
echo "  docker compose -f deploy/docker-compose.yml exec api python -m app.cli import-run /data/import/$RUN_ID"
