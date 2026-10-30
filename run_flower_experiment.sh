#!/bin/bash

################################################################################
# Federated Learning Experiment Runner
#
# This script sets up the environment and runs Flower federated learning
# experiments with configurable FL training and LLM model parameters.
#
# Usage:
#   ./run_flower_experiment.sh [OPTIONS]
#
# Examples:
#   # Interactive mode
#   ./run_flower_experiment.sh
#
#   # Quick test run
#   ./run_flower_experiment.sh --mode quick
#
#   # Custom FL parameters only
#   ./run_flower_experiment.sh --rounds 20 --lr 0.001 --local-epochs 3
#
#   # Custom model parameters
#   ./run_flower_experiment.sh --seq-len 512 --pred-len 96 --d-model 256
#
#   # Full custom configuration
#   ./run_flower_experiment.sh --rounds 15 --lr 0.0005 --seq-len 336 \
#       --pred-len 120 --llm-layers 6 --lora-r 16
################################################################################

set -e  # Exit on error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
FLOWER_APP_DIR="$PROJECT_ROOT/Long-term_Forecasting/flower_app"

################################################################################
# Default Parameters (can be overridden by config file or command-line args)
################################################################################

# Path to config file (can be set via --config argument)
CONFIG_FILE=""

# Federated Learning Parameters (--run-config)
NUM_ROUNDS=10
FRACTION_TRAIN=1.0
LOCAL_EPOCHS=2
LEARNING_RATE=0.0005
BATCH_SIZE=32
NUM_CLIENTS=5

# Strategy and Optimization Parameters
STRATEGY="fedavg"           # fedavg, fedprox, or scaffold
PROXIMAL_MU=0.01            # FedProx proximal term coefficient (only used if STRATEGY=fedprox)
WARMUP_ROUNDS=3             # Number of rounds for learning rate warmup
WEIGHT_DECAY=0.01           # L2 regularization coefficient for AdamW optimizer

# Early Stopping Parameters
EARLY_STOPPING=true         # Enable/disable early stopping
EARLY_STOP_PATIENCE=5       # Number of rounds without improvement before stopping

# Model Architecture Parameters (requires code modification)
SEQ_LEN=336
PRED_LEN=120
LABEL_LEN=48
PATCH_SIZE=4
STRIDE=1
D_MODEL=768
HIDDEN_SIZE=16
KERNEL_SIZE=3
LLM_LAYERS=4
ENC_IN=1
DEC_IN=1
C_OUT=1
EMBED_TYPE=0
EMBED="timeF"
FREQ="h"
FACTOR=1
N_HEADS=4
E_LAYERS=2
D_LAYERS=1
D_FF=512
DISTIL=true
ACTIVATION="gelu"
OUTPUT_ATTENTION=false
FC_DROPOUT=0.05
HEAD_DROPOUT=0.0
PATCH_LEN=16
PADDING_PATCH="end"
REVIN=1
AFFINE=0
SUBTRACT_LAST=0
DECOMPOSITION=0
INDIVIDUAL=0
LORA_R=8
LORA_ALPHA=16
LORA_DROPOUT=0.0  # No dropout for LoRA
PEFT_METHOD="lora"  # lora, loha, adalora, pft, fft
IS_PRETRAINED=false
DROPOUT=0.15  # Model dropout for regularization (default: 0.15)

# Model selection (passed through to pyproject.toml via --run-config)
MODEL="gpt4ts_nonlinear"

# Dataset parameters
DATASET_NAME=""
TARGET_COLUMN=""

# Conda environment
CONDA_ENV=flwr39

# Setup Options
SKIP_SETUP=true  # Default: skip setup (faster)
SKIP_VENV_CHECK=false
USE_LATEST_DEPS=false
DRY_RUN=false
INTERACTIVE=false
AUTO_APPROVE=false
MODE=""

# MLflow Options (optional)
MLFLOW_ENABLE=false
MLFLOW_TRACKING_URI=""
MLFLOW_EXPERIMENT_NAME="flwr-experiments"
MLFLOW_RUN_NAME=""
MLFLOW_MODEL_NAME=""
MLFLOW_TRAINING_MODE=""

################################################################################
# Helper Functions
################################################################################

