"""
system_clock.py — Seven's Swarm Unified Time Source
═══════════════════════════════════════════════════════════════════════════════
Single source of truth for all timestamps. Centralized system clock used by all
agents, database operations, and UI components.

Usage:
  from system_clock import get_timestamp, get_system_clock
  
  ts = get_timestamp()                    # "2026-03-26 14:45:33"
  ts_iso = get_timestamp_iso()            # "2026-03-26T14:45:33+00:00"
  ts_ms = get_timestamp_with_ms()         # "2026-03-26 14:45:33.123"
  
  clock = get_system_clock()
  clock.now()                             # datetime object
  clock.get_time_string()                 # "2:45 PM UTC"
  clock.get_date_string()                 # "Wed, March 26"
═══════════════════════════════════════════════════════════════════════════════
"""

import os
import sys
from datetime import datetime

# Python 3.9+ has zoneinfo in stdlib
try:
    from zoneinfo import ZoneInfo
except ImportError:
    # Fallback for Python < 3.9
    import pytz
    ZoneInfo = None

sys.path.insert(0, '/home/seven/swarm')


class SystemClock:
    """
    Unified system clock for Seven's Swarm.
    
    Provides consistent timestamps with timezone awareness.
    All timestamps use UTC by default, but can be configured via TZ env var.
    """
    
    def __init__(self, timezone='UTC'):
        """Initialize clock with specified timezone."""
        self.timezone_name = timezone
        
        # Use zoneinfo if available (Python 3.9+), else fallback to pytz
        if ZoneInfo is not None:
            try:
                self.tz = ZoneInfo(timezone)
            except KeyError:
                print(f"[SystemClock] Warning: Unknown timezone '{timezone}', using UTC")
                self.tz = ZoneInfo('UTC')
        else:
            try:
                self.tz = pytz.timezone(timezone)
            except Exception:
                self.tz = pytz.UTC
    
    def now(self):
        """Return current datetime with timezone info."""
        return datetime.now(tz=self.tz)
    
    def timestamp(self):
        """Return ISO 8601 format: 2026-03-26T14:45:33+00:00"""
        return self.now().isoformat()
    
    def timestamp_compact(self):
        """Return compact format: 2026-03-26 14:45:33 (no timezone)"""
        return self.now().strftime('%Y-%m-%d %H:%M:%S')
    
    def timestamp_with_ms(self):
        """Return with milliseconds: 2026-03-26 14:45:33.123"""
        return self.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
    
    def timestamp_date_only(self):
        """Return date only: 2026-03-26"""
        return self.now().strftime('%Y-%m-%d')
    
    def get_time_string(self):
        """Human-readable time for UI: '2:45:33 PM UTC'"""
        return self.now().strftime('%I:%M:%S %p %Z')
    
    def get_time_short(self):
        """Short time for UI: '2:45 PM'"""
        return self.now().strftime('%I:%M %p')
    
    def get_date_string(self):
        """Human-readable date: 'Wed, March 26'"""
        return self.now().strftime('%a, %B %d')
    
    def get_full_string(self):
        """Full readable format: 'Wed, March 26 • 2:45:33 PM UTC'"""
        return f"{self.get_date_string()} • {self.get_time_string()}"
    
    def get_unix_timestamp(self):
        """Return Unix timestamp (seconds since epoch)"""
        return int(self.now().timestamp())


# Global singleton instance
_clock_instance = None


def get_system_clock():
    """Get or create the global system clock instance."""
    global _clock_instance
    if _clock_instance is None:
        tz = os.environ.get('TZ', 'UTC')
        _clock_instance = SystemClock(tz)
    return _clock_instance


def get_timestamp():
    """Convenience function: get current compact timestamp right now."""
    return get_system_clock().timestamp_compact()


def get_timestamp_iso():
    """Convenience function: get ISO 8601 timestamp."""
    return get_system_clock().timestamp()


def get_timestamp_with_ms():
    """Convenience function: get timestamp with milliseconds."""
    return get_system_clock().timestamp_with_ms()


def get_timestamp_date():
    """Convenience function: get date only."""
    return get_system_clock().timestamp_date_only()


def get_time_string():
    """Convenience function: get human-readable time."""
    return get_system_clock().get_time_string()


def get_date_string():
    """Convenience function: get human-readable date."""
    return get_system_clock().get_date_string()


def get_full_time_string():
    """Convenience function: get full formatted time string."""
    return get_system_clock().get_full_string()


# Test/Demo
if __name__ == '__main__':
    clock = get_system_clock()
    print('[SystemClock] Testing system_clock.py...')
    print(f'  Timezone: {clock.timezone_name}')
    print(f'  Date: {clock.get_date_string()}')
    print(f'  Time: {clock.get_time_string()}')
    print(f'  Compact: {clock.timestamp_compact()}')
    print(f'  With MS: {clock.timestamp_with_ms()}')
    print(f'  ISO: {clock.timestamp()}')
    print(f'  Unix: {clock.get_unix_timestamp()}')
    print('✓ system_clock.py works')
