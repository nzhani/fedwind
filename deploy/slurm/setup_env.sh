#!/usr/bin/env bash
# Once, on a login node (it needs the internet): Python environment, GPT-2 cache, NASA POWER data.
#   bash deploy/slurm/setup_env.sh
# If the cluster provides Python through modules, load it first, e.g. `module load python/3.12`.
set -euo pipefail
FEDWIND_REPO="${FEDWIND_REPO:-$HOME/fedwind}"
FEDWIND_ENV="${FEDWIND_ENV:-$HOME/envs/fedwind}"
FEDWIND_DATA="${FEDWIND_DATA:-$HOME/fedwind-data}"
TORCH_INDEX_URL="${TORCH_INDEX_URL:-https://download.pytorch.org/whl/cu128}"   # cu126 for older drivers

python3 -c 'import sys; assert sys.version_info >= (3, 12), "Python 3.12 needed"'
python3 -m venv "$FEDWIND_ENV"
source "$FEDWIND_ENV/bin/activate"
pip install --upgrade pip
pip install torch==2.8.0 --index-url "$TORCH_INDEX_URL"
pip install -r "$FEDWIND_REPO/deploy/flower/requirements.lock.txt"
pip install "flwr[simulation]==1.25.0" pytest==9.2.0 httpx==0.28.1     # Ray for simulation mode; tests

# GPT-2 weights for offline compute nodes
mkdir -p "$FEDWIND_DATA/hf-cache"
HF_HOME="$FEDWIND_DATA/hf-cache" python -c "from transformers import GPT2Model; GPT2Model.from_pretrained('gpt2')"

# NASA POWER data for the ten lab sites (2015-2024): per-site folders (baselines) and the dataset
# registry folders Long-term_Forecasting/datasets/{custom,solar} (simulation mode)
cd "$FEDWIND_REPO/Long-term_Forecasting"
python scripts/download_kzmet.py --sites-dir "$FEDWIND_DATA/sites"
python scripts/download_kzmet.py --energy solar --sites-dir "$FEDWIND_DATA/sites"
echo "environment ready: $FEDWIND_ENV, data: $FEDWIND_DATA"