print_header() {
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}$1${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Configuration:
    --config FILE             Load parameters from config file (default: experiment_config.conf)
                             Config file values override script defaults.
                             Command-line arguments override config file.

Dataset Options:
    --dataset-name NAME       Dataset name (e.g., VNMET, custom, nasa_almaty)
    --target-column COL       Target column name for forecasting

Setup Options:
    --setup                   Run full environment setup (Python, CUDA, venv checks)
    --skip-venv-check         Skip virtual environment check
    --use-latest              Use latest dependencies (requirements.txt)
    --dry-run                 Show what would be executed without running
    -i, --interactive         Interactive mode (prompt for all parameters)
    -y, --yes                 Auto-approve all prompts (non-interactive mode)

MLflow Options (optional):
    --mlflow                  Enable MLflow logging
    --no-mlflow               Disable MLflow logging (default)
    --mlflow-tracking-uri URI MLflow tracking URI (default: file:$PROJECT_ROOT/mlruns)
    --mlflow-experiment NAME  MLflow experiment name (default: flwr-experiments)
    --mlflow-run-name NAME    MLflow run name (default: auto)
    --model-name NAME         Tag MLflow run with model name (e.g., GPT4TS, PatchTST)
    --training-mode NAME      Tag MLflow run with training mode (centralized/fedavg/fedprox/scaffold)

Note: By default, environment setup is SKIPPED for faster execution.
      Use --setup to explicitly run environment checks.

Experiment Modes (Presets):
    --mode quick              Quick test: 3 rounds, 1 epoch, lr=0.001
    --mode standard           Standard: 10 rounds, 2 epochs, lr=0.0005
    --mode full               Full training: 20 rounds, 5 epochs, lr=0.0001
    --mode debug              Debug: 2 rounds, 1 epoch, 1 client

Federated Learning Parameters:
    --rounds NUM              Number of FL rounds (default: 10)
    --fraction-train FRAC     Fraction of clients per round (default: 1.0)
    --local-epochs NUM        Local training epochs (default: 2)
    --lr FLOAT                Base learning rate (default: 0.0005)
    --batch-size NUM          Batch size (default: 16)
    --num-clients NUM         Number of simulated clients (default: 5)

Model Architecture Parameters:
    --seq-len NUM             Input sequence length (default: 336)
    --pred-len NUM            Prediction horizon (default: 120)
    --label-len NUM           Label length for Informer (default: 48)
    --patch-size NUM          Patch size (default: 4)
    --stride NUM              Stride (default: 1)
    --d-model NUM             Model dimension (default: 128)
    --hidden-size NUM         Hidden layer size (default: 128)
    --kernel-size NUM         Convolution kernel size (default: 3)
    --llm-layers NUM          Number of LLM layers (default: 2)
    --enc-in NUM              Encoder input size (default: 1)
    --dec-in NUM              Decoder input size (default: 1)
    --c-out NUM               Output size (default: 1)
    --embed-type NUM          Embed type (default: 0)
    --embed STR               Embed mode (default: timeF)
    --freq STR                Time feature frequency (default: h)
    --factor NUM              Attention factor (default: 1)
    --n-heads NUM             Number of attention heads (default: 4)
    --e-layers NUM            Encoder layers (default: 2)
    --d-layers NUM            Decoder layers (default: 1)
    --d-ff NUM                Feed-forward dimension (default: 512)
    --distil BOOL             Use distillation in encoder (default: true)
    --activation STR          Activation (default: gelu)
    --output-attention BOOL   Output attention (default: false)
    --fc-dropout FLOAT        PatchTST FC dropout (default: 0.05)
    --head-dropout FLOAT      PatchTST head dropout (default: 0.0)
    --patch-len NUM           PatchTST patch length (default: 16)
    --padding-patch STR       PatchTST padding mode (default: end)
    --revin NUM               PatchTST RevIN (1/0, default: 1)
    --affine NUM              PatchTST RevIN affine (1/0, default: 0)
    --subtract-last NUM       PatchTST subtract last (1/0, default: 0)
    --decomposition NUM       PatchTST decomposition (1/0, default: 0)
    --individual NUM          PatchTST individual head (1/0, default: 0)
    --lora-r NUM              LoRA rank (default: 8)
    --lora-alpha NUM          LoRA alpha (default: 16)
    --lora-dropout FLOAT      LoRA dropout (default: 0.1)
    --peft-method STR         PEFT method (lora, loha, adalora, pft, fft)
    --is-pretrained BOOL      Whether to treat run as pretrained-only (default: false)
    --dropout FLOAT           Model dropout for regularization (default: 0.15)

Other Options:
    -h, --help                Show this help message

Examples:
    # Use default config file (experiment_config.conf)
    $0

    # Use custom config file
    $0 --config my_experiment.conf

    # Config file + override specific parameters
    $0 --config experiment_config.conf --rounds 20 --pred-len 96

    # Quick test (preset mode)
    $0 --mode quick

    # Full training with custom parameters
    $0 --rounds 15 --lr 0.0005 --pred-len 120 --llm-layers 6

    # Interactive configuration
    $0 --interactive

    # With full environment setup
    $0 --config experiment_config.conf --setup

EOF
}

################################################################################
# Load Configuration File
################################################################################

load_config() {
    local config_file="$1"

    if [ -z "$config_file" ]; then
        # Try default config file if it exists
        if [ -f "$SCRIPT_DIR/experiment_config.conf" ]; then
            config_file="$SCRIPT_DIR/experiment_config.conf"
            print_info "Loading default config: $config_file"
        else
            return 0  # No config file specified and no default found
        fi
    fi

    if [ ! -f "$config_file" ]; then
        print_error "Config file not found: $config_file"
        exit 1
    fi

    print_info "Loading configuration from: $config_file"

    # Source the config file (it's a bash script with KEY=VALUE pairs)
    # shellcheck disable=SC1090
    source "$config_file"
    if [ -n "$MODEL_NAME" ] && [ "$MODEL" = "gpt4ts_nonlinear" ]; then
        MODEL="$MODEL_NAME"
    fi

    print_success "Configuration loaded successfully"
}

