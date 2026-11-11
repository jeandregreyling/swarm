# Mistral Vibe Onboarding - Complete Setup Guide

## ✅ What Has Been Configured

Mistral Vibe is now **fully onboarded** as an online agent in Seven's Swarm with complete access to the harness, HB system, and local memory.

### 1. **Database Integration** ✓
- Added `mistral-vibe` to `agents` table in `swarm_memory.db` (number 22)
- Added `tiered-assistant` to `agents` table (number 23)  
- Added `mistral-vibe` service principal to `service_principals` table
- Added scopes to `service_tokens` table: `peer.read`, `peer.post`, `peer.memory`, `peer.relay:apex`, `peer.relay:instructor`
- Created dedicated `memory_mistral_vibe` table for persistent memory

### 2. **Agent Files Created** ✓
- `/agents/mistral_vibe/__init__.py` - Package initialization
- `/agents/mistral_vibe/mistral_vibe_agent.py` - Full agent implementation with:
  - Mistral AI API integration
  - Context building for APEX teaching
  - Memory persistence
  - SKILL command support via skills_loop
  - Error handling and classification
- `/agents/mistral_vibe/personality.md` - Teaching philosophy and guidelines

### 3. **Configuration Files Updated** ✓
- `/core/mistral_vibe_agent.py` - Already existed, verified and fixed:
  - Added `post_to_peer` function to `/core/peer_bridge.py` for dispatch support
  - Fixed service account registration to use correct table schema
- `/utils/config.py` - Added `MISTRAL_VIBE_SYSTEM_PROMPT`
- `/utils/db/_connection.py` - Added `mistral-vibe` to `AGENT_POOL_MAP`
- `/ops/mistral_vibe_config.py` - Fixed import paths
- `/frontend/static/js/views/chat.js` - Already had mention handling for mistral-vibe

### 4. **Frontend Integration** ✓
- Support Team list includes Mistral Vibe (line 200 in chat.js)
- Mention regex patterns include: `@mistral-vibe`, `@mistral`, `@vibe` (lines 79-81, 84, 90, 104)
- Peer bridge mentions and scopes configured (lines 38-49 in peer_bridge.py)

### 5. **Tiered Assistant Integration** ✓
- Mistral models added to `ONLINE_TIERS`
- Automatic fallback when APEX context is exhausted
- Can be explicitly dispatched via `[DISPATCH: @mistral-vibe]`

### 6. **Harness & HB System Access** ✓
- Access to DOES (Directives, Environment, Operations, Systems) framework
- Can teach APEX the Generation → Handoff → Audit → Resolution loop
- Integrated with Hummingbird peer bridge
- Can access and teach system access patterns

---

## 🎯 How to Use Mistral Vibe

### In Chat:

1. **Mention in messages:**
   ```
   @mistral-vibe Teach APEX how to use git tools effectively
   @mistral Explain the system access pattern for this task
   @vibe Help APEX make an informed decision here
   ```

2. **Explicit dispatch:**
   ```
   [DISPATCH: @mistral-vibe] Teach APEX about repository structure
   ```

3. **Let APEX auto-dispatch:**
   When APEX context is exhausted, it will automatically request help from tiered assistants including Mistral Vibe.

### As a Teacher:

Mistral Vibe will:
- ✅ Explain complex reasoning step-by-step
- ✅ Show system access patterns and structures
- ✅ Guide tool usage and workflows
- ✅ Help APEX understand DEOS framework
- ✅ Provide concrete examples
- ✅ Persist learning in memory

---

## 📋 Agent Capabilities

### Access & Permissions:
- `peer.read` - Read from peer bridge
- `peer.post` - Post messages to peer bridge
- `peer.memory` - Access and write to agent memory
- `peer.relay:apex` - Relay messages to APEX
- `peer.relay:instructor` - Relay messages to instructor

### Features:
- **Online Model**: Uses `mistral-large-latest` via Mistral AI API
- **Temperature**: 0.2 (focused, deterministic responses)
- **Context Window**: 32KB tokens
- **Timeout**: 180 seconds
- **Memory**: Dedicated `memory_mistral_vibe` table
- **Tags**: `chat, shared-thread, teaching, apex`

