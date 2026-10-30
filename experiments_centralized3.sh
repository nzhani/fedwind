#!/bin/bash

################################################################################
# Centralized Experiment Hyperparameter Sweep Script
#
# Same structure as experiments_gpu*.sh but calls run_centralized.py directly.
# Strips FL-only params (strategy, proximal_mu, num_clients, fraction_train).
#
# IMPORTANT: patch_size=16 and stride=16 match the federated setup exactly.
# The old centralized runs used patch_size=4/stride=1 (wrong defaults) which
# made each round ~16x slower and produced incomparable results.
#
# Usage:
#   bash experiments_centralized.sh > centralized.log 2>&1 &
#   (GPU is selected automatically — freest GPU by memory usage)
################################################################################

source /home/tin_trungchau/miniconda3/etc/profile.d/conda.sh
conda activate flwr39

cd /raid/tin_trungchau/federated_learning

# ============================================================================
# COLOR HELPERS
# ============================================================================
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'
print_success() { echo -e "${GREEN}[INFO]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }

# ============================================================================
# GPU SELECTION — pick least-busy GPU by memory usage
# ============================================================================
select_gpu() {
    if command -v nvidia-smi &> /dev/null; then
        SELECTED_GPU=$(nvidia-smi --query-gpu=index,memory.used --format=csv,noheader,nounits | \
                       sort -t',' -k2 -n | \
                       head -1 | \
                       cut -d',' -f1 | \
                       tr -d ' ')
        GPU_MEM_USED=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -i $SELECTED_GPU)
        GPU_MEM_TOTAL=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits -i $SELECTED_GPU)
        GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader -i $SELECTED_GPU)
        print_success "Selected GPU $SELECTED_GPU: $GPU_NAME ($GPU_MEM_USED MB / $GPU_MEM_TOTAL MB used)"
        export CUDA_VISIBLE_DEVICES=$SELECTED_GPU
    else
        print_warning "No GPU available, will use CPU"
    fi
}

if [[ -n "${CUDA_VISIBLE_DEVICES:-}" ]]; then
    print_success "Using pre-set CUDA_VISIBLE_DEVICES=$CUDA_VISIBLE_DEVICES"
else
    select_gpu
fi

# ============================================================================
# DATASET PARAMETERS
# ============================================================================
declare -a DATASET_NAME=(VNMET)

# ============================================================================
# TRAINING PARAMETERS
# ============================================================================
declare -a NUM_ROUNDS=(25)
declare -a LOCAL_EPOCHS=(1)
declare -a LEARNING_RATE=(0.0005)
declare -a BATCH_SIZE=(32)
declare -a WARMUP_ROUNDS=(1)
declare -a WEIGHT_DECAY=(0.01)
declare -a EARLY_STOP_PATIENCE=(5)

# ============================================================================
# MODEL ARCHITECTURE PARAMETERS
# ============================================================================
declare -a MODEL=(gpt4ts_nonlinear)
declare -a SEQ_LEN=(336)
declare -a PRED_LEN=(1 72 432)
declare -a PATCH_SIZE=(16)
declare -a STRIDE=(16)
declare -a D_MODEL=(768)
declare -a HIDDEN_SIZE=(16)
declare -a KERNEL_SIZE=(3)
declare -a LLM_LAYERS=(4)
declare -a N_HEADS=(4)
declare -a E_LAYERS=(3)
declare -a D_LAYERS=(1)
declare -a D_FF=(768)
declare -a LORA_R=(8)
declare -a LORA_ALPHA=(16)
declare -a LORA_DROPOUT=(0.0)
declare -a PEFT_METHODS=(fft peft adalora lora)
declare -a IS_PRETRAINED=(true)
declare -a DROPOUT=(0.15)

# Total experiments counter
total=0
current=0