################################################################################
# Parse Command Line Arguments
################################################################################

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                usage
                exit 0
                ;;
            --config)
                CONFIG_FILE="$2"
                shift 2
                ;;
            --setup)
                SKIP_SETUP=false  # Explicitly enable setup
                shift
                ;;
            --skip-venv-check)
                SKIP_VENV_CHECK=true
                shift
                ;;
            --use-latest)
                USE_LATEST_DEPS=true
                shift
                ;;
            --dry-run)
                DRY_RUN=true
                shift
                ;;
            -i|--interactive)
                INTERACTIVE=true
                shift
                ;;
            -y|--yes)
                AUTO_APPROVE=true
                shift
                ;;
            --mlflow)
                MLFLOW_ENABLE=true
                shift
                ;;
            --no-mlflow)
                MLFLOW_ENABLE=false
                shift
                ;;
            --mlflow-tracking-uri)
                MLFLOW_TRACKING_URI="$2"
                shift 2
                ;;
            --mlflow-experiment)
                MLFLOW_EXPERIMENT_NAME="$2"
                shift 2
                ;;
            --mlflow-run-name)
                MLFLOW_RUN_NAME="$2"
                shift 2
                ;;
            --model-name)
                MLFLOW_MODEL_NAME="$2"
                shift 2
                ;;
            --training-mode)
                MLFLOW_TRAINING_MODE="$2"
                shift 2
                ;;
            --mode)
                MODE="$2"
                shift 2
                ;;
            --rounds)
                NUM_ROUNDS="$2"
                shift 2
                ;;
            --fraction-train)
                FRACTION_TRAIN="$2"
                shift 2
                ;;
            --local-epochs)
                LOCAL_EPOCHS="$2"
                shift 2
                ;;
            --lr)
                LEARNING_RATE="$2"
                shift 2
                ;;
            --batch-size)
                BATCH_SIZE="$2"
                shift 2
                ;;
            --num-clients)
                NUM_CLIENTS="$2"
                shift 2
                ;;
            --seq-len)
                SEQ_LEN="$2"
                shift 2
                ;;
            --pred-len)
                PRED_LEN="$2"
                shift 2
                ;;
            --label-len)
                LABEL_LEN="$2"
                shift 2
                ;;
            --patch-size)
                PATCH_SIZE="$2"
                shift 2
                ;;
            --stride)
                STRIDE="$2"
                shift 2
                ;;
            --d-model)
                D_MODEL="$2"
                shift 2
                ;;
            --hidden-size)
                HIDDEN_SIZE="$2"
                shift 2
                ;;
            --kernel-size)
                KERNEL_SIZE="$2"
                shift 2
                ;;
            --llm-layers)
                LLM_LAYERS="$2"
                shift 2
                ;;
            --enc-in)
                ENC_IN="$2"
                shift 2
                ;;
            --dec-in)
                DEC_IN="$2"
                shift 2
                ;;
            --c-out)
                C_OUT="$2"
                shift 2
                ;;
            --embed-type)
                EMBED_TYPE="$2"
                shift 2
                ;;
            --embed)
                EMBED="$2"
                shift 2
                ;;
            --freq)
                FREQ="$2"
                shift 2
                ;;
            --factor)
                FACTOR="$2"
                shift 2
                ;;
            --n-heads)
                N_HEADS="$2"
                shift 2
                ;;
            --e-layers)
                E_LAYERS="$2"
                shift 2
                ;;
            --d-layers)
                D_LAYERS="$2"
                shift 2
                ;;
            --d-ff)
                D_FF="$2"
                shift 2
                ;;
            --distil)
                DISTIL="$2"
                shift 2
                ;;
            --activation)
                ACTIVATION="$2"
                shift 2
                ;;
            --output-attention)
                OUTPUT_ATTENTION="$2"
                shift 2
                ;;
            --fc-dropout)
                FC_DROPOUT="$2"
                shift 2
                ;;
            --head-dropout)
                HEAD_DROPOUT="$2"
                shift 2
                ;;
            --patch-len)
                PATCH_LEN="$2"
                shift 2
                ;;
            --padding-patch)
                PADDING_PATCH="$2"
                shift 2
                ;;
            --revin)
                REVIN="$2"
                shift 2
                ;;
            --affine)
                AFFINE="$2"
                shift 2
                ;;
            --subtract-last)
                SUBTRACT_LAST="$2"
                shift 2
                ;;
            --decomposition)
                DECOMPOSITION="$2"
                shift 2
                ;;
            --individual)
                INDIVIDUAL="$2"
                shift 2
                ;;
            --lora-r)
                LORA_R="$2"
                shift 2
                ;;
            --lora-alpha)
                LORA_ALPHA="$2"
                shift 2
                ;;
            --lora-dropout)
                LORA_DROPOUT="$2"
                shift 2
                ;;
            --peft-method)
                PEFT_METHOD="$2"
                shift 2
                ;;
            --is-pretrained)
                IS_PRETRAINED="$2"
                shift 2
                ;;
            --dropout)
                DROPOUT="$2"
                shift 2
                ;;
            --model)
                MODEL="$2"
                shift 2
                ;;
            --strategy)
                STRATEGY="$2"
                shift 2
                ;;
            --proximal-mu)
                PROXIMAL_MU="$2"
                shift 2
                ;;
            --warmup-rounds)
                WARMUP_ROUNDS="$2"
                shift 2
                ;;
            --weight-decay)
                WEIGHT_DECAY="$2"
                shift 2
                ;;
            --early-stopping)
                EARLY_STOPPING="$2"
                shift 2
                ;;
            --early-stop-patience)
                EARLY_STOP_PATIENCE="$2"
                shift 2
                ;;
            --dataset-name)
                DATASET_NAME="$2"
                shift 2
                ;;
            --target-column)
                TARGET_COLUMN="$2"
                shift 2
                ;;
            *)
                print_error "Unknown option: $1"
                usage
                exit 1
                ;;
        esac
    done
}

################################################################################
# Apply Preset Modes
################################################################################

