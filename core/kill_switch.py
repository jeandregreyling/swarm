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
        """Hard global shutdown of all agents and services."""
        alert = f"🛑 EMERGENCY SHUTDOWN TRIGGERED\nReason: {reason}\nTime: {datetime.now().isoformat()}"
        self.broadcast_alert(alert, severity='CRITICAL')
        self.record_kill_event('emergency_shutdown', 'system', reason)
        
        try:
            subprocess.run(['pkill', '-f', 'frontend/terminal.py'], check=False)
            subprocess.run(['pkill', '-f', 'fridays/'], check=False)
            subprocess.run(['pkill', '-f', 'ollama'], check=False)
            subprocess.run(['pkill', '-f', 'python.*agent'], check=False)
            print("[KillSwitch] HARD global emergency shutdown complete")
            return True
        except Exception as e:
            print(f"[KillSwitch] Shutdown error: {e}")
            return False

    def kill_agent(self, agent_name: str, thread_id: str = None, reason: str = "User requested hard stop") -> bool:
        """Hard stop for a specific agent and optional chat thread."""
        alert = f"🔴 HARD KILL AGENT: {agent_name}\nThread: {thread_id or 'all'}\nReason: {reason}\nTime: {datetime.now().isoformat()}"
        self.broadcast_alert(alert, severity='CRITICAL')
        self.record_kill_event('kill_agent', agent_name, reason)

        try:
            from utils.db._connection import get_connection
            conn = get_connection()
            try:
                if thread_id:
                    conn.execute(
                        """
                        UPDATE queue
                           SET status='cancelled', error=?
                         WHERE status IN ('processing', 'queued')
                           AND (agent=? OR CAST(thread_id AS TEXT)=?)
                        """,
                        (reason, agent_name, str(thread_id)),
                    )
                    conn.execute(
                        """
                        UPDATE chat_jobs
                           SET status='cancelled', stage='cancelled by kill switch',
                               error=?, updated_at=datetime('now')
                         WHERE agent=? AND CAST(conversation_id AS TEXT)=?
                           AND status IN ('running', 'dispatched', 'processing')
                        """,
                        (reason, agent_name, str(thread_id)),
                    )
                else:
                    conn.execute(
                        """
                        UPDATE queue
                           SET status='cancelled', error=?
                         WHERE agent=? AND status IN ('processing', 'queued')
                        """,
                        (reason, agent_name),
                    )
                    conn.execute(
                        """
                        UPDATE chat_jobs
                           SET status='cancelled', stage='cancelled by kill switch',
                               error=?, updated_at=datetime('now')
                         WHERE agent=? AND status IN ('running', 'dispatched', 'processing')
                        """,
                        (reason, agent_name),
                    )
                conn.commit()
            finally:
                conn.close()

            subprocess.run(['pkill', '-f', str(agent_name)], check=False)
            print(f"[KillSwitch] Hard killed agent {agent_name} (thread {thread_id or 'all'})")
            return True
        except Exception as e:
            print(f"[KillSwitch] kill_agent failed: {e}")
            return False
    
    def reset_agent(self, agent_name: str) -> bool:
        """Reset an agent's session without full shutdown."""
        alert = f"⚙️ AGENT RESET: {agent_name}\nTime: {datetime.now().isoformat()}"
        self.broadcast_alert(alert)
        self.record_kill_event('reset_agent', agent_name)
        
        try:
            # Import database to clear agent session
            from utils.db._connection import get_connection
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
        self.record_kill_event('pause_all', 'system', reason)
        
        try:
            from utils.db._connection import get_connection
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
        self.record_kill_event('resume_all', 'system')
        
        try:
            from utils.db._connection import get_connection
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
        These can be rendered in the agents tile, chat, taskbar, or widget.
        """
        return {
            'buttons': [
                {
                    'id': 'emergency_shutdown',
                    'label': '🛑 HARD SHUTDOWN ALL',
                    'tooltip': 'Emergency hard stop all agents and services',
                    'color': '#ff3333',
                    'action': '/api/killswitch/emergency',
                    'confirm': True,
                    'confirm_message': 'CONFIRM HARD GLOBAL SHUTDOWN? This stops everything.'
                },
                {
                    'id': 'kill_selected_agent',
                    'label': '🔴 KILL SELECTED AGENT',
                    'tooltip': 'Hard stop a specific agent',
                    'color': '#cc0000',
                    'action': '/api/killswitch/kill_agent',
                    'confirm': True,
                    'confirm_message': 'Kill this agent and cancel its tasks?'
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
