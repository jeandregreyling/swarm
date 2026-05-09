"""Tests for core.hive.providers.android (Android/Termux telemetry)."""
from __future__ import annotations

import json
import os
from unittest.mock import patch

import pytest

from core.hive.providers.android import AndroidProvider, is_android


# ---- fixtures --------------------------------------------------------------

_MEMINFO = """\
MemTotal:        5557456 kB
MemFree:          338940 kB
MemAvailable:    1395200 kB
Buffers:            1236 kB
Cached:          1175388 kB
SwapTotal:       2097148 kB
SwapFree:        1820416 kB
"""

_BATTERY_OK = json.dumps({
    'health': 'GOOD',
    'percentage': 87,
    'plugged': 'UNPLUGGED',
    'status': 'DISCHARGING',
    'temperature': 31.5,
    'current': -845,
})


# ---- platform_name / capabilities -----------------------------------------

def test_platform_name_is_android():
    assert AndroidProvider().platform_name() == 'android'


def test_capabilities_minimal():
    caps = AndroidProvider().capabilities()
    assert 'inference.cpu' in caps


# ---- memory --------------------------------------------------------------

def test_memory_parses_meminfo(monkeypatch):
    p = AndroidProvider()
    monkeypatch.setattr(p, '_read_text', staticmethod(lambda path: _MEMINFO if path == '/proc/meminfo' else None))
    mem = p.memory()
    assert mem['ram_total_mb'] == 5557456 // 1024
    # MemAvailable wins over MemFree.
    assert mem['ram_free_mb'] == 1395200 // 1024
    assert mem['swap_used_mb'] == (2097148 - 1820416) // 1024


def test_memory_handles_missing_meminfo(monkeypatch):
    p = AndroidProvider()
    monkeypatch.setattr(p, '_read_text', staticmethod(lambda path: None))
    mem = p.memory()
    assert mem['ram_total_mb'] is None
    assert mem['ram_free_mb'] is None
    assert mem['swap_used_mb'] is None


def test_memory_falls_back_to_memfree(monkeypatch):
    p = AndroidProvider()
    txt = "MemTotal: 1024000 kB\nMemFree: 200000 kB\n"
    monkeypatch.setattr(p, '_read_text', staticmethod(lambda path: txt))
    mem = p.memory()
    assert mem['ram_free_mb'] == 200000 // 1024


# ---- compute (CPU load via cpufreq) --------------------------------------

def test_cpu_load_pct_averages_freq_ratio(tmp_path, monkeypatch):
    # Build a fake /sys/devices/system/cpu/ tree with two cores.
    root = tmp_path / 'cpu'
    for n, (cur, mx) in enumerate([(2002000, 2002000), (533000, 2002000)]):
        d = root / f'cpu{n}' / 'cpufreq'
        d.mkdir(parents=True)
        (d / 'scaling_cur_freq').write_text(str(cur))
        (d / 'cpuinfo_max_freq').write_text(str(mx))

    p = AndroidProvider()

    def fake_read_int(path):
        # Translate /sys/devices/system/cpu/cpuN/... -> tmp tree.
        marker = '/sys/devices/system/cpu/'
        if marker in path:
            rel = path.split(marker, 1)[1]
            mapped = root / rel
            if mapped.exists():
                return int(mapped.read_text().strip())
        return None

    monkeypatch.setattr(p, '_read_int_file', staticmethod(fake_read_int))
    monkeypatch.setattr(os.path, 'isdir', lambda path: '/sys/devices/system/cpu/cpu' in path and (root / path.split('/sys/devices/system/cpu/', 1)[1].split('/', 1)[0]).exists())
    monkeypatch.setattr(os.path, 'exists', lambda path: False)

    load = p._cpu_load_pct()
    # cpu0 = 100%, cpu1 = 26.6% → avg ~63.3%
    assert load is not None
    assert 60.0 <= load <= 65.0


def test_cpu_load_pct_returns_none_when_no_cores(monkeypatch):
    p = AndroidProvider()
    monkeypatch.setattr(os.path, 'isdir', lambda path: False)
    assert p._cpu_load_pct() is None


# ---- battery / power -----------------------------------------------------

def test_termux_battery_parsed_when_present(monkeypatch):
    p = AndroidProvider()
    monkeypatch.setattr(p, '_termux_battery', staticmethod(lambda: json.loads(_BATTERY_OK)))
    pw = p.power()
    assert pw['battery_pct'] == 87
    assert pw['on_battery'] is True
    assert pw['thermal_pressure'] is None  # derived later in local_node


def test_termux_battery_absent_defaults_safely(monkeypatch):
    p = AndroidProvider()
    monkeypatch.setattr(p, '_termux_battery', staticmethod(lambda: None))
    pw = p.power()
    assert pw['battery_pct'] is None
    # Mobile devices default to on_battery=True when status unknown.
    assert pw['on_battery'] is True


def test_battery_temp_used_for_cpu_peak(monkeypatch):
    p = AndroidProvider()
    monkeypatch.setattr(p, '_termux_battery', staticmethod(lambda: {'temperature': 36.2}))
    assert p._cpu_peak_temp_c() == 36.2


def test_battery_temp_missing_returns_none(monkeypatch):
    p = AndroidProvider()
    monkeypatch.setattr(p, '_termux_battery', staticmethod(lambda: None))
    assert p._cpu_peak_temp_c() is None


# ---- thermal block (passive) --------------------------------------------

