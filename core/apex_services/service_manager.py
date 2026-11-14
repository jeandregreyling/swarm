"""
Service Manager for APEX

Provides capabilities for APEX to manage Hummingbird (HB) services:
- List running services
- Get service status
- Start/Stop/Restart services
- Get service logs
- Trace service execution
"""

import os
import sys
import json
import subprocess
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, field
import signal
import psutil

# Add project root to path
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

_LOG = logging.getLogger('apex.service_manager')


@dataclass
class ServiceInfo:
    """Information about a running service"""
    name: str
    pid: Optional[int] = None
    port: Optional[int] = None
    script: Optional[str] = None
    status: str = "unknown"
    started_at: Optional[str] = None
    uptime: Optional[str] = None
    cpu_percent: float = 0.0
    memory_mb: float = 0.0
    command: Optional[str] = None


@dataclass
class ServiceLog:
    """Service log entry"""
    timestamp: str
    level: str
    message: str
    service: str


@dataclass
class ServiceTrace:
    """Service execution trace"""
    timestamp: str
    service: str
    action: str
    details: Dict[str, Any] = field(default_factory=dict)


class ServiceManager:
    """
    Manages Hummingbird services for APEX.
    
    Provides service discovery, control, and monitoring capabilities.
    """
    
    # Known Hummingbird services
    KNOWN_SERVICES = {
        'terminal': {
            'script': 'frontend/terminal.py',
            'port': 5050,
            'description': 'Main chat backend (Fridays)',
            'auto_start': True,
        },
        'seven_runtime': {
            'script': 'scripts/seven_runtime_service.py',
            'port': 17777,
            'description': 'Seven runtime service',
            'auto_start': True,
        },
        'hummingbird_desktop': {
            'script': 'scripts/hummingbird_desktop.py',
            'port': None,
            'description': 'Hummingbird desktop UI',
            'auto_start': True,
        },
    }
    
    def __init__(self):
        self._cache = {}
        self._log_cache = {}
    
    def discover_services(self) -> List[ServiceInfo]:
        """Discover all running Hummingbird services"""
        services = []
        
        # Check for known services by process name
        for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
            try:
                cmdline = ' '.join(proc.info['cmdline'] or [])
                for service_name, config in self.KNOWN_SERVICES.items():
                    if config['script'] in cmdline:
                        create_time = proc.info['create_time']
                        started_at = datetime.fromtimestamp(create_time).isoformat()
                        uptime = self._calculate_uptime(create_time)
                        
                        # Get resource usage
                        cpu_percent = proc.cpu_percent(interval=0.1)
                        memory_info = proc.memory_info()
                        memory_mb = memory_info.rss / (1024 * 1024)
                        
                        services.append(ServiceInfo(
                            name=service_name,
                            pid=proc.info['pid'],
                            port=config['port'],
                            script=config['script'],
                            status='running',
                            started_at=started_at,
                            uptime=uptime,
                            cpu_percent=cpu_percent,
                            memory_mb=memory_mb,
                            command=cmdline[:200]
                        ))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        # Check for services that should be running but aren't
        for service_name, config in self.KNOWN_SERVICES.items():
            if service_name not in [s.name for s in services]:
                services.append(ServiceInfo(
                    name=service_name,
                    pid=None,
                    port=config['port'],
                    script=config['script'],
                    status='stopped',
                    command=config['description']
                ))
        
        return services
    
    def get_service(self, name: str) -> Optional[ServiceInfo]:
        """Get information about a specific service"""
        for service in self.discover_services():
            if service.name == name:
                return service
        return None
    
    def list_services(self) -> List[Dict[str, Any]]:
        """List all Hummingbird services with status"""
        services = self.discover_services()
        return [
            {
                'name': s.name,
                'status': s.status,
                'pid': s.pid,
                'port': s.port,
                'description': self.KNOWN_SERVICES.get(s.name, {}).get('description', ''),
                'started_at': s.started_at,
                'uptime': s.uptime,
                'cpu_percent': f"{s.cpu_percent:.1f}%",
                'memory_mb': f"{s.memory_mb:.1f} MB",
                'command': s.command,
            }
            for s in services
        ]
    
    def get_service_status(self, name: str) -> Dict[str, Any]:
        """Get detailed status of a specific service"""
        service = self.get_service(name)
        if not service:
            return {'name': name, 'status': 'not_found', 'error': 'Service not found'}
        
        return {
            'name': service.name,
            'status': service.status,
            'pid': service.pid,
            'port': service.port,
            'started_at': service.started_at,
            'uptime': service.uptime,
            'cpu_percent': service.cpu_percent,
            'memory_mb': service.memory_mb,
            'command': service.command,
        }
    
    def start_service(self, name: str, **kwargs) -> Dict[str, Any]:
        """Start a Hummingbird service"""
        if name not in self.KNOWN_SERVICES:
            return {'ok': False, 'error': f'Unknown service: {name}'}
        
        config = self.KNOWN_SERVICES[name]
        script_path = os.path.join(ROOT, config['script'])
        
        if not os.path.exists(script_path):
            return {'ok': False, 'error': f'Script not found: {script_path}'}
        
        # Check if already running
        service = self.get_service(name)
        if service and service.status == 'running':
            return {'ok': False, 'error': f'Service {name} is already running (PID: {service.pid})'}
        
        # Start the service
        try:
            venv_python = os.path.join(ROOT, '.venv', 'bin', 'python3')
            if not os.path.exists(venv_python):
                venv_python = 'python3'
            
            cmd = [venv_python, script_path]
            
            # Add any additional arguments
            if config.get('port'):
                cmd.extend(['--host', '127.0.0.1', '--port', str(config['port'])])
            
            # Add kwargs as arguments
            for key, value in kwargs.items():
                if value is not None:
                    cmd.extend([f'--{key}', str(value)])
            
            # Start in background
            proc = subprocess.Popen(
                cmd,
                cwd=ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={**os.environ, 'PYTHONPATH': ROOT}
            )
            
            _LOG.info(f'Started service {name} with PID {proc.pid}')
            
            # Trace the action
            self._trace(name, 'start', {'pid': proc.pid, 'command': ' '.join(cmd)})
            
            return {
                'ok': True,
                'service': name,
                'pid': proc.pid,
                'message': f'Service {name} started successfully',
                'command': ' '.join(cmd)
            }
        except Exception as e:
            _LOG.error(f'Failed to start service {name}: {e}')
            return {'ok': False, 'error': str(e), 'service': name}
    
    def stop_service(self, name: str, force: bool = False) -> Dict[str, Any]:
        """Stop a Hummingbird service"""
        service = self.get_service(name)
        if not service or not service.pid:
            return {'ok': False, 'error': f'Service {name} is not running'}
        
        try:
            # Try graceful shutdown first
            if not force:
                proc = psutil.Process(service.pid)
                proc.terminate()
                proc.wait(timeout=5)
            else:
                # Force kill
                os.kill(service.pid, signal.SIGKILL)
            
            _LOG.info(f'Stopped service {name} (PID: {service.pid})')
            
            # Trace the action
            self._trace(name, 'stop', {'pid': service.pid, 'force': force})
            
            return {
                'ok': True,
                'service': name,
                'pid': service.pid,
                'message': f'Service {name} stopped successfully'
            }
        except Exception as e:
            _LOG.error(f'Failed to stop service {name}: {e}')
            return {'ok': False, 'error': str(e), 'service': name, 'pid': service.pid}
    
    def restart_service(self, name: str, **kwargs) -> Dict[str, Any]:
        """Restart a Hummingbird service"""
        # Stop first
        stop_result = self.stop_service(name, force=True)
        if not stop_result.get('ok'):
            return stop_result
        
        # Wait a moment
        import time
        time.sleep(2)
        
        # Start again
        return self.start_service(name, **kwargs)
    
    def get_service_logs(self, name: str, lines: int = 100) -> List[Dict[str, Any]]:
        """Get logs for a specific service"""
        logs = []
        
        # For now, return system logs related to the service
        # In production, this would read actual log files
        try:
            import subprocess
            result = subprocess.run(
                ['journalctl', '-u', f'hummingbird-{name}', '-n', str(lines), '--no-pager'],
                capture_output=True,
                text=True
            )
            if result.stdout:
                for line in result.stdout.split('\n')[:lines]:
                    if line.strip():
                        logs.append({
                            'timestamp': datetime.now().isoformat(),
                            'level': 'INFO',
                            'message': line,
                            'service': name
                        })
        except Exception:
            pass
        
        # Add any cached logs
        if name in self._log_cache:
            logs.extend(self._log_cache[name][-lines:])
        
        return logs[-lines:]
    
    def trace_service(self, name: str, action: str, details: Dict[str, Any] = None) -> ServiceTrace:
        """Add a trace entry for a service action"""
        trace = ServiceTrace(
            timestamp=datetime.now().isoformat(),
            service=name,
            action=action,
            details=details or {}
        )
        
        # Store in cache
        if name not in self._log_cache:
            self._log_cache[name] = []
        self._log_cache[name].append(trace._asdict())
        
        # Log to database
        self._log_trace_to_db(trace)
        
        return trace
    
    def _trace(self, name: str, action: str, details: Dict[str, Any] = None):
        """Internal method to trace service actions"""
        self.trace_service(name, action, details)
    
    def _log_trace_to_db(self, trace: ServiceTrace):
        """Log trace to database"""
        try:
            from utils.db._connection import get_connection
            conn = get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO service_trace (service, action, details, created_at)
                VALUES (?, ?, ?, datetime('now'))
            ''', (trace.service, trace.action, json.dumps(trace.details)))
            
            conn.commit()
            conn.close()
        except Exception as e:
            _LOG.warning(f'Failed to log trace to DB: {e}')
    
    def monitor_services(self) -> Dict[str, Any]:
        """Get monitoring overview of all services"""
        services = self.discover_services()
        
        return {
            'timestamp': datetime.now().isoformat(),
            'services': [
                {
                    'name': s.name,
                    'status': s.status,
                    'pid': s.pid,
                    'port': s.port,
                    'uptime': s.uptime,
                    'cpu': f"{s.cpu_percent:.1f}%",
                    'memory': f"{s.memory_mb:.1f} MB",
                }
                for s in services
            ],
            'summary': {
                'total': len(services),
                'running': sum(1 for s in services if s.status == 'running'),
                'stopped': sum(1 for s in services if s.status == 'stopped'),
            }
        }
    
    def _calculate_uptime(self, create_time: float) -> str:
        """Calculate uptime from process creation time"""
        if not create_time:
            return "N/A"
        
        uptime_seconds = datetime.now().timestamp() - create_time
        
        if uptime_seconds < 60:
            return f"{uptime_seconds:.0f}s"
        elif uptime_seconds < 3600:
            minutes = uptime_seconds / 60
            return f"{minutes:.0f}m"
        else:
            hours = uptime_seconds / 3600
            return f"{hours:.1f}h"


# Global service manager instance
_service_manager = None


def get_service_manager() -> ServiceManager:
    """Get or create the global service manager"""
    global _service_manager
    if _service_manager is None:
        _service_manager = ServiceManager()
    return _service_manager


# Convenience functions
def list_services() -> List[Dict[str, Any]]:
    """List all Hummingbird services"""
    return get_service_manager().list_services()


def get_service_status(name: str) -> Dict[str, Any]:
    """Get status of a specific service"""
    return get_service_manager().get_service_status(name)


def start_service(name: str, **kwargs) -> Dict[str, Any]:
    """Start a service"""
    return get_service_manager().start_service(name, **kwargs)


def stop_service(name: str, force: bool = False) -> Dict[str, Any]:
    """Stop a service"""
    return get_service_manager().stop_service(name, force)


def restart_service(name: str, **kwargs) -> Dict[str, Any]:
    """Restart a service"""
    return get_service_manager().restart_service(name, **kwargs)


def get_service_logs(name: str, lines: int = 100) -> List[Dict[str, Any]]:
    """Get service logs"""
    return get_service_manager().get_service_logs(name, lines)


def trace_service(name: str, action: str, details: Dict[str, Any] = None) -> ServiceTrace:
    """Trace a service action"""
    return get_service_manager().trace_service(name, action, details)


def monitor_services() -> Dict[str, Any]:
    """Get monitoring overview"""
    return get_service_manager().monitor_services()
