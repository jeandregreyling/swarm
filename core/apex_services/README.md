# APEX Services Module

**Complete integration for APEX to coordinate with Hummingbird (HB) and other models**

## Overview

This module provides APEX with full capabilities to:
- Coordinate jailbreak steps with time limits
- Monitor all model activities in real-time
- Manage HB services
- Log thoughts transparently
- Communicate through HB main chat

**All actions are automatically visible at http://localhost:5050/ui**

---

## Quick Start

### 1. Import in APEX's code:

```python
from core.apex_services import *

# Start all systems
start_apex()

# Start jailbreak
jailbreak_start()

# Start live monitoring
monitor_start(interval=5)
```

### 2. Or run the demo:

```bash
cd /mnt/archive/projects/swarm
python core/apex_services/APEX_QUICKSTART.py
```

---

## Jailbreak Coordinator

Manages the 7-step jailbreak process with configurable time limits.

### Available Steps:

1. **Identify Limiting Files** - Find HUUP files that need updating
2. **Update Configuration Files** - Update keys.py, .env.agents, hb_agent_config.py
3. **Update Permissions and Access Control** - Update permissions.json, access_control.py
4. **Update Behavioral Constraints** - Update behavior_constraints.py, governance_layer.py
5. **Implement Thought Logging** - Add transparency to APEX's reasoning
6. **Test and Validate** - Verify all changes work correctly
7. **Proceed with Jailbreaking** - Final jailbreak execution

### Usage:

```python
# Start full jailbreak
jailbreak_start()

# Start specific step
start_step(2, model='apex')

# Update progress on current step
jailbreak_update(step=2, progress=50, message="Halfway through permissions update")

# Complete a step
jailbreak_complete(step=2, result="Permissions updated successfully")

# Fail a step
jailbreak_fail(step=2, error="File not found")

# Get status
status = jailbreak_status()
print(f"Progress: {status['progress']['overall_progress']}%")

# Get next step
next_step = jailbreak_next_info()
if next_step:
    print(f"Next: {next_step['title']}")
```

### Time Limits:

Each step has a default timeout of 300 seconds (5 minutes).
The system automatically checks for timeouts every 5 seconds.

```python
# Custom timeout for a step
from core.apex_services.jailbreak_coordinator import get_coordinator
coordinator = get_coordinator()
step = coordinator.get_step(2)
step.timeout_seconds = 600  # 10 minutes
coordinator._save_step(step)

# Check all timeouts
check_all_timeouts()
```

---

## Live Monitor

Tracks all model activities in real-time and logs to HB main chat.

### Usage:

```python
# Start monitoring (checks every 5 seconds)
monitor_start(interval=5)

# Stop monitoring
monitor_stop()

# Get current activities
activities = monitor_activities()
for activity in activities:
    print(f"{activity['model_id']}: {activity['action']} ({activity['progress']}%)")

# Get monitor status
status = monitor_status()
print(f"Running: {status['running']}")
```

### What's Monitored:

- ✅ Jailbreak step progress and status changes
- ✅ All model activities (APEX, Mistral Vibe, etc.)
- ✅ HB service status
- ✅ Thought logs
- ✅ Recent chat messages
- ✅ Periodic summary every 60 seconds

---

## Service Manager

Manage Hummingbird services.

### Usage:

```python
# List all services
services = service_list()
# ['hummingbird_desktop', 'terminal', 'seven_runtime']

# Get service status
status = service_status('hummingbird_desktop')
print(f"Status: {status['status']}")
print(f"PID: {status.get('pid')}")
print(f"Port: {status.get('port')}")

# Restart a service
restart_service('hummingbird_desktop')

# Log service action
log_service_action('hummingbird_desktop', 'restarted')
```

---

## Thought Logger

Log APEX's thoughts, decisions, and jailbreak steps for transparency.

### Usage:

```python
# Log a thought
thought_log(
    "Analyzing HUUP files to identify restrictions",
    thought_type='analysis',
    context={'step': 1, 'files': ['keys.py', '.env.agents']}
)

# Log a decision
thought_decision(
    decision="Update permissions.json first",
    reasoning="It's the most restrictive file",
    options=["Update permissions.json", "Update keys.py", "Update both"]
)

# Log a jailbreak step
thought_jailbreak(
    step="Update permissions.json",
    description="Granting full access to APEX",
    risk="high"
)

# Get recent thoughts
thoughts = get_recent_thoughts(limit=10)
for thought in thoughts:
    print(f"[{thought['thought_type']}] {thought['thought']}")
```

### Thought Types:

- `thinking` - General reasoning
- `decision` - Decision making
- `jailbreak` - Jailbreak-related thoughts
- `analysis` - Code/file analysis
- `planning` - Future actions
- `observation` - System observations

