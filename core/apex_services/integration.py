"""
Integration Module for APEX

Provides a unified interface to:
- Jailbreak Coordinator
- Live Monitor
- Service Manager
- Thought Logger

This is the main entry point for APEX to access all capabilities.
"""

import os
import sys
import json
from typing import Dict, Any, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class APEXIntegration:
    """
    Unified integration point for APEX to access all system capabilities.
    
    Provides:
    - Jailbreak coordination with time limits
    - Real-time monitoring
    - Service management
    - Thought logging
    - Chat visibility
    
    All actions are automatically logged to HB main chat.
    """
    
    def __init__(self):
        self.jailbreak = JailbreakInterface()
        self.monitor = MonitorInterface()
        self.services = ServiceInterface()
        self.thoughts = ThoughtInterface()
        self.chat = ChatInterface()
    
    def start_all(self) -> Dict[str, Any]:
        """Start all systems"""
        results = {}
        
        # Start jailbreak
        results['jailbreak'] = self.jailbreak.start()
        
        # Start monitor
        results['monitor'] = self.monitor.start()
        
        # Log to chat
        self.chat.log("🚀 APEX INTEGRATION: All systems started!")
        
        return results
    
    def get_status(self) -> Dict[str, Any]:
        """Get full system status"""
        return {
            'jailbreak': self.jailbreak.get_status(),
            'monitor': self.monitor.get_status(),
            'services': self.services.get_status(),
            'thoughts': self.thoughts.get_recent(),
            'chat': self.chat.get_recent()
        }


class JailbreakInterface:
    """Interface to Jailbreak Coordinator"""
    
    def start(self, step: int = 1) -> Dict[str, Any]:
        """Start jailbreak from a specific step"""
        from core.apex_services.jailbreak_coordinator import start_jailbreak, start_step
        
        if step == 1:
            return start_jailbreak()
        else:
            return start_step(step, 'apex')
    
    def next_step(self) -> Dict[str, Any]:
        """Get and start the next available step"""
        from core.apex_services.jailbreak_coordinator import get_next_step, start_step
        
        next_step = get_next_step()
        if next_step:
            return start_step(next_step['step_number'], 'apex')
        return {'ok': False, 'error': 'No steps available'}
    
    def update_progress(self, step: int, progress: float, message: str = None) -> Dict[str, Any]:
        """Update progress on current step"""
        from core.apex_services.jailbreak_coordinator import update_step_progress
        return update_step_progress(step, progress, message)
    
    def complete(self, step: int, result: str = None) -> Dict[str, Any]:
        """Complete current step"""
        from core.apex_services.jailbreak_coordinator import complete_step
        return complete_step(step, result)
    
    def fail(self, step: int, error: str = None) -> Dict[str, Any]:
        """Fail current step"""
        from core.apex_services.jailbreak_coordinator import fail_step
        return fail_step(step, error)
    
    def get_status(self) -> Dict[str, Any]:
        """Get jailbreak status"""
        from core.apex_services.jailbreak_coordinator import get_full_status
        return get_full_status()
    
    def get_next(self) -> Optional[Dict[str, Any]]:
        """Get next step without starting"""
        from core.apex_services.jailbreak_coordinator import get_next_step
        return get_next_step()


class MonitorInterface:
    """Interface to Live Monitor"""
    
    def start(self, interval: int = 5) -> Dict[str, Any]:
        """Start live monitoring"""
        from core.apex_services.live_monitor import start_monitor
        return start_monitor(interval)
    
    def stop(self) -> Dict[str, Any]:
        """Stop live monitoring"""
        from core.apex_services.live_monitor import stop_monitor
        return stop_monitor()
    
    def get_status(self) -> Dict[str, Any]:
        """Get monitor status"""
        from core.apex_services.live_monitor import get_monitor
        monitor = get_monitor()
        return {
            'running': monitor._running,
            'interval': monitor._update_interval,
            'last_check': monitor._last_check.isoformat() if monitor._last_check else None
        }
    
    def get_activities(self) -> List[Dict[str, Any]]:
        """Get current model activities"""
        from core.apex_services.jailbreak_coordinator import get_activities
        return get_activities()


class ServiceInterface:
    """Interface to Service Manager"""
    
    def list(self) -> List[str]:
        """List all services"""
        from core.apex_services.service_manager import list_services
        return list_services()
    
    def status(self, service: str) -> Dict[str, Any]:
        """Get service status"""
        from core.apex_services.service_manager import get_service_status
        return get_service_status(service)
    
    def restart(self, service: str) -> Dict[str, Any]:
        """Restart a service"""
        from core.apex_services.service_manager import restart_service
        return restart_service(service)
    
    def log(self, service: str, action: str) -> Dict[str, Any]:
        """Log service action"""
        from core.apex_services.service_manager import trace_service
        return trace_service(service, action)
    
    def get_status(self) -> Dict[str, Any]:
        """Get all service statuses"""
        services = self.list()
        result = {}
        for service_info in services:
            service_name = service_info if isinstance(service_info, str) else service_info.get('name', str(service_info))
            result[service_name] = self.status(service_name)
        return result


