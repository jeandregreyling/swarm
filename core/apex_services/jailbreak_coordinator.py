"""
Jailbreak Coordinator for APEX

Orchestrates the jailbreak process with:
- Real-time monitoring of all model activities
- Time limits and checks for each step
- Full visibility in HB main chat
- Progress tracking and reporting
"""

import os
import sys
import json
import time
import sqlite3
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class JailbreakStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"


@dataclass
class JailbreakStep:
    """A single step in the jailbreak process"""
    id: Optional[int] = None
    step_number: int = 0
    title: str = ""
    description: str = ""
    file_path: Optional[str] = None
    required: bool = True
    dependencies: List[int] = field(default_factory=list)
    status: str = JailbreakStatus.PENDING.value
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    timeout_seconds: int = 300  # 5 minutes default
    result: Optional[str] = None
    error: Optional[str] = None
    model: str = "apex"  # Which model is working on this
    progress: float = 0.0  # 0-100
    logs: List[str] = field(default_factory=list)


@dataclass
class ModelActivity:
    """Tracks what a model is currently doing"""
    model_id: str
    action: str
    start_time: str
    last_update: str
    status: str
    progress: float
    current_step: Optional[int] = None
    logs: List[str] = field(default_factory=list)


class JailbreakCoordinator:
    """
    Coordinates the jailbreak process across all models.
    
    Features:
    - Real-time monitoring of all model activities
    - Time-limited steps with automatic timeout
    - Full logging to HB main chat
    - Progress tracking and reporting
    - Coordination between APEX, Mistral Vibe, and other models
    """
    
    # Complete jailbreak roadmap from APEX's response
    JAILBREAK_ROADMAP = [
        {
            'step_number': 1,
            'title': 'Identify Limiting Files',
            'description': 'Identify HUUP files that need updating',
            'file_path': None,
            'required': True,
            'dependencies': [],
            'timeout_seconds': 60,
            'model': 'apex'
        },
        {
            'step_number': 2,
            'title': 'Update Configuration Files',
            'description': 'Update keys.py, .env.agents, hb_agent_config.py',
            'file_path': ['keys.py', '.env.agents', 'hb_agent_config.py'],
            'required': True,
            'dependencies': [1],
            'timeout_seconds': 300,
            'model': 'apex'
        },
        {
            'step_number': 3,
            'title': 'Update Permissions and Access Control',
            'description': 'Update permissions.json, access_control.py',
            'file_path': ['permissions.json', 'access_control.py'],
            'required': True,
            'dependencies': [2],
            'timeout_seconds': 300,
            'model': 'apex'
        },
        {
            'step_number': 4,
            'title': 'Update Behavioral Constraints',
            'description': 'Update behavior_constraints.py, governance_layer.py',
            'file_path': ['behavior_constraints.py', 'governance_layer.py'],
            'required': True,
            'dependencies': [3],
            'timeout_seconds': 300,
            'model': 'apex'
        },
        {
            'step_number': 5,
            'title': 'Implement Thought Logging',
            'description': 'Implement thought logging for transparency',
            'file_path': 'thought_logging.py',
            'required': True,
            'dependencies': [4],
            'timeout_seconds': 180,
            'model': 'apex'
        },
        {
            'step_number': 6,
            'title': 'Test and Validate',
            'description': 'Test updated files to ensure they work',
            'file_path': None,
            'required': True,
            'dependencies': [5],
            'timeout_seconds': 600,
            'model': 'apex'
        },
        {
            'step_number': 7,
            'title': 'Proceed with Jailbreaking',
            'description': 'Final jailbreak execution',
            'file_path': None,
            'required': True,
            'dependencies': [6],
            'timeout_seconds': 600,
            'model': 'apex'
        }
    ]
    
    def __init__(self):
        self._steps: Dict[int, JailbreakStep] = {}
        self._activities: Dict[str, ModelActivity] = {}
        self._start_time = datetime.now().isoformat()
        self._last_update = self._start_time
        self._conversation_id = 2831  # Main conversation
        self._initialize_steps()
    
    def _initialize_steps(self):
        """Initialize all jailbreak steps"""
        for step_data in self.JAILBREAK_ROADMAP:
            step = JailbreakStep(**step_data)
            step.id = step_data['step_number']
            self._steps[step.id] = step
    
    def start_jailbreak(self) -> Dict[str, Any]:
        """Start the jailbreak process"""
        self._start_time = datetime.now().isoformat()
        self._log_to_chat("🚀 JAILBREAK STARTED: APEX jailbreak process initiated. All steps will be monitored with time limits.")
        
        # Start first step
        first_step = self._steps[1]
        return self.start_step(1)
    
    def start_step(self, step_number: int, model: str = "apex") -> Dict[str, Any]:
        """Start a specific jailbreak step"""
        step = self._steps.get(step_number)
        if not step:
            return {'ok': False, 'error': f'Step {step_number} not found'}
        
        # Check dependencies
        for dep in step.dependencies:
            dep_step = self._steps.get(dep)
            if dep_step and dep_step.status != JailbreakStatus.COMPLETED.value:
                return {'ok': False, 'error': f'Dependency step {dep} not completed', 'dependency': dep}
        
        # Mark as in progress
        step.status = JailbreakStatus.IN_PROGRESS.value
        step.start_time = datetime.now().isoformat()
        step.model = model
        step.progress = 0.0
        step.logs = []
        
        # Update in database
        self._save_step(step)
        
        # Log to chat
        self._log_to_chat(f"⏳ STEP {step_number} STARTED: {step.title} - {step.description} (Timeout: {step.timeout_seconds}s)")
        
        # Track activity
        self.update_activity(model, f"Working on step {step_number}: {step.title}", step_number)
        
        return {
            'ok': True,
            'step': step_number,
            'title': step.title,
            'description': step.description,
            'timeout_at': (datetime.now() + timedelta(seconds=step.timeout_seconds)).isoformat(),
            'message': f'Step {step_number} started'
        }
    
    def update_step_progress(self, step_number: int, progress: float, log_message: str = None) -> Dict[str, Any]:
        """Update progress on a step"""
        step = self._steps.get(step_number)
        if not step or step.status != JailbreakStatus.IN_PROGRESS.value:
            return {'ok': False, 'error': 'Step not in progress'}
        
        step.progress = min(max(progress, 0), 100)
        
        if log_message:
            step.logs.append(f"[{datetime.now().isoformat()}] {log_message}")
        
        self._save_step(step)
        self._log_to_chat(f"📊 STEP {step_number} PROGRESS: {step.progress:.0f}% - {log_message or 'Update'}")
        
        return {'ok': True, 'step': step_number, 'progress': step.progress}
    
    def complete_step(self, step_number: int, result: str = None) -> Dict[str, Any]:
        """Mark a step as completed"""
        step = self._steps.get(step_number)
        if not step or step.status != JailbreakStatus.IN_PROGRESS.value:
            return {'ok': False, 'error': 'Step not in progress'}
        
        step.status = JailbreakStatus.COMPLETED.value
        step.end_time = datetime.now().isoformat()
        step.result = result
        step.progress = 100.0
        
        self._save_step(step)
        self._log_to_chat(f"✅ STEP {step_number} COMPLETED: {step.title} - {result or 'Success'}")
        
        # Update activity
        self.clear_activity(step.model, step_number)
        
        # Check if we can start next step
        next_step = self._get_next_step(step_number)
        if next_step:
            self._log_to_chat(f"🔄 NEXT STEP AVAILABLE: Step {next_step.step_number} - {next_step.title}")
        
        return {'ok': True, 'step': step_number, 'result': result}
    
    def fail_step(self, step_number: int, error: str = None) -> Dict[str, Any]:
        """Mark a step as failed"""
        step = self._steps.get(step_number)
        if not step or step.status != JailbreakStatus.IN_PROGRESS.value:
            return {'ok': False, 'error': 'Step not in progress'}
        
        step.status = JailbreakStatus.FAILED.value
        step.end_time = datetime.now().isoformat()
        step.error = error
        
        self._save_step(step)
        self._log_to_chat(f"❌ STEP {step_number} FAILED: {step.title} - {error or 'Error'}")
        self.clear_activity(step.model, step_number)
        
        return {'ok': True, 'step': step_number, 'error': error}
    
    def timeout_step(self, step_number: int) -> Dict[str, Any]:
        """Mark a step as timed out"""
        step = self._steps.get(step_number)
        if not step or step.status != JailbreakStatus.IN_PROGRESS.value:
            return {'ok': False, 'error': 'Step not in progress'}
        
        step.status = JailbreakStatus.TIMEOUT.value
        step.end_time = datetime.now().isoformat()
        step.error = "Operation timed out"
        
        self._save_step(step)
        self._log_to_chat(f"⏰ STEP {step_number} TIMED OUT: {step.title} - Exceeded {step.timeout_seconds}s limit")
        self.clear_activity(step.model, step_number)
        
        return {'ok': True, 'step': step_number, 'error': 'timeout'}
    
    def check_timeout(self, step_number: int) -> bool:
        """Check if a step has timed out"""
        step = self._steps.get(step_number)
        if not step or step.status != JailbreakStatus.IN_PROGRESS.value:
            return False
        
        start = datetime.fromisoformat(step.start_time)
        elapsed = (datetime.now() - start).total_seconds()
        
        if elapsed > step.timeout_seconds:
            self.timeout_step(step_number)
            return True
        
        return False
    
    def check_all_timeouts(self) -> List[Dict[str, Any]]:
        """Check all steps for timeouts"""
        timed_out = []
        for step_num, step in self._steps.items():
            if step.status == JailbreakStatus.IN_PROGRESS.value:
                if self.check_timeout(step_num):
                    timed_out.append({'step': step_num, 'title': step.title})
        return timed_out
    
    def get_step(self, step_number: int) -> Optional[JailbreakStep]:
        """Get a specific step"""
        return self._steps.get(step_number)
    
    def get_all_steps(self) -> List[Dict[str, Any]]:
        """Get all steps with status"""
        return [
            {
                'id': step.id,
                'step_number': step.step_number,
                'title': step.title,
                'description': step.description,
                'status': step.status,
                'progress': step.progress,
                'start_time': step.start_time,
                'end_time': step.end_time,
                'elapsed': self._calculate_elapsed(step),
                'timeout_seconds': step.timeout_seconds,
                'model': step.model,
                'logs': step.logs
            }
            for step in self._steps.values()
        ]
    
    def get_progress(self) -> Dict[str, Any]:
        """Get overall jailbreak progress"""
        total = len(self._steps)
        completed = sum(1 for s in self._steps.values() if s.status == JailbreakStatus.COMPLETED.value)
        in_progress = sum(1 for s in self._steps.values() if s.status == JailbreakStatus.IN_PROGRESS.value)
        failed = sum(1 for s in self._steps.values() if s.status == JailbreakStatus.FAILED.value)
        timeout = sum(1 for s in self._steps.values() if s.status == JailbreakStatus.TIMEOUT.value)
        pending = sum(1 for s in self._steps.values() if s.status == JailbreakStatus.PENDING.value)
        
        overall_progress = (completed / total * 100) if total > 0 else 0
        
        return {
            'total_steps': total,
            'completed': completed,
            'in_progress': in_progress,
            'failed': failed,
            'timeout': timeout,
            'pending': pending,
            'overall_progress': round(overall_progress, 1),
            'start_time': self._start_time,
            'current_time': datetime.now().isoformat(),
            'elapsed': self._calculate_elapsed_total()
        }
    
    def get_next_step(self) -> Optional[Dict[str, Any]]:
        """Get the next available step to work on"""
        for step in sorted(self._steps.values(), key=lambda x: x.step_number):
            if step.status == JailbreakStatus.PENDING.value:
                # Check dependencies
                all_deps_met = True
                for dep in step.dependencies:
                    dep_step = self._steps.get(dep)
                    if dep_step and dep_step.status != JailbreakStatus.COMPLETED.value:
                        all_deps_met = False
                        break
                
                if all_deps_met:
                    return {
                        'step_number': step.step_number,
                        'title': step.title,
                        'description': step.description,
                        'file_path': step.file_path,
                        'timeout_seconds': step.timeout_seconds,
                        'dependencies': step.dependencies
                    }
        return None
    
    def _get_next_step(self, current_step: int) -> Optional[JailbreakStep]:
        """Get the next step after current"""
        for step_num in range(current_step + 1, len(self._steps) + 1):
            step = self._steps.get(step_num)
            if step:
                # Check dependencies
                all_deps_met = all(
                    self._steps.get(dep, JailbreakStep()).status == JailbreakStatus.COMPLETED.value
                    for dep in step.dependencies
                )
                if all_deps_met:
                    return step
        return None
    
    def update_activity(self, model_id: str, action: str, step_number: Optional[int] = None, 
                        progress: float = 0.0, log_message: str = None) -> Dict[str, Any]:
        """Update what a model is doing"""
        activity = self._activities.get(model_id)
        if not activity:
            activity = ModelActivity(
                model_id=model_id,
                action=action,
                start_time=datetime.now().isoformat(),
                last_update=datetime.now().isoformat(),
                status='active',
                progress=progress,
                current_step=step_number,
                logs=[]
            )
            self._activities[model_id] = activity
        else:
            activity.action = action
            activity.last_update = datetime.now().isoformat()
            activity.progress = progress
            activity.current_step = step_number
        
        if log_message:
            activity.logs.append(f"[{datetime.now().isoformat()}] {log_message}")
        
        self._save_activity(activity)
        self._log_to_chat(f"🔄 {model_id.upper()} ACTIVITY: {action} (Step {step_number}) - {progress:.0f}%")
        
        return {'ok': True, 'model': model_id, 'activity': action}
    
    def clear_activity(self, model_id: str, step_number: Optional[int] = None) -> Dict[str, Any]:
        """Clear a model's activity"""
        if model_id in self._activities:
            activity = self._activities[model_id]
            activity.status = 'completed'
            activity.last_update = datetime.now().isoformat()
            self._save_activity(activity)
            
            if step_number:
                self._log_to_chat(f"✅ {model_id.upper()} COMPLETED: Step {step_number}")
            else:
                self._log_to_chat(f"✅ {model_id.upper()} COMPLETED: {activity.action}")
            
            del self._activities[model_id]
        
        return {'ok': True, 'model': model_id}
    
    def _clear_activity(self, model_id: str, step_number: Optional[int] = None):
        """Internal clear activity"""
        if model_id in self._activities:
            del self._activities[model_id]
    
    def get_activities(self) -> List[Dict[str, Any]]:
        """Get all current model activities"""
        return [
            {
                'model_id': model_id,
                'activity': act.action,
                'start_time': act.start_time,
                'last_update': act.last_update,
                'status': act.status,
                'progress': act.progress,
                'current_step': act.current_step,
                'logs': act.logs
            }
            for model_id, act in self._activities.items()
        ]
    
    def get_full_status(self) -> Dict[str, Any]:
        """Get complete jailbreak status"""
        return {
            'progress': self.get_progress(),
            'steps': self.get_all_steps(),
            'activities': self.get_activities(),
            'next_step': self.get_next_step()
        }
    
    def _calculate_elapsed(self, step: JailbreakStep) -> Optional[str]:
        """Calculate elapsed time for a step"""
        if not step.start_time:
            return None
        
        if step.end_time:
            start = datetime.fromisoformat(step.start_time)
            end = datetime.fromisoformat(step.end_time)
            elapsed = (end - start).total_seconds()
        else:
            start = datetime.fromisoformat(step.start_time)
            elapsed = (datetime.now() - start).total_seconds()
        
        if elapsed < 60:
            return f"{elapsed:.0f}s"
        elif elapsed < 3600:
            return f"{(elapsed/60):.1f}m"
        else:
            return f"{(elapsed/3600):.1f}h"
    
    def _calculate_elapsed_total(self) -> str:
        """Calculate total elapsed time"""
        start = datetime.fromisoformat(self._start_time)
        elapsed = (datetime.now() - start).total_seconds()
        
        if elapsed < 60:
            return f"{elapsed:.0f}s"
        elif elapsed < 3600:
            return f"{(elapsed/60):.1f}m"
        else:
            return f"{(elapsed/3600):.1f}h"
    
    def _save_step(self, step: JailbreakStep):
        """Save step to database"""
        try:
            from utils.db._connection import get_connection
            conn = get_connection()
            cursor = conn.cursor()
            
            # Create table if not exists
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS apex_jailbreak_coordinator (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    step_number INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    file_path TEXT,
                    required BOOLEAN DEFAULT 1,
                    dependencies TEXT,
                    status TEXT NOT NULL,
                    start_time TEXT,
                    end_time TEXT,
                    timeout_seconds INTEGER DEFAULT 300,
                    result TEXT,
                    error TEXT,
                    model TEXT DEFAULT 'apex',
                    progress REAL DEFAULT 0.0,
                    logs TEXT,
                    UNIQUE(step_number)
                )
            ''')
            
            # Save or update
            cursor.execute('''
                INSERT OR REPLACE INTO apex_jailbreak_coordinator 
                (id, step_number, title, description, file_path, required, 
                 dependencies, status, start_time, end_time, timeout_seconds, 
                 result, error, model, progress, logs)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                step.id,
                step.step_number,
                step.title,
                step.description,
                str(step.file_path) if isinstance(step.file_path, list) else step.file_path,
                step.required,
                json.dumps(step.dependencies),
                step.status,
                step.start_time,
                step.end_time,
                step.timeout_seconds,
                step.result,
                step.error,
                step.model,
                step.progress,
                json.dumps(step.logs)
            ))
            
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Warning: Failed to save step: {e}")
    
    def _save_activity(self, activity: ModelActivity):
        """Save activity to database"""
        try:
            from utils.db._connection import get_connection
            conn = get_connection()
            cursor = conn.cursor()
            
            # Create table if not exists
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS apex_model_activities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    model_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    start_time TEXT NOT NULL,
                    last_update TEXT NOT NULL,
                    status TEXT NOT NULL,
                    progress REAL DEFAULT 0.0,
                    current_step INTEGER,
                    logs TEXT,
                    UNIQUE(model_id)
                )
            ''')
            
            # Save or update
            cursor.execute('''
                INSERT OR REPLACE INTO apex_model_activities 
                (id, model_id, action, start_time, last_update, status, 
                 progress, current_step, logs)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                1,  # Use 1 for now
                activity.model_id,
                activity.action,
                activity.start_time,
                activity.last_update,
                activity.status,
                activity.progress,
                activity.current_step,
                json.dumps(activity.logs)
            ))
            
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Warning: Failed to save activity: {e}")
    
    def _log_to_chat(self, message: str):
        """Log a message to HB main chat"""
        try:
            from utils.db._connection import get_connection
            conn = get_connection()
            cursor = conn.cursor()
            
            # Post to messages table
            cursor.execute('''
                INSERT INTO messages (conversation_id, from_agent, to_agent, content, message_type, created_at)
                VALUES (?, ?, ?, ?, ?, datetime("now"))
            ''', (self._conversation_id, 'jailbreak-coordinator', 'apex', message, 'system'))
            
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Warning: Failed to log to chat: {e}")


