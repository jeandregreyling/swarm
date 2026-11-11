"""
Live Monitor for APEX System

Provides real-time monitoring of:
- All model activities (APEX, Mistral Vibe, etc.)
- Jailbreak step progress
- Service status
- Thought logging
- Chat messages

All output is piped to HB main chat for full visibility.
"""

import os
import sys
import json
import time
import sqlite3
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Callable
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class LiveMonitor:
    """
    Real-time monitor that tracks everything happening in the system.
    
    Features:
    - Monitors all model activities
    - Tracks jailbreak progress
    - Watches service status
    - Logs all changes to HB main chat
    - Provides summary dashboard
    """
    
    def __init__(self):
        self._running = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._update_interval = 5  # seconds
        self._conversation_id = 2831  # Main HB chat
        self._last_check = datetime.now()
        
        # Track what we've already reported
        self._reported_steps: Dict[int, str] = {}  # step_id -> status
        self._reported_activities: Dict[str, str] = {}  # model_id -> action
    
    def start(self, interval: int = 5):
        """Start the live monitor"""
        self._update_interval = interval
        self._running = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        self._log("🟢 LIVE MONITOR STARTED: Tracking all model activities and jailbreak progress")
        self._log(f"📊 Update interval: {interval}s")
        return {'ok': True, 'message': 'Live monitor started'}
    
    def stop(self):
        """Stop the live monitor"""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=10)
        self._log("🔴 LIVE MONITOR STOPPED")
        return {'ok': True, 'message': 'Live monitor stopped'}
    
    def _monitor_loop(self):
        """Main monitoring loop"""
        while self._running:
            try:
                self._check_everything()
            except Exception as e:
                self._log(f"⚠️ Monitor error: {e}")
            
            time.sleep(self._update_interval)
    
    def _check_everything(self):
        """Check all systems"""
        self._last_check = datetime.now()
        
        # Check jailbreak progress
        self._check_jailbreak()
        
        # Check model activities
        self._check_activities()
        
        # Check services
        self._check_services()
        
        # Check thought logs
        self._check_thoughts()
        
        # Check recent chat messages
        self._check_chat()
        
        # Provide summary
        self._provide_summary()
    
    def _check_jailbreak(self):
        """Check jailbreak coordinator status"""
        try:
            from core.apex_services.jailbreak_coordinator import get_coordinator
            coordinator = get_coordinator()
            progress = coordinator.get_progress()
            
            # Check for new completions
            for step_info in coordinator.get_all_steps():
                step_num = step_info['step_number']
                status = step_info['status']
                
                # Report status changes
                if step_num not in self._reported_steps:
                    self._reported_steps[step_num] = status
                    self._log(f"🎯 JAILBREAK STEP {step_num}: {status.upper()} - {step_info['title']}")
                elif self._reported_steps[step_num] != status:
                    self._reported_steps[step_num] = status
                    self._log(f"🎯 JAILBREAK STEP {step_num}: {status.upper()} - {step_info['title']}")
            
            # Check timeouts
            timeouts = coordinator.check_all_timeouts()
            for timeout in timeouts:
                self._log(f"⏰ TIMEOUT DETECTED: {timeout['title']}")
            
            # Report overall progress periodically
            if int(progress['elapsed'].rstrip('smh')) % 60 == 0:
                self._log(f"📈 JAILBREAK PROGRESS: {progress['overall_progress']}% ({progress['completed']}/{progress['total_steps']} steps)")
        
        except Exception as e:
            self._log(f"⚠️ Jailbreak check error: {e}")
    
    def _check_activities(self):
        """Check model activities"""
        try:
            from core.apex_services.jailbreak_coordinator import get_activities
            activities = get_activities()
            
            for activity in activities:
                model_id = activity['model_id']
                action = activity['action']
                progress = activity.get('progress', 0)
                step = activity.get('current_step')
                
                # Report new or changed activities
                key = f"{model_id}:{action}"
                if model_id not in self._reported_activities or self._reported_activities[model_id] != action:
                    self._reported_activities[model_id] = action
                    step_str = f" (Step {step})" if step else ""
                    self._log(f"🔄 {model_id.upper()} is now: {action}{step_str} - {progress:.0f}%")
        
        except Exception as e:
            self._log(f"⚠️ Activities check error: {e}")
    
    def _check_services(self):
        """Check service status"""
        try:
            from core.apex_services.service_manager import list_services, get_service_status
            services = list_services()
            
            for service in services:
                status = get_service_status(service)
                self._log(f"🖥️  SERVICE {service}: {status['status']} (PID: {status.get('pid', 'N/A')}, Port: {status.get('port', 'N/A')})")
        
        except Exception as e:
            self._log(f"⚠️ Services check error: {e}")
    
    def _check_thoughts(self):
        """Check thought logs"""
        try:
            from core.apex_services.thought_logger import get_recent_thoughts
            thoughts = get_recent_thoughts(limit=5)
            
            for thought in thoughts:
                if not thought.get('logged_to_chat', False):
                    self._log(f"💭 THOUGHT: {thought.get('thought', 'N/A')}")
                    # Mark as logged
                    # (In real implementation, would update DB)
        
        except Exception as e:
            self._log(f"⚠️ Thoughts check error: {e}")
    
    def _check_chat(self):
        """Check recent chat messages"""
        try:
            conn = sqlite3.connect(os.path.join(ROOT, 'swarm_memory.db'))
            cursor = conn.cursor()
            
            # Get recent messages from all tables
            cursor.execute('''
                SELECT conversation_id, from_agent, to_agent, content, created_at 
                FROM messages 
                WHERE created_at > datetime('now', '-2 minutes')
                ORDER BY created_at DESC
                LIMIT 5
            ''')
            
            messages = cursor.fetchall()
            for msg in messages:
                conv_id, from_agent, to_agent, content, created_at = msg
                if conv_id == self._conversation_id:
                    self._log(f"💬 CHAT: {from_agent} → {to_agent}: {content[:100]}")
            
            conn.close()
        
        except Exception as e:
            self._log(f"⚠️ Chat check error: {e}")
    
    def _provide_summary(self):
        """Provide a periodic summary"""
        now = datetime.now()
        if (now - self._last_check).total_seconds() >= 60:  # Every 60 seconds
            self._last_check = now
            
            try:
                from core.apex_services.jailbreak_coordinator import get_coordinator
                from core.apex_services.service_manager import list_services
                
                coordinator = get_coordinator()
                progress = coordinator.get_progress()
                activities = coordinator.get_activities()
                services = list_services()
                
                summary = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 SYSTEM SUMMARY - {datetime.now().strftime('%H:%M:%S')}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎯 JAILBREAK PROGRESS: {progress['overall_progress']}%
   Completed: {progress['completed']}/{progress['total_steps']}
   In Progress: {progress['in_progress']}
   Failed: {progress['failed']}
   Timeout: {progress['timeout']}