apply_mode() {
    case $MODE in
        quick)
            print_info "Applying QUICK mode preset..."
            NUM_ROUNDS=2
            LOCAL_EPOCHS=1
            LEARNING_RATE=0.001
            BATCH_SIZE=32
            NUM_CLIENTS=2
            ;;
        standard)
            print_info "Applying STANDARD mode preset..."
            NUM_ROUNDS=10
            LOCAL_EPOCHS=2
            LEARNING_RATE=0.0005
            BATCH_SIZE=32
            NUM_CLIENTS=5
            ;;
        full)
            print_info "Applying FULL mode preset..."
            NUM_ROUNDS=20
            LOCAL_EPOCHS=5
            LEARNING_RATE=0.0001
            BATCH_SIZE=32
            NUM_CLIENTS=5
            ;;
        debug)
            print_info "Applying DEBUG mode preset..."
            NUM_ROUNDS=2
            LOCAL_EPOCHS=1
            LEARNING_RATE=0.001
            BATCH_SIZE=8
            NUM_CLIENTS=1
            ;;
        "")
            # No mode specified, use defaults or command line args
            ;;
        *)
            print_error "Unknown mode: $MODE"
            print_info "Valid modes: quick, standard, full, debug"
            exit 1
            ;;
    esac
}

################################################################################
# Interactive Mode
################################################################################

interactive_mode() {
    print_header "Interactive Configuration"

    echo -e "\n${YELLOW}Federated Learning Parameters:${NC}"
    read -p "Number of FL rounds [$NUM_ROUNDS]: " input
    NUM_ROUNDS=${input:-$NUM_ROUNDS}

    read -p "Fraction of clients per round [$FRACTION_TRAIN]: " input
    FRACTION_TRAIN=${input:-$FRACTION_TRAIN}

    read -p "Local epochs per round [$LOCAL_EPOCHS]: " input
    LOCAL_EPOCHS=${input:-$LOCAL_EPOCHS}

    read -p "Learning rate [$LEARNING_RATE]: " input
    LEARNING_RATE=${input:-$LEARNING_RATE}

    read -p "Batch size [$BATCH_SIZE]: " input
    BATCH_SIZE=${input:-$BATCH_SIZE}

    read -p "Number of clients [$NUM_CLIENTS]: " input
    NUM_CLIENTS=${input:-$NUM_CLIENTS}

    echo -e "\n${YELLOW}Model Architecture Parameters:${NC}"
    read -p "Input sequence length [$SEQ_LEN]: " input
    SEQ_LEN=${input:-$SEQ_LEN}

    read -p "Prediction horizon [$PRED_LEN]: " input
    PRED_LEN=${input:-$PRED_LEN}

    read -p "Model dimension (d_model) [$D_MODEL]: " input
    D_MODEL=${input:-$D_MODEL}

    read -p "Number of LLM layers [$LLM_LAYERS]: " input
    LLM_LAYERS=${input:-$LLM_LAYERS}

    read -p "LoRA rank [$LORA_R]: " input
    LORA_R=${input:-$LORA_R}

    echo -e "\n${YELLOW}Advanced Parameters (press Enter to keep defaults):${NC}"
    read -p "Patch size [$PATCH_SIZE]: " input
    PATCH_SIZE=${input:-$PATCH_SIZE}

    read -p "Stride [$STRIDE]: " input
    STRIDE=${input:-$STRIDE}

    read -p "Hidden size [$HIDDEN_SIZE]: " input
    HIDDEN_SIZE=${input:-$HIDDEN_SIZE}

    read -p "Kernel size [$KERNEL_SIZE]: " input
    KERNEL_SIZE=${input:-$KERNEL_SIZE}

    read -p "LoRA alpha [$LORA_ALPHA]: " input
    LORA_ALPHA=${input:-$LORA_ALPHA}

    read -p "LoRA dropout [$LORA_DROPOUT]: " input
    LORA_DROPOUT=${input:-$LORA_DROPOUT}

    read -p "Model dropout [$DROPOUT]: " input
    DROPOUT=${input:-$DROPOUT}
}

################################################################################
# Environment Setup
################################################################################

check_python() {
    print_info "Checking Python installation..."

    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 is not installed"
        exit 1
    fi

    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
    print_success "Found Python $PYTHON_VERSION"

    # Check if version is 3.8+
    PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d'.' -f1)
    PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d'.' -f2)

    if [[ $PYTHON_MAJOR -lt 3 ]] || [[ $PYTHON_MAJOR -eq 3 && $PYTHON_MINOR -lt 8 ]]; then
        print_error "Python 3.8+ is required (found $PYTHON_VERSION)"
        exit 1
    fi
}

check_cuda() {
    print_info "Checking CUDA availability..."

    if command -v nvidia-smi &> /dev/null; then
        CUDA_VERSION=$(nvidia-smi | grep "CUDA Version" | awk '{print $9}')
        GPU_COUNT=$(nvidia-smi --list-gpus | wc -l)
        print_success "Found CUDA $CUDA_VERSION with $GPU_COUNT GPU(s)"

        # Show GPU info with memory usage
        echo ""
        nvidia-smi --query-gpu=index,name,memory.used,memory.total,utilization.gpu --format=table
        echo ""
    else
        print_warning "CUDA not found - will use CPU (training will be slow)"
        SELECTED_GPU=""
    fi
}

select_gpu() {
    print_info "Selecting GPU..."

    if command -v nvidia-smi &> /dev/null; then
        # Find least busy GPU (lowest memory usage)
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
        SELECTED_GPU=""
    fi
}

setup_venv() {
    print_info "Checking conda environment '$CONDA_ENV'..."

    # Check if conda is available
    if command -v conda &> /dev/null; then
        # Initialize conda for bash
        eval "$(conda shell.bash hook)"

        # Try to activate conda environment
        if conda activate "$CONDA_ENV" 2>/dev/null; then
            print_success "Conda environment '$CONDA_ENV' activated"
        else
            print_error "Conda environment '$CONDA_ENV' not found"
            print_info "Please create it with: conda create -n $CONDA_ENV python=3.9 -y"
            print_info "Then install flower: conda activate $CONDA_ENV && pip install flwr[simulation]"
            exit 1
        fi
    else
        print_error "conda command not found"
        print_info "Please ensure conda/miniconda is installed and in PATH"
        exit 1
    fi

    # Verify flwr is available
    if command -v flwr &> /dev/null; then
        print_success "flwr command is available"
        PYTHON_PATH=$(which python3)
        print_info "Using Python from: $PYTHON_PATH"
    else
        print_error "flwr command not found in conda environment '$CONDA_ENV'"
        print_info "Please install flower: pip install flwr[simulation]"
        exit 1
    fi
}

