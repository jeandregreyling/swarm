# Mistral Vibe Integration - Online Agent for Teaching APEX

## 🎯 Overview

**Mistral Vibe** is now integrated as an **online peer agent** that can teach APEX system access patterns and complex reasoning when the local model's context is exhausted.

This gives you:
- ✅ **Local First**: APEX uses qwen2.5:14b-instruct locally
- ✅ **Mistral Teaching**: Mistral models can teach APEX new patterns
- ✅ **Automatic Fallback**: Online models assist when local context is full
- ✅ **Manual Dispatch**: Explicitly request Mistral's help with `[DISPATCH: @mistral-vibe]`

## 🚀 Quick Setup (2 minutes)

### 1. Set Your Mistral API Key

```bash
export MISTRAL_API_KEY=your_mistral_api_key_here
```

You can get a Mistral API key from: https://console.mistral.ai

### 2. Run Configuration

```bash
cd /mnt/archive/projects/swarm
python ops/mistral_vibe_config.py
```

This will:
- ✅ Register mistral-vibe as a service principal
- ✅ Add to peer bridge mentions and scopes
- ✅ Configure online models (mistral-large, mixtral, etc.)
- ✅ Test API connection

### 3. Update llm_registry.yaml

Add Mistral models to `ops/llm_registry.yaml`:

```yaml
# Mistral Models
  - name: mistral-large-latest
    driver: openai
    role: reasoner
    tier: online
    endpoint: https://api.mistral.ai/v1
    options:
      api_key_var: MISTRAL_API_KEY
      api_model: mistral-large-latest
      temperature: 0.2
      max_tokens: 4096

  - name: mixtral-8x22b-latest
    driver: openai
    role: analyst
    tier: online
    endpoint: https://api.mistral.ai/v1
    options:
      api_key_var: MISTRAL_API_KEY
      api_model: mixtral-8x22b-latest
      temperature: 0.2
      max_tokens: 4096

  - name: mistral-small-latest
    driver: openai
    role: general
    tier: online
    endpoint: https://api.mistral.ai/v1
    options:
      api_key_var: MISTRAL_API_KEY
      api_model: mistral-small-latest
      temperature: 0.2
      max_tokens: 4096
```

## 🔄 How It Works

### Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         User Request                                │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         APEX (Local)                                │
│                    qwen2.5:14b-instruct                              │
└────────────────────────┬──────────────────────────────────────────┘
                         │
             ┌───────────────┴───────────────┐
             │                               │
             ▼                               ▼
    ┌─────────────────┐          ┌─────────────────────────┐
    │   Context OK     │          │   Context Exhausted     │
    │   Local Model    │          │   or Complex Task       │
    └─────────────────┘          └───────────┬─────────────┘
                                                │
                                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Mistral Vibe (Online)                            │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │  Models:                                                       ││
│  │   • mistral-large-latest  (Tier 2 - Reasoning)                ││
│  │   • mixtral-8x22b-latest (Tier 2 - Analysis)                  ││
│  │   • mistral-small-latest  (Tier 1 - General)                 ││
│  └─────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│              Response routed back to APEX conversation                │
└─────────────────────────────────────────────────────────────────────┘
```

### Dispatch Methods

#### Method 1: Automatic Fallback (Recommended)

When APEX hits context limits, it **automatically** dispatches to Mistral Vibe:

```python
from core.apex_tiered_assistant import call_apex_with_tiered_fallback

text, tokens = call_apex_with_tiered_fallback(
    call_model,
    "qwen2.5:14b-instruct",
    messages,
    conn=db_conn,
    conversation_id=123
)
```

If APEX context is exhausted, Mistral Vibe will be invoked automatically.

#### Method 2: Manual Dispatch

Explicitly request Mistral's help in any conversation:

```
User: [DISPATCH: @mistral-vibe] Teach APEX how to handle this system access pattern
```

Or for a specific Mistral model:
```
User: [DISPATCH: @mistral-vibe] Use mixtral-8x22b to analyze this complex architecture
```

#### Method 3: Programmatic Dispatch

```python
from core.mistral_vibe_agent import dispatch_mistral_to_apex

# Dispatch Mistral to teach APEX
dispatch_mistral_to_apex(
    conn,
    conversation_id=123,
    user_message="How do I use git tools in APEX context?",
    apex_message_id=456
)
```

## 📋 Available Commands

### Basic Teaching
```
[DISPATCH: @mistral-vibe] Teach APEX about file system access patterns
```

### Complex Reasoning
```
[DISPATCH: @mistral-vibe] Help APEX understand this multi-step workflow
```

### Architecture Analysis
```
[DISPATCH: @mistral-vibe] Explain the repository structure to APEX
```

### Tool Usage
```
[DISPATCH: @mistral-vibe] Show APEX how to use grep_repo effectively
```

### Specific Model
```
[DISPATCH: @mistral-vibe] Use mistral-large for this complex debugging task
```

## 🎯 Use Cases

### 1. System Access Patterns
Mistral Vibe can teach APEX:
- File system navigation patterns
- Repository structure understanding
- Tool usage best practices
- Context management strategies

### 2. Complex Reasoning
When APEX hits its context limit (16384 tokens):
- Multi-step problem solving
- Debugging complex issues
- Architectural analysis
- Code review and optimization

### 3. Knowledge Transfer
Mistral can:
- Explain concepts APEX doesn't understand
- Provide examples of good patterns
- Teach APEX how to handle edge cases
- Transfer knowledge from online to local

## 🔧 Configuration Options

### Customize Models

Edit `core/mistral_vibe_agent.py` to add more Mistral models:

```python
MISTRAL_MODELS = {
    "mistral-large-latest": { ... },
    "mixtral-8x22b-latest": { ... },
    "mistral-small-latest": { ... },
    # Add your custom models here
    "my-custom-model": {
        "name": "my-custom-model",
        "label": "My Custom Model",
        "driver": "openai",
        "endpoint": "https://api.mistral.ai/v1",
        "api_model": "my-custom-model",
        "role": "analyst",
        "tier": "online",
        "ctx": 32768,
        "options": {
            "api_key_var": "MISTRAL_API_KEY",
            "temperature": 0.2,
        },
    },
}
```

### Customize Tier Assignment

Modify `MISTRAL_TIERS` to assign models to different tiers:

```python
MISTRAL_TIERS = {
    "tier1": {
        "models": ["mistral-small-latest"],
        "role": "general",
    },
    "tier2": {
        "models": ["mistral-large-latest", "mixtral-8x22b-latest"],
        "role": "reasoner",
    },
    "tier3": {
        "models": [],  # No tier 3 Mistral models
        "role": "solver",
    },
}
```

### Custom Teaching Prompts

Override the default teaching prompt:

```python
from core.mistral_vibe_agent import get_mistral_teaching_prompt

