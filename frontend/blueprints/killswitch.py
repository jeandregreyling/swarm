"""killswitch.py — Kill Switches routes"""
from flask import Blueprint, request, Response, jsonify, send_file
from services import *

killswitch_bp = Blueprint('killswitch', __name__)

@killswitch_bp.route('/api/killswitch/buttons', methods=['GET'])
def api_killswitch_buttons():
    """Get desktop kill switch button configuration."""
    return jsonify(kill_switch.create_desktop_buttons())



@killswitch_bp.route('/api/killswitch/emergency', methods=['POST'])
def api_killswitch_emergency():
    """EMERGENCY SHUTDOWN — immediate stop all agents."""
    reason = request.json.get('reason', 'Manual emergency shutdown') if request.json else 'Manual emergency shutdown'
    
    kill_switch.record_kill_event('emergency_shutdown', agent='system', reason=reason)
    success = kill_switch.emergency_shutdown(reason=reason)
    
    return jsonify({
        'action': 'emergency_shutdown',
        'success': success,
        'timestamp': datetime.now(timezone.utc).isoformat() + 'Z'
    })



@killswitch_bp.route('/api/killswitch/pause', methods=['POST'])
def api_killswitch_pause():
    """Pause all active agents."""
    reason = request.json.get('reason', 'Manual pause') if request.json else 'Manual pause'
    
    kill_switch.record_kill_event('pause_all', agent='system', reason=reason)
    success = kill_switch.pause_all_agents(reason=reason)
    
    return jsonify({
        'action': 'pause_all',
        'success': success,
        'timestamp': datetime.now(timezone.utc).isoformat() + 'Z'
    })



@killswitch_bp.route('/api/killswitch/resume', methods=['POST'])
def api_killswitch_resume():
    """Resume paused agents."""
    kill_switch.record_kill_event('resume_all', agent='system')
    success = kill_switch.resume_agents()
    
    return jsonify({
        'action': 'resume_all',
        'success': success,
        'timestamp': datetime.now(timezone.utc).isoformat() + 'Z'
    })



@killswitch_bp.route('/api/killswitch/restart', methods=['POST'])
def api_killswitch_restart():
    """Restart swarm server."""
    kill_switch.record_kill_event('restart_server', agent='system')
    kill_switch.broadcast_alert('🔄 RESTART SERVER initiated')
    
    # Spawn restart in background
    def _restart():
        import time
        time.sleep(1)
        os.execv(sys.executable, [sys.executable] + sys.argv)
    
    threading.Thread(target=_restart, daemon=True).start()
    
    return jsonify({
        'action': 'restart',
        'success': True,
        'timestamp': datetime.now(timezone.utc).isoformat() + 'Z',
        'note': 'Server restarting in 1 second...'
    })



@killswitch_bp.route('/api/killswitch/agent/<agent_name>/reset', methods=['POST'])
def api_killswitch_agent_reset(agent_name):
    """Reset specific agent."""
    kill_switch.record_kill_event('agent_reset', agent=agent_name)
    success = kill_switch.reset_agent(agent_name)
    
    return jsonify({
        'action': 'agent_reset',
        'agent': agent_name,
        'success': success,
        'timestamp': datetime.now(timezone.utc).isoformat() + 'Z'
    })