install_dependencies() {
    print_info "Installing dependencies..."

    if [ "$USE_LATEST_DEPS" = true ]; then
        REQUIREMENTS_FILE="$PROJECT_ROOT/requirements.txt"
        print_info "Using latest dependencies: $REQUIREMENTS_FILE"
    else
        REQUIREMENTS_FILE="$PROJECT_ROOT/Long-term_Forecasting/requirements_ss.txt"
        print_info "Using simulation dependencies: $REQUIREMENTS_FILE"
    fi

    if [ ! -f "$REQUIREMENTS_FILE" ]; then
        print_error "Requirements file not found: $REQUIREMENTS_FILE"
        exit 1
    fi

    pip install --upgrade pip
    pip install -r "$REQUIREMENTS_FILE"

    # Ensure Flower is installed
    print_info "Ensuring Flower framework is installed..."
    pip install "flwr[simulation]>=1.11.0" "flwr-datasets[vision]>=0.5.0"

    print_success "Dependencies installed"
}

check_data() {
    print_info "Checking dataset availability..."

    DATA_DIR="$PROJECT_ROOT/Long-term_Forecasting/datasets/custom"

    if [ ! -d "$DATA_DIR" ]; then
        print_error "Data directory not found: $DATA_DIR"
        exit 1
    fi

    # Check for required NASA datasets
    REQUIRED_FILES=("nasa_almaty.csv" "nasa_zhezkazgan.csv" "nasa_aktau.csv" "nasa_taraz.csv" "nasa_aktobe.csv" "nasa_astana.csv")
    MISSING_FILES=()

    for file in "${REQUIRED_FILES[@]}"; do
        if [ ! -f "$DATA_DIR/$file" ]; then
            MISSING_FILES+=("$file")
        fi
    done

    if [ ${#MISSING_FILES[@]} -eq 0 ]; then
        print_success "All required datasets found (${#REQUIRED_FILES[@]} files)"

        # Show file sizes
        for file in "${REQUIRED_FILES[@]}"; do
            SIZE=$(du -h "$DATA_DIR/$file" | cut -f1)
            print_info "  $file: $SIZE"
        done
    else
        print_error "Missing datasets:"
        for file in "${MISSING_FILES[@]}"; do
            print_error "  - $file"
        done
        exit 1
    fi
}

################################################################################
# Modify Model Configuration
################################################################################

update_model_config() {
    print_header "Updating Model Configuration"

    TASK_FILE="$FLOWER_APP_DIR/my_flower_app/task.py"

    if [ ! -f "$TASK_FILE" ]; then
        print_error "Task file not found: $TASK_FILE"
        exit 1
    fi

    # Create backup
    BACKUP_FILE="${TASK_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
    cp "$TASK_FILE" "$BACKUP_FILE"
    print_info "Created backup: $BACKUP_FILE"

    # Update configuration using sed
    print_info "Updating model parameters in task.py..."

    sed -i "s/seq_len=[0-9]*/seq_len=$SEQ_LEN/" "$TASK_FILE"
    # DISABLED: pred_len is now passed as function parameter, not hardcoded
    # sed -i "s/pred_len=[0-9]*/pred_len=$PRED_LEN/" "$TASK_FILE"
    sed -i "s/patch_size=[0-9]*/patch_size=$PATCH_SIZE/" "$TASK_FILE"
    sed -i "s/stride=[0-9]*/stride=$STRIDE/" "$TASK_FILE"
    sed -i "s/d_model=[0-9]*/d_model=$D_MODEL/" "$TASK_FILE"
    sed -i "s/hidden_size=[0-9]*/hidden_size=$HIDDEN_SIZE/" "$TASK_FILE"
    sed -i "s/kernel_size=[0-9]*/kernel_size=$KERNEL_SIZE/" "$TASK_FILE"
    sed -i "s/llm_layers=[0-9]*/llm_layers=$LLM_LAYERS/" "$TASK_FILE"
    sed -i "s/lora_r=[0-9]*/lora_r=$LORA_R/" "$TASK_FILE"
    sed -i "s/lora_alpha=[0-9]*/lora_alpha=$LORA_ALPHA/" "$TASK_FILE"
    sed -i "s/lora_dropout=[0-9.]*,/lora_dropout=$LORA_DROPOUT,/" "$TASK_FILE"
    sed -i "s/dropout=[0-9.]*,/dropout=$DROPOUT,/" "$TASK_FILE"

    print_success "Model configuration updated"

    # Verify changes
    print_info "Current model configuration:"
    grep -E "(seq_len|pred_len|patch_size|stride|d_model|hidden_size|kernel_size|llm_layers|lora_r|lora_alpha|lora_dropout|dropout)=" "$TASK_FILE" | head -13
}

################################################################################
# Get Federation Name based on Client Count
################################################################################

get_federation_name() {
    # Map number of clients to federation name in pyproject.toml
    case $NUM_CLIENTS in
        1)
            echo "local-simulation-1"
            ;;
        2)
            echo "local-simulation-2"
            ;;
        3)
            echo "local-simulation-3"
            ;;
        4)
            echo "local-simulation-4"
            ;;
        5)
            echo "local-simulation-5"
            ;;
        7)
            echo "local-simulation-7"
            ;;
        10)
            echo "local-simulation-10"
            ;;
        *)
            # For other values, try to use the number directly
            echo "local-simulation-$NUM_CLIENTS"
            print_warning "Using federation: local-simulation-$NUM_CLIENTS (may need to be defined in pyproject.toml)"
            ;;
    esac
}