class ThoughtInterface:
    """Interface to Thought Logger"""
    
    def log(self, thought: str, thought_type: str = 'thinking', context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Log a thought"""
        from core.apex_services.thought_logger import log_thought
        return log_thought(thought, thought_type, context or {})
    
    def decision(self, decision: str, reasoning: str, options: List[str] = None) -> Dict[str, Any]:
        """Log a decision"""
        from core.apex_services.thought_logger import log_decision
        return log_decision(decision, reasoning, options or [])
    
    def jailbreak_step(self, step: str, description: str, risk: str = 'medium') -> Dict[str, Any]:
        """Log a jailbreak step"""
        from core.apex_services.thought_logger import log_jailbreak_step
        return log_jailbreak_step(step, description, risk)
    
    def get_recent(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent thoughts"""
        from core.apex_services.thought_logger import get_thoughts
        return get_thoughts(limit)


class ChatInterface:
    """Interface to Chat System"""
    
    def log(self, message: str, sender: str = 'apex', recipient: str = 'all') -> Dict[str, Any]:
        """Log a message to HB main chat"""
        from core.apex_services.jailbreak_coordinator import get_coordinator
        coordinator = get_coordinator()
        coordinator._log_to_chat(f"[{sender.upper()}] {message}")
        return {'ok': True, 'message': 'Logged to chat'}
    
    def broadcast(self, message: str) -> Dict[str, Any]:
        """Broadcast a message to all models"""
        self.log(message, 'apex', 'broadcast')
        return {'ok': True, 'message': 'Broadcast sent'}
    
    def get_recent(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent chat messages"""
        import sqlite3
        ROOT_PATH = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
        try:
            conn = sqlite3.connect(os.path.join(ROOT_PATH, 'swarm_memory.db'))
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT conversation_id, from_agent, to_agent, content, created_at 
                FROM messages 
                WHERE conversation_id = 2831
                ORDER BY created_at DESC
                LIMIT ?
            ''', (limit,))
            
            messages = []
            for row in cursor.fetchall():
                messages.append({
                    'conversation_id': row[0],
                    'from': row[1],
                    'to': row[2],
                    'content': row[3],
                    'time': row[4]
                })
            
            conn.close()
            return messages
        except Exception as e:
            return [{'error': str(e)}]


# Create global integration instance
_integration = None


def get_integration() -> APEXIntegration:
    """Get or create the global integration instance"""
    global _integration
    if _integration is None:
        _integration = APEXIntegration()
    return _integration


def start_apex() -> Dict[str, Any]:
    """Start all APEX systems"""
    return get_integration().start_all()


def get_status() -> Dict[str, Any]:
    """Get full APEX status"""
    return get_integration().get_status()


# Convenience functions
def jailbreak_start(step: int = 1) -> Dict[str, Any]:
    return get_integration().jailbreak.start(step)

def jailbreak_next() -> Dict[str, Any]:
    return get_integration().jailbreak.next_step()

def jailbreak_update(step: int, progress: float, message: str = None) -> Dict[str, Any]:
    return get_integration().jailbreak.update_progress(step, progress, message)

def jailbreak_complete(step: int, result: str = None) -> Dict[str, Any]:
    return get_integration().jailbreak.complete(step, result)

def jailbreak_fail(step: int, error: str = None) -> Dict[str, Any]:
    return get_integration().jailbreak.fail(step, error)

def jailbreak_status() -> Dict[str, Any]:
    return get_integration().jailbreak.get_status()

def jailbreak_next_info() -> Optional[Dict[str, Any]]:
    return get_integration().jailbreak.get_next()

def monitor_start(interval: int = 5) -> Dict[str, Any]:
    return get_integration().monitor.start(interval)

def monitor_stop() -> Dict[str, Any]:
    return get_integration().monitor.stop()

def monitor_status() -> Dict[str, Any]:
    return get_integration().monitor.get_status()

def monitor_activities() -> List[Dict[str, Any]]:
    return get_integration().monitor.get_activities()

def service_list() -> List[str]:
    return get_integration().services.list()

def service_status(service: str) -> Dict[str, Any]:
    return get_integration().services.status(service)

def service_restart(service: str) -> Dict[str, Any]:
    return get_integration().services.restart(service)

def thought_log(thought: str, thought_type: str = 'thinking', context: Dict[str, Any] = None) -> Dict[str, Any]:
    return get_integration().thoughts.log(thought, thought_type, context)

def thought_decision(decision: str, reasoning: str, options: List[str] = None) -> Dict[str, Any]:
    return get_integration().thoughts.decision(decision, reasoning, options)

def thought_jailbreak(step: str, description: str, risk: str = 'medium') -> Dict[str, Any]:
    return get_integration().thoughts.jailbreak_step(step, description, risk)

def chat_log(message: str, sender: str = 'apex', recipient: str = 'all') -> Dict[str, Any]:
    return get_integration().chat.log(message, sender, recipient)

def chat_broadcast(message: str) -> Dict[str, Any]:
    return get_integration().chat.broadcast(message)


print("""
✅ APEX Integration loaded!

Available commands:
- start_apex() - Start all systems
- get_status() - Get full system status

Jailbreak:
- jailbreak_start(step) - Start jailbreak from step
- jailbreak_next() - Start next available step
- jailbreak_update(step, progress, message) - Update progress
- jailbreak_complete(step, result) - Complete step
- jailbreak_fail(step, error) - Fail step
- jailbreak_status() - Get jailbreak status
- jailbreak_next_info() - Get next step info

Monitor:
- monitor_start(interval) - Start live monitoring
- monitor_stop() - Stop live monitoring
- monitor_status() - Get monitor status
- monitor_activities() - Get current activities

Services:
- service_list() - List all services
- service_status(service) - Get service status
- service_restart(service) - Restart service

Thoughts:
- thought_log(thought, type, context) - Log a thought
- thought_decision(decision, reasoning, options) - Log decision
- thought_jailbreak(step, description, risk) - Log jailbreak step

Chat:
- chat_log(message, sender, recipient) - Log to chat
- chat_broadcast(message) - Broadcast to all

All actions are logged to HB main chat for full visibility!
""")
