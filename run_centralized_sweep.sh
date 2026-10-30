#!/bin/bash

# Script to run centralized experiments for multiple models in sequence

# Path to the centralized script
SCRIPT_PATH="Long-term_Forecasting/flower_app/run_centralized.py"
# Path to the sweep configuration
CONFIG_PATH="centralized_sweep.conf"

# Source the config to get the MODELS array and other parameters
# (We handle the MODELS array specifically, other params are passed via --config)
source "$CONFIG_PATH"

echo "----------------------------------------------------------------"
echo "Starting Centralized Sequential Sweep"
echo "Models: ${MODELS[*]}"
echo "----------------------------------------------------------------"

for MODEL_NAME in "${MODELS[@]}"; do
    echo ""
    echo "================================================================"
    echo "RUNNING MODEL: $MODEL_NAME"
    echo "================================================================"
    
    # Run the centralized experiment, overriding MODEL from the config file via CLI
    python "$SCRIPT_PATH" --config "$CONFIG_PATH" --model "$MODEL_NAME"
    
    EXIT_CODE=$?
    if [ $EXIT_CODE -eq 0 ]; then
        echo "Successfully completed $MODEL_NAME"
    else
        echo "Error running $MODEL_NAME (Exit code: $EXIT_CODE)"
        exit $EXIT_CODE
    fi
done

echo ""
echo "----------------------------------------------------------------"
echo "Sweep Completed Successfully"
echo "----------------------------------------------------------------"
