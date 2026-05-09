# Coder Bible - Enhanced for Local LLMs (Mistral, Gemma4, DeepSeek)

This is the living Coder Bible for all agents and local models in the Swarm.

## Core Principles (from the-standard.md)
- No TODOs in production
- Four UI states
- Mountain Rule
- Single Stamp approval

## Model-Specific Guidance

### General Best Practices for Local Coding LLMs
- Temperature: 0.2 or lower for deterministic code generation
- Top-p: 0.95
- Use strong Chain-of-Thought and explicit step-by-step instructions
- Always include full context, file paths, existing code snippets
- Enforce the-standard.md on every output

### Mistral Models
- Strengths: Fast, good at following complex instructions
- Prompt style: Clear, structured, use XML tags or markdown sections
- Recommended: Low temperature, repeat key constraints

### Gemma4
- ... (fill based on knowledge)

### DeepSeek
- Excellent at code reasoning
- ... 

Edits now tracked via Grok Pot in Studio.
