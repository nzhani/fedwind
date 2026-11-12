# One image for the federation and inference (plan T1.1):
#   superlink        flower-superlink (runs the ServerApp)
#   client-<site>    flower-supernode (runs the ClientApp on this site's data)
#   inference-<site> uvicorn app:app (per-site forecasts)
#
# Build from the repo root:
#   docker build -f deploy/flower/Dockerfile -t fedwind-flower .
# GPU builds take torch from the CUDA index that matches the host driver:
#   cu128 needs driver >= 570; use --build-arg TORCH_INDEX_URL=https://download.pytorch.org/whl/cu126
#   for older drivers, or .../whl/cpu for a CPU-only image.
FROM python:3.12-slim

ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cu128
ENV PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1

RUN pip install torch==2.8.0 --index-url ${TORCH_INDEX_URL}
COPY deploy/flower/requirements.lock.txt /tmp/requirements.lock.txt
RUN pip install -r /tmp/requirements.lock.txt

WORKDIR /opt/fedwind
COPY Long-term_Forecasting/models Long-term_Forecasting/models
COPY Long-term_Forecasting/utils Long-term_Forecasting/utils
COPY Long-term_Forecasting/flower_app/pyproject.toml Long-term_Forecasting/flower_app/pyproject.toml
COPY Long-term_Forecasting/flower_app/my_flower_app Long-term_Forecasting/flower_app/my_flower_app
COPY inference inference

# The ServerApp/ClientApp run from the FAB Flower installs under FLWR_HOME; models/ and
# utils/ are found through FEDWIND_ML_ROOT and PYTHONPATH. GPT-2 comes from the mounted
# HF cache (deploy/scripts/prefetch_models.sh fills it once).
ENV FEDWIND_ML_ROOT=/opt/fedwind/Long-term_Forecasting \
    PYTHONPATH=/opt/fedwind/Long-term_Forecasting:/opt/fedwind/Long-term_Forecasting/flower_app:/opt/fedwind/inference \
    HF_HOME=/hf-cache \
    HF_HUB_OFFLINE=1 \
    FLWR_HOME=/flwr-home
