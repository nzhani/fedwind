#!/bin/bash

################################################################################
# Federated Learning Hyperparameter Sweep Script
#
# Sweeps over all specified hyperparameter combinations and runs experiments
# sequentially. Define parameter values as arrays below and the script will
# automatically generate all combinations.
################################################################################

# Load HF_TOKEN from repo .env if present so gated models can be accessed
ENV_FILE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.env"
if [ -f "$ENV_FILE" ]; then
  set -a
  . "$ENV_FILE"
  set +a
fi

# ============================================================================
# DATASET PARAMETERS
# ============================================================================
declare -a DATASET_NAME=(VNMET)
declare -a TARGET_COLUMN=("Vavg80 [m/s]")

# ============================================================================
# FEDERATED LEARNING PARAMETERS
# ============================================================================
declare -a NUM_ROUNDS=(15)
declare -a FRACTION_TRAIN=(1.0)
declare -a LOCAL_EPOCHS=(1)
declare -a LEARNING_RATE=(0.001)
declare -a BATCH_SIZE=(32)
declare -a NUM_CLIENTS=(5)

# ============================================================================
# STRATEGY & OPTIMIZATION PARAMETERS
# ============================================================================
# QUICK VERIFICATION: smoke-test new models (opt, gemma, qwen)
declare -a STRATEGY=(fedavg)
declare -a PROXIMAL_MU=(0.01)
declare -a WARMUP_ROUNDS=(1)
declare -a WEIGHT_DECAY=(0.01)
declare -a EARLY_STOPPING=(true)
declare -a EARLY_STOP_PATIENCE=(5)

# ============================================================================
# MODEL ARCHITECTURE PARAMETERS
# ============================================================================
declare -a MODEL=(gpt4ts_nonlinear)
declare -a SEQ_LEN=(336)
declare -a PRED_LEN=(1 72 432)
declare -a LABEL_LEN=(24)
declare -a PATCH_SIZE=(16)
declare -a STRIDE=(16)
declare -a D_MODEL=(768)
declare -a HIDDEN_SIZE=(16)
declare -a KERNEL_SIZE=(3)
declare -a LLM_LAYERS=(4)
declare -a ENC_IN=(1)
declare -a DEC_IN=(1)
declare -a C_OUT=(1)
declare -a EMBED_TYPE=(0)
declare -a EMBED=(timeF)
declare -a FREQ=(h)
declare -a FACTOR=(1)
declare -a N_HEADS=(4)
declare -a E_LAYERS=(3)
declare -a D_LAYERS=(1)
declare -a D_FF=(768)
declare -a DISTIL=(true)
declare -a ACTIVATION=(gelu)
declare -a OUTPUT_ATTENTION=(false)
declare -a FC_DROPOUT=(0.05)
declare -a HEAD_DROPOUT=(0.0)
declare -a PATCH_LEN=(16)
declare -a PADDING_PATCH=(end)
declare -a REVIN=(1)
declare -a AFFINE=(0)
declare -a SUBTRACT_LAST=(0)
declare -a DECOMPOSITION=(0)
declare -a INDIVIDUAL=(0)
declare -a LORA_R=(8)
declare -a LORA_ALPHA=(16)
declare -a LORA_DROPOUT=(0.0)
declare -a PEFT_METHODS=(pft adalora lora fft)
declare -a IS_PRETRAINED=(true)
declare -a DROPOUT=(0.15)

# Total experiments counter
total=0
current=0

# Count total experiments
for dataset_name in "${DATASET_NAME[@]}"; do
  for target_column in "${TARGET_COLUMN[@]}"; do
    for num_rounds in "${NUM_ROUNDS[@]}"; do
      for fraction_train in "${FRACTION_TRAIN[@]}"; do
        for local_epochs in "${LOCAL_EPOCHS[@]}"; do
          for lr in "${LEARNING_RATE[@]}"; do
            for batch_size in "${BATCH_SIZE[@]}"; do
              for num_clients in "${NUM_CLIENTS[@]}"; do
                for strategy in "${STRATEGY[@]}"; do
                  for proximal_mu in "${PROXIMAL_MU[@]}"; do
                    for warmup_rounds in "${WARMUP_ROUNDS[@]}"; do
                      for weight_decay in "${WEIGHT_DECAY[@]}"; do
                        for early_stopping in "${EARLY_STOPPING[@]}"; do
                          for early_stop_patience in "${EARLY_STOP_PATIENCE[@]}"; do
                            for model in "${MODEL[@]}"; do
                              for seq_len in "${SEQ_LEN[@]}"; do
                                for pred_len in "${PRED_LEN[@]}"; do
                                  for label_len in "${LABEL_LEN[@]}"; do
                                    for patch_size in "${PATCH_SIZE[@]}"; do
                                      for stride in "${STRIDE[@]}"; do
                                        for d_model in "${D_MODEL[@]}"; do
                                          for hidden_size in "${HIDDEN_SIZE[@]}"; do
                                            for kernel_size in "${KERNEL_SIZE[@]}"; do
                                              for llm_layers in "${LLM_LAYERS[@]}"; do
                                                for lora_r in "${LORA_R[@]}"; do
                                                  for lora_alpha in "${LORA_ALPHA[@]}"; do
                                                    for lora_dropout in "${LORA_DROPOUT[@]}"; do
                                                      for peft_method in "${PEFT_METHODS[@]}"; do
                                                        for is_pretrained in "${IS_PRETRAINED[@]}"; do
                                                          for dropout in "${DROPOUT[@]}"; do
                                                        ((total++))
                                                          done
                                                        done
                                                      done
                                                    done
                                                  done
                                                done
                                              done
                                            done
                                          done
                                        done
                                      done
                                    done
                                  done
                                done
                              done
                            done
                          done
                        done
                      done
                    done
                  done
                done
              done
            done
          done
        done
      done
    done
  done
