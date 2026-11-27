#!/usr/bin/env bash
# Build the two images a site kit runs and push them to a registry, so a plant needs only Docker and
# its kit zip: `docker compose up -d` downloads them. Then tell the server to write these names
# into new kits (KIT_AGENT_IMAGE, KIT_SUPERNODE_IMAGE in deploy/.env or deploy/central/.env).
#
#   docker login ghcr.io            # yourself, once: GitHub user + a token with write:packages
#   deploy/publish_images.sh ghcr.io/<github user>          # agent + Flower image
#   AGENT_ONLY=1 deploy/publish_images.sh ghcr.io/<user>    # the small agent image only
#
# Afterwards make the packages public on GitHub (Packages -> package settings -> visibility), or
# every plant has to `docker login` first. The Flower image is several GB; TORCH_INDEX_URL picks
# CUDA (default cu128) or CPU (https://download.pytorch.org/whl/cpu).
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
REGISTRY="${1:?usage: publish_images.sh <registry prefix, e.g. ghcr.io/myuser>}"
AGENT_VERSION="$(python3 -c "import re,sys; print(re.search(r'__version__ = \"(.+)\"', open(sys.argv[1]).read())[1])" "$REPO/site_agent/__init__.py")"
FLOWER_TAG="${FLOWER_TAG:-$(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || date +%Y%m%d)}"

agent="$REGISTRY/arqauquat-site-agent:$AGENT_VERSION"
docker build -f "$REPO/site_agent/Dockerfile" -t "$agent" "$REPO"
docker push "$agent"
echo "KIT_AGENT_IMAGE=$agent"

if [[ -z "${AGENT_ONLY:-}" ]]; then
  flower="$REGISTRY/arqauquat-flower:$FLOWER_TAG"
  docker build -f "$REPO/deploy/flower/Dockerfile" \
    --build-arg TORCH_INDEX_URL="${TORCH_INDEX_URL:-https://download.pytorch.org/whl/cu128}" -t "$flower" "$REPO"
  docker push "$flower"
  echo "KIT_SUPERNODE_IMAGE=$flower"
fi
echo
echo "Add the KIT_* lines above to the server's .env and restart the api; new kits use these images."