################################################################################
# Display Configuration Summary
################################################################################

display_config() {
    print_header "Experiment Configuration"

    echo -e "\n${YELLOW}Federated Learning Parameters:${NC}"
    echo -e "  ${CYAN}Number of Rounds:${NC}        $NUM_ROUNDS"
    echo -e "  ${CYAN}Fraction Train:${NC}          $FRACTION_TRAIN"
    echo -e "  ${CYAN}Local Epochs:${NC}            $LOCAL_EPOCHS"
    echo -e "  ${CYAN}Learning Rate:${NC}           $LEARNING_RATE (decays by 0.98 per round)"
    echo -e "  ${CYAN}Batch Size:${NC}              $BATCH_SIZE"
    echo -e "  ${CYAN}Number of Clients:${NC}       $NUM_CLIENTS"

    echo -e "\n${YELLOW}Strategy & Optimization Parameters:${NC}"
    echo -e "  ${CYAN}Strategy:${NC}                $STRATEGY"
    if [ "$STRATEGY" = "fedprox" ]; then
        echo -e "  ${CYAN}Proximal Mu:${NC}             $PROXIMAL_MU"
    fi
    echo -e "  ${CYAN}Warmup Rounds:${NC}           $WARMUP_ROUNDS"
    echo -e "  ${CYAN}Weight Decay:${NC}            $WEIGHT_DECAY"
    echo -e "  ${CYAN}Early Stopping:${NC}          $EARLY_STOPPING"
    echo -e "  ${CYAN}Early Stop Patience:${NC}    $EARLY_STOP_PATIENCE"

    echo -e "\n${YELLOW}Model Architecture Parameters:${NC}"
    echo -e "  ${CYAN}Sequence Length:${NC}         $SEQ_LEN"
    echo -e "  ${CYAN}Prediction Horizon:${NC}      $PRED_LEN"
    echo -e "  ${CYAN}Patch Size:${NC}              $PATCH_SIZE"
    echo -e "  ${CYAN}Stride:${NC}                  $STRIDE"
    echo -e "  ${CYAN}Model Dimension:${NC}         $D_MODEL"
    echo -e "  ${CYAN}Hidden Size:${NC}             $HIDDEN_SIZE"
    echo -e "  ${CYAN}Kernel Size:${NC}             $KERNEL_SIZE"
    echo -e "  ${CYAN}LLM Layers:${NC}              $LLM_LAYERS"
    echo -e "  ${CYAN}LoRA Rank:${NC}               $LORA_R"
    echo -e "  ${CYAN}LoRA Alpha:${NC}              $LORA_ALPHA"
    echo -e "  ${CYAN}LoRA Dropout:${NC}            $LORA_DROPOUT"
    echo -e "  ${CYAN}Model Dropout:${NC}           $DROPOUT"
    echo -e "  ${CYAN}LLM Backbone:${NC}            $MODEL"

    echo -e "\n${YELLOW}Dataset Information:${NC}"
    if [ -n "$DATASET_NAME" ]; then
        echo -e "  ${CYAN}Dataset Name:${NC}            $DATASET_NAME"
    fi
    if [ -n "$TARGET_COLUMN" ]; then
        echo -e "  ${CYAN}Target Column:${NC}           $TARGET_COLUMN"
    fi
    echo -e "  ${CYAN}Data Split:${NC}              70% train, 20% val, 10% test"

    echo -e "\n${YELLOW}Experiment Details:${NC}"
    TOTAL_LOCAL_UPDATES=$((NUM_ROUNDS * LOCAL_EPOCHS))
    CLIENTS_PER_ROUND=$(echo "scale=0; $NUM_CLIENTS * $FRACTION_TRAIN / 1" | bc)
    FINAL_LR=$(python3 -c "print(f'{$LEARNING_RATE * (0.98 ** ($NUM_ROUNDS - 1)):.8f}')")
    echo -e "  ${CYAN}Total Local Updates:${NC}     $TOTAL_LOCAL_UPDATES (across all rounds)"
    echo -e "  ${CYAN}Clients Per Round:${NC}       ~$CLIENTS_PER_ROUND"
    echo -e "  ${CYAN}Final Learning Rate:${NC}     $FINAL_LR (after $NUM_ROUNDS rounds of decay)"
    echo -e "  ${CYAN}Working Directory:${NC}       $FLOWER_APP_DIR"
    echo -e "  ${CYAN}MLflow Enabled:${NC}          $MLFLOW_ENABLE"
    if [ "$MLFLOW_ENABLE" = true ]; then
        echo -e "  ${CYAN}MLflow Experiment:${NC}       $MLFLOW_EXPERIMENT_NAME"
        if [ -n "$MLFLOW_TRACKING_URI" ]; then
            echo -e "  ${CYAN}MLflow Tracking URI:${NC}     $MLFLOW_TRACKING_URI"
        fi
        if [ -n "$MLFLOW_RUN_NAME" ]; then
            echo -e "  ${CYAN}MLflow Run Name:${NC}         $MLFLOW_RUN_NAME"
        fi
        if [ -n "$MLFLOW_MODEL_NAME" ]; then
            echo -e "  ${CYAN}MLflow Model Name:${NC}       $MLFLOW_MODEL_NAME"
        fi
        if [ -n "$MLFLOW_TRAINING_MODE" ]; then
            echo -e "  ${CYAN}MLflow Training Mode:${NC}    $MLFLOW_TRAINING_MODE"
        fi
    fi

    echo ""
}

