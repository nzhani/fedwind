#!/usr/bin/env bash
# Download LLM backbones into deploy/data/hf-cache once; containers then run offline.
#   deploy/scripts/prefetch_models.sh              # gpt2 (default backbone)
#   deploy/scripts/prefetch_models.sh gpt2 facebook/opt-350m
# Without internet on the server, copy deploy/data/hf-cache from a machine that has it.
set -euo pipefail
DEPLOY="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$DEPLOY/data/hf-cache"
MODELS=("${@:-gpt2}")
docker run --rm -e HF_HUB_OFFLINE=0 -v "$DEPLOY/data/hf-cache:/hf-cache" fedwind-flower:latest \
  python -c "
import sys
from huggingface_hub import snapshot_download
for m in sys.argv[1:]:
    print(snapshot_download(m, allow_patterns=['*.json', '*.safetensors', '*.txt', '*.model']))
" "${MODELS[@]}"
