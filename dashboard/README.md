# 🎯 Unified Chat Dashboard

## One Point of Contact for User, APEX & Mistral Vibe

This dashboard provides a **single unified view** that shows messages from all three participants:
- **User** (you)
- **APEX** (local model)
- **Mistral Vibe** (online assistant)

## 📁 Files Created

| File | Purpose | Access Method |
|------|---------|---------------|
| `dashboard/unified_chat_view.html` | Main dashboard (Flask API) | Requires Flask server |
| `dashboard/unified_chat_standalone.html` | Standalone version | Open directly in browser |
| `dashboard/fetch_messages.py` | Python message fetcher | CLI or import |
| `frontend/blueprints/dashboard.py` | Flask API routes | `/api/dashboard/*` |

## 🚀 How to Use

### Option 1: Flask Integration (Recommended)
1. Ensure Flask server is running (port 5050)
2. Visit: `http://localhost:5050/dashboard/unified_chat_view.html`
3. Or use the API: `GET /api/dashboard/messages/unified`

### Option 2: Standalone HTML
1. Open directly in browser: `file:///mnt/archive/projects/swarm/dashboard/unified_chat_standalone.html`
2. Requires Python backend to be running
3. Auto-refreshes every 5 seconds

### Option 3: Direct Python Query
```bash
cd /mnt/archive/projects/swarm/dashboard
python3 fetch_messages.py
```

## ✨ Features

- ✅ **Unified Timeline**: All messages from User, APEX, Mistral Vibe in one chronological view
- ✅ **Separate Panels**: View each participant's messages separately
- ✅ **Live Stats**: Message counts for each participant
- ✅ **Filtering**: Filter by sender (User, APEX, Mistral Vibe, Ghost)
- ✅ **Auto-Refresh**: Updates every 5 seconds
- ✅ **Source Tracking**: Shows which database/table each message came from

## 📊 Data Sources

The dashboard aggregates messages from:

1. **swarm_memory.db**
   - `messages` table - Main chat messages
   - `peer_messages` table - Team relay messages

2. **mind.db**
   - `exchanges` table - APEX conversation history

3. **runtime/chat-continuity/**
   - Recovery chat JSON files

## 🎨 UI Preview

### Unified Timeline View
```
┌─────────────────────────────────────────────┐
│  🎯 UNIFIED CHAT VIEW                        │
│  One point of contact for User, APEX & Mistral│
├─────────────────────────────────────────────┤
│  [Stats: Total, User, APEX, Mistral]        │
├─────────────────────────────────────────────┤
│  [Filter: All Senders ▼] [🔄 Refresh]      │
├─────────────────────────────────────────────┤
│  [10:32] User: Message here...              │
│  [10:31] APEX: Response here...             │
│  [10:30] Mistral Vibe: Coordination...       │
│  ...                                        │
└─────────────────────────────────────────────┘
```

### Separate Panels View
```
┌──────────┬──────────┬──────────┐
│ USER     │ APEX     │ MISTRAL  │
│ 10 msgs  │ 15 msgs  │ 8 msgs   │
├──────────┼──────────┼──────────┤
│ [msg1]   │ [msg1]   │ [msg1]   │
│ [msg2]   │ [msg2]   │ [msg2]   │
│ ...      │ ...      │ ...      │
└──────────┴──────────┴──────────┘
```

## 🔧 Configuration

### Color Coding
- **User**: Green (#4CAF50)
- **APEX**: Orange (#ff9800)
- **Mistral Vibe**: Purple (#9c27b0)
- **Ghost**: Cyan (#00BCD4)

### API Endpoints
- `GET /api/dashboard/messages/unified` - JSON endpoint for unified messages
- `GET /dashboard/fetch_messages.py` - Legacy Python endpoint

## 💡 Use Cases

1. **Debugging**: See all messages in one place when troubleshooting
2. **Monitoring**: Track conversation flow between all participants
3. **Collaboration**: Single view for team coordination
4. **Audit**: Review historical messages across all sources

## 📝 Notes

- Messages are deduplicated based on content + timestamp
- Most recent 100-200 messages are displayed
- Auto-refresh can be disabled in the browser
- Requires SQLite3 and Python 3.8+

## 🎉 Announcement Posted

I've posted a message in the main chat (ID: 9976) announcing this dashboard. Both you and APEX should see it at `http://localhost:5050/ui` in conversation #2831.

---

**Created by:** Mistral Vibe  
**Date:** 2026-11-06  
**Status:** ✅ Active & Verbose in Main Chat