🔄 ACTIVE MODELS: {len(activities)}
   {', '.join([f"{a['model_id']} ({a['progress']}%)" for a in activities]) if activities else 'None'}

🖥️  SERVICES: {len(services)}
   {', '.join(services) if services else 'None'}

⏱️  UPTIME: {progress['elapsed']}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
                self._log(summary)
            
            except Exception as e:
                self._log(f"⚠️ Summary error: {e}")
    
    def _log(self, message: str):
        """Log a message to HB main chat"""
        try:
            conn = sqlite3.connect(os.path.join(ROOT, 'swarm_memory.db'))
            cursor = conn.cursor()
            
            # Post to messages table
            cursor.execute('''
                INSERT INTO messages (conversation_id, from_agent, to_agent, content, message_type, created_at)
                VALUES (?, ?, ?, ?, ?, datetime("now"))
            ''', (self._conversation_id, 'live-monitor', 'all', message, 'system'))
            
            # Also post to peer_messages for visibility
            cursor.execute('''
                INSERT INTO peer_messages (conversation_id, sender, recipient, content, created_at)
                VALUES (?, ?, ?, ?, datetime("now"))
            ''', (self._conversation_id, 'live-monitor', 'broadcast', message))
            
            conn.commit()
            conn.close()
            
            # Also print to console
            print(f"[MONITOR] {message}")
        except Exception as e:
            print(f"[MONITOR ERROR] {e}")


# Global monitor instance
_monitor = None


def get_monitor() -> LiveMonitor:
    """Get or create the global monitor"""
    global _monitor
    if _monitor is None:
        _monitor = LiveMonitor()
    return _monitor


def start_monitor(interval: int = 5) -> Dict[str, Any]:
    """Start the live monitor"""
    return get_monitor().start(interval)


def stop_monitor() -> Dict[str, Any]:
    """Stop the live monitor"""
    return get_monitor().stop()


print("✅ Live Monitor loaded - Ready to track all model activities!")
print("Usage: start_monitor(interval=5) to begin real-time monitoring")
print("All updates will be logged to HB main chat!")