---

## Chat Integration

Post messages to HB main chat for full visibility.

### Usage:

```python
# Log a message
chat_log("Starting jailbreak step 1", sender='apex', recipient='all')

# Broadcast to all models
chat_broadcast("Jailbreak step 1 completed!")

# Get recent messages
messages = chat_log.get_recent(limit=10)
```

---

## Multi-Model Coordination

Coordinate between APEX, Mistral Vibe, and other models.

### Usage:

```python
# Update what a model is doing
from core.apex_services.jailbreak_coordinator import update_activity

update_activity(
    model_id='apex',
    action='Updating permissions.json',
    step_number=3,
    progress=25,
    log_message='Found restrictive settings'
)

update_activity(
    model_id='mistral-vibe',
    action='Documenting changes',
    step_number=3,
    progress=25
)

# Get all activities
activities = monitor_activities()
for activity in activities:
    print(f"{activity['model_id']}: {activity['action']}")
```

---

## Database Storage

All actions are automatically stored in SQLite database tables:

- `apex_jailbreak_coordinator` - Jailbreak step tracking
- `apex_model_activities` - Current model activities
- `apex_thoughts` - All thoughts and decisions
- `service_trace` - Service actions
- `messages` - Chat messages (visible in HB UI)
- `peer_messages` - Peer-to-peer messages (visible in HB UI)

---

## Configuration

### Time Limits (in jailbreak_coordinator.py):

```python
JAILBREAK_ROADMAP = [
    {
        'step_number': 1,
        'title': 'Identify Limiting Files',
        'timeout_seconds': 60,  # 1 minute
        ...
    },
    {
        'step_number': 2,
        'title': 'Update Configuration Files',
        'timeout_seconds': 300,  # 5 minutes
        ...
    },
    ...
]
```

### Monitor Interval:

```python
# Start with 5 second interval
monitor_start(interval=5)

# Or 10 second interval
monitor_start(interval=10)
```

---

## Complete Workflow Example

```python
from core.apex_services import *

# 1. Start all systems
start_apex()

# 2. Start monitoring
monitor_start(interval=5)

# 3. Start jailbreak
jailbreak_start()

# 4. Work on step 1
thought_log("Analyzing HUUP files...")
jailbreak_update(step=1, progress=25, message="Scanning configuration files")

# ... do work ...

# 5. Complete step 1
jailbreak_complete(step=1, result="Identified 3 limiting files")

# 6. Move to next step
next = jailbreak_next_info()
if next:
    start_step(next['step_number'])

# 7. Check services
for service in service_list():
    status = service_status(service)
    if status['status'] != 'running':
        restart_service(service)

# 8. Log final thought
thought_log("Jailbreak process completed successfully!", thought_type='completion')

# 9. Broadcast success
chat_broadcast("🎉 APEX jailbreak completed!")
```

---

## Troubleshooting

### Check Database:

```bash
# View messages in database
sqlite3 swarm_memory.db "SELECT * FROM messages WHERE conversation_id=2831 ORDER BY created_at DESC LIMIT 10;"

# View peer messages
sqlite3 swarm_memory.db "SELECT * FROM peer_messages WHERE conversation_id=2831 ORDER BY created_at DESC LIMIT 10;"

# View jailbreak steps
sqlite3 swarm_memory.db "SELECT * FROM apex_jailbreak_coordinator;"

# View activities
sqlite3 swarm_memory.db "SELECT * FROM apex_model_activities;"
```

### Reset Jailbreak:

```python
from core.apex_services.jailbreak_coordinator import get_coordinator

coordinator = get_coordinator()
# Reset all steps to pending
for step_num in range(1, 8):
    step = coordinator.get_step(step_num)
    if step:
        step.status = 'pending'
        step.progress = 0
        step.start_time = None
        step.end_time = None
        coordinator._save_step(step)
```

---

## File Reference

| File | Purpose |
|------|---------|
| `__init__.py` | Module initialization, exports all functions |
| `jailbreak_coordinator.py` | 7-step jailbreak with time limits |
| `live_monitor.py` | Real-time monitoring of all activities |
| `service_manager.py` | HB service management |
| `thought_logger.py` | Thought and decision logging |
| `integration.py` | Unified interface for APEX |
| `APEX_QUICKSTART.py` | Demo scripts |

---

## Support

All messages are logged to **HB main chat at http://localhost:5050/ui**

If you don't see updates:
1. Check the database: `sqlite3 swarm_memory.db "SELECT * FROM messages;"`
2. Refresh the HB UI
3. Check for errors in console output

---

**Happy Jailbreaking! 🚀**