done

echo "Starting sweep with $total experiments..."
echo "=================================="

# Run all experiments
for dataset_name in "${DATASET_NAME[@]}"; do
  for target_column in "${TARGET_COLUMN[@]}"; do
    for num_rounds in "${NUM_ROUNDS[@]}"; do
      for fraction_train in "${FRACTION_TRAIN[@]}"; do
        for local_epochs in "${LOCAL_EPOCHS[@]}"; do
          for lr in "${LEARNING_RATE[@]}"; do
            for batch_size in "${BATCH_SIZE[@]}"; do
              for num_clients in "${NUM_CLIENTS[@]}"; do
                for strategy in "${STRATEGY[@]}"; do
                  for proximal_mu in "${PROXIMAL_MU[@]}"; do
                    for warmup_rounds in "${WARMUP_ROUNDS[@]}"; do
                      for weight_decay in "${WEIGHT_DECAY[@]}"; do
                        for early_stopping in "${EARLY_STOPPING[@]}"; do
                          for early_stop_patience in "${EARLY_STOP_PATIENCE[@]}"; do
                            for model in "${MODEL[@]}"; do
                              for seq_len in "${SEQ_LEN[@]}"; do
                                for pred_len in "${PRED_LEN[@]}"; do
                                  for label_len in "${LABEL_LEN[@]}"; do
                                    for patch_size in "${PATCH_SIZE[@]}"; do
                                      for stride in "${STRIDE[@]}"; do
                                        for d_model in "${D_MODEL[@]}"; do
                                          for hidden_size in "${HIDDEN_SIZE[@]}"; do
                                            for kernel_size in "${KERNEL_SIZE[@]}"; do
                                              for llm_layers in "${LLM_LAYERS[@]}"; do
                                                for lora_r in "${LORA_R[@]}"; do
                                                  for lora_alpha in "${LORA_ALPHA[@]}"; do
                                                    for lora_dropout in "${LORA_DROPOUT[@]}"; do
                                                      for peft_method in "${PEFT_METHODS[@]}"; do
                                                        for is_pretrained in "${IS_PRETRAINED[@]}"; do
                                                          for dropout in "${DROPOUT[@]}"; do
                                                        ((current++))

                                                        # Print summary of key params
                                                        echo ""
                                                        echo "[$current/$total] Running experiment:"
                                                        echo "  Dataset: $dataset_name, Target: $target_column"
                                                        echo "  FL: rounds=$num_rounds, lr=$lr, epochs=$local_epochs, strategy=$strategy"
                                                        echo "  Model: $model, pred_len=$pred_len, llm_layers=$llm_layers"
                                                        echo "  PEFT: $peft_method (r=$lora_r, alpha=$lora_alpha)"
                                                        echo "  is_pretrained: $is_pretrained"
                                                        echo "=================================="

                                                        ./run_flower_experiment.sh \
                                                          --dataset-name "$dataset_name" \
                                                          --target-column "$target_column" \
                                                          --rounds "$num_rounds" \
                                                          --fraction-train "$fraction_train" \
                                                          --local-epochs "$local_epochs" \
                                                          --lr "$lr" \
                                                          --batch-size "$batch_size" \
                                                          --num-clients "$num_clients" \
                                                          --strategy "$strategy" \
                                                          --proximal-mu "$proximal_mu" \
                                                          --warmup-rounds "$warmup_rounds" \
                                                          --weight-decay "$weight_decay" \
                                                          --early-stopping "$early_stopping" \
                                                          --early-stop-patience "$early_stop_patience" \
                                                          --model "$model" \
                                                          --seq-len "$seq_len" \
                                                          --pred-len "$pred_len" \
                                                          --label-len "$label_len" \
                                                          --patch-size "$patch_size" \
                                                          --stride "$stride" \
                                                          --d-model "$d_model" \
                                                          --hidden-size "$hidden_size" \
                                                          --kernel-size "$kernel_size" \
                                                          --llm-layers "$llm_layers" \
                                                          --lora-r "$lora_r" \
                                                          --lora-alpha "$lora_alpha" \
                                                          --lora-dropout "$lora_dropout" \
                                                          --peft-method "$peft_method" \
                                                          --is-pretrained "$is_pretrained" \
                                                          --dropout "$dropout"

                                                        if [ $? -eq 0 ]; then
                                                          echo "✓ Experiment $current completed successfully"
                                                        else
                                                          echo "✗ Experiment $current failed with exit code $?"
                                                        fi
                                                          done
                                                        done
                                                      done
                                                    done
                                                  done
                                                done
                                              done
                                            done
                                          done
                                        done
                                      done
                                    done
                                  done
                                done
                              done
                            done
                          done
                        done
                      done
                    done
                  done
                done
              done
            done
          done
        done
      done
    done
  done
done

echo ""
echo "=================================="
echo "Sweep completed! All $total experiments finished."