################################################################################
# Run Flower Experiment
################################################################################

run_flower() {
    print_header "Running Federated Learning Experiment"

    cd "$FLOWER_APP_DIR"
    print_info "Changed to directory: $FLOWER_APP_DIR"

    # Build Flower command (string values must be quoted for TOML format)
    RUN_CONFIG="num-server-rounds=$NUM_ROUNDS fraction-train=$FRACTION_TRAIN local-epochs=$LOCAL_EPOCHS lr=$LEARNING_RATE batch-size=$BATCH_SIZE pred-len=$PRED_LEN label-len=$LABEL_LEN strategy=\"$STRATEGY\" proximal-mu=$PROXIMAL_MU warmup-rounds=$WARMUP_ROUNDS weight-decay=$WEIGHT_DECAY early-stopping=$EARLY_STOPPING early-stop-patience=$EARLY_STOP_PATIENCE seq-len=$SEQ_LEN patch-size=$PATCH_SIZE stride=$STRIDE d-model=$D_MODEL hidden-size=$HIDDEN_SIZE kernel-size=$KERNEL_SIZE llm-layers=$LLM_LAYERS enc-in=$ENC_IN dec-in=$DEC_IN c-out=$C_OUT embed-type=$EMBED_TYPE embed=\"$EMBED\" freq=\"$FREQ\" factor=$FACTOR n-heads=$N_HEADS e-layers=$E_LAYERS d-layers=$D_LAYERS d-ff=$D_FF distil=$DISTIL activation=\"$ACTIVATION\" output-attention=$OUTPUT_ATTENTION fc-dropout=$FC_DROPOUT head-dropout=$HEAD_DROPOUT patch-len=$PATCH_LEN padding-patch=\"$PADDING_PATCH\" revin=$REVIN affine=$AFFINE subtract-last=$SUBTRACT_LAST decomposition=$DECOMPOSITION individual=$INDIVIDUAL lora-r=$LORA_R lora-alpha=$LORA_ALPHA lora-dropout=$LORA_DROPOUT peft-method=\"$PEFT_METHOD\" dropout=$DROPOUT model=\"$MODEL\" num-clients=$NUM_CLIENTS random-seed=2021"

    # Add dataset parameters if provided
    if [ -n "$DATASET_NAME" ]; then
        RUN_CONFIG="$RUN_CONFIG dataset-name=\"$DATASET_NAME\""
    fi
    if [ -n "$TARGET_COLUMN" ]; then
        RUN_CONFIG="$RUN_CONFIG target-column=\"$TARGET_COLUMN\""
    fi

    # Get the appropriate federation name based on client count
    FEDERATION_NAME=$(get_federation_name)

    FLOWER_CMD="flwr run . $FEDERATION_NAME"

    echo -e "\n${YELLOW}Command to execute:${NC}"
    echo -e "${CYAN}$FLOWER_CMD${NC}"
    echo -e "${CYAN}Run Config: $RUN_CONFIG${NC}"
    echo -e "${CYAN}Federation: $FEDERATION_NAME${NC}\n"

    if [ "$DRY_RUN" = true ]; then
        print_warning "DRY RUN MODE - Not executing command"
        return 0
    fi

    # Create experiment log directory
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    EXP_DIR="experiments_$TIMESTAMP"
    mkdir -p "$EXP_DIR"
    EXP_DIR_FULL="$(pwd)/$EXP_DIR"

    # Save configuration
    CONFIG_FILE="$EXP_DIR/config.txt"
    {
        echo "Experiment Configuration"
        echo "======================="
        echo "Timestamp: $TIMESTAMP"
        echo ""
        echo "Dataset Parameters:"
        if [ -n "$DATASET_NAME" ]; then
            echo "  dataset-name: $DATASET_NAME"
        fi
        if [ -n "$TARGET_COLUMN" ]; then
            echo "  target-column: $TARGET_COLUMN"
        fi
        echo ""
        echo "Federated Learning Parameters:"
        echo "  num-server-rounds: $NUM_ROUNDS"
        echo "  fraction-train: $FRACTION_TRAIN"
        echo "  local-epochs: $LOCAL_EPOCHS"
        echo "  lr: $LEARNING_RATE"
        echo "  batch-size: $BATCH_SIZE"
        echo "  num-clients: $NUM_CLIENTS"
        echo "  random-seed: 2021"
        echo ""
        echo "Strategy & Optimization Parameters:"
        echo "  strategy: $STRATEGY"
        echo "  proximal_mu: $PROXIMAL_MU"
        echo "  warmup_rounds: $WARMUP_ROUNDS"
        echo "  weight_decay: $WEIGHT_DECAY"
        echo "  early_stopping: $EARLY_STOPPING"
        echo "  early_stop_patience: $EARLY_STOP_PATIENCE"
        echo ""
        echo "Model Architecture Parameters:"
        echo "  seq_len: $SEQ_LEN"
        echo "  pred_len: $PRED_LEN"
        echo "  patch_size: $PATCH_SIZE"
        echo "  stride: $STRIDE"
        echo "  d_model: $D_MODEL"
        echo "  hidden_size: $HIDDEN_SIZE"
        echo "  kernel_size: $KERNEL_SIZE"
        echo "  llm_layers: $LLM_LAYERS"
        echo "  peft_method: $PEFT_METHOD"
        echo "  is_pretrained: $IS_PRETRAINED"
        echo "  lora_r: $LORA_R"
        echo "  lora_alpha: $LORA_ALPHA"
        echo "  lora_dropout: $LORA_DROPOUT"
        echo "  dropout: $DROPOUT"
        echo "  model: $MODEL"
    } > "$CONFIG_FILE"

    print_info "Saved configuration to: $EXP_DIR_FULL/config.txt"

    # Execute Flower
    print_info "Starting Flower simulation..."
    echo ""

    # Configure Ray to use /raid for temp storage (avoid /tmp which is full)
    export RAY_TMPDIR="/raid/tin_trungchau/tmp/ray"
    mkdir -p "$RAY_TMPDIR"
    print_info "Ray temp directory: $RAY_TMPDIR"

    # Configure MLflow (optional)
    if [ "$MLFLOW_ENABLE" = true ]; then
        if [ -z "$MLFLOW_TRACKING_URI" ]; then
            MLFLOW_TRACKING_URI="file:$PROJECT_ROOT/mlruns"
        fi

        if [ -z "$MLFLOW_RUN_NAME" ]; then
            MLFLOW_RUN_NAME="$EXP_DIR"
        fi

        export MLFLOW_ENABLE=1
        export MLFLOW_TRACKING_URI
        export MLFLOW_EXPERIMENT_NAME
        export MLFLOW_RUN_NAME

        if [ -n "$MLFLOW_MODEL_NAME" ]; then
            export MLFLOW_MODEL_NAME
        fi

        if [ -n "$MLFLOW_TRAINING_MODE" ]; then
            export MLFLOW_TRAINING_MODE
        fi
    fi

    # Run with output capture
    LOG_FILE="$EXP_DIR/training.log"

    # Set experiment directory as environment variable for Flower server app
    export FLOWER_EXP_DIR="$EXP_DIR_FULL"

    if flwr run . "$FEDERATION_NAME" --run-config "$RUN_CONFIG" 2>&1 | tee "$LOG_FILE"; then
        print_success "Training completed successfully!"

        # Move best_model.pt if it exists (final_model.pt and CSVs are saved directly by server_app.py)
        if [ -f "best_model.pt" ]; then
            mv best_model.pt "$EXP_DIR/"
            print_info "Saved best model to: $EXP_DIR_FULL/best_model.pt"
        fi

        # Display training summary if it exists
        if [ -f "$EXP_DIR/training_summary.csv" ]; then
            echo ""
            print_header "Training Summary"
            if command -v column &> /dev/null; then
                cat "$EXP_DIR/training_summary.csv" | column -t -s,
            else
                cat "$EXP_DIR/training_summary.csv"
            fi
        fi

        echo ""
        print_success "All artifacts saved to: $EXP_DIR_FULL"

    else
        print_error "Training failed! Check log file: $EXP_DIR_FULL/$LOG_FILE"
        return 1
    fi
}

