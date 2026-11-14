"""Sundial hardware truth: amdgpu sysfs and per-process VRAM counted once per GPU client."""
import os

import pytest

from core import hb_hardware as hw


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as fh:
        fh.write(text)


def test_amdgpu_sysfs_is_read_and_the_largest_card_wins(tmp_path):
    write(str(tmp_path / 'card0/device/mem_info_vram_total'), str(512 * 2**20))       # small iGPU
    write(str(tmp_path / 'card0/device/mem_info_vram_used'), str(100 * 2**20))
    write(str(tmp_path / 'card1/device/mem_info_vram_total'), str(16 * 2**30))
    write(str(tmp_path / 'card1/device/mem_info_vram_used'), str(12 * 2**30))
    write(str(tmp_path / 'card1/device/gpu_busy_percent'), '37')
    g = hw.gpu_stats(str(tmp_path))
    assert g == {'vram_used_gb': 12.0, 'vram_total_gb': 16.0, 'vram_percent': 75.0, 'busy_percent': 37, 'source': 'amdgpu sysfs'}


def _proc(root, pid, argv, rss_kb, fds):
    write(str(root / str(pid) / 'cmdline'), '\0'.join(argv) + '\0')
    write(str(root / str(pid) / 'status'), f'Name:\tllama-server\nVmRSS:\t{rss_kb} kB\n')
    for fd, text in fds.items():
        write(str(root / str(pid) / 'fdinfo' / str(fd)), text)


def test_model_processes_count_vram_once_per_client_and_spot_the_apex_service(tmp_path):
    client = 'drm-driver:\tamdgpu\ndrm-client-id:\t23\ndrm-memory-vram:\t11387756 KiB\n'
    _proc(tmp_path, 2450, ['/x/llama-server', '-m', '/m/sha256-2049', '--port', '8080'], 277256, {3: client, 4: client})
    _proc(tmp_path, 382727, ['/x/llama-server', '-m', '/m/sha256-60e0', '--alias', 'apex-direct:7b', '--port', '18229'], 695420,
          {5: 'drm-client-id:\t30\ndrm-memory-vram:\t2474728 KiB\n'})
    _proc(tmp_path, 241128, ['/x/llama-server', '-m', '/m/sha256-dde5', '--alias', 'seven-direct:daily', '--port', '18161',
                             '--n-gpu-layers', '0'], 622692, {})
    _proc(tmp_path, 999, ['/usr/bin/python3', 'llama-server-lookalike'], 100, {})
    procs = {p['model']: p for p in hw.model_processes(str(tmp_path))}
    assert set(procs) == {'apex-server', 'apex-direct:7b', 'seven-direct:daily'}
    apex = procs['apex-server']
    assert apex['vram_gb'] == pytest.approx(10.86, abs=0.01)           # two fds, one client: not doubled
    assert apex['kind'] == 'service' and apex['unit'] == 'apex-server' and apex['placement'] == 'gpu'
    assert procs['apex-direct:7b']['kind'] == 'managed' and procs['apex-direct:7b']['vram_gb'] == pytest.approx(2.36, abs=0.01)
    assert procs['seven-direct:daily']['placement'] == 'ram' and procs['seven-direct:daily']['ram_gb'] == pytest.approx(0.59, abs=0.01)


def test_service_switch_only_accepts_whitelisted_units_and_actions():
    with pytest.raises(ValueError):
        hw.service_action('ssh', 'stop')
    with pytest.raises(ValueError):
        hw.service_action('apex-server', 'restart-everything')
    assert hw.service_state('ssh') is None


def test_housekeeping_stops_duplicates_idle_and_gpu_hogs_but_keeps_one_of_each(monkeypatch):
    from core.seven_llm import llama_server as ls
    running = [
        {'model': 'seven-direct:daily', 'pid': 300, 'port': 18163, 'own': False},
        {'model': 'seven-direct:daily', 'pid': 100, 'port': 18161, 'own': False},
        {'model': 'seven-direct:daily', 'pid': 200, 'port': 18162, 'own': False},
        {'model': 'apex-direct:7b', 'pid': 400, 'port': 18229, 'own': False},
        {'model': 'fred-cpu:24b', 'pid': 500, 'port': 18757, 'own': False},
    ]
    stopped = []
    monkeypatch.setattr(ls, '_residents', lambda: [r for r in running if r['pid'] not in stopped])
    monkeypatch.setattr(ls, '_stop_resident', lambda r: stopped.append(r['pid']))
    now = 10_000_000.0
    state = {'seven-direct:daily': {'last_used': now - 60},
             'apex-direct:7b': {'last_used': now - 2400, 'gpu': True, 'ttl_seconds': 7200},  # within its time limit, idle 40 min
             'fred-cpu:24b': {'last_used': now - 7200, 'gpu': False, 'ttl_seconds': 1800}}   # past its own time limit
    monkeypatch.setattr(ls, '_load_state', lambda: state)
    monkeypatch.setattr(ls, '_save_state', lambda s: None)
    monkeypatch.setattr(ls.time, 'time', lambda: now)
    result = ls.housekeep(now=now, vram_percent=90.0)
    reasons = {(s['pid'], s['reason'].split(' ')[0]) for s in result['stopped']}
    assert (200, 'duplicate') in reasons and (300, 'duplicate') in reasons and 100 not in stopped   # oldest copy kept
    assert (500, 'idle') in reasons                                                                # TTL rule, now scheduled
    assert any(pid == 400 and r.startswith('GPU') for pid, r in reasons)                            # GPU pressure rule
    stopped.clear(); state['apex-direct:7b'] = {'last_used': now - 2400, 'gpu': True, 'ttl_seconds': 7200}
    result = ls.housekeep(now=now, vram_percent=60.0)
    assert 400 not in stopped                                     # no pressure: an idle GPU model may stay loaded


def test_housekeeping_tick_runs_at_most_once_a_minute_in_the_background(monkeypatch):
    import threading
    hw._HK_LAST[0] = 0.0
    ran = threading.Event()
    assert hw.housekeeping_tick(now=1000.0, housekeep=lambda: (ran.set(), {'stopped': []})[1]) is True
    assert ran.wait(2)
    assert hw.housekeeping_tick(now=1030.0, housekeep=lambda: {'stopped': []}) is False
