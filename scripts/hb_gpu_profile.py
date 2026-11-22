#!/usr/bin/env python3
"""hb-gpu-profile: apply JD's approved GPU profiles on the RX 6800 - the only root action HB and APEX may take (JD 22 Nov 2026).

Installed by JD as /usr/local/sbin/hb-gpu-profile (root:root 0755), allowed to HB with one sudoers rule. Profiles live in
/etc/hb/gpu-profiles.json (root-owned): HB and APEX can only pick a profile JD wrote, never change its numbers.

  hb-gpu-profile status          current clocks, power cap, temperatures (JSON)
  hb-gpu-profile list            the approved profiles
  hb-gpu-profile apply NAME      apply one approved profile, then watch temperatures for 60 s; too hot -> automatic reset
  hb-gpu-profile reset           back to the driver defaults (stock clocks, default power cap, automatic mode)

Hard limits, checked before anything is written: clocks inside the driver's OD_RANGE, power cap at most power1_cap_max,
voltage offset between -150 and 0 mV (undervolt only - no overvolting). Every action is logged.
"""
import glob
import json
import os
import re
import sys
import time

PROFILES = os.environ.get('HB_GPU_PROFILES', '/etc/hb/gpu-profiles.json')
LOG = os.environ.get('HB_GPU_LOG', '/var/log/hb-gpu-profile.log')
SYSFS = os.environ.get('HB_GPU_SYSFS', '/sys/class/drm')
VOFF_MIN, VOFF_MAX = -150, 0
JUNCTION_LIMIT_C = 100.0
WATCH_S = int(os.environ.get('HB_GPU_WATCH_S', '60'))


def device():
    for d in sorted(glob.glob(os.path.join(SYSFS, 'card*/device'))):
        if os.path.isfile(os.path.join(d, 'pp_od_clk_voltage')):
            return d
    raise SystemExit(json.dumps({'ok': False, 'error': 'no AMD GPU with overdrive found'}))


def hwmon(d):
    found = sorted(glob.glob(os.path.join(d, 'hwmon', 'hwmon*')))
    if not found:
        raise SystemExit(json.dumps({'ok': False, 'error': 'no hwmon for the GPU'}))
    return found[0]


def read(path, default=''):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return default


def write(path, value):
    with open(path, 'w') as f:
        f.write(str(value) + '\n')


def od_ranges(d):
    text = read(os.path.join(d, 'pp_od_clk_voltage'))
    sclk = re.search(r'SCLK:\s*(\d+)\s*Mhz\s+(\d+)\s*Mhz', text, re.I)
    mclk = re.search(r'MCLK:\s*(\d+)\s*Mhz\s+(\d+)\s*Mhz', text, re.I)
    if not sclk or not mclk:
        raise SystemExit(json.dumps({'ok': False, 'error': 'driver did not report OD_RANGE'}))
    return (int(sclk.group(1)), int(sclk.group(2))), (int(mclk.group(1)), int(mclk.group(2)))


def temps(h):
    out = {}
    for f in glob.glob(os.path.join(h, 'temp*_input')):
        label = read(f.replace('_input', '_label'), os.path.basename(f))
        try:
            out[label] = int(read(f)) / 1000.0
        except ValueError:
            pass
    return out


def status():
    d = device()
    h = hwmon(d)
    return {'ok': True, 'mode': read(os.path.join(d, 'power_dpm_force_performance_level')),
            'od': read(os.path.join(d, 'pp_od_clk_voltage')),
            'power_cap_w': int(read(os.path.join(h, 'power1_cap'), '0')) // 1_000_000,
            'power_cap_max_w': int(read(os.path.join(h, 'power1_cap_max'), '0')) // 1_000_000,
            'temps_c': temps(h)}


def profiles():
    try:
        with open(PROFILES) as f:
            data = json.load(f)
    except (OSError, ValueError) as exc:
        raise SystemExit(json.dumps({'ok': False, 'error': f'cannot read {PROFILES}: {exc}'}))
    if not isinstance(data, dict):
        raise SystemExit(json.dumps({'ok': False, 'error': 'profiles file must be a JSON object of name -> settings'}))
    return data


