# Irgetas (Slurm) jobs

Batch work that is too heavy for a laptop: the ML and baseline tests, the baselines (FR-19) and
federated runs in Flower's simulation mode. The website does not run here; finished runs are copied
to it and imported. Run everything from the repository root on the cluster.

| Step | Command |
|---|---|
| Once, on a login node (internet): environment, GPT-2 cache, NASA data | `bash deploy/slurm/setup_env.sh` |
| Tests | `sbatch -p <partition> [-A <account>] deploy/slurm/tests.sbatch` |
| Baselines, 18 tasks (wind/solar × 1/72/432 h × 3 seeds) | `sbatch -p <partition> deploy/slurm/baselines.sbatch` |
| LLM baselines (slow) | `METHODS=llm_local,llm_central sbatch -p <partition> deploy/slurm/baselines.sbatch` |
| One federated run (simulation, 5 clients on 2 GPUs) | `ENERGY=wind HORIZON=72 ROUNDS=20 sbatch -p <partition> deploy/slurm/fl_sim.sbatch` |

Paths: `FEDWIND_REPO` (default `~/fedwind`), `FEDWIND_ENV` (`~/envs/fedwind`), `FEDWIND_DATA`
(`~/fedwind-data`: `sites/`, `hf-cache/`, `runs/`, `results/`); set them in `deploy/slurm/common.sh`
or export them before `sbatch`. Logs go to `deploy/slurm/logs/`. Adjust `--gres`, `--mem` and
`--time` in the job headers to the partition's limits.

## Show a cluster run on the website

`fl_sim.sbatch` writes the website's run folder (`result.json`, `metrics.jsonl`, `checkpoints/`,
`run_config.toml`) to `$FEDWIND_DATA/runs/<run id>`. Copy it to the website's data folder and import:

```bash
rsync -a irgetas:fedwind-data/runs/<run id> ~/fedwind-demo-data/import/
docker compose -f ~/fedwind/deploy/docker-compose.yml exec api python -m app.cli import-run /data/import/<run id> [--promote]
```

The run appears under Training with its dashboard and results, and as a model version under
Admin → Models. Train with the same code version the website runs, or its forecasts can't load
the checkpoint.

Simulation mode uses the dataset registry, so it has as many clients as the registry has sites
(5 wind, 5 solar). The baselines' results stay files (`results/baselines/summary.csv`).
