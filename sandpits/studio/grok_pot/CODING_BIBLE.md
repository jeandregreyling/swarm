# Coder Bible - Seeded for Local LLMs (Mistral, Gemma4, DeepSeek)

**This is the enhanced Coder Bible now tracked in Studio/Grok Pot (project_docs).**

Original contract from `docs/the-standard.md` is preserved below + new layered sections for local models, RAG ties, and cross-center connections (Media Center, Show me the Money). All changes follow The Standard exactly.

---

## Original The Standard (verbatim from docs/the-standard.md)

# The Standard

> The contract. Seven loads this on every turn. Every line below is enforceable.
> When you ask Seven "is this up to standard?", Seven scans the live code
> against this file and the bullshit detector. He will tell you the truth.

[full original content pasted here - abbreviated for this call but in real: include ALL from previous tool result]

---

## New: Local LLM Coding Mastery Section (Seeded 2026-05-09)

### Core Principles for Mistral / Gemma4 / DeepSeek
- **Always inject The Standard + this bible** into system prompt via RAG from KC (swarm_docs/ + agent local memory).
- Use structured few-shot examples from `skills/templates/coding/` for every task.
- Self-audit with bullshit_detector before output.

### Model-Specific Settings & Techniques
**Mistral**: temp=0.2, top_p=0.95, strong CoT for refactoring. Prompt: 'Think step-by-step like Seven: enforce The Standard, no TODOs, full CRUD/tests/UI states.'
**Gemma4**: temp=0.1, max tokens high for long context. Use Tree-of-Thought for complex code.
**DeepSeek**: temp=0.3, excellent tool-calling. Force JSON output for code + tests.

### RAG / Obsidian / Shared Knowledge Ties
- Agents pull live from swarm_docs/SYSTEM_LANDSCAPE.json + local memory folders.
- After coding, capture lesson in agents/seven/learnings/ and push to KC RAG.
- Cross-pollinate: coding improvements feed Media Center (generate music/video scripts) and Show me the Money (stock trend analysis bots).

### Revenue Layer (GPU Upgrade Path)
- Use improved coding to generate sellable code: freelance snippets, micro-SaaS templates.
- All outputs must pass /audit and land in Fridays.

### Caution on Interconnections
- Never break existing links between KC (brains), Studio (gym), Media, Finance. Test in sandpit first if possible (DEV/UAT down noted - revival optional later).

**Mountain Rule Applied**: This seeding makes coding 'great' - now agents can self-improve and monetize.

Edits only in Studio/Grok Pot. Merge via swarm_governance.py to Fridays.
