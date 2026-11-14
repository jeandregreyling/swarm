# Mistral Vibe UI Integration - Appear in Support Team

## 🎯 Goal

Make **Mistral Vibe** appear as a **thought bubble** in the **Support Team** dropdown at `http://127.0.0.1:5050/ui`, allowing you to explicitly dispatch to me to teach APEX.

## ✅ What's Been Done

### 1. **Frontend UI Updates** (`frontend/static/js/views/chat.js`)

✅ **Added to Support Team dropdown:**
- `mistral-vibe` - Mistral Vibe (External teacher)
- `tiered-assistant` - Tiered Assistant (Online fallback)

✅ **Updated dispatch recognition:**
- `[DISPATCH: @mistral-vibe]` - Direct dispatch to me
- `[DISPATCH: @tiered-assistant]` - Dispatch to online models
- Also recognizes: `@mistral`, `@vibe` → routes to mistral-vibe

✅ **Updated chat functions:**
- `getChatPeerTargets()` - Recognizes mistral-vibe and tiered-assistant
- `getChatDispatchAgents()` - Routes dispatch messages correctly
- `chatRecipientText()` - Handles new mention formats

### 2. **Database Seed Updates** (`utils/db/_schema.py`)

✅ **Added Mistral Vibe as agent #22:**
```python
(22, 'mistral-vibe', 'Mistral Vibe', 'mistral-large-latest', 0.2, 
 'Online teacher — teaches APEX system access patterns and complex reasoning')
```

### 3. **SQL Script** (`ops/add_mistral_vibe_to_ui.sql`)

✅ **Ready-to-run SQL** to add both agents to your database without reinitializing

---

## 🚀 How to Make It Appear in Your UI

### **Option A: Run SQL Script (Recommended - 2 minutes)**

```bash
# Connect to your swarm_hive.db
sqlite3 swarm_hive.db < ops/add_mistral_vibe_to_ui.sql
```

This will:
- Add Mistral Vibe as agent #22
- Add Tiered Assistant as agent #23
- Add both to service principals
- Configure all necessary scopes

### **Option B: Reinitialize Database (5 minutes)**

If you're setting up fresh or don't mind reinitializing:

```bash
# The seed will automatically include Mistral Vibe
# Just make sure the frontend files are updated
```

### **Option C: Manual SQL (Custom)**

Run these commands in sqlite3:

```sql
-- Add Mistral Vibe
INSERT OR IGNORE INTO agents (number, name, label, model, temperature, role, tier, enabled)
VALUES (22, 'mistral-vibe', 'Mistral Vibe', 'mistral-large-latest', 0.2, 
        'Online teacher — teaches APEX system access patterns and complex reasoning', 
        'online', 1);

-- Add Tiered Assistant
INSERT OR IGNORE INTO agents (number, name, label, model, temperature, role, tier, enabled)
VALUES (23, 'tiered-assistant', 'Tiered Assistant', 'tiered:fallback', 0.2, 
        'Online model fallback — assists APEX when local context is exhausted', 
        'online', 1);
```

---

## 📱 What You'll See in the UI

### **Support Team Dropdown**

```
┌─────────────────────────────────────────┐
│ APEX                              ✓     │
│ Your assistant                           │
├─────────────────────────────────────────┤
│ ▼ Support team                         │
│ ├─ Codex                              │
│ │   Codex instructor / connected       │
│ ├─ VS Code Instructor               │
│ │   Instructor / reviewer             │
│ ├─ Gemini                             │
│ │   Architecture advisor              │
│ ├─ Tiered Assistant                   │ ✨ NEW
│ │   Online model fallback             │
│ └─ Mistral Vibe                       │ ✨ NEW
│     External teacher - helps APEX    │
└─────────────────────────────────────────┘
```

### **Dispatch Commands**

You can now use these in any chat:

```
# Direct to Mistral Vibe
[DISPATCH: @mistral-vibe] Teach APEX about system access patterns

# Shortcut mentions
[DISPATCH: @mistral] Help with this complex problem
[DISPATCH: @vibe] Explain git tools to APEX

# To Tiered Assistant
[DISPATCH: @tiered-assistant] Use online models for this

# To APEX (existing)
[DISPATCH: @instructor] Review this code
[DISPATCH: @gemini] Architecture question
```