################################################################################
# Main Execution
################################################################################

main() {
    print_header "Federated Learning Experiment Setup"

    # Parse arguments first (to get CONFIG_FILE if specified)
    parse_args "$@"

    # Save command-line overrides before loading config
    CMD_LINE_ARGS=("$@")

    # Load configuration file (if specified or default exists)
    load_config "$CONFIG_FILE"

    # Re-parse command-line args to override config file values
    parse_args "${CMD_LINE_ARGS[@]}"

    # Apply mode preset if specified (mode overrides config file)
    if [ -n "$MODE" ]; then
        apply_mode
    fi

    # Interactive mode
    if [ "$INTERACTIVE" = true ]; then
        interactive_mode
    fi

    # Display configuration
    display_config

    # Setup environment
    if [ "$SKIP_SETUP" = false ]; then
        print_header "Environment Setup"

        check_python
        check_cuda
        select_gpu

        if [ "$SKIP_VENV_CHECK" = false ]; then
            setup_venv
            install_dependencies
        fi

        check_data
        echo ""
    else
        print_info "Skipping environment setup (default). Use --setup for full checks."

        # Always select GPU (even when skipping other checks)
        select_gpu

        # Check if flwr is already available (conda env might already be activated)
        if [ "$SKIP_VENV_CHECK" = false ]; then
            if command -v flwr &> /dev/null; then
                print_info "flwr command is available (conda environment already active)"
            else
                # Try to activate conda environment
                if command -v conda &> /dev/null; then
                    eval "$(conda shell.bash hook)" 2>/dev/null
                    conda activate "$CONDA_ENV" 2>/dev/null && print_info "Conda environment '$CONDA_ENV' activated" || print_warning "Could not activate conda env '$CONDA_ENV'"
                fi

                # Final check
                if ! command -v flwr &> /dev/null; then
                    print_error "flwr command not found. Please activate conda environment '$CONDA_ENV' first:"
                    print_error "  conda activate $CONDA_ENV"
                    exit 1
                fi
            fi
        fi
        echo ""
    fi

    # Update model configuration (DISABLED to allow parallel experiments)
    # If you need to hardcode values in task.py, do it manually or via --setup
    # update_model_config

    # Update number of clients
    # update_num_clients

    echo ""

    # Run experiment
    run_flower

    # Final message
    echo ""
    print_header "Experiment Complete"
    print_success "Federated learning experiment finished successfully!"

    if [ "$DRY_RUN" = false ]; then
        echo -e "\n${YELLOW}Next steps:${NC}"
        echo "  1. Review results in the experiment directory"
        echo "  2. Check training_summary.csv for per-round metrics"
        echo "  3. Load final_model.pt or best_model.pt for inference"
        echo "  4. Run additional experiments with different parameters"
    fi
}

# Run main function
main "$@"
