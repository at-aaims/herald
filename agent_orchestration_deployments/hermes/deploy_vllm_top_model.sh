#!/bin/bash
# Deployment script for agentic module

# Create logs directory
mkdir -p logs

# Set up logging
LOGFILE="logs/deploy_debug_$(date +%Y%m%d_%H%M%S).log"
ERRORLOG="logs/deploy_error_$(date +%Y%m%d_%H%M%S).log"

echo "Deploying Agentic Model with vLLM"
echo "====================================="
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

# GPU configuration
export CUDA_VISIBLE_DEVICES=0
log "Using GPU: $CUDA_VISIBLE_DEVICES"
nvidia-smi --query-gpu=index,name,memory.used,memory.total --format=csv


MODEL_PATH="NousResearch/Hermes-4-14B-FP8"
MODEL_NAME="Hermes-4-14B-FP8"
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

python3 -m vllm.entrypoints.openai.api_server \
    --model "$MODEL_PATH" \
    --trust-remote-code \
    --host="0.0.0.0" \
    --port=8082 \
    --served-model-name "$MODEL_NAME" \
    --tensor-parallel-size=1 \
    --max-model-len=8192 \
    --gpu-memory-utilization=0.8 \
    --tool-call-parser hermes \
    --chat-template chat_template.jinja \
    --enable-auto-tool-choice

trap - EXIT