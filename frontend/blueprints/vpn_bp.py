"""vpn_bp.py — Tailscale / VPN status API for Fridays terminal."""
import subprocess
import json
from flask import Blueprint, jsonify

vpn_bp = Blueprint('vpn', __name__)


def _tailscale_status():
    """Run `tailscale status --json` and return parsed dict."""
    try:
        proc = subprocess.run(
            ['tailscale', 'status', '--json'],
            capture_output=True, text=True, timeout=10,
        )
        if proc.returncode != 0:
            return {'error': (proc.stderr or 'tailscale status failed').strip()[:300]}
        return json.loads(proc.stdout)
    except FileNotFoundError:
        return {'error': 'tailscale binary not found'}
    except subprocess.TimeoutExpired:
        return {'error': 'tailscale status timed out'}
    except Exception as exc:
        return {'error': str(exc)[:300]}


@vpn_bp.route('/api/vpn/status', methods=['GET'])
def api_vpn_status():
    """Return Tailscale network status."""
    data = _tailscale_status()
    if 'error' in data:
        return jsonify({'ok': False, 'error': data['error']}), 503

    self_node = data.get('Self', {})
    peers = data.get('Peer', {})
    peer_list = []
    for key, peer in peers.items():
        peer_list.append({
            'hostname': peer.get('HostName', ''),
            'dns_name': peer.get('DNSName', ''),
            'ip': (peer.get('TailscaleIPs') or [''])[0],
            'os': peer.get('OS', ''),
            'online': peer.get('Online', False),
            'active': peer.get('Active', False),
            'relay': peer.get('Relay', ''),
            'rx_bytes': peer.get('RxBytes', 0),
            'tx_bytes': peer.get('TxBytes', 0),
        })

    return jsonify({
        'ok': True,
        'self': {
            'hostname': self_node.get('HostName', ''),
            'dns_name': self_node.get('DNSName', ''),
            'ip': (self_node.get('TailscaleIPs') or [''])[0],
            'os': self_node.get('OS', ''),
            'online': self_node.get('Online', False),
        },
        'peers': peer_list,
        'peer_count': len(peer_list),
        'online_count': sum(1 for p in peer_list if p['online']),
        'backend_state': data.get('BackendState', ''),
        'tailnet_name': data.get('MagicDNSSuffix', ''),
    })
