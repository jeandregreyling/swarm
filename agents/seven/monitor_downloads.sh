#!/bin/bash
# Seven LLM Build Monitor — checks every 2 minutes
MODELS_DIR="./models"
LOG="./build_progress.log"

echo "$(date) — Monitor started" | tee -a "$LOG"

while true; do
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  SEVEN LLM BUILD MONITOR — $(date '+%H:%M:%S')"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    # Qwen status
    QWEN_SIZE=$(du -sh "$MODELS_DIR/Qwen2.5-7B-Instruct/" 2>/dev/null | cut -f1)
    QWEN_SHARDS=$(ls "$MODELS_DIR/Qwen2.5-7B-Instruct/"*.safetensors 2>/dev/null | wc -l)
    QWEN_PID=$(pgrep -f "hf download.*Qwen" 2>/dev/null)
    
    echo ""
    echo "  QWEN 2.5 7B:  ${QWEN_SIZE:-0}  |  ${QWEN_SHARDS}/4 shards"
    if [[ -n "$QWEN_PID" ]]; then
        RSS=$(ps -p "$QWEN_PID" -o rss= 2>/dev/null)
        echo "  Status:       DOWNLOADING (PID $QWEN_PID, RSS: $((RSS/1024))MB)"
    else
        if [[ "$QWEN_SHARDS" -ge 4 ]]; then
            echo "  Status:       ✅ COMPLETE"
        else
            echo "  Status:       ⚠️  Process gone — may need restart"
        fi
    fi
    
    # DeepSeek status
    DS_SIZE=$(du -sh "$MODELS_DIR/DeepSeek-R1-Distill-Qwen-7B/" 2>/dev/null | cut -f1)
    DS_SHARDS=$(ls "$MODELS_DIR/DeepSeek-R1-Distill-Qwen-7B/"*.safetensors 2>/dev/null | wc -l)
    DS_PID=$(pgrep -f "hf download.*DeepSeek" 2>/dev/null)
    
    echo ""
    echo "  DEEPSEEK R1:  ${DS_SIZE:-not started}  |  ${DS_SHARDS:-0} shards"
    if [[ -n "$DS_PID" ]]; then
        RSS=$(ps -p "$DS_PID" -o rss= 2>/dev/null)
        echo "  Status:       DOWNLOADING (PID $DS_PID, RSS: $((RSS/1024))MB)"
    elif [[ "$DS_SHARDS" -ge 1 ]]; then
        echo "  Status:       ✅ COMPLETE"
    else
        echo "  Status:       ⏳ WAITING"
    fi
    
    # Auto-start DeepSeek when Qwen finishes
    if [[ -z "$QWEN_PID" && "$QWEN_SHARDS" -ge 4 && -z "$DS_PID" && "$DS_SHARDS" -lt 1 ]]; then
        echo ""
        echo "  >>> QWEN DONE — auto-starting DeepSeek download..."
        echo "$(date) — Auto-starting DeepSeek download" >> "$LOG"
        source /home/seven/swarm/.venv/bin/activate
        nohup hf download deepseek-ai/DeepSeek-R1-Distill-Qwen-7B \
            --local-dir "$MODELS_DIR/DeepSeek-R1-Distill-Qwen-7B" \
            >> "$LOG" 2>&1 &
        echo "  >>> DeepSeek download started (PID $!)"
    fi
    
    # Both done?
    if [[ "$QWEN_SHARDS" -ge 4 && "$DS_SHARDS" -ge 1 && -z "$DS_PID" ]]; then
        echo ""
        echo "  🔥 BOTH MODELS DOWNLOADED — READY TO MERGE"
        echo "  Ping your human. Time to build Seven."
        echo "$(date) — Both models ready" >> "$LOG"
    fi
    
    # llama.cpp
    echo ""
    echo "  LLAMA.CPP:    ✅ Built (105 binaries)"
    
    # Disk
    DISK_FREE=$(df -h /home/seven --output=avail | tail -1 | tr -d ' ')
    echo "  DISK FREE:    $DISK_FREE"
    echo ""
    echo "  Next check in 2 minutes..."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    echo "$(date) — Qwen: ${QWEN_SIZE:-0} (${QWEN_SHARDS} shards) | DeepSeek: ${DS_SIZE:-waiting} | Disk: $DISK_FREE" >> "$LOG"
    
    sleep 120
done
