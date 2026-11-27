# Sourced by every job script: the environment and paths for the ML code on a Slurm cluster (Irgetas).
# Edit the three lines below once, or export the variables before sbatch.
: "${FEDWIND_ENV:=$HOME/envs/fedwind}"          # created by setup_env.sh (python venv)
: "${FEDWIND_REPO:=$HOME/fedwind}"              # this repository on the cluster
: "${FEDWIND_DATA:=$HOME/fedwind-data}"         # sites/<site>/nasa_<site>.csv, hf-cache/ (GPT-2), runs/

# shellcheck disable=SC1091
source "$FEDWIND_ENV/bin/activate"
export FEDWIND_ML_ROOT="$FEDWIND_REPO/Long-term_Forecasting"
export PYTHONPATH="$FEDWIND_ML_ROOT:$FEDWIND_ML_ROOT/flower_app:$FEDWIND_REPO/inference${PYTHONPATH:+:$PYTHONPATH}"
export HF_HOME="$FEDWIND_DATA/hf-cache" HF_HUB_OFFLINE=1        # compute nodes usually have no internet
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-4}"
mkdir -p "$FEDWIND_DATA/runs" "$FEDWIND_REPO/deploy/slurm/logs"
echo "job ${SLURM_JOB_ID:-local} on $(hostname): $(python -c 'import torch; print("torch", torch.__version__, "cuda", torch.cuda.is_available())')"
