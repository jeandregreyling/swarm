"""NVMe swap for very large models (owner 14 Nov 2026): slow but possible. HB works out WHETHER a model needs swap and HOW MUCH;
creating or removing the swap file needs root, so HB only hands JD the one pkexec command (scripts/hb_swapfile.sh). HB never
changes swap itself."""
import shutil
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'hb_swapfile.sh'
FILE = '/srv/hb-swapfile'
RAM_RESERVE_GB = 8.0       # RAM that stays free for HB, APEX's worker and the desktop
DISK_RESERVE_GB = 20.0
MAX_GB = 64


def plan(model_gb, ram_total_gb, ram_available_gb, disk_free_gb):
    """{'needed': bool, 'swap_gb': int, 'ok': bool, 'why': plain words} for running a model of model_gb in RAM."""
    model_gb = float(model_gb)
    short = model_gb + RAM_RESERVE_GB - float(ram_available_gb)
    if short <= 0:
        return {'needed': False, 'swap_gb': 0, 'ok': True, 'why': f'{model_gb:g} GB fits in RAM ({ram_available_gb:.0f} GB available, {RAM_RESERVE_GB:g} GB kept free)'}
    if model_gb > float(ram_total_gb) * 1.5:
        return {'needed': True, 'swap_gb': 0, 'ok': False, 'why': f'{model_gb:g} GB is more than 1.5x the RAM ({ram_total_gb:.0f} GB): it would spend its time swapping'}
    size = min(MAX_GB, int(short + 0.999) + 2)
    if size + DISK_RESERVE_GB > float(disk_free_gb):
        return {'needed': True, 'swap_gb': size, 'ok': False, 'why': f'needs {size} GB of swap but the disk has only {disk_free_gb:.0f} GB free ({DISK_RESERVE_GB:g} GB must stay)'}
    return {'needed': True, 'swap_gb': size, 'ok': True, 'why': f'{model_gb:g} GB is {short:.1f} GB more than RAM can give now; {size} GB of swap covers it (slow)'}


def status(run=subprocess.run):
    try:
        out = run(['swapon', '--show=NAME,SIZE,USED', '--noheadings'], capture_output=True, text=True, timeout=5).stdout
    except Exception:
        out = ''
    mine = [l.split() for l in out.splitlines() if l.startswith(FILE)]
    return {'on': bool(mine), 'size': mine[0][1] if mine else None, 'used': mine[0][2] if mine else None, 'other': [l.split()[0] for l in out.splitlines() if l and not l.startswith(FILE)]}


def _machine():
    mem = {}
    with open('/proc/meminfo') as handle:
        for line in handle:
            if line.startswith(('MemTotal', 'MemAvailable')):
                mem[line.split(':')[0]] = int(line.split()[1]) / 1024 ** 2
    return mem.get('MemTotal', 0.0), mem.get('MemAvailable', 0.0), shutil.disk_usage('/srv').free / 1024 ** 3


def command(args, machine=_machine, run=subprocess.run):
    """/swap  ·  /swap plan <model GB>"""
    s = status(run)
    if args and args[0].lower() == 'plan' and len(args) == 2:
        try:
            p = plan(float(args[1]), *machine())
        except ValueError:
            return 'Use /swap plan <model size in GB>.'
        if not p['needed'] or not p['ok']:
            return ('No swap needed: ' if not p['needed'] else 'Not possible: ') + p['why'] + '.'
        return (f"{p['why']}.\nTo create it (your password popup): pkexec {SCRIPT} create {p['swap_gb']}\n"
                f"To remove it afterwards: pkexec {SCRIPT} remove\nHB does not create or remove swap itself.")
    return (f"HB swap file: {'on, ' + s['size'] + ' (' + s['used'] + ' used)' if s['on'] else 'none'}"
            + (f"; other swap: {', '.join(s['other'])}" if s['other'] else '') + '. Plan one with /swap plan <model GB>.')