# Count total experiments
for dataset_name in "${DATASET_NAME[@]}"; do
  for num_rounds in "${NUM_ROUNDS[@]}"; do
    for local_epochs in "${LOCAL_EPOCHS[@]}"; do
      for lr in "${LEARNING_RATE[@]}"; do
        for batch_size in "${BATCH_SIZE[@]}"; do
          for warmup_rounds in "${WARMUP_ROUNDS[@]}"; do
            for weight_decay in "${WEIGHT_DECAY[@]}"; do
              for early_stop_patience in "${EARLY_STOP_PATIENCE[@]}"; do
                for model in "${MODEL[@]}"; do
                  for seq_len in "${SEQ_LEN[@]}"; do
                    for pred_len in "${PRED_LEN[@]}"; do
                      for patch_size in "${PATCH_SIZE[@]}"; do
                        for stride in "${STRIDE[@]}"; do
                          for d_model in "${D_MODEL[@]}"; do
                            for hidden_size in "${HIDDEN_SIZE[@]}"; do
                              for kernel_size in "${KERNEL_SIZE[@]}"; do
                                for llm_layers in "${LLM_LAYERS[@]}"; do
                                  for n_heads in "${N_HEADS[@]}"; do
                                    for e_layers in "${E_LAYERS[@]}"; do
                                      for d_layers in "${D_LAYERS[@]}"; do
                                        for d_ff in "${D_FF[@]}"; do
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

echo "Starting centralized sweep with $total experiments..."
echo "=================================="

# Run all experiments
for dataset_name in "${DATASET_NAME[@]}"; do
  for num_rounds in "${NUM_ROUNDS[@]}"; do
    for local_epochs in "${LOCAL_EPOCHS[@]}"; do
      for lr in "${LEARNING_RATE[@]}"; do
        for batch_size in "${BATCH_SIZE[@]}"; do
          for warmup_rounds in "${WARMUP_ROUNDS[@]}"; do
            for weight_decay in "${WEIGHT_DECAY[@]}"; do
              for early_stop_patience in "${EARLY_STOP_PATIENCE[@]}"; do
                for model in "${MODEL[@]}"; do
                  for seq_len in "${SEQ_LEN[@]}"; do
                    for pred_len in "${PRED_LEN[@]}"; do
                      for patch_size in "${PATCH_SIZE[@]}"; do
                        for stride in "${STRIDE[@]}"; do
                          for d_model in "${D_MODEL[@]}"; do
                            for hidden_size in "${HIDDEN_SIZE[@]}"; do
                              for kernel_size in "${KERNEL_SIZE[@]}"; do
                                for llm_layers in "${LLM_LAYERS[@]}"; do
                                  for n_heads in "${N_HEADS[@]}"; do
                                    for e_layers in "${E_LAYERS[@]}"; do
                                      for d_layers in "${D_LAYERS[@]}"; do
                                        for d_ff in "${D_FF[@]}"; do
                                          for lora_r in "${LORA_R[@]}"; do
                                            for lora_alpha in "${LORA_ALPHA[@]}"; do
                                              for lora_dropout in "${LORA_DROPOUT[@]}"; do
                                                for peft_method in "${PEFT_METHODS[@]}"; do
                                                  for is_pretrained in "${IS_PRETRAINED[@]}"; do
                                                    for dropout in "${DROPOUT[@]}"; do
                                                      ((current++))

                                                      echo ""
                                                      echo "[$current/$total] Running centralized experiment:"
                                                      echo "  Dataset: $dataset_name"
                                                      echo "  Training: rounds=$num_rounds, lr=$lr, epochs=$local_epochs"
                                                      echo "  Model: $model, pred_len=$pred_len, llm_layers=$llm_layers"
                                                      echo "  Arch: patch_size=$patch_size, stride=$stride, dropout=$dropout"
                                                      echo "  PEFT: $peft_method, is_pretrained: $is_pretrained"
                                                      echo "=================================="

                                                      python Long-term_Forecasting/flower_app/run_centralized.py \
                                                        --dataset-name "$dataset_name" \
                                                        --model "$model" \
                                                        --rounds "$num_rounds" \
                                                        --local-epochs "$local_epochs" \
                                                        --lr "$lr" \
                                                        --batch-size "$batch_size" \
                                                        --warmup-rounds "$warmup_rounds" \
                                                        --weight-decay "$weight_decay" \
                                                        --early-stop-patience "$early_stop_patience" \
                                                        --seq-len "$seq_len" \
                                                        --pred-len "$pred_len" \
                                                        --patch-size "$patch_size" \
                                                        --stride "$stride" \
                                                        --d-model "$d_model" \
                                                        --hidden-size "$hidden_size" \
                                                        --kernel-size "$kernel_size" \
                                                        --llm-layers "$llm_layers" \
                                                        --n-heads "$n_heads" \
                                                        --e-layers "$e_layers" \
                                                        --d-layers "$d_layers" \
                                                        --d-ff "$d_ff" \
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

echo ""
echo "=================================="
echo "Centralized sweep completed! All $total experiments finished."