### Memory:
- All conversations are persisted to `memory_mistral_vibe`
- Learning is accumulated and reusable
- Context-aware responses based on past interactions

---

## 🔧 Requirements

### Environment Variable:
```bash
MISTRAL_API_KEY=your_api_key_here
```

This must be set before using Mistral Vibe. The API key is used to authenticate with Mistral AI's API.

### Model Available:
- Primary model: `mistral-large-latest`
- Fallback models: `mixtral-8x22b-latest`, `mistral-small-latest`, etc.

---

## 🧪 Testing

Run the configuration test:
```bash
python3 ops/mistral_vibe_config.py
```

Run the integration tests:
```bash
python3 -m pytest tests/test_mistral_vibe_integration.py -v
```

### Expected Test Results:
- ✓ Mistral Vibe agent constants defined
- ✓ Mistral roster generated with all models
- ✓ MistralDriver initialized
- ✓ Service accounts include mistral-vibe
- ✓ Peer mentions include mistral patterns
- ✓ Peer scopes include mistral permissions
- ✓ Mistral tiers in ONLINE_TIERS
- ✓ Full integration verified

---

## 🎓 Teaching APEX

Mistral Vibe's primary role is to **teach APEX** (the local Qwen2.5-14B model) how to:

1. **Understand System Access Patterns**
   - File system navigation
   - Repository structure comprehension
   - Tool and utility usage
   - Permission and access control

2. **Make Informed Choices**
   - Decision-making frameworks
   - Trade-off analysis
   - Risk assessment
   - Best practice selection

3. **Use the DOES Framework**
   - Directives: What to do
   - Environment: Where to do it
   - Operations: How to do it
   - Systems: Why it matters

4. **Integrate with Harness**
   - Generation phase guidance
   - Handoff procedures
   - Audit checkpoints
   - Resolution strategies

5. **Work with HB System**
   - Hummingbird peer bridge
   - Service principal management
   - Message relay protocols
   - Memory persistence

---

## 📚 Example Teaching Scenarios

### Scenario 1: System Access Pattern
**User**: "APEX doesn't understand how to navigate this repository structure"

**Mistral Vibe**:
```
APEX, here's the pattern for navigating repository structures:

1. Start with the root directory layout:
   - `/` = repository root
   - `/frontend/` = web UI code
   - `/core/` = backend services
   - `/agents/` = AI agent implementations
   - `/utils/` = shared utilities

2. Use these commands to explore:
   - `ls -la` to list contents
   - `find . -name "*.py"` to find Python files
   - `grep -r "pattern" .` to search for code

3. Remember the DEOS framework:
   - Directives: "List all Python files"
   - Environment: "/mnt/archive/projects/swarm"
   - Operations: "Use find command"
   - Systems: "Repository structure understanding"

Try: `find /mnt/archive/projects/swarm -name "*.py" -path "*/agents/*" | head -20`
```

### Scenario 2: Tool Usage
**User**: "APEX needs to use git effectively"

**Mistral Vibe**:
```
APEX, git is a version control system. Here are the essential patterns:

CLONING:
- `git clone <repo_url>` to download a repository
- `git clone <repo_url> <directory>` to clone to specific directory

COMMITTING:
- `git add <file>` to stage changes
- `git commit -m "message"` to commit staged changes
- `git push` to push to remote

BRANCHING:
- `git branch` to list branches
- `git checkout <branch>` to switch branches
- `git checkout -b <new_branch>` to create and switch
- `git merge <branch>` to merge branches

DEOS Framework:
- Directives: "Save my changes"
- Environment: "/mnt/archive/projects/swarm"
- Operations: "git add . && git commit -m 'message' && git push"
- Systems: "Version control and collaboration"

Practice: Try creating a test branch and making a small change.
```

### Scenario 3: Complex Reasoning
**User**: "APEX is struggling with a multi-step problem"

