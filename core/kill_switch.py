"""
KILL SWITCHES — Emergency control agents via Telegram/Discord
Allows Ghost to trigger immediate actions:
- Emergency shutdown (all agents)
- Agent reset/restart
- Session termination
- State rollback
"""

import requests
import json
from datetime import datetime, UTC
from pathlib import Path
import subprocess
import signal
import os

from utils.config import TELEGRAM_TOKEN, TELEGRAM_BOT_NAME, GHOST_TELEGRAM_CHAT_ID
from utils.config import DISCORD_TOKEN, DISCORD_BOT_NAME, DISCORD_CHANNEL_ID

class KillSwitch:
    """Emergency control interface for the swarm."""
    
    def notify_telegram(self, message: str, action: str = None) -> bool:
        """Send alert to Ghost via Telegram."""
        try:
            payload = {
                'chat_id': GHOST_TELEGRAM_CHAT_ID,
                'text': message,
                'parse_mode': 'HTML'
            }
            r = requests.post(
                f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage',
                json=payload, timeout=10
            )
            return r.status_code == 200
        except Exception as e:
            print(f"[KillSwitch] Telegram notify failed: {e}")
            return False
    
    def notify_discord(self, message: str, action: str = None) -> bool:
        """Send alert to Ghost via Discord."""
        try:
            payload = {
                'content': message[:2000]  # Discord 2000 char limit
            }
            r = requests.post(
                f'https://discordapp.com/api/channels/{DISCORD_CHANNEL_ID}/messages',
                json=payload,
                headers={'Authorization': f'Bot {DISCORD_TOKEN}'},
                timeout=10
            )
            return r.status_code == 201
        except Exception as e:
            print(f"[KillSwitch] Discord notify failed: {e}")
            return False
    
    def broadcast_alert(self, message: str, severity: str = 'INFO') -> bool:
        """Send alert via Telegram + Discord."""
        formatted = f"🚨 [{severity}] {message}" if severity != 'INFO' else f"ℹ️ {message}"
        
        telegram_ok = self.notify_telegram(formatted)
        discord_ok = self.notify_discord(formatted)
        
        return telegram_ok or discord_ok
    
    def emergency_shutdown(self, reason: str = "Unknown") -> bool:
        """Gracefully shutdown all agents and services."""
        alert = f"🛑 EMERGENCY SHUTDOWN TRIGGERED\nReason: {reason}\nTime: {datetime.now().isoformat()}"
        self.broadcast_alert(alert, severity='CRITICAL')
        
        try:
            # Kill all terminal.py instances
            subprocess.run(['pkill', '-f', 'frontend/terminal.py'], check=False)
            # Kill all Ollama agents
            subprocess.run(['pkill', '-f', 'ollama'], check=False)
            print("[KillSwitch] Emergency shutdown complete")
            return True
        except Exception as e:
            print(f"[KillSwitch] Shutdown error: {e}")
            return False
    
    def reset_agent(self, agent_name: str) -> bool:
        """Reset an agent's session without full shutdown."""
        alert = f"⚙️ AGENT RESET: {agent_name}\nTime: {datetime.now().isoformat()}"
        self.broadcast_alert(alert)
        
        try:
            # Import database to clear agent session
            from utils.database import get_connection
            conn = get_connection()
            
            # Clear any active requests for this agent
            conn.execute("UPDATE queue SET status = 'cancelled' WHERE agent = ? AND status = 'processing'", 
                        (agent_name,))
            conn.commit()
            conn.close()
            
            print(f"[KillSwitch] Agent {agent_name} reset")
            return True
        except Exception as e:
            print(f"[KillSwitch] Reset failed: {e}")
            return False
    
    def pause_all_agents(self, reason: str = "Maintenance") -> bool:
        """Pause all agents (does not shutdown, allows resume)."""
        alert = f"⏸️ PAUSE ALL AGENTS\nReason: {reason}\nTime: {datetime.now().isoformat()}"
        self.broadcast_alert(alert)
        
        try:
            from utils.database import get_connection
            conn = get_connection()
            
            # Mark all processing tasks as paused
            conn.execute("""
                UPDATE queue
                SET status = 'paused'
                WHERE status = 'processing'
            """)
            
            conn.commit()
            conn.close()
            
            print("[KillSwitch] All agents paused")
            return True
        except Exception as e:
            print(f"[KillSwitch] Pause failed: {e}")
            return False
    
    def resume_agents(self) -> bool:
        """Resume paused agents."""
        alert = f"▶️ RESUME ALL AGENTS\nTime: {datetime.now().isoformat()}"
        self.broadcast_alert(alert)
        
        try:
            from utils.database import get_connection
            conn = get_connection()
            
            # Resume paused tasks
            conn.execute("""
                UPDATE queue
                SET status = 'queued'
                WHERE status = 'paused'
            """)
            
            conn.commit()
            conn.close()
            
            print("[KillSwitch] All agents resumed")
            return True
        except Exception as e:
            print(f"[KillSwitch] Resume failed: {e}")
            return False
    
    def record_kill_event(self, action: str, agent: str = 'system', reason: str = '') -> bool:
        """Log kill switch event in time machine."""
        try:
            from core.time_machine import time_wizard
            time_wizard.record_event(
                agent=agent,
                action=action,
                event_type='kill_switch',
                details={'reason': reason, 'timestamp': datetime.now(UTC).isoformat()}
            )
            return True
        except Exception as e:
            print(f"[KillSwitch] Event logging failed: {e}")
            return False
    
    def create_desktop_buttons(self) -> dict:
        """
        Generate JSON config for desktop kill switch buttons.
        These can be rendered in a taskbar, panel, or widget.
        """
        return {
            'buttons': [
                {
                    'id': 'emergency_shutdown',
                    'label': '🛑 SHUTDOWN',
                    'tooltip': 'Emergency shutdown all agents',
                    'color': '#ff3333',
                    'action': '/api/killswitch/emergency',
                    'confirm': True,
                    'confirm_message': 'CONFIRM EMERGENCY SHUTDOWN?'
                },
                {
                    'id': 'pause_agents',
                    'label': '⏸️ PAUSE',
                    'tooltip': 'Pause all active agents',
                    'color': '#ffaa00',
                    'action': '/api/killswitch/pause',
                    'confirm': False
                },
                {
                    'id': 'resume_agents',
                    'label': '▶️ RESUME',
                    'tooltip': 'Resume paused agents',
                    'color': '#00aa00',
                    'action': '/api/killswitch/resume',
                    'confirm': False
                },
                {
                    'id': 'restart_server',
                    'label': '🔄 RESTART',
                    'tooltip': 'Restart swarm server',
                    'color': '#0066ff',
                    'action': '/api/killswitch/restart',
                    'confirm': True,
                    'confirm_message': 'Restart swarm server?'
                }
            ]
        }


# Global instance
kill_switch = KillSwitch()
