#!/bin/bash
# Monitor running federated learning experiments

echo "==================================================================="
echo "FEDERATED LEARNING EXPERIMENT MONITOR"
echo "==================================================================="

echo -e "\n1. RUNNING PROCESSES:"
ps aux | grep -E "run_flower_experiment|flwr run" | grep -v grep | grep -v monitor || echo "   No experiments running"

echo -e "\n2. RECENT EXPERIMENT DIRECTORIES:"
ls -ltd /raid/tin_trungchau/federated_learning/experiments_* 2>/dev/null | head -5 || echo "   No experiment directories found yet"
ls -ltd /raid/tin_trungchau/federated_learning/Long-term_Forecasting/flower_app/experiments_* 2>/dev/null | head -5 || echo "   No experiment directories in flower_app/"

echo -e "\n3. GPU USAGE:"
nvidia-smi --query-gpu=index,utilization.gpu,memory.used,memory.total --format=csv,noheader | nl -v 0

echo -e "\n4. RECENT LOG FILES:"
find /raid/tin_trungchau/federated_learning -name "training.log" -mmin -60 2>/dev/null | head -3 || echo "   No recent training logs"

echo -e "\n==================================================================="
echo "TIP: Run this script periodically to track experiment progress"
echo "     watch -n 10 ./monitor_experiments.sh"
echo "==================================================================="