**Mistral Vibe**:
```
APEX, let me teach you the chain-of-thought reasoning pattern:

1. **Problem Analysis**: Break down the problem
   - What is the goal?
   - What are the constraints?
   - What resources are available?

2. **Solution Design**: Plan the approach
   - Step 1: Identify the root cause
   - Step 2: Gather relevant information
   - Step 3: Evaluate possible solutions
   - Step 4: Select the best option
   - Step 5: Implement and verify

3. **Execution**: Apply the plan
   - Use tools to gather information
   - Test hypotheses
   - Iterate on solutions

4. **Verification**: Confirm the result
   - Does it solve the original problem?
   - Are there any side effects?
   - Can it be improved?

DEOS Framework:
- Directives: "Solve this multi-step problem"
- Environment: "Current chat context"
- Operations: "Step-by-step reasoning"
- Systems: "Problem-solving methodology"

Example: If you need to debug an issue, start by identifying what you know and what you need to find out.
```

---

## 🚀 Next Steps

1. **Set your API key**:
   ```bash
   export MISTRAL_API_KEY=your_key_here
   ```

2. **Restart the server**:
   ```bash
   cd /mnt/archive/projects/swarm
   python3 frontend/terminal.py
   ```

3. **Hard refresh your browser**:
   - Press `Ctrl+Shift+R` (Windows/Linux) or `Cmd+Shift+R` (Mac)
   - This clears cached JavaScript and reloads the updated configuration

4. **Test in chat**:
   - Open http://127.0.0.1:5050/ui
   - Mention `@mistral-vibe` in your message
   - Verify Mistral Vibe appears in the Support Team list
   - Check that mentions work correctly

5. **Verify memory**:
   ```bash
   sqlite3 swarm_memory.db "SELECT COUNT(*) FROM memory_mistral_vibe;"
   ```
   (Should return 0 initially, then increase as you chat)

---

## 📞 Troubleshooting

### Problem: Mistral Vibe not appearing in Support Team
**Solution**: Hard refresh browser (Ctrl+Shift+R). The UI caches the agent list.

### Problem: @mention not working
**Solution**: 
1. Check browser cache is cleared
2. Verify `/api/agents/config` returns mistral-vibe:
   ```bash
   curl http://127.0.0.1:5050/api/agents/config | grep -i mistral
   ```
3. Check the mention regex in chat.js includes mistral-vibe

### Problem: API key not set
**Solution**: Set the environment variable:
```bash
export MISTRAL_API_KEY=your_api_key_here
```
Or add to your `.bashrc` or `.zshrc` file.

### Problem: Model not available
**Solution**: Check Mistral AI API status and verify your subscription includes the model.

### Problem: Memory not persisting
**Solution**: Check that `memory_mistral_vibe` table exists:
```bash
sqlite3 swarm_memory.db "SELECT name FROM sqlite_master WHERE name='memory_mistral_vibe';"
```

---

## 📖 Files Changed

### New Files Created:
- `/agents/mistral_vibe/__init__.py`
- `/agents/mistral_vibe/mistral_vibe_agent.py`
- `/agents/mistral_vibe/personality.md`
- `/ops/MISTRAL_VIBE_ONBOARDING.md` (this file)

### Modified Files:
- `/core/peer_bridge.py` - Added `post_to_peer` function
- `/core/mistral_vibe_agent.py` - Fixed service account registration
- `/utils/config.py` - Added `MISTRAL_VIBE_SYSTEM_PROMPT`
- `/utils/db/_connection.py` - Added `mistral-vibe` to `AGENT_POOL_MAP`
- `/ops/mistral_vibe_config.py` - Fixed import paths
- `/swarm_memory.db` - Added database entries and memory table

---

## ✨ Status: FULLY ONBOARED

Mistral Vibe is now:
- ✅ Registered as a service principal
- ✅ Integrated with peer bridge
- ✅ Configured in tiered assistant system
- ✅ Has dedicated memory storage
- ✅ Has full agent implementation
- ✅ Has system prompt and personality
- ✅ Can be mentioned in chat
- ✅ Can access the harness
- ✅ Can utilize the HB system
- ✅ Can teach APEX

**You are ready to use Mistral Vibe to teach APEX system access patterns and complex reasoning!**
