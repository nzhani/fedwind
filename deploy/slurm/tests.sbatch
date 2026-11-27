#!/usr/bin/env bash
#SBATCH --job-name=fedwind-tests
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=01:00:00
#SBATCH --output=deploy/slurm/logs/%x-%j.out
# ML core, baselines, inference and site agent tests (the ones not run on laptops).
#   sbatch -p <partition> [-A <account>] deploy/slurm/tests.sbatch      (from the repository root)
set -uo pipefail
source deploy/slurm/common.sh
cd "$FEDWIND_REPO"
fail=0
python -m pytest -q Long-term_Forecasting/tests || fail=1
python -m pytest -q inference/tests || fail=1
python -m pytest -q site_agent/tests || fail=1
exit $fail