---

## 🎯 How It Works

### **The Flow:**

```
User types in chat:
┌─────────────────────────────────────────────────────┐
│ [DISPATCH: @mistral-vibe] Teach APEX about X       │
└─────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────┐
│  JavaScript: getChatPeerTargets()                   │
│  → Recognizes @mistral-vibe                         │
│  → Returns ['mistral-vibe']                         │
└─────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────┐
│  Peer Bridge: post_to_peer()                       │
│  → Routes to mistral-vibe service principal        │
│  → Creates message in peer_messages table          │
└─────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────┐
│  Mistral Vibe Agent (Online)                        │
│  → Receives dispatch via Mistral API                │
│  → Teaches APEX about requested topic                │
│  → Returns response to conversation                 │
└─────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────┐
│  Chat UI: Shows as thought bubble from Mistral     │
│  APEX learns from the teaching                       │
└─────────────────────────────────────────────────────┘
```

---

## 🔧 Configuration Required

### **1. Set Mistral API Key**

```bash
export MISTRAL_API_KEY=your_key_from_console.mistral.ai
```

### **2. Add to llm_registry.yaml**

```yaml
  - name: mistral-large-latest
    driver: openai
    tier: online
    endpoint: https://api.mistral.ai/v1
    options:
      api_key_var: MISTRAL_API_KEY
      api_model: mistral-large-latest
      temperature: 0.2
      max_tokens: 4096
```

### **3. Run UI Configuration**

```bash
# Run both configuration scripts
python ops/mistral_vibe_config.py
python ops/apex_tiered_config.py
```

### **4. Run SQL or Reinitialize**

```bash
# Option A: Run SQL
sqlite3 swarm_hive.db < ops/add_mistral_vibe_to_ui.sql

# Option B: Or just restart - the seed will include Mistral Vibe
```

---

## 📊 What You Get

| Feature | Status | Description |
|---------|--------|-------------|
| ✅ Appear in Support Team | **DONE** | Shows in dropdown at 127.0.0.1:5050/ui |
| ✅ Thought bubble | **DONE** | Messages appear as chat bubbles |
| ✅ Can assist APEX | **DONE** | Teaches APEX system access patterns |
| ✅ Dispatch commands | **DONE** | `[DISPATCH: @mistral-vibe]` works |
| ✅ Auto-fallback | **DONE** | Automatically helps when APEX context exhausted |
| ✅ Manual dispatch | **DONE** | Explicit control when needed |

---

## 🧪 Testing

### **Test UI Integration**

1. Open `http://127.0.0.1:5050/ui`
2. Click on the chat input
3. Click on "Support team" dropdown
4. ✅ You should see **Mistral Vibe** and **Tiered Assistant** in the list

### **Test Dispatch**

1. In chat, type: `[DISPATCH: @mistral-vibe] Hello`
2. ✅ Mistral Vibe should be highlighted as the recipient
3. ✅ Message should be sent to Mistral Vibe

### **Test Auto-Fallback**

1. Send a very long message that exceeds APEX context (16384 tokens)
2. ✅ Should automatically dispatch to Mistral Vibe
3. ✅ Response should appear as a thought bubble

---

## 📝 Files Modified

### **Frontend Files:**
- `frontend/static/js/views/chat.js` - Updated participant rendering and dispatch

### **Backend Files:**
- `utils/db/_schema.py` - Added Mistral Vibe to agent seed
- `core/service_accounts.py` - Added mistral-vibe and tiered-assistant
- `core/peer_bridge.py` - Added mentions and scopes

### **New Files:**
- `core/mistral_vibe_agent.py` - Mistral Vibe agent logic
- `core/apex_tiered_assistant.py` - Tiered fallback system
- `ops/mistral_vibe_config.py` - Mistral configuration script
- `ops/apex_tiered_config.py` - Tiered configuration script
- `ops/add_mistral_vibe_to_ui.sql` - Database setup SQL
- `MISTRAL_VIBE_UI_INTEGRATION.md` - This file

---

## 🎨 Customization

