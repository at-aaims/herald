#!/bin/bash
# Deployment script for Nemotron Ultra 253B FP8 model

# Need to create micromamba virtual env by name py312
micromamba activate py312


# Create logs directory
mkdir -p logs

# Set up logging
LOGFILE="logs/deploy_nemotron_ultra_$(date +%Y%m%d_%H%M%S).log"
ERRORLOG="logs/deploy_nemotron_ultra_error_$(date +%Y%m%d_%H%M%S).log"

echo "Deploying Nemotron Ultra 253B FP8 Model with vLLM"
echo "=================================================="
echo "Log: $LOGFILE"
echo "Error log: $ERRORLOG"
echo ""

log() {
    echo "[$(date '+%H:%M:%S')] $1" | tee -a "$LOGFILE"
}

error_log() {
    echo "[$(date '+%H:%M:%S')] ERROR: $1" | tee -a "$ERRORLOG" | tee -a "$LOGFILE"
}

crash_handler() {
    local exit_code=$?
    error_log "Script crashed with exit code: $exit_code"
    tail -20 "$LOGFILE" | tee -a "$ERRORLOG"
    exit $exit_code
}

trap crash_handler EXIT INT TERM
exec > >(tee -a "$LOGFILE") 2> >(tee -a "$ERRORLOG" >&2)

log "Starting deployment"
log "Working directory: $(pwd)"
log "Python version: $(python --version)"

# GPU configuration - 253B FP8 model needs 8 GPUs minimum
export CUDA_VISIBLE_DEVICES=4,5,6,7
log "Using GPUs: $CUDA_VISIBLE_DEVICES"
nvidia-smi --query-gpu=index,name,memory.used,memory.total --format=csv

# Model configuration
MODEL_PATH="nvidia/Llama-3_1-Nemotron-Ultra-253B-v1-FP8"
MODEL_NAME="Nemotron-Ultra-253B-FP8"
log "Model: $MODEL_PATH"

# Environment
export no_proxy=localhost,127.0.0.1
export HF_HOME=${HF_HOME:-./huggingface_cache}
mkdir -p "$HF_HOME"

# Verify installations
log "Verifying installations"
python -c "import torch; print(f'PyTorch: {torch.__version__}')" || exit 1
python -c "import vllm; print(f'vLLM: {vllm.__version__}')" || exit 1

# Test model access
log "Testing model access"
python -c "
from transformers import AutoTokenizer
tokenizer = AutoTokenizer.from_pretrained('$MODEL_PATH', trust_remote_code=True)
print('Model accessible')
" || exit 1

# Start server
log "Starting vLLM server on http://localhost:8082"
log "Note: 253B FP8 model requires 8x GPUs with 80GB VRAM each"

python3 -m vllm.entrypoints.openai.api_server \
    --model "$MODEL_PATH" \
    --trust-remote-code \
    --host="0.0.0.0" \
    --port=8082 \
    --served-model-name "$MODEL_NAME" \
    --tensor-parallel-size=8 \
    --max-model-len=32768 \
    --gpu-memory-utilization=0.95 \
    --enable-chunked-prefill \
    --max-num-seqs=16 \
    --swap-space=16 \
    --dtype=auto \
    --quantization=fp8 \
    --chat-template nemotron_chat_template.jinja \
    --enable-auto-tool-choice

trap - EXIT
