#!/usr/bin/env bash
#SBATCH --job-name=fedwind-baselines
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --time=12:00:00
#SBATCH --array=0-17
#SBATCH --output=deploy/slurm/logs/%x-%A_%a.out
# Baselines (FR-19) as an array: energy x horizon x seed = 2 x 3 x 3 = 18 tasks, one GPU each.
#   sbatch -p <partition> [-A <account>] deploy/slurm/baselines.sbatch
#   METHODS=llm_local,llm_central sbatch ... deploy/slurm/baselines.sbatch     # the slow LLM baselines
#   sbatch --array=0-5 ...                                                     # wind only
# Results: $FEDWIND_DATA/results/baselines/*.json and summary.csv (one file shared by all tasks).
set -euo pipefail
source deploy/slurm/common.sh
ENERGIES=(wind solar); HORIZONS=(1 72 432); SEEDS=(2021 1 2)
i="${SLURM_ARRAY_TASK_ID:-0}"
energy="${ENERGIES[$(( i / 9 ))]}"; horizon="${HORIZONS[$(( (i / 3) % 3 ))]}"; seed="${SEEDS[$(( i % 3 ))]}"
METHODS="${METHODS:-persistence,arima,lstm_local,lstm_central,lstm_fedavg,patchtst_local,patchtst_central}"
echo "task $i: $energy h$horizon seed $seed: $METHODS"
cd "$FEDWIND_ML_ROOT/flower_app"
python -m baselines.run --energy "$energy" --horizon "$horizon" --seed "$seed" --methods "$METHODS" \
  --data-root "$FEDWIND_DATA/sites" --out "$FEDWIND_DATA/results/baselines" ${BASELINE_ARGS:-}