def check(name, p, d, h):
    """The hard limits. Returns a list of problems (empty = safe to apply)."""
    (smin, smax), (mmin, mmax) = od_ranges(d)
    cap_max = int(read(os.path.join(h, 'power1_cap_max'), '0')) // 1_000_000
    problems = []
    for key, lo, hi in (('sclk_mhz', smin, smax), ('mclk_mhz', mmin, mmax), ('power_cap_w', 1, cap_max), ('vddgfx_offset_mv', VOFF_MIN, VOFF_MAX)):
        if key in p:
            v = p[key]
            if type(v) is not int or not lo <= v <= hi:
                problems.append(f'{name}.{key}={v!r} is outside {lo}..{hi}')
    unknown = set(p) - {'sclk_mhz', 'mclk_mhz', 'power_cap_w', 'vddgfx_offset_mv', 'fan_pwm', 'note'}
    if unknown:
        problems.append(f'{name} has unknown settings: {sorted(unknown)}')
    return problems


def log(entry):
    entry = {'at': time.strftime('%Y-%m-%d %H:%M:%S'), **entry}
    try:
        with open(LOG, 'a') as f:
            f.write(json.dumps(entry) + '\n')
    except OSError:
        pass
    return entry


def reset(reason='reset requested'):
    d = device()
    h = hwmon(d)
    od = os.path.join(d, 'pp_od_clk_voltage')
    write(od, 'r')
    write(od, 'c')
    write(os.path.join(d, 'power_dpm_force_performance_level'), 'auto')
    default = read(os.path.join(h, 'power1_cap_default'))
    if default:
        write(os.path.join(h, 'power1_cap'), default)
    # Restore GPU 3-fan automatic curve when returning to stock
    pwm_en = os.path.join(h, 'pwm1_enable')
    if os.path.exists(pwm_en):
        try:
            write(pwm_en, '2')
        except OSError:
            pass
    return log({'ok': True, 'action': 'reset', 'reason': reason, 'temps_c': temps(h)})


def apply(name):
    data = profiles()
    if name not in data:
        return {'ok': False, 'error': f'{name!r} is not an approved profile; approved: {sorted(data)}'}
    p = data[name]
    d = device()
    h = hwmon(d)
    problems = check(name, p, d, h)
    if problems:
        return log({'ok': False, 'action': 'apply', 'profile': name, 'refused': problems})
    # Fan-first thermal safety: spool RX 6800 3-fan pwm1 to ~88% (225/255) BEFORE raising clocks/power cap!
    pwm_en = os.path.join(h, 'pwm1_enable')
    pwm_val = os.path.join(h, 'pwm1')
    if os.path.exists(pwm_en) and os.path.exists(pwm_val):
        try:
            write(pwm_en, '1')
            write(pwm_val, str(int(p.get('fan_pwm', 225))))
        except OSError:
            pass
    od = os.path.join(d, 'pp_od_clk_voltage')
    write(os.path.join(d, 'power_dpm_force_performance_level'), 'manual')
    if 'sclk_mhz' in p:
        write(od, f"s 1 {p['sclk_mhz']}")
    if 'mclk_mhz' in p:
        write(od, f"m 1 {p['mclk_mhz']}")
    if 'vddgfx_offset_mv' in p:
        write(od, f"vo {p['vddgfx_offset_mv']}")
    write(od, 'c')
    if 'power_cap_w' in p:
        write(os.path.join(h, 'power1_cap'), p['power_cap_w'] * 1_000_000)
    peak = {}
    end = time.time() + WATCH_S
    while time.time() < end:
        t = temps(h)
        peak = {k: max(v, peak.get(k, v)) for k, v in t.items()}
        if any('junction' in k.lower() and v > JUNCTION_LIMIT_C for k, v in t.items()):
            reset(f'{name}: junction {t} above {JUNCTION_LIMIT_C} C within {WATCH_S} s - automatic revert')
            return log({'ok': False, 'action': 'apply', 'profile': name, 'reverted': True, 'peak_temps_c': peak})
        time.sleep(2)
    return log({'ok': True, 'action': 'apply', 'profile': name, 'settings': p, 'peak_temps_c': peak, 'od': read(od)})


def main(argv):
    if not argv or argv[0] not in ('status', 'list', 'apply', 'reset') or (argv[0] == 'apply') != (len(argv) == 2) or len(argv) > 2:
        print(json.dumps({'ok': False, 'error': 'usage: hb-gpu-profile status | list | apply NAME | reset'}))
        return 2
    cmd = argv[0]
    if cmd == 'status':
        out = status()
    elif cmd == 'list':
        out = {'ok': True, 'profiles': profiles()}
    elif cmd == 'reset':
        out = reset()
    else:
        out = apply(argv[1])
    print(json.dumps(out))
    return 0 if out.get('ok') else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
