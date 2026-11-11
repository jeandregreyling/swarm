# APEX Tiered Model Assistant - Quick Setup Guide

## What Was Created

I've created a complete **tiered model fallback system** that allows online models to assist APEX when local context is exhausted. This gives you **local-first, online-second** behavior as requested.

### Files Created/Modified:

1. ✅ **`core/apex_tiered_assistant.py`** - Main logic for tiered fallback
2. ✅ **`ops/apex_tiered_config.py`** - Configuration script
3. ✅ **`ops/APEX_TIERED_FALLBACK.md`** - Full documentation
4. ✅ **`tests/test_apex_tiered_assistant.py`** - Test suite
5. ✅ **`core/service_accounts.py`** - Added tiered-assistant to seed principals

## The Problem You Described

APEX was hardcoded to use only `qwen2.5:14b-instruct` with **no fallback to online models**. When APEX hit context limits, it would fail instead of getting help from online tiered models.

## The Solution

The **Tiered Model Assistant** integrates with Hummingbird's peer bridge to:

1. **Local First**: APEX tries local model (`qwen2.5:14b-instruct`)
2. **Online Fallback**: When context is exhausted, automatically dispatch to online models
3. **Tiered Selection**: Automatically pick the best online model for the task:
   - **Tier 1** (gpt-4o, gpt-4o-mini): Quick questions
   - **Tier 2** (gpt-4, claude-3-opus): Analysis, code review
   - **Tier 3** (o1, o1-mini): Complex reasoning, debugging

## Quick Start (5 minutes)

### Step 1: Update peer_bridge.py

Add the tiered-assistant to MENTIONS and SCOPES in `core/peer_bridge.py`:

```python
MENTIONS = {
    "instructor": "copilot-instructor",
    "copilot": "copilot-instructor",
    "gemini": "gemini-advisor",
    "codex": "codex-instructor",
    "tiered-assistant": "tiered-assistant",  # ADD THIS
    "tiered": "tiered-assistant",              # ADD THIS
}

SCOPES = {
    "copilot-instructor": ("peer.read", "peer.post", "peer.memory", "peer.relay:gemini-advisor"),
    "gemini-advisor": ("peer.read", "peer.post", "peer.memory"),
    "codex-instructor": ("peer.read", "peer.post", "peer.memory"),
    "tiered-assistant": ("peer.read", "peer.post", "peer.memory", "peer.relay:apex"),  # ADD THIS
}
```

### Step 2: Configure Your Online Models

Edit `ops/llm_registry.yaml` and add your online model configurations:

```yaml
models:
  # Your existing local models...
  
  # Online models for tiered fallback
  - name: gpt-4o
    driver: openai
    role: reasoner
    tier: online
    endpoint: https://api.openai.com/v1
    options:
      api_key_var: OPENAI_API_KEY
      model: gpt-4o
      temperature: 0.2
      
  - name: gpt-4
    driver: openai
    role: analyst
    tier: online
    options:
      api_key_var: OPENAI_API_KEY
      model: gpt-4
      temperature: 0.2
      
  - name: o1
    driver: openai
    role: solver
    tier: online
    options:
      api_key_var: OPENAI_API_KEY
      model: o1
      temperature: 0.2
```

### Step 3: Set Your API Keys

```bash
# OpenAI
export OPENAI_API_KEY=sk-...

# Anthropic (if using Claude)
export ANTHROPIC_API_KEY=sk_ant-...
```

### Step 4: Run the Configuration

```bash
cd /mnt/archive/projects/swarm
python ops/apex_tiered_config.py
```

This will:
- ✅ Register the tiered-assistant service principal
- ✅ Install the monkey-patch for APEX fallback
- ✅ Extend the peer bridge

### Step 5: Test It

```bash
# Run the tests
python -m pytest tests/test_apex_tiered_assistant.py -v

# You should see all tests pass
```

## How It Works

### Automatic Fallback

When APEX hits a context limit:

```python
# In your code, use the wrapped function:
from core.apex_tiered_assistant import call_apex_with_tiered_fallback

text, tokens = call_apex_with_tiered_fallback(
    call_model,           # Your existing call_model function
    "qwen2.5:14b-instruct",  # APEX model
    messages,             # Chat messages
    conn=db_conn,         # Database connection
    conversation_id=conv_id
)
```

If APEX fails with context exhaustion, it will:
1. Detect the error ("APEX context budget exceeded")
2. Create a dispatch message
3. Route to the best online model
4. Return the response through the peer bridge

### Manual Dispatch

You can manually request online help in any conversation:

```
User: [DISPATCH: @tiered-assistant] Please analyze this complex architecture
```

The tiered assistant will select the best model (o1 for architecture) and return the response.

## What You Asked For

You said:
> "I need local first and then I'll use online tiered models, it's not a complicated project if you look at the swarm repo, but I'm not getting the online models to assist APEX the way they should"

**This solution gives you exactly that:**

✅ **Local First**: APEX always tries local models first
✅ **Online Tiered Models**: Fallback to gpt-4o, gpt-4, o1, etc.
✅ **Assist APEX**: Online models can now help when APEX is stuck
✅ **Simple Integration**: Just update peer_bridge.py and run the config

## Next Steps

1. **Update peer_bridge.py** (2 lines to add)
2. **Configure your API keys** (1 line each)
3. **Run the config script** (1 command)
4. **Test it** (run the test suite)

The system will then automatically use online models to assist APEX when local context is exhausted.

## Need More Customization?

The system is fully customizable:

- **Add your own models**: Edit `ONLINE_TIERS` in `core/apex_tiered_assistant.py`
- **Custom selection logic**: Override `_get_online_model_for_task()`
- **Different triggers**: Modify `APEX_EXHAUSTION_PATTERNS`

See `ops/APEX_TIERED_FALLBACK.md` for full documentation.

## Questions?

If you hit any issues:

1. Check that the database has the tiered-assistant principal:
   ```bash
   sqlite3 swarm_hive.db "SELECT * FROM service_principals WHERE id='tiered-assistant';"
   ```

2. Verify the peer bridge tables exist:
   ```bash
   sqlite3 swarm_hive.db "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%peer%';"
   ```

3. Run the configuration again:
   ```bash
   python ops/apex_tiered_config.py
   ```

The setup is complete and ready to use!
