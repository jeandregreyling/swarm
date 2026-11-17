"""HB network manager (owner 14 Nov 2026): know every connection, measure them, and pick one by job size and data budget.

  inventory()        the connections found NOW (never a fixed name): up or down, IPv4 / IPv6, default route, kind
  benchmark(...)     a short timed download bound to one connection (curl --interface); saved with the hour of day
  budget / usage     JD's monthly mobile figure, bytes HB sent over connections marked mobile, warn at 80%, stop at JD's floor
  pick(...)          small jobs: the home line; big jobs: the fastest measured connection, mobile only when the budget allows
HB never changes the system's default route. A job is bound to a connection per command (curl --interface)."""
import json
import re
import subprocess
import time

BIG_JOB_BYTES = 1024 ** 3
BENCH_URL = 'https://speed.cloudflare.com/__down?bytes=20000000'
# Practice 132: ProtonVPN (proton0 and its IPv6 kill-switch link) and WireGuard/tun links are VPNs - never a download route
KINDS = (('tailscale', 'vpn'), ('proton', 'vpn'), ('ipv6leak', 'vpn'), ('wg', 'vpn'), ('tun', 'vpn'), ('enx', 'usb tether'), ('wl', 'wifi'), ('en', 'wired'), ('eth', 'wired'), ('usb', 'usb tether'), ('ww', 'mobile modem'))


def _run(cmd, timeout=20):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout


def ensure_schema(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS hb_network_links(name TEXT PRIMARY KEY, mobile INTEGER NOT NULL DEFAULT 0, label TEXT, set_by TEXT, updated_at REAL)')
    conn.execute('CREATE TABLE IF NOT EXISTS hb_network_bench(id INTEGER PRIMARY KEY, at REAL NOT NULL, hour INTEGER, name TEXT NOT NULL, mbytes_per_s REAL, bytes INTEGER, ok INTEGER)')
    conn.execute('CREATE TABLE IF NOT EXISTS hb_network_usage(id INTEGER PRIMARY KEY, at REAL NOT NULL, name TEXT NOT NULL, bytes INTEGER NOT NULL, what TEXT)')
    conn.execute('CREATE TABLE IF NOT EXISTS hb_network_choice(id INTEGER PRIMARY KEY CHECK (id=1), name TEXT, set_by TEXT, at REAL)')
    conn.execute('CREATE TABLE IF NOT EXISTS hb_network_budget(id INTEGER PRIMARY KEY CHECK (id=1), limit_gb REAL, floor_gb REAL, period_start REAL, set_by TEXT)')


def kind(name):
    return next((k for prefix, k in KINDS if name.startswith(prefix)), 'other')


def inventory(conn=None, run=_run):
    """[{name, kind, up, ipv4, ipv6, default, metric, mobile, label}] for every real connection, best default route first."""
    links = json.loads(run(['ip', '-j', 'addr']) or '[]')
    routes = {r['dev']: r.get('metric', 0) for r in json.loads(run(['ip', '-j', 'route', 'show', 'default']) or '[]') if r.get('dev')}
    marks = {}
    if conn is not None:
        ensure_schema(conn)
        marks = {n: (bool(m), l) for n, m, l in conn.execute('SELECT name, mobile, label FROM hb_network_links')}
    nets = networks(run)                 # Practice 132
    out = []
    for link in links:
        name = link.get('ifname', '')
        if name == 'lo' or name.startswith(('docker', 'veth', 'br-', 'virbr')):
            continue
        addrs = link.get('addr_info') or []
        k = kind(name)
        net = nets.get(name, '')
        out.append({'name': name, 'kind': k, 'up': link.get('operstate') in ('UP', 'UNKNOWN') and bool(addrs),
                    'ipv4': any(a.get('family') == 'inet' for a in addrs),
                    'ipv6': any(a.get('family') == 'inet6' and a.get('scope') == 'global' for a in addrs),
                    'default': name in routes, 'metric': routes.get(name),
                    'mobile': _mark(marks, name, net, (k in ('usb tether', 'mobile modem') or net in MOBILE_NETWORKS, None))[0],
                    'label': _mark(marks, name, net, (None, None))[1] or (f'{net} Wi-Fi' if k == 'wifi' and net else ''),
                    'network': net})
    return sorted(out, key=lambda c: (c['metric'] is None, c['metric'] or 0, c['name']))


def mark(conn, name, mobile, actor, label=None):
    ensure_schema(conn)
    conn.execute('INSERT INTO hb_network_links(name, mobile, label, set_by, updated_at) VALUES (?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET '
                 'mobile=excluded.mobile, label=COALESCE(excluded.label, label), set_by=excluded.set_by, updated_at=excluded.updated_at',
                 (name, int(bool(mobile)), label, str(actor)[:80], time.time()))
    return f"{name} is {'mobile data (counts against the bundle)' if mobile else 'not mobile data'}."


def record_usage(conn, name, nbytes, what=''):
    ensure_schema(conn)
    conn.execute('INSERT INTO hb_network_usage(at, name, bytes, what) VALUES (?,?,?,?)', (time.time(), name, int(nbytes), str(what)[:120]))


def benchmark(conn, name, run=_run, url=BENCH_URL, seconds=8, now=None):
    """Timed download over one connection. Returns MB/s (0.0 when it failed) and saves the result; its bytes count as usage."""
    now = time.time() if now is None else now
    try:
        speed, size = (run(['curl', '-s', '-o', '/dev/null', '--interface', name, '-m', str(seconds), '-w', '%{speed_download} %{size_download}', url],
                           timeout=seconds + 10) or '0 0').split()[:2]
        speed, size = float(speed), int(float(size))
    except Exception:
        speed, size = 0.0, 0
    ensure_schema(conn)
    mbs = round(speed / 1e6, 2)
    conn.execute('INSERT INTO hb_network_bench(at, hour, name, mbytes_per_s, bytes, ok) VALUES (?,?,?,?,?,?)',
                 (now, time.localtime(now).tm_hour, name, mbs, size, int(size > 0)))
    if size:
        record_usage(conn, name, size, 'benchmark')
    return mbs


def set_budget(conn, limit_gb, floor_gb, actor, now=None):
    ensure_schema(conn)
    conn.execute('INSERT INTO hb_network_budget(id, limit_gb, floor_gb, period_start, set_by) VALUES (1,?,?,?,?) ON CONFLICT(id) DO UPDATE SET '
                 'limit_gb=excluded.limit_gb, floor_gb=excluded.floor_gb, period_start=excluded.period_start, set_by=excluded.set_by',
                 (float(limit_gb), float(floor_gb), time.time() if now is None else now, str(actor)[:80]))
    return f'Mobile data: {float(limit_gb):g} GB left as of now; HB stops using mobile connections when {float(floor_gb):g} GB remain.'


def budget(conn, inv=None):
    """{'set', 'left_gb', 'floor_gb', 'used_gb', 'warn'}: what is left of JD's mobile figure after what HB itself sent over mobile links."""
    ensure_schema(conn)
    row = conn.execute('SELECT limit_gb, floor_gb, period_start FROM hb_network_budget WHERE id=1').fetchone()
    if not row:
        return {'set': False, 'left_gb': None, 'floor_gb': None, 'used_gb': 0.0, 'warn': False}
    mobile = [c['name'] for c in (inv if inv is not None else inventory(conn)) if c['mobile']]
    used = conn.execute(f"SELECT COALESCE(SUM(bytes),0) FROM hb_network_usage WHERE at>=? AND name IN ({','.join('?' * len(mobile)) or 'NULL'})",
                        (row[2], *mobile)).fetchone()[0] / 1024 ** 3
    left = row[0] - used
    return {'set': True, 'left_gb': round(left, 2), 'floor_gb': row[1], 'used_gb': round(used, 2), 'warn': used >= 0.8 * max(row[0] - row[1], 0.001)}


def _speed(conn, name):
    row = conn.execute('SELECT mbytes_per_s FROM hb_network_bench WHERE name=? AND ok=1 ORDER BY id DESC LIMIT 1', (name,)).fetchone()
    return row[0] if row else None


def pick(conn, job_bytes, inv=None):
    """{'name', 'why'} - the connection a job of this size should use. Never the VPN; mobile only for big jobs within the budget."""
    inv = [c for c in (inv if inv is not None else inventory(conn)) if c['up'] and c['kind'] != 'vpn' and c['ipv4']]
    home = [c for c in inv if not c['mobile']]
    b = budget(conn, inv)
    mobile_ok = bool(b['set']) and b['left_gb'] - job_bytes / 1024 ** 3 >= b['floor_gb']
    if not inv:
        return {'name': None, 'why': 'no connection is up'}
    chosen = choice(conn)                # Practice 132: JD's choice first, but mobile data still stops at JD's floor
    hit = next((c for c in inv if chosen and chosen in (c['name'], c.get('network'))), None)
    if hit and not (hit['mobile'] and b['set'] and b['left_gb'] - job_bytes / 1024 ** 3 < b['floor_gb']):
        return {'name': hit['name'], 'why': 'your choice (/net use auto lets HB pick)'}
    if job_bytes < BIG_JOB_BYTES or not mobile_ok:
        if home:
            best = max(home, key=lambda c: (_speed(conn, c['name']) or 0, c['kind'] == 'wired'))
            return {'name': best['name'], 'why': ('small job: the home line' if job_bytes < BIG_JOB_BYTES else
                                                  'big job, but mobile data is not allowed (' + ('no budget set' if not b['set'] else 'it would go under your floor') + ')')}
        return {'name': None, 'why': 'only mobile connections are up and this job may not use mobile data'}
    best = max(inv, key=lambda c: (_speed(conn, c['name']) or 0, not c['mobile']))
    return {'name': best['name'], 'why': f"big job: the fastest measured connection ({_speed(conn, best['name']) or '?'} MB/s)"
                                         + (f"; uses mobile data, {b['left_gb']} GB left" if best['mobile'] else '')}


def text(conn, run=_run):
    inv = inventory(conn, run)
    b = budget(conn, inv)
    lines = ['Connections:']
    for c in inv:
        speed = _speed(conn, c['name'])
        lines.append(f"- {c['name']} ({c['label'] or c['kind']}{', mobile data' if c['mobile'] else ''}): {'up' if c['up'] else 'down'}"
                     + (f", IPv4{'+IPv6' if c['ipv6'] else ''}" if c['ipv4'] else (', IPv6 only' if c['ipv6'] else ''))
                     + (f", default route (metric {c['metric']})" if c['default'] else '') + (f', last measured {speed} MB/s' if speed is not None else ''))
    first = next((c for c in inv if c['default']), None)
    if first and first['mobile']:
        lines.append(f"⚠ The system's first default route is {first['name']}, which is mobile data: ordinary traffic is using the bundle.")
    lines.append('Mobile data: ' + (f"{b['left_gb']} GB left, HB used {b['used_gb']} GB, floor {b['floor_gb']} GB" + (' - over 80% used' if b['warn'] else '')
                                    if b['set'] else 'no figure set (/net budget <GB left> <floor GB>)') + '.')
    return '\n'.join(lines)


def command(conn, args, actor, run=_run):
    """/net · /net bench [name] · /net budget <GB left> <floor GB> · /net mobile <name> on|off · /net pick <GB>"""
    sub = args[0].lower() if args else ''
    try:
        if sub == 'bench':
            names = args[1:2] or [c['name'] for c in inventory(conn, run) if c['up'] and c['kind'] != 'vpn' and c['ipv4']]
            return 'Measured: ' + '; '.join(f'{n} {benchmark(conn, n, run)} MB/s' for n in names) + '.'
        if sub == 'budget' and len(args) == 3:
            return set_budget(conn, float(args[1]), float(args[2]), actor)
        if sub == 'mobile' and len(args) == 3 and args[2].lower() in ('on', 'off'):
            return mark(conn, args[1], args[2].lower() == 'on', actor)
        if sub == 'use' and len(args) >= 2:          # Practice 132: select and control
            return choose(conn, ' '.join(args[1:]), actor)
        if sub == 'wifi':
            nets = wifi_list(run)
            return 'Saved Wi-Fi: ' + ('; '.join(f"{w['network']} ({'connected' if w['active'] else str(w['signal']) + '%' if w['in_range'] else 'not in range'})"
                                              for w in nets) or 'none') + '.'
        if sub == 'connect' and len(args) >= 2:
            return connect(conn, ' '.join(args[1:]), actor, run)
        if sub == 'disconnect' and len(args) == 2:
            return disconnect(conn, args[1], actor, run)
        if sub == 'pick' and len(args) == 2:
            p = pick(conn, float(args[1]) * 1024 ** 3)
            return f"{p['name'] or 'No connection'}: {p['why']}."
    except ValueError:
        return 'Use numbers: /net budget <GB left> <floor GB>, /net pick <GB>.'
    return text(conn, run) if not sub else ('Use /net, /net bench [name], /net budget <GB left> <floor GB>, /net mobile <name> on|off, /net pick <GB>, '
                                           '/net use <name>|auto, /net wifi, /net connect <Wi-Fi>, /net disconnect <name>.')


# Practice 132 (owner 17 Nov 2026): "the network status call and select and control". Status names the network each connection is on
# (wlo1 is the home ORBI16 Wi-Fi now, not the S9FE hotspot the download messages still said); JD picks the connection for downloads;
# JD connects a saved Wi-Fi network or disconnects a side connection. Control is JD's command or click only - never the main route
# or the VPN, never this machine's own "Hotspot" profile.
MOBILE_NETWORKS = {'S9FE'}            # JD's Samsung tablet hotspot (S-B59A6049BC); more with /net mobile <name> on


def _plain(name):
    return re.sub(r'^Auto ', '', str(name or ''))


def _mark(marks, name, net, default):
    return marks.get(name) or (marks.get(net) if net else None) or default


def networks(run=_run):
    """{device: network name} for the active NetworkManager connections ('Auto ORBI16' -> 'ORBI16')."""
    out = {}
    for line in (run(['nmcli', '-t', '-f', 'NAME,DEVICE', 'connection', 'show', '--active']) or '').splitlines():
        name, _, dev = line.rpartition(':')
        if name and dev and not dev.startswith('{'):
            out[dev] = _plain(name.replace('\\:', ':'))
    return out


def wifi_list(run=_run):
    """Saved Wi-Fi networks: [{name, network, in_range, signal, active}] (strongest first). This machine's own hotspot is left out."""
    saved = [l[:-len(':802-11-wireless')].replace('\\:', ':') for l in (run(['nmcli', '-t', '-f', 'NAME,TYPE', 'connection', 'show']) or '').splitlines()
             if l.endswith(':802-11-wireless')]
    seen = {}
    for l in (run(['nmcli', '-t', '-f', 'ACTIVE,SSID,SIGNAL', 'dev', 'wifi', 'list', '--rescan', 'no']) or '').splitlines():
        m = re.fullmatch(r'(yes|no):(.*):(\d+)', l.strip())
        if m and m.group(2):
            ssid = m.group(2).replace('\\:', ':')
            sig, act = seen.get(ssid, (0, False))
            seen[ssid] = (max(sig, int(m.group(3))), act or m.group(1) == 'yes')
    out = [{'name': s, 'network': _plain(s), 'in_range': _plain(s) in seen, 'signal': seen.get(_plain(s), (0, False))[0],
            'active': seen.get(_plain(s), (0, False))[1]} for s in saved if s != 'Hotspot']
    return sorted(out, key=lambda w: (not w['active'], -w['signal'], w['network']))


def choose(conn, name, actor):
    """JD's connection for downloads and big jobs ('auto' gives the choice back to HB)."""
    ensure_schema(conn)
    if str(name or '').lower() in ('', 'auto'):
        conn.execute('DELETE FROM hb_network_choice')
        return 'HB picks the connection for each job again: small jobs the home line, big ones the fastest within the mobile budget.'
    conn.execute('INSERT INTO hb_network_choice(id, name, set_by, at) VALUES (1,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name, '
                 'set_by=excluded.set_by, at=excluded.at', (str(name)[:80], str(actor)[:80], time.time()))
    return f'HB uses {name} for downloads and big jobs until you choose another (/net use auto lets HB pick again).'


def choice(conn):
    ensure_schema(conn)
    row = conn.execute('SELECT name FROM hb_network_choice WHERE id=1').fetchone()
    return row[0] if row else None


def _act(cmd, timeout=45):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, 'it did not finish in time'
    said = ((p.stdout or '') + (p.stderr or '')).strip().splitlines()
    return p.returncode == 0, (said[-1] if said else '')[:200]


def connect(conn, name, actor, run=_run, act=_act):
    """Connect a saved Wi-Fi network that is in range (JD's command or click)."""
    w = next((w for w in wifi_list(run) if name in (w['name'], w['network'])), None)
    if not w:
        return f'{name} is not a saved Wi-Fi network. Saved: ' + (', '.join(x['network'] for x in wifi_list(run)) or 'none') + '.'
    if w['active']:
        return f"Already connected to {w['network']}."
    if not w['in_range']:
        return f"{w['network']} is not in range right now (is the hotspot on?)."
    ok, said = act(['nmcli', 'connection', 'up', 'id', w['name']])
    return (f"Connected to {w['network']}." if ok else f"Could not connect to {w['network']}: {said}") + ' ' + text(conn, run).split('\n', 1)[-1].split('\nMobile')[0].strip()


def disconnect(conn, name, actor, run=_run, act=_act):
    """Disconnect a side connection (JD's command or click). Never the main route, the VPN, or the last connection that is up."""
    inv = inventory(conn, run)
    c = next((c for c in inv if c['name'] == name), None)
    main = next((x['name'] for x in inv if x['default']), None)
    if not c or not c['up']:
        return f'{name} is not up.'
    if c['kind'] == 'vpn':
        return f'{name} is the VPN (Tailscale); HB leaves it alone.'
    if name == main or not any(x['up'] and x['kind'] != 'vpn' and x['name'] != name for x in inv):
        return f'{name} carries the main route; HB will not disconnect it (you could lose access to HB).'
    ok, said = act(['nmcli', 'device', 'disconnect', name])
    return f'Disconnected {name}.' if ok else f'Could not disconnect {name}: {said}'


def status(conn, run=_run, wifi=False):
    """Everything main chat's network bar shows."""
    inv = inventory(conn, run)
    return {'links': [{**c, 'speed': _speed(conn, c['name'])} for c in inv], 'budget': budget(conn, inv), 'choice': choice(conn),
            'main': next((c['name'] for c in inv if c['default']), None), 'wifi': wifi_list(run) if wifi else []}