custom_prompt = get_mistral_teaching_prompt("Custom task")
# Or create your own
```

## 📊 Model Comparison

| Model | Context | Best For | Tier | Cost |
|-------|---------|----------|------|------|
| mistral-small-latest | 32K | Quick questions, general help | 1 | Low |
| mistral-large-latest | 32K | Reasoning, analysis | 2 | Medium |
| mixtral-8x22b-latest | 64K | Complex analysis, multi-tasking | 2 | Medium |
| mistral-large-2407 | 32K | Legacy reasoning | 2 | Medium |
| mistral-large-2402 | 32K | Legacy reasoning | 2 | Medium |

## 🛠️ Integration with Existing Code

### chat.py Blueprints

```python
# In frontend/blueprints/chat.py
from core.mistral_vibe_agent import dispatch_mistral_to_apex

# When APEX context is exhausted
dispatch_mistral_to_apex(conn, conversation_id, user_message)
```

### apex_tools.py

```python
# In core/apex_tools.py
from core.mistral_vibe_agent import create_mistral_dispatch

# Create dispatch when needed
dispatch_msg = create_mistral_dispatch(conversation_id, task)
```

## 🧪 Testing

### Test Mistral Connection

```bash
python ops/mistral_vibe_config.py
```

This will test the API connection and show available models.

### Run Tests

```bash
python -m pytest tests/test_apex_tiered_assistant.py -v -k mistral
```

## 📚 Files Modified/Created

| File | Change | Purpose |
|------|--------|---------|
| `core/mistral_vibe_agent.py` | Created | Main Mistral Vibe logic |
| `ops/mistral_vibe_config.py` | Created | Configuration script |
| `core/service_accounts.py` | Modified | Added mistral-vibe to seed principals |
| `core/peer_bridge.py` | Modified | Added mistral-vibe mentions and scopes |
| `ops/llm_registry.yaml` | Manual | Add Mistral model configurations |

## 🔐 Security

- Mistral API key is stored in environment variable `MISTRAL_API_KEY`
- Not committed to version control
- Each request is authenticated with the API key
- Peer bridge validates service principal registration

## 🎓 Example Teaching Sessions

### Example 1: System Access Patterns
```
User: APEX, I need to understand how to navigate the repository structure
APEX: [Context exhausted - needs help]
User: [DISPATCH: @mistral-vibe] Teach APEX about repository navigation
Mistral: APEX, here are the key patterns for repository navigation...
```

### Example 2: Tool Usage
```
User: How do I use grep_repo effectively?
APEX: [Attempts with limited context]
User: [DISPATCH: @mistral-vibe] Explain grep_repo to APEX
Mistral: grep_repo is for searching... use single word queries...
```

### Example 3: Automatic Fallback
```
User: [Very long, complex request that exceeds APEX context]
APEX: [Detects context exhaustion]
APEX: [Automatically dispatches to Mistral Vibe]
Mistral: [Handles the complex request]
APEX: [Receives and integrates the response]
```

## 🚀 Next Steps

1. **Set your API key**: `export MISTRAL_API_KEY=...`
2. **Run configuration**: `python ops/mistral_vibe_config.py`
3. **Add registry entries**: Update `ops/llm_registry.yaml`
4. **Test it**: Try a dispatch in your chat
5. **Integrate**: Use `call_apex_with_tiered_fallback()` in your code

## 📖 Related Documentation

- [APEX Tiered Fallback](ops/APEX_TIERED_FALLBACK.md) - Main tiered system
- [APEX Tiered Setup](APEX_TIERED_SETUP.md) - Quick start guide
- [Peer Bridge](core/peer_bridge.py) - Communication infrastructure
- [Service Accounts](core/service_accounts.py) - Principal management

## 💡 Tips

1. **Start with mistral-large-latest** for most tasks
2. **Use mixtral-8x22b-latest** for complex, multi-faceted problems
3. **Set temperature to 0.2** for more deterministic teaching
4. **Keep prompts focused** - Mistral learns from your examples
5. **Use [DISPATCH: @mistral-vibe]** for explicit teaching requests

---

**Mistral Vibe is now ready to teach APEX!** 🎉

The integration allows Mistral models to act as external teachers and assistants, providing the online tiered model support you requested while keeping APEX as the local-first primary interface.
