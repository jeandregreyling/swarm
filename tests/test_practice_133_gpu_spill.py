"""Practice 133 (owner 17 Nov 2026: "keep letting apex do it, it needs to know how to use the system anyway"). APEX's model server spilled
2.6 GB out of the GPU into system RAM (llama.cpp --fit took all free VRAM at boot; the desktop grew later) and ran at 14 tokens/s. HB's GPU
guard now sees the spill, raises the --fit margin in its own drop-in (keeping the old one), restarts the server while idle, and says so."""
import sqlite3

from core import hb_gpu_guard as g, hb_hardware as hw
from test_hb_hardware import write

DROPIN = """[Service]
ExecStart=
ExecStart=/home/jd/llama.cpp/build-vulkan/bin/llama-server -m /m/model \\
    --device Vulkan0 --fit on -fitc 16384 \\
    --host 0.0.0.0 --port 8080 --parallel 1 --no-webui
"""


def test_practice_133_spill_is_measured_per_process(tmp_path):
    write(str(tmp_path / '9/cmdline'), '\0'.join(['/x/llama-server', '-m', '/m/model', '--port', '8080']) + '\0')
    write(str(tmp_path / '9/status'), 'VmRSS:\t1000 kB\n')
    write(str(tmp_path / '9/fdinfo/5'), 'drm-client-id:\t33\ndrm-memory-vram:\t14416592 KiB\ndrm-memory-gtt: \t2612264 KiB\n')
    write(str(tmp_path / '9/fdinfo/6'), 'drm-client-id:\t33\ndrm-memory-vram:\t14416592 KiB\ndrm-memory-gtt: \t2612264 KiB\n')
    p = hw.model_processes(str(tmp_path))[0]
    assert p['placement'] == 'gpu' and p['spilled_gb'] == 2.49


def test_practice_133_margin_text():
    assert g.margin(DROPIN) is None and g.margin(g.with_margin(DROPIN, 1536)) == 1536
    assert '--fit on -fitt 1536 -fitc 16384' in g.with_margin(DROPIN, 1536)
    assert g.margin(g.with_margin(g.with_margin(DROPIN, 1536), 2048)) == 2048
    assert g.with_margin('ExecStart=llama-server --ctx-size 8192', 1536) is None


def _run(tmp_path, spilled, idle=True, now=1000.0, conn=None):
    path = tmp_path / 'gpu-offload.conf'
    if not path.exists():
        path.write_text(DROPIN)
    conn, said, done = conn or sqlite3.connect(':memory:'), [], []
    out = g.spill_tick(conn, now=now, procs=[{'port': 8080, 'placement': 'gpu', 'spilled_gb': spilled}], path=path, idle=lambda: idle,
                       reload=lambda: done.append('reload') or True, restart=lambda: done.append('restart') or True,
                       answers=lambda: True, say=said.append)
    return out, path, done, said, conn


def test_practice_133_spill_is_fixed_once_and_announced(tmp_path):
    assert _run(tmp_path, 0.1)[0] is None and _run(tmp_path, 2.5, idle=False)[0] is None      # no spill / busy: wait
    out, path, done, said, conn = _run(tmp_path, 2.5)
    assert done == ['reload', 'restart'] and g.margin(path.read_text()) == 1536
    assert (tmp_path / 'gpu-offload.conf.before-hb').read_text() == DROPIN
    assert said and 'keeps 1536 MiB of GPU memory free' in said[0] and 'A test answer works' in said[0]
    assert _run(tmp_path, 2.5, now=1500.0, conn=conn)[0] is None                              # not again within SPILL_GAP_S
    _run(tmp_path, 1.0, now=1000.0 + g.SPILL_GAP_S + 1, conn=conn)
    assert g.margin(path.read_text()) == 2048                                                 # still spilling: one step more
