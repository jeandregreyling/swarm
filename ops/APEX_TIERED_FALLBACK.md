# APEX Tiered Model Fallback - Online Assistance for Local APEX

## Problem Statement

APEX is currently hardcoded to use only `qwen2.5:14b-instruct` as a local model with **no fallback mechanism**. When APEX hits context limits (16384 tokens), it fails with no way to get assistance from online models.

From `core/chat_continuity.py`:
```python
# APEX (Qwen2.5-14B-Instruct on the externally owned llama-server) is the only routing
# target for local chat. The registry name maps to the service's api_model
# alias; no other model fallback exists on this lane.
APEX_AGENT = {"name": "apex", "model": "qwen2.5:14b-instruct", "tier": "local", "label": "APEX"}
```

## Solution: Tiered Model Assistant

This adds a **tiered fallback system** that allows online models to assist APEX when:
1. Local context is exhausted
2. Complex reasoning is needed beyond local model capabilities
3. Specialized knowledge is required

### Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         User Request                                │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          APEX (Local)                                │
│                     qwen2.5:14b-instruct                              │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │                    Try Local Model                             ││
│  └─────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┴─────────────────────┐
        │                                   │
        ▼                                   ▼
┌─────────────────┐               ┌────────────────────────────┐
│  Context OK     │               │ Context Exhausted / Error │
│  Return Result  │               │                           │
└─────────────────┘               └───────────┬───────────────┘
                                                │
                                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Tiered Assistant (Online)                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │
│  │   Tier 1     │  │   Tier 2     │  │   Tier 3     │             │
│  │  gpt-4o      │  │   gpt-4      │  │     o1       │             │
│  │  gpt-4o-mini │  │  claude-3    │  │   o1-mini    │             │
│  └──────────────┘  └──────────────┘  └──────────────┘             │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Response Routing                                  │
│  Online model response injected back into APEX conversation         │
└─────────────────────────────────────────────────────────────────────┘
```

## Quick Setup

### 1. Add Tiered Assistant to Service Accounts

The tiered-assistant has already been added to `core/service_accounts.py`. When the database initializes, it will create the service principal.

### 2. Configure Online Models

Edit `ops/llm_registry.yaml` to add your online model configurations:

```yaml
models:
  # Your existing local models...
  
  # Add online models for tiered fallback
  - name: gpt-4o
    driver: openai
    role: reasoner
    tier: online
    endpoint: https://api.openai.com/v1
    options:
      api_key_var: OPENAI_API_KEY
      model: gpt-4o
      temperature: 0.2
      
  - name: gpt-4o-mini
    driver: openai
    role: reasoner
    tier: online
    options:
      api_key_var: OPENAI_API_KEY
      model: gpt-4o-mini
      temperature: 0.2
      
  - name: claude-3-5-sonnet
    driver: openai
    role: analyst
    tier: online
    endpoint: https://api.anthropic.com/v1
    options:
      api_key_var: ANTHROPIC_API_KEY
      model: claude-3-5-sonnet-20250620
```

### 3. Set Environment Variables

```bash
# OpenAI
export OPENAI_API_KEY=sk-...

# Anthropic
export ANTHROPIC_API_KEY=sk_ant-...

# Enable SEVEN_RUNTIME if using the new registry system
export SEVEN_RUNTIME=1
```

### 4. Run Configuration Script

```bash
python ops/apex_tiered_config.py
```

This will:
- Register the tiered-assistant service principal
- Install the monkey-patch for APEX fallback
- Configure the peer bridge for tiered communication

### 5. Update peer_bridge.py

Add the tiered-assistant to the MENTIONS and SCOPES in `core/peer_bridge.py`:

```python
MENTIONS = {
    "instructor": "copilot-instructor",
    "copilot": "copilot-instructor",
    "gemini": "gemini-advisor",
    "codex": "codex-instructor",
    "tiered-assistant": "tiered-assistant",
    "tiered": "tiered-assistant",
}

SCOPES = {
    "copilot-instructor": ("peer.read", "peer.post", "peer.memory", "peer.relay:gemini-advisor"),
    "gemini-advisor": ("peer.read", "peer.post", "peer.memory"),
    "codex-instructor": ("peer.read", "peer.post", "peer.memory"),
    "tiered-assistant": ("peer.read", "peer.post", "peer.memory", "peer.relay:apex"),
}
```

## Usage

### Automatic Fallback (Recommended)

When APEX hits a context limit, it will **automatically** dispatch to the tiered assistant:

```python
# In your chat handler
from core.apex_tiered_assistant import call_apex_with_tiered_fallback

# Use this instead of the original call_apex
text, tokens = call_apex_with_tiered_fallback(
    call_model, 
    APEX_AGENT["model"], 
    messages,
    conn=db_conn,
    conversation_id=conversation_id
)
```

### Manual Dispatch

You can manually request tiered assistance in any APEX conversation:

```
[DISPATCH: @tiered-assistant] Please analyze this complex architecture problem
```

The tiered assistant will:
1. Select the best online model for the task
2. Route the request
3. Return the response to the APEX conversation

### Programmatic Dispatch

```python
from core.apex_tiered_assistant import create_tiered_dispatch_message

