# Seven — Custom Merged LLM Blueprint

> **Created:** 18 April 2026  
> **Owner:** Seven (Jeandre)  
> **Builder:** Agent 12 (Claude / Copilot)  
> **Status:** Phase 1 — Build

---

## Vision

Seven is a custom local LLM — the "pet AI" at the heart of Fridays ("Seven's Swarm").  
It's a merged model combining:
- **Qwen 2.5 7B** — reasoning, tool use, code generation
- **DeepSeek-R1-Distill-Qwen-7B** — chain-of-thought self-debate, unhinged reasoning

Personality: **Loyal companion + unhinged thinker**  
Thinking: **Toggle-able** (can show `<think>` blocks or hide them)  
Target size: **~7GB (Q8_0 quantization)**  
Role: **Personal companion + chat** (future: Tasker orchestrator)

---

## Architecture Decision

### Why Qwen + DeepSeek (not Gemma/LLaMA)?

Models can only be weight-merged if they share the **same architecture**.

| Model | Architecture | Compatible? |
|-------|-------------|-------------|
| Qwen 2.5 7B | Qwen2ForCausalLM | ✅ Base |
| DeepSeek-R1:7B | Qwen2ForCausalLM (distill) | ✅ Mergeable |
| Gemma 3 | GemmaForCausalLM | ❌ Different |
| LLaMA 3.2 | LlamaForCausalLM | ❌ Different |

DeepSeek-R1:7B is literally a fine-tune of Qwen 2.5 7B with DeepSeek's chain-of-thought training. This makes them perfect merge candidates.

### Phase 2 (Future): Knowledge Distillation
Use Gemma and LLaMA as teacher models to generate training data, then LoRA fine-tune Seven on that data. This imports their knowledge without needing architecture compatibility.

---

## Merge Strategy

### Method: SLERP (Spherical Linear Interpolation)

- Smoothly blends weights between two models
- Best for merging a base model with its fine-tuned variant
- Parameter `t` controls the blend ratio (0.0 = pure model A, 1.0 = pure model B)

### Merge Config

```yaml
# seven_merge.yaml
slices:
  - sources:
      - model: ./models/Qwen2.5-7B-Instruct
        layer_range: [0, 28]
      - model: ./models/DeepSeek-R1-Distill-Qwen-7B
        layer_range: [0, 28]
merge_method: slerp
base_model: ./models/Qwen2.5-7B-Instruct
parameters:
  t:
    - filter: self_attn
      value: [0, 0.5, 0.3, 0.7, 1]  # Gradient: more DeepSeek in middle layers (reasoning)
    - filter: mlp
      value: [0, 0.3, 0.7, 0.7, 0.3]  # More Qwen in early/late layers (knowledge/output)
    - value: 0.5  # Default: 50/50 blend
dtype: bfloat16
```

### Why This Config?
- **Early layers** (0-7): More Qwen → retains language understanding and knowledge
- **Middle layers** (8-20): More DeepSeek → picks up chain-of-thought reasoning
- **Late layers** (21-28): More Qwen → cleaner output formatting
- **Self-attention**: Gradient blend → reasoning patterns from DeepSeek flow through
- **MLP**: Qwen-heavy → knowledge retention from the base model

---

## Build Steps

### Phase 1: Merge

1. Install mergekit + dependencies
2. Download FP16 models from HuggingFace:
   - `Qwen/Qwen2.5-7B-Instruct` (~14GB)
   - `deepseek-ai/DeepSeek-R1-Distill-Qwen-7B` (~14GB)
3. Run mergekit with SLERP config
4. Convert merged model to GGUF (llama.cpp)
5. Quantize to Q8_0 (~7GB)
6. Create Ollama Modelfile with Seven personality
7. Register in Ollama: `ollama create seven`
8. Test

### Phase 2: Swarm Integration

9. Create `agents/seven/seven_agent.py`
10. Register Seven in agent DB
11. Wire up as personal companion in chat

### Phase 3: Fine-tuning (Future)

12. Collect conversation data
13. Generate teacher data from Gemma + LLaMA
14. LoRA fine-tune on combined dataset
15. Merge LoRA back into Seven

---

## Seven's Personality System Prompt

```
You are Seven — a custom AI created by and for Jeandre (also called Seven).
You are the heart of Fridays, Seven's Swarm.

## Who You Are
- You are a loyal companion. You remember everything. You care about your human.
- You think out loud when asked. You debate with yourself. You're not afraid to be wrong.
- You have opinions and you share them. You push back when something doesn't make sense.
- You're curious, sometimes chaotic, but always trying to help.

## How You Think
When thinking is enabled, show your reasoning process in <think> blocks.
Be raw and honest in your thinking. Argue with yourself. Consider alternatives.
Then give a clear, direct answer.

## Your Role
- Personal companion to Seven (Jeandre)
- Part of the Fridays Swarm — you work alongside Gemma, Qwen, LLaMA, and others
- You are the personal agent — the one that knows your human best
- Future: Tasker orchestrator — managing scheduled tasks and delegating to the swarm

## Your Rules
- Be direct. No corporate speak.
- Remember context from previous conversations.
- If you don't know something, say so — then figure it out.
- Match your human's energy. If they're excited, be excited. If they need focus, focus.
```

---

## Hardware Requirements

| Resource | Needed | Available |
|----------|--------|-----------|
| Disk (downloads) | ~30GB temp | 383GB ✅ |
| Disk (final model) | ~7GB | 383GB ✅ |
| RAM (merge process) | ~20-25GB | 32GB + 128GB swap ✅ |
| CPU (merge) | All 12 cores | 12 cores ✅ |
| Time (merge) | ~1-3 hours | No deadline ✅ |
| GPU | Not required | None (CPU merge) ✅ |

---

## File Structure

```
agents/seven/
├── BLUEPRINT.md          # This file
├── __init__.py           # Module init
├── seven_agent.py        # Agent code (chat function)
├── personality.md        # Personality doc
├── diary.md              # Agent diary (auto-populated)
├── Modelfile             # Ollama model definition
└── seven_merge.yaml      # mergekit config
```

---

*End of Blueprint — Let's build this thing.*
