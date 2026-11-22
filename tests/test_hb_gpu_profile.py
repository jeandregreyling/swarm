"""hb-gpu-profile: approved profiles only, hard limits, automatic revert - tested on a fake sysfs, never the real card."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
OD = ("OD_SCLK:\n0: 500Mhz\n1: 2159Mhz\nOD_MCLK:\n0: 97Mhz\n1: 1000MHz\nOD_RANGE:\nSCLK:     500Mhz       2600Mhz\n"
      "MCLK:     674Mhz       1075Mhz\nOD_VDDGFX_OFFSET:\n0mV\n")


@pytest.fixture
def gpu(tmp_path, monkeypatch):
    d = tmp_path / 'sys' / 'card1' / 'device'
    h = d / 'hwmon' / 'hwmon4'
    h.mkdir(parents=True)
    (d / 'pp_od_clk_voltage').write_text(OD)
    (d / 'power_dpm_force_performance_level').write_text('auto\n')
    for name, value in (('power1_cap', 227000000), ('power1_cap_max', 249000000), ('power1_cap_default', 227000000)):
        (h / name).write_text(f'{value}\n')
    (h / 'temp2_input').write_text('60000\n')
    (h / 'temp2_label').write_text('junction\n')
    profiles = tmp_path / 'profiles.json'
    profiles.write_text(json.dumps({'stock': {'note': 'driver defaults'},
                                    'tested': {'sclk_mhz': 2400, 'mclk_mhz': 1050, 'power_cap_w': 240, 'vddgfx_offset_mv': -50},
                                    'too_hot': {'sclk_mhz': 2900}, 'overvolt': {'vddgfx_offset_mv': 50}}))
    monkeypatch.setenv('HB_GPU_SYSFS', str(tmp_path / 'sys'))
    monkeypatch.setenv('HB_GPU_PROFILES', str(profiles))
    monkeypatch.setenv('HB_GPU_LOG', str(tmp_path / 'log'))
    monkeypatch.setenv('HB_GPU_WATCH_S', '0')
    spec = importlib.util.spec_from_file_location('hb_gpu_profile', ROOT / 'scripts' / 'hb_gpu_profile.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, d, h


def test_an_approved_profile_is_applied(gpu):
    mod, d, h = gpu
    out = mod.apply('tested')
    assert out['ok'] and (d / 'power_dpm_force_performance_level').read_text().strip() == 'manual'
    assert (h / 'power1_cap').read_text().strip() == '240000000'


def test_unapproved_names_and_out_of_range_values_are_refused(gpu):
    mod, d, h = gpu
    assert not mod.apply('made_up')['ok']
    assert 'outside' in mod.apply('too_hot')['refused'][0]
    assert 'outside' in mod.apply('overvolt')['refused'][0]          # no overvolting
    assert (d / 'power_dpm_force_performance_level').read_text().strip() == 'auto'   # nothing was written


def test_reset_restores_defaults(gpu):
    mod, d, h = gpu
    mod.apply('tested')
    assert mod.reset()['ok']
    assert (d / 'power_dpm_force_performance_level').read_text().strip() == 'auto'
    assert (h / 'power1_cap').read_text().strip() == '227000000'


def test_usage_is_strict(gpu):
    mod, *_ = gpu
    assert mod.main(['apply']) == 2 and mod.main(['rm', '-rf']) == 2 and mod.main(['apply', 'a', 'b']) == 2
