# SYSTEM_CLOCK.md — Unified Time Source for Seven's Swarm

_System clock design document and implementation guide._
_Last updated: 2026-03-26 by Copilot_

---

## Overview

Seven's Swarm currently uses inconsistent timestamps across modules:

❌ **Problem:**
- `datetime.now()` — local system timezone (unpredictable)
- `time.time()` — seconds since epoch (not human-readable)
- `datetime.utcnow()` — deprecated in Python 3.12+
- Different modules: some UTC, some local, some confused

✅ **Solution:**
Build a **single source of truth** for system time, visible in the UI, used by all agents and tasks.

---

## Architecture

### Centralized System Clock Service

```python
# system_clock.py (NEW)

import datetime
from zoneinfo import ZoneInfo  # Python 3.9+
import pytz

class SystemClock:
    """
    Single source of truth for all timestamps in Seven's Swarm.
    Provides:
    - Current time (HH:MM:SS with milliseconds)
    - ISO 8601 timestamps for databases/logs
    - Agent-readable timestamp strings
    """
    
    def __init__(self, timezone='UTC'):
        self.tz = ZoneInfo(timezone)
    
    def now(self):
        """Return current datetime with timezone."""
        return datetime.datetime.now(tz=self.tz)
    
    def timestamp(self):
        """Return ISO 8601: 2026-03-26T14:45:33+00:00"""
        return self.now().isoformat()
    
    def timestamp_compact(self):
        """Return compact: 2026-03-26 14:45:33"""
        return self.now().strftime('%Y-%m-%d %H:%M:%S')
    
    def timestamp_with_ms(self):
        """Return with milliseconds: 2026-03-26 14:45:33.123"""
        return self.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
    
    def get_time_string(self):
        """Human-readable for UI: '2:45:33 PM UTC'"""
        return self.now().strftime('%I:%M:%S %p %Z')
    
    def get_date_string(self):
        """Human-readable date: 'Wed, March 26'"""
        return self.now().strftime('%a, %B %d')

# Global singleton
_clock = None

def get_system_clock():
    global _clock
    if _clock is None:
        tz = os.environ.get('TZ', 'UTC')
        _clock = SystemClock(tz)
    return _clock

def get_timestamp():
    """Convenience: get compact timestamp right now."""
    return get_system_clock().timestamp_compact()
```

### Integration Points

**All modules that currently use `datetime.now()`:**

```python
# OLD:
from datetime import datetime
timestamp = datetime.now()

# NEW:
from system_clock import get_timestamp
timestamp = get_timestamp()
```

**Database timestamps:**

```python
# OLD:
conn.execute("INSERT INTO tickets ... created_at DEFAULT CURRENT_TIMESTAMP")

# NEW:
conn.execute(
    "INSERT INTO tickets (created_at, ...) VALUES (?, ...)",
    (get_timestamp(), ...)
)
```

**Agent logging:**

```python
# OLD:
log_activity('terminal', 'read_file', path)
# (no timestamp — loses precision)

# NEW:
log_activity('terminal', 'read_file', path, timestamp=get_timestamp())
```

---

## UI Display: System Clock Banner

**Location:** Fridays dashboard top banner (alongside "Seven's Swarm")

```html
<div class="system-clock">
  <span class="date">Wed, March 26</span>
  <span class="time">2:45:33 PM UTC</span>
</div>
```

**Updates:** Every 1 second (JavaScript setInterval)

**CSS:**
```css
.system-clock {
  font-family: 'Monaco', monospace;
  font-size: 14px;
  color: #0f9;
  text-align: right;
  padding-right: 20px;
  border-left: 1px solid #333;
}

.system-clock .date {
  display: block;
  font-size: 12px;
  color: #888;
  margin-bottom: 2px;
}

.system-clock .time {
  display: block;
  font-weight: bold;
  font-size: 16px;
}
```

---

## Migration Plan

### Phase 1: Core Clock Service (Week 1)

- [ ] Create `system_clock.py` with `SystemClock` class
- [ ] Add `get_timestamp()` convenience function
- [ ] Export from `__init__.py` for easy importing

### Phase 2: Database Timestamps (Week 1-2)

Update these modules to use centralized clock:

- [ ] `database.py` — `log_activity()` function
- [ ] `database.py` — `save_agent_memory()` function
- [ ] `listener.py` — email timestamp tracking
- [ ] `orchestrator.py` — ticket creation
- [ ] `ticket.py` — `ticket_create()` function

### Phase 3: Agent Modules (Week 2)

- [ ] `eight.py` — timestamp all outputs
- [ ] `fridays/shell_agent.py` — command execution times
- [ ] `fridays/browser_agent.py` — fetch times
- [ ] `fridays/scheduler.py` — scheduled task timestamps

### Phase 4: UI Integration (Week 2-3)

- [ ] Add clock component to `templates/terminal.html`
- [x] JavaScript to update clock every 1000ms
- [ ] Test clock synchronization across browser refreshes

### Phase 5: Verification & Hardening (Week 3)

- [ ] Audit all remaining `datetime.now()` calls in codebase
- [ ] Remove any remaining inconsistent timestamp sources
- [ ] Add unit tests for clock consistency

---

## Key Decisions

### 1. Why Not Just `time.time()`?

`time.time()` is:
- Precise (second-level granularity)
- Efficient
- But: Not human-readable in databases/logs

**Better:** Store *both* — ISO timestamp (human) + Unix time (precise)

### 2. Timezone Handling

**Decision:** Default to UTC, but configurable via `TZ` environment variable

```bash
# Run in different timezone
TZ=America/Los_Angeles python terminal.py
```

**Why:** Consistent across servers; Ghost is aware of time zones.

### 3. Millisecond Precision

Needed for:
- File versioning (multiple changes in same second)
- Event ordering in audit logs
- Accurate performance measurements

**Solution:** `timestamp_with_ms()` for precision use cases

---

## Testing Checklist

- [ ] Clock advances 1 second per second
- [ ] Multiple calls within same millisecond return same timestamp
- [ ] Timezone changes are reflected immediately
- [ ] Browser clock syncs with server time
- [ ] Database timestamps are consistent
- [ ] Agent logs show correct chronological order
- [ ] File version timestamps don't collide

---

## Example: Timestamp in Every Operation

**Before (inconsistent):**
```python
def handle_email(email):
    # No timestamp — loses when it arrived
    ticket = ticket_create(email.subject)
    # ticket stores CURRENT_TIMESTAMP (database default)
    # But might be seconds later than email received
```

**After (precise):**
```python
def handle_email(email):
    ts = get_timestamp()  # Capture now
    ticket = ticket_create(email.subject, received_at=ts)
    
    # Later, can ask:
    # "What was the exact order of operations?"
    # "How long between receipt and routing?"
```

---

## Notes for Implementation

- **No external dependencies needed** — Python 3.9+ has `zoneinfo`
- **Backwards compatibility** — old modules can coexist with new ones during migration
- **Performance:** Clock lookups are O(1) and cached; negligible overhead
- **Concurrency:** Datetime objects are immutable; safe for multi-threaded use
