"""Service truth (Studio S-C0FDABC627, built 15 Nov 2026): the services list must agree with systemd and with live port ownership.

systemd says a unit is active; that does not prove its port is held by that unit (a stray process may hold it, or the unit may be
up without listening). verdict() compares the two and says so in plain words. Read-only: ss and /proc, nothing is changed."""
import re
import subprocess
import time

_CACHE = {'at': 0.0, 'owners': {}}
_SS_LINE = re.compile(r':(\d+)\s+\S+\s+users:\(\("([^"]+)",pid=(\d+)')


def parse_ss(text):
    """`ss -ltnpH` output -> {port: {'name': process name, 'pid': pid}} (first listener per port)."""
    owners = {}
    for line in str(text or '').splitlines():
        m = _SS_LINE.search(line)
        if m:
            owners.setdefault(int(m.group(1)), {'name': m.group(2), 'pid': int(m.group(3))})
    return owners


def listeners(max_age=2.0):
    """Live listening TCP ports of this machine (cached for a moment: the panel asks once per service)."""
    if time.time() - _CACHE['at'] > max_age:
        try:
            out = subprocess.run(['ss', '-ltnpH'], capture_output=True, text=True, timeout=4).stdout
        except Exception:
            out = ''
        _CACHE.update(at=time.time(), owners=parse_ss(out))
    return _CACHE['owners']


def unit_of(pid):
    """The systemd unit a process runs in (from its cgroup), or '' when unknown."""
    try:
        with open(f'/proc/{int(pid)}/cgroup') as handle:
            last = handle.read().strip().splitlines()[-1].rsplit('/', 1)[-1]
    except Exception:
        return ''
    return last if last.endswith(('.service', '.scope', '.timer')) else ''


def verdict(unit, active, port, owners=None, unit_of=unit_of):
    """{'truth': 'ok' | 'no port' | plain-words disagreement, 'port_owner': {...} | None} for one service."""
    if not port:
        return {'truth': 'no port', 'port_owner': None}
    owner = (listeners() if owners is None else owners).get(int(port))
    if not owner:
        return {'truth': f'systemd says active, but nothing listens on port {port}' if active else 'ok', 'port_owner': None}
    holder = unit_of(owner['pid'])
    owner = {**owner, 'unit': holder}
    if holder == unit:
        return {'truth': 'ok' if active else f'not active in systemd, but its own process {owner["pid"]} still holds port {port}', 'port_owner': owner}
    who = f'{owner["name"]} (pid {owner["pid"]}{", " + holder if holder else ""})'
    return {'truth': f'port {port} is held by {who}, not by this service', 'port_owner': owner}