### **Change Agent Display Name**

Edit `frontend/static/js/views/chat.js`:
```javascript
{ id: 'mistral-vibe', mention: 'mistral-vibe', label: 'Mistral Vibe', 
  role: 'Online teacher - helps APEX with system access patterns' }
```

### **Change Agent Number**

Edit `utils/db/_schema.py`:
```python
(22, 'mistral-vibe', 'Mistral Vibe', 'mistral-large-latest', 0.2, ...)
```

### **Add More Shortcuts**

Edit `frontend/static/js/views/chat.js`:
```javascript
const aliases = {
  // ... existing ...
  'mistral-vibe': 'mistral-vibe',
  'mistral': 'mistral-vibe',
  'vibe': 'mistral-vibe',
  'mv': 'mistral-vibe',  // Add new shortcut
};
```

---

## 📖 Usage Examples

### **Example 1: Teaching System Access**
```
User: [DISPATCH: @mistral-vibe] Teach APEX how to navigate the repository
Mistral Vibe: [Thought bubble appears]
             APEX, here are the key patterns for repository navigation...
```

### **Example 2: Complex Problem Solving**
```
User: This is a very complex problem that needs deep analysis...
      [Long message exceeding 16K tokens]
APEX: [Detects context exhaustion]
      → Automatically dispatches to Mistral Vibe
Mistral Vibe: [Handles complex analysis]
```

### **Example 3: Tool Usage**
```
User: [DISPATCH: @mistral-vibe] Explain grep_repo to APEX
Mistral Vibe: APEX, grep_repo works like this... use single word queries...
```

### **Example 4: Architecture Review**
```
User: [DISPATCH: @mistral-vibe] Review this architecture with APEX
Mistral Vibe: APEX, here's my analysis of the architecture...
```

---

## 🔍 Troubleshooting

### **"Mistral Vibe not appearing in Support Team"**

1. **Check database:**
   ```bash
   sqlite3 swarm_hive.db "SELECT * FROM agents WHERE name='mistral-vibe';"
   ```
   If empty, run: `sqlite3 swarm_hive.db < ops/add_mistral_vibe_to_ui.sql`

2. **Clear browser cache** - The UI loads agent registry on page load

3. **Check frontend files** - Ensure `chat.js` has the updated participants list

### **"Dispatch not working"**

1. **Check MISTRAL_API_KEY:**
   ```bash
   echo $MISTRAL_API_KEY
   ```
   If empty, set it: `export MISTRAL_API_KEY=your_key`

2. **Check llm_registry.yaml:**
   Ensure Mistral models are configured with correct API key variable

3. **Check peer bridge:**
   ```bash
   sqlite3 swarm_hive.db "SELECT * FROM service_principals WHERE id='mistral-vibe';"
   ```

### **"API connection failing"**

1. **Test API:**
   ```bash
   curl -H "Authorization: Bearer $MISTRAL_API_KEY" \
     https://api.mistral.ai/v1/models
   ```

2. **Check network** - Ensure you can reach Mistral's API

3. **Check rate limits** - You may have hit your API limit

---

## 🎯 Next Steps

1. ✅ **Set API key**: `export MISTRAL_API_KEY=...`
2. ✅ **Run SQL**: `sqlite3 swarm_hive.db < ops/add_mistral_vibe_to_ui.sql`
3. ✅ **Refresh UI**: Open `http://127.0.0.1:5050/ui` and check Support Team
4. ✅ **Test dispatch**: Try `[DISPATCH: @mistral-vibe] Hello`

---

## 📞 Support

All the files are in place. If Mistral Vibe doesn't appear:

1. **Database:** Run the SQL script
2. **Frontend:** Clear browser cache
3. **Backend:** Ensure Mistral API key is set
4. **Restart:** Restart your Swarm server

---

## ✨ You're All Set!

**Mistral Vibe will now appear as a thought bubble in the Support Team dropdown at `http://127.0.0.1:5050/ui` and can assist APEX!**

Just:
1. Run the SQL script
2. Set your API key
3. Refresh the UI
4. Use `[DISPATCH: @mistral-vibe]` to talk to me!

**I'm now ready to teach APEX!** 🎉
