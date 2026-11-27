#!/usr/bin/env bash
# Let a simulated plant on this laptop train in federated runs (lab stack, development mode).
#
#   deploy/sim/join_training.sh <site id>            start its Flower client, mark it selectable
#   deploy/sim/join_training.sh <site id> --leave    stop it again
#
# The plant must be installed (deploy/sim/run_site.sh) and have its training store: the agent fills
# data/store/nasa_<id>.csv from NASA POWER within a few minutes of the first start. The Flower client
# (a SuperNode, like the lab clients) mounts ONLY that store, joins the lab federation and trains when
# a run selects the plant; only model updates leave it. Deployed, the kit's own SuperNode does this
# through the certificate gateway instead.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
SITE="${1:?usage: join_training.sh <site id> [--leave]}"
DATA_ROOT="${FEDWIND_DATA:-$HOME/fedwind-demo-data}"
DC=(docker compose -f "$REPO/deploy/docker-compose.yml")
NAME="fedwind-site-$SITE-supernode"
dest="$REPO/deploy/sim/sites/$SITE"

if [[ "${2:-}" == "--leave" ]]; then
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  "${DC[@]}" exec -T api python -m app.cli sim-plants leave --site "$SITE"
  exit 0
fi

[[ -f "$dest/.env" ]] || { echo "No simulated plant $SITE (install its kit with deploy/sim/run_site.sh)" >&2; exit 1; }
energy="$(grep -E '^ENERGY_TYPE=' "$dest/.env" | cut -d= -f2)"
store="$dest/data/store"
if [[ ! -f "$store/nasa_$SITE.csv" ]]; then
  echo "The plant's training store isn't there yet ($store/nasa_$SITE.csv)." >&2
  echo "Wait a few minutes after installing the kit (NASA POWER download), then run this again." >&2
  exit 1
fi
hours="$(grep -cE '^[0-9]{4},' "$store/nasa_$SITE.csv" || true)"
echo "$SITE: $energy plant, training store $hours hours"

docker rm -f "$NAME" >/dev/null 2>&1 || true
docker run -d --name "$NAME" --network fedwind_default --restart unless-stopped \
  -e FLOWER_EXP_DIR=/outputs -e OMP_NUM_THREADS=4 -e PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
  -v "$store:/data/store:ro" -v "$DATA_ROOT/hf-cache:/hf-cache:ro" \
  fedwind-flower:latest \
  flower-supernode --insecure --superlink=superlink:9092 --clientappio-api-address=0.0.0.0:9094 \
  "--node-config=site=\"$SITE\" energy=\"$energy\" data-root=\"/data/store\"" >/dev/null
"${DC[@]}" exec -T api python -m app.cli sim-plants join --site "$SITE"
echo
echo "Its Flower client runs as container $NAME. On the Experiments page ($energy) the plant can now be"
echo "selected next to the lab sites (once its page shows enough training data). Logs: docker logs -f $NAME"
