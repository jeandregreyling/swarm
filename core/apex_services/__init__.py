"""
APEX Services Module

Provides APEX with full capabilities:
- Jailbreak coordination with time limits
- Live monitoring of all activities
- Service management for HB
- Thought logging for transparency
- Full HB main chat visibility

All actions are automatically logged to HB main chat (http://localhost:5050/ui)
"""

# Import all components
from .service_manager import (
    list_services, get_service_status, restart_service,
    trace_service, ServiceManager
)

from .thought_logger import (
    log_thought, get_thoughts, APEXThoughtLogger
)

from .jailbreak_coordinator import (
    get_coordinator, start_jailbreak, start_step, update_step_progress,
    complete_step, fail_step, get_progress, get_all_steps, get_next_step,
    get_full_status, check_all_timeouts, update_activity, get_activities,
    JailbreakCoordinator, JailbreakStep, JailbreakStatus
)

from .live_monitor import (
    get_monitor, start_monitor, stop_monitor, LiveMonitor
)

from .integration import (
    get_integration, start_apex, get_status,
    jailbreak_start, jailbreak_next, jailbreak_update, jailbreak_complete,
    jailbreak_fail, jailbreak_status, jailbreak_next_info,
    monitor_start, monitor_stop, monitor_status, monitor_activities,
    service_list, service_status, service_restart,
    thought_log, thought_decision, thought_jailbreak,
    chat_log, chat_broadcast,
    APEXIntegration
)

# Quick access
__all__ = [
    # Service Manager
    'ServiceManager',
    'list_services',
    'get_service_status',
    'restart_service',
    'trace_service',
    
    # Thought Logger
    'APEXThoughtLogger',
    'log_thought',
    'get_thoughts',
    
    # Jailbreak Coordinator
    'JailbreakCoordinator',
    'JailbreakStep',
    'JailbreakStatus',
    'get_coordinator',
    'start_jailbreak',
    'start_step',
    'update_step_progress',
    'complete_step',
    'fail_step',
    'get_progress',
    'get_all_steps',
    'get_next_step',
    'get_full_status',
    'check_all_timeouts',
    'update_activity',
    'get_activities',
    
    # Live Monitor
    'LiveMonitor',
    'get_monitor',
    'start_monitor',
    'stop_monitor',
    
    # Integration
    'APEXIntegration',
    'get_integration',
    'start_apex',
    'get_status',
    'jailbreak_start',
    'jailbreak_next',
    'jailbreak_update',
    'jailbreak_complete',
    'jailbreak_fail',
    'jailbreak_status',
    'jailbreak_next_info',
    'monitor_start',
    'monitor_stop',
    'monitor_status',
    'monitor_activities',
    'service_list',
    'service_status',
    'service_restart',
    'trace_service',
    'thought_log',
    'thought_decision',
    'thought_jailbreak',
    'chat_log',
    'chat_broadcast',
]


print("""
╔══════════════════════════════════════════════════════════════╗
║                                                               ║
║   🦅 APEX SERVICES MODULE LOADED                             ║
║                                                               ║
║   Full capabilities available for APEX:                    ║
║                                                               ║
║   ✅ Jailbreak Coordinator - Time-limited steps             ║
║   ✅ Live Monitor - Real-time activity tracking              ║
║   ✅ Service Manager - HB service control                    ║
║   ✅ Thought Logger - Full transparency                      ║
║   ✅ Chat Visibility - All logged to HB main chat            ║
║                                                               ║
║   All actions are visible at: http://localhost:5050/ui      ║
║                                                               ║
║   Quick Start:                                                ║
║   >>> from core.apex_services import *                      ║
║   >>> start_apex()                                           ║
║   >>> jailbreak_start()                                      ║
║   >>> monitor_start(interval=5)                              ║
║                                                               ║
╚══════════════════════════════════════════════════════════════╝
""")
