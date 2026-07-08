#!/bin/bash
# ============================================================
# vLLM Qwen2.5-VL-7B 启动脚本 (WSL2)
# ============================================================
# 使用: bash start_vllm.sh [--force]
#
# 环境变量:
#   VLLM_USE_FLASHINFER_SAMPLER=0  禁用FlashInfer (WSL无nvcc)
# ============================================================
set -euo pipefail

export VLLM_USE_FLASHINFER_SAMPLER=0
export PATH=/usr/bin:/bin:/usr/local/bin

# ---- 配置 ----
MODEL_DIR="${HF_HOME:-/mnt/c/Users/Administrator/.cache/huggingface/hub}/models--Qwen--Qwen2.5-VL-7B-Instruct/snapshots"
MODEL_SNAPSHOT=$(ls -1t "$MODEL_DIR" 2>/dev/null | head -1)
MODEL_PATH="$MODEL_DIR/$MODEL_SNAPSHOT"

HOST="0.0.0.0"
PORT="${VLLM_PORT:-8000}"
MAX_MODEL_LEN="${VLLM_MAX_LEN:-4096}"
GPU_MEM_UTIL="${VLLM_GPU_UTIL:-0.85}"

# WSL下不能用torch.compile和CUDAGraph
ENFORCE_EAGER="--enforce-eager"

LOG_DIR="/home/administrator"
PID_FILE="$LOG_DIR/vllm.pid"
LOG_FILE="$LOG_DIR/vllm.log"

# ---- 函数 ----
log() { echo "[$(date '+%H:%M:%S')] $*"; }

check_stale() {
    if [ -f "$PID_FILE" ]; then
        local old_pid=$(cat "$PID_FILE")
        if kill -0 "$old_pid" 2>/dev/null; then
            log "发现运行中的 vLLM (PID $old_pid)"
            if [ "${1:-}" = "--force" ]; then
                log "强制停止..."
                kill "$old_pid" 2>/dev/null || true
                sleep 3
                kill -9 "$old_pid" 2>/dev/null || true
                rm -f "$PID_FILE"
            else
                log "vLLM 已在运行 (http://${HOST}:${PORT})"
                exit 0
            fi
        else
            rm -f "$PID_FILE"
        fi
    fi
}

# ---- 主流程 ----
check_stale "${1:-}"

log "验证模型路径: $MODEL_PATH"
if [ ! -d "$MODEL_PATH" ]; then
    log "ERROR: 模型未找到: $MODEL_PATH"
    exit 1
fi

log "启动 vLLM..."
log "  Model: Qwen2.5-VL-7B-Instruct"
log "  Host: $HOST:$PORT"
log "  Max model len: $MAX_MODEL_LEN"
log "  GPU mem util: $GPU_MEM_UTIL"
log "  FlashInfer sampler: disabled"
log "  Log: $LOG_FILE"

nohup /mnt/d/EduNUWA/.venv/bin/vllm serve "$MODEL_PATH" \
    --host "$HOST" \
    --port "$PORT" \
    --max-model-len "$MAX_MODEL_LEN" \
    --gpu-memory-utilization "$GPU_MEM_UTIL" \
    $ENFORCE_EAGER \
    > "$LOG_FILE" 2>&1 &

VLLM_PID=$!
echo "$VLLM_PID" > "$PID_FILE"

log "vLLM 已启动 PID=$VLLM_PID"

# 等待服务就绪 (最多5分钟)
log "等待服务就绪..."
for i in $(seq 1 60); do
    sleep 5
    if curl -s "http://${HOST}:${PORT}/health" > /dev/null 2>&1; then
        log "vLLM 服务就绪 (http://${HOST}:${PORT})"
        exit 0
    fi
    log "  ... ${i}x5s"
done

log "启动超时，请检查日志: $LOG_FILE"
exit 1