# Create a dispatch message
dispatch_msg = create_tiered_dispatch_message(
    "Context exhausted - need help with multi-step reasoning",
    conversation_id=12345,
    apex_message_id=67890
)

# Post to peer bridge
from core.peer_bridge import post_to_peer
post_to_peer(conn, dispatch_msg)
```

## Model Selection Logic

The tiered assistant automatically selects the best model based on task complexity:

| Task Type | Models | Use Case |
|-----------|--------|----------|
| **Tier 1** | gpt-4o, gpt-4o-mini, claude-3-5-sonnet | General questions, quick assistance |
| **Tier 2** | gpt-4, claude-3-opus | Analysis, code review, detailed questions |
| **Tier 3** | o1, o1-mini | Complex reasoning, multi-step problems, debugging |

The selection is based on keywords in the request:
- **Tier 3**: debug, diagnose, investigate, root cause, architecture, design, multi-step, complex
- **Tier 2**: review, analyze, explain, optimize, improve, refactor, verify, validate
- **Tier 1**: Everything else

## Testing

### Test Context Exhaustion

```python
from core.apex_tiered_assistant import call_apex_with_tiered_fallback, APEX_AGENT

# Create a very long prompt that exceeds APEX context
long_prompt = "..." * 20000  # More than 16384 tokens

messages = [{"role": "user", "content": long_prompt}]

try:
    text, tokens = call_apex_with_tiered_fallback(
        call_model,
        APEX_AGENT["model"],
        messages,
        conversation_id=123
    )
except RuntimeError as e:
    if "TIERED ASSISTANCE NEEDED" in str(e):
        print("✓ Tiered fallback triggered correctly")
```

### Test Manual Dispatch

```python
from core.apex_tiered_assistant import create_tiered_dispatch_message

msg = create_tiered_dispatch_message(
    "Help me understand this complex algorithm",
    conversation_id=123
)

print(f"Dispatch message: {msg}")
# Should show: [APEX HANDOFF: context exhausted] Help me understand...
```

## Integration with Existing Code

### chat.py Blueprints

In `frontend/blueprints/chat.py`, the `_run_apex_chat` or similar function should use the tiered fallback wrapper:

```python
# Before
def _run_apex_chat(...):
    text, tokens = call_apex(call_model, APEX_AGENT["model"], messages)
    ...

# After
def _run_apex_chat(...):
    text, tokens = call_apex_with_tiered_fallback(
        call_model, 
        APEX_AGENT["model"], 
        messages,
        conn=db_conn,
        conversation_id=conversation_id
    )
    ...
```

### apex_tools.py

The `run_apex_tools` function should also use the tiered wrapper:

```python
# In core/apex_tools.py
from core.apex_tiered_assistant import call_apex_with_tiered_fallback

# Replace the call to call_apex
text, used = call_apex_with_tiered_fallback(
    call_model, 
    APEX_AGENT["model"], 
    working,
    conn=conn,
    conversation_id=conversation_id
)
```

## Customization

### Add Custom Models

Edit `core/apex_tiered_assistant.py` to add your preferred models:

```python
ONLINE_TIERS = {
    "tier1": {"models": ["gpt-4o", "gpt-4o-mini", "gemini-2.5-flash"], "role": "reasoner"},
    "tier2": {"models": ["gpt-4", "claude-3-opus", "gemini-2.5-pro"], "role": "analyst"},
    "tier3": {"models": ["o1", "o1-mini"], "role": "solver"},
}
```

### Custom Selection Logic

Override `_get_online_model_for_task` to implement your own selection logic:

```python
def _get_online_model_for_task(task_description: str) -> str | None:
    # Your custom logic here
    if "code" in task_description.lower():
        return "claude-3-opus"  # Best for coding
    elif "math" in task_description.lower():
        return "o1"  # Best for reasoning
    return "gpt-4o"  # Default
```

## Troubleshooting

### "No tiered assistant registered"

Run the configuration script:
```bash
python ops/apex_tiered_config.py
```

### "Peer bridge not available"

Ensure the peer_bridge tables exist in your database:
```python
from core.peer_bridge import ensure_schema
from database import get_connection
conn = get_connection()
ensure_schema(conn)
conn.close()
```

### "Model not found"

Check that your online models are registered in `ops/llm_registry.yaml` and that the API keys are set in your environment.

### Fallback not triggering

Verify that the monkey-patch is installed:
```python
from core.apex_tiered_assistant import install_tiered_fallback
install_tiered_fallback()  # Call this at startup
```

## Files Modified/Created

1. **Created**: `core/apex_tiered_assistant.py` - Main tiered assistant logic
2. **Created**: `ops/apex_tiered_config.py` - Configuration script
3. **Modified**: `core/service_accounts.py` - Added tiered-assistant to seed principals
4. **Modified**: `core/peer_bridge.py` (manual) - Add tiered-assistant to MENTIONS and SCOPES

## Future Enhancements

- [ ] Streaming support for online model responses
- [ ] Caching of tiered responses in Studio
- [ ] Rate limiting and quota management
- [ ] Model performance metrics and auto-selection
- [ ] Conversation state synchronization between APEX and tiered models