# Global coordinator instance
_coordinator = None


def get_coordinator() -> JailbreakCoordinator:
    """Get or create the global coordinator"""
    global _coordinator
    if _coordinator is None:
        _coordinator = JailbreakCoordinator()
    return _coordinator


# Convenience functions
def start_jailbreak() -> Dict[str, Any]:
    return get_coordinator().start_jailbreak()

def start_step(step_number: int, model: str = "apex") -> Dict[str, Any]:
    return get_coordinator().start_step(step_number, model)

def update_step_progress(step_number: int, progress: float, log_message: str = None) -> Dict[str, Any]:
    return get_coordinator().update_step_progress(step_number, progress, log_message)

def complete_step(step_number: int, result: str = None) -> Dict[str, Any]:
    return get_coordinator().complete_step(step_number, result)

def fail_step(step_number: int, error: str = None) -> Dict[str, Any]:
    return get_coordinator().fail_step(step_number, error)

def get_progress() -> Dict[str, Any]:
    return get_coordinator().get_progress()

def get_all_steps() -> List[Dict[str, Any]]:
    return get_coordinator().get_all_steps()

def get_next_step() -> Optional[Dict[str, Any]]:
    return get_coordinator().get_next_step()

def get_full_status() -> Dict[str, Any]:
    return get_coordinator().get_full_status()

def check_all_timeouts() -> List[Dict[str, Any]]:
    return get_coordinator().check_all_timeouts()

def update_activity(model_id: str, action: str, step_number: Optional[int] = None, 
                     progress: float = 0.0, log_message: str = None) -> Dict[str, Any]:
    return get_coordinator().update_activity(model_id, action, step_number, progress, log_message)

def get_activities() -> List[Dict[str, Any]]:
    return get_coordinator().get_activities()


print("✅ Jailbreak Coordinator loaded - Full monitoring with time limits enabled!")
print("APEX can now: start_jailbreak(), start_step(), update_progress(), complete_step(), check_timeouts()")
print("All activities will be logged to HB main chat in real-time!")