def test_thermal_block_is_passive():
    th = AndroidProvider().thermal()
    assert th['controllable'] is False
    assert th['fan_mode'] == 'passive'
    assert th['fan_rpm'] is None


# ---- sample bundle shape -------------------------------------------------

def test_sample_returns_all_four_sections(monkeypatch):
    p = AndroidProvider()
    monkeypatch.setattr(p, '_read_text', staticmethod(lambda path: _MEMINFO if path == '/proc/meminfo' else None))
    monkeypatch.setattr(p, '_termux_battery', staticmethod(lambda: None))
    monkeypatch.setattr(p, '_cpu_load_pct', lambda: 25.0)
    bundle = p.sample()
    assert set(bundle.keys()) == {'compute', 'thermal', 'memory', 'power'}
    assert bundle['compute']['cpu_load_pct'] == 25.0
    assert bundle['memory']['ram_total_mb'] == 5557456 // 1024


# ---- is_android() detection ---------------------------------------------

def test_is_android_via_env(monkeypatch):
    monkeypatch.setenv('ANDROID_ROOT', '/system')
    assert is_android() is True


def test_is_android_via_termux_prefix(monkeypatch):
    monkeypatch.delenv('ANDROID_ROOT', raising=False)
    monkeypatch.delenv('ANDROID_DATA', raising=False)
    monkeypatch.setenv('PREFIX', '/data/data/com.termux/files/usr')
    assert is_android() is True


def test_is_android_false_on_plain_linux(monkeypatch):
    monkeypatch.delenv('ANDROID_ROOT', raising=False)
    monkeypatch.delenv('ANDROID_DATA', raising=False)
    monkeypatch.setenv('PREFIX', '')
    with patch('os.path.exists', return_value=False):
        assert is_android() is False


# ---- Samsung / GPU / NPU detection ----------------------------------------

def test_gpu_present_is_always_true():
    """All Android devices with a display have a GLES GPU."""
    assert AndroidProvider()._gpu_present() is True


def test_npu_present_false_on_generic_android(monkeypatch):
    """Non-Samsung devices without NNAPI libs report no NPU."""
    p = AndroidProvider()
    monkeypatch.setattr(p, '_getprop', staticmethod(lambda key: 'google' if key == 'ro.product.manufacturer' else None))
    with patch('os.path.exists', return_value=False):
        assert p._npu_present() is False


def test_npu_present_true_via_samsung_driver(monkeypatch):
    """Samsung devices with Eden NN driver libs report NPU present."""
    p = AndroidProvider()
    monkeypatch.setattr(p, '_getprop', staticmethod(lambda key: 'samsung' if key == 'ro.product.manufacturer' else None))

    def exists_probe(path):
        return 'libeden_nn_onsystem.so' in str(path)

    with patch('os.path.exists', side_effect=exists_probe):
        assert p._npu_present() is True


def test_npu_present_true_via_samsung_soc(monkeypatch):
    """Samsung devices with known NPU SoCs report NPU present."""
    p = AndroidProvider()

    def fake_getprop(key):
        if key == 'ro.product.manufacturer':
            return 'samsung'
        if key == 'ro.hardware':
            return 'exynos2200'
        return None

    monkeypatch.setattr(p, '_getprop', staticmethod(fake_getprop))
    with patch('os.path.exists', return_value=False):
        assert p._npu_present() is True


def test_npu_present_true_via_generic_nnapi_lib(monkeypatch):
    """Any device with NNAPI HAL libs reports NPU present."""
    p = AndroidProvider()
    monkeypatch.setattr(p, '_getprop', staticmethod(lambda key: 'google' if key == 'ro.product.manufacturer' else None))

    def exists_probe(path):
        return 'libneuralnetworks.so' in str(path)

    with patch('os.path.exists', side_effect=exists_probe):
        assert p._npu_present() is True


def test_capabilities_includes_tflite_and_gpu(monkeypatch):
    """Capabilities always include inference.cpu + inference.tflite + inference.gpu."""
    p = AndroidProvider()
    monkeypatch.setattr(p, '_npu_present', lambda: False)
    caps = p.capabilities()
    assert 'inference.cpu' in caps
    assert 'inference.tflite' in caps
    assert 'inference.gpu' in caps
    assert 'inference.npu' not in caps


def test_capabilities_includes_npu_when_present(monkeypatch):
    """Capabilities include inference.npu when NPU is detected."""
    p = AndroidProvider()
    monkeypatch.setattr(p, '_npu_present', lambda: True)
    caps = p.capabilities()
    assert 'inference.npu' in caps


def test_compute_reports_gpu_and_npu_flags(monkeypatch):
    """compute() dict reflects gpu_present and npu_present dynamically."""
    p = AndroidProvider()
    monkeypatch.setattr(p, '_cpu_load_pct', lambda: 30.0)
    monkeypatch.setattr(p, '_cpu_peak_temp_c', lambda: 40.0)
    monkeypatch.setattr(p, '_gpu_present', lambda: True)
    monkeypatch.setattr(p, '_npu_present', lambda: True)
    c = p.compute()
    assert c['gpu_present'] is True
    assert c['npu_present'] is True


# ---- dispatcher -----------------------------------------------------------

def test_detect_provider_picks_android(monkeypatch):
    from core.hive.providers import detect_provider
    monkeypatch.setenv('ANDROID_ROOT', '/system')
    with patch('platform.system', return_value='Linux'):
        prov = detect_provider()
    assert prov.platform_name() == 'android'
