#!/usr/bin/env python3
"""ops/hive_agent.py — portable Hive node agent.

Runs on any owner-confirmed device (Linux, macOS, Windows). Samples
local telemetry against the Node Resource Contract v0 and posts it to
the Hive leader at $SWARM_HIVE_LEADER (default http://localhost:5050).

Two modes:

    hive_agent.py --enrol [--leader URL] [--node-id ID]
        Register this device with the leader, receive a token, persist
        it to the local config dir, then exit.

    hive_agent.py --run [--interval 30] [--once]
        Sample telemetry and POST it to /api/hive/telemetry. Loops
        forever unless --once is given.

Standard library only. No third-party deps. Importable as a module.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import platform
import signal
import socket
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

# Make the parent repo importable when run from a checkout.
_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from core.hive import build_local_telemetry  # noqa: E402
from core.hive.local_node import get_local_node  # noqa: E402

_LOG = logging.getLogger('hive_agent')

DEFAULT_LEADER = 'http://localhost:5050'
DEFAULT_INTERVAL = 30
USER_AGENT = 'swarm-hive-agent/0.1'


# ---- config dir ------------------------------------------------------------

def _config_dir() -> Path:
    """Return per-user config dir for the agent."""
    override = os.environ.get('SWARM_HIVE_AGENT_DIR', '').strip()
    if override:
        path = Path(override).expanduser()
    elif platform.system() == 'Windows':
        base = os.environ.get('APPDATA') or str(Path.home() / 'AppData' / 'Roaming')
        path = Path(base) / 'swarm-hive'
    elif platform.system() == 'Darwin':
        path = Path.home() / 'Library' / 'Application Support' / 'swarm-hive'
    else:
        base = os.environ.get('XDG_CONFIG_HOME') or str(Path.home() / '.config')
        path = Path(base) / 'swarm-hive'
    path.mkdir(parents=True, exist_ok=True)
    return path


def _config_path() -> Path:
    return _config_dir() / 'agent.json'


def load_config() -> dict[str, Any]:
    """Read the agent config (token + leader). Empty dict if missing."""
    p = _config_path()
    if not p.exists():
        return {}
    try:
        with p.open('r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError):
        _LOG.exception('failed to read %s', p)
    return {}


def save_config(cfg: dict[str, Any]) -> None:
    """Persist the agent config atomically, mode 0o600."""
    p = _config_path()
    tmp = p.with_suffix('.json.tmp')
    payload = json.dumps(cfg, indent=2, sort_keys=True)
    with tmp.open('w', encoding='utf-8') as f:
        f.write(payload)
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, p)


# ---- HTTP helpers ----------------------------------------------------------

class AgentError(RuntimeError):
    """Agent-level error (network, auth, contract)."""


def _http(method: str, url: str, *,
          payload: dict[str, Any] | None = None,
          token: str | None = None,
          timeout: float = 10.0) -> dict[str, Any]:
    """Issue an HTTP request and return the decoded JSON body."""
    body: bytes | None = None
    headers = {'User-Agent': USER_AGENT, 'Accept': 'application/json'}
    if payload is not None:
        body = json.dumps(payload).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    if token:
        headers['X-Hive-Token'] = token
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode('utf-8') or '{}'
    except urllib.error.HTTPError as exc:
        try:
            err_body = exc.read().decode('utf-8', errors='replace')
        except Exception:
            err_body = ''
        raise AgentError(f'HTTP {exc.code} {url}: {err_body[:200]}') from exc
    except urllib.error.URLError as exc:
        raise AgentError(f'network error {url}: {exc.reason}') from exc
    except (TimeoutError, socket.timeout) as exc:
        raise AgentError(f'timeout {url}') from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AgentError(f'non-JSON response from {url}: {raw[:120]}') from exc
    if not isinstance(data, dict):
        raise AgentError(f'expected JSON object from {url}, got {type(data).__name__}')
    return data


# ---- enrolment -------------------------------------------------------------

def enrol(leader: str, node_id: str | None = None,
          metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """Register the local node with the leader and persist the token."""
    leader = leader.rstrip('/')
    node = get_local_node()
    nid = node_id or node.node_id
    payload: dict[str, Any] = {'node_id': nid}
    if metadata:
        payload['metadata'] = metadata
    data = _http('POST', f'{leader}/api/hive/enrol', payload=payload)
    if not data.get('ok'):
        raise AgentError(f'enrol rejected: {data}')
    token = data.get('token')
    if not token:
        raise AgentError(f'enrol response missing token: {data}')
    cfg = load_config()
    cfg.update({
        'leader': leader,
        'node_id': nid,
        'token': token,
        'enrolled_at': time.time(),
    })
    save_config(cfg)
    return {'node_id': nid, 'leader': leader, 'token': token}


# ---- run loop --------------------------------------------------------------

class HiveAgent:
    """Sample local telemetry on a tick and POST to the leader."""

    def __init__(self, leader: str | None = None,
                 token: str | None = None,
                 node_id: str | None = None,
                 interval: float = DEFAULT_INTERVAL,
                 transport=None) -> None:
        cfg = load_config()
        self.leader = (leader
                       or os.environ.get('SWARM_HIVE_LEADER')
                       or cfg.get('leader')
                       or DEFAULT_LEADER).rstrip('/')
        self.token = (token
                      or os.environ.get('SWARM_HIVE_TOKEN')
                      or cfg.get('token'))
        self.node_id = (node_id
                        or os.environ.get('SWARM_NODE_ID')
                        or cfg.get('node_id'))
        self.interval = max(2.0, float(interval))
        self._stop = False
        self._transport = transport or _http  # injectable for tests

    def stop(self, *_args) -> None:
        self._stop = True

    def sample_payload(self) -> dict[str, Any]:
        """Build a contract-v0 telemetry envelope for this host."""
        return build_local_telemetry(node_id=self.node_id)

    def post_once(self) -> dict[str, Any]:
        """Sample once and POST to the leader. Returns the server reply."""
        payload = self.sample_payload()
        return self._transport(
            'POST',
            f'{self.leader}/api/hive/telemetry',
            payload=payload,
            token=self.token,
        )

    def run(self) -> None:
        """Loop forever (or until stop()) sampling + posting."""
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)
        _LOG.info('hive_agent starting node=%s leader=%s interval=%.0fs',
                  self.node_id, self.leader, self.interval)
        backoff = 1.0
        while not self._stop:
            t0 = time.time()
            try:
                reply = self.post_once()
                if reply.get('ok'):
                    _LOG.info('telemetry posted ok ts=%s', reply.get('ts'))
                    backoff = 1.0
                else:
                    _LOG.warning('leader rejected telemetry: %s', reply)
            except AgentError as exc:
                _LOG.warning('post failed: %s (backoff %.1fs)', exc, backoff)
                self._sleep(backoff)
                backoff = min(backoff * 2, 60.0)
                continue
            except Exception:
                _LOG.exception('unexpected error in agent loop')
                self._sleep(min(backoff * 2, 60.0))
                continue
            elapsed = time.time() - t0
            self._sleep(max(0.0, self.interval - elapsed))

    def _sleep(self, seconds: float) -> None:
        """Interruptible sleep so SIGTERM exits within ~1s."""
        end = time.time() + seconds
        while time.time() < end and not self._stop:
            time.sleep(min(1.0, end - time.time()))


# ---- CLI -------------------------------------------------------------------

def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog='hive_agent',
        description='Swarm Hive node agent — sample telemetry and report to the leader.',
    )
    p.add_argument('--leader', default=None,
                   help='Leader URL (default $SWARM_HIVE_LEADER or http://localhost:5050)')
    p.add_argument('--node-id', default=None, help='Override node id')
    p.add_argument('--interval', type=float, default=DEFAULT_INTERVAL,
                   help='Seconds between samples (default 30)')
    p.add_argument('--once', action='store_true', help='Sample once then exit')
    g = p.add_mutually_exclusive_group()
    g.add_argument('--enrol', action='store_true', help='Register and store a token, then exit')
    g.add_argument('--run', action='store_true', help='Run the sampling loop (default)')
    g.add_argument('--show', action='store_true', help='Print the local telemetry to stdout')
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_argparser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s %(message)s',
    )
    if args.show:
        print(json.dumps(build_local_telemetry(node_id=args.node_id), indent=2))
        return 0
    if args.enrol:
        leader = (args.leader or os.environ.get('SWARM_HIVE_LEADER') or DEFAULT_LEADER)
        try:
            result = enrol(leader, node_id=args.node_id)
        except AgentError as exc:
            _LOG.error('enrol failed: %s', exc)
            return 2
        print(json.dumps(result, indent=2))
        return 0
    agent = HiveAgent(
        leader=args.leader,
        node_id=args.node_id,
        interval=args.interval,
    )
    if args.once:
        try:
            reply = agent.post_once()
        except AgentError as exc:
            _LOG.error('post failed: %s', exc)
            return 2
        print(json.dumps(reply, indent=2))
        return 0
    try:
        agent.run()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == '__main__':
    sys.exit(main())
