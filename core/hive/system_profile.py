"""core.hive.system_profile — Cross-platform host hardware, runtime & model awareness.

Probes the host HB is currently running on (Windows, Linux, macOS) so the
harness stops assuming a single AMD/Linux rig:
  - Hardware fingerprint: manufacturer, model, OS, CPU, cores/threads, RAM, swap,
    disk headroom, GPUs (discrete vs integrated, VRAM, backend), and node tier.
  - Local runtimes: Ollama (/api/tags + /api/ps) and local llama-server /
    OpenAI-compatible endpoints.
  - Per-model fit classification (fast / tight / too-large) for THIS host.
  - Role model recommendations for APEX (interactive worker), FRED (deep
    thinker / reviewer in RAM), and HB (fast coordinator / homework).
  - Shareable capability manifest so enrolled potato nodes know what each peer
    can run and share.

All probes are read-only, bounded by short timeouts, and never raise.
"""
from __future__ import annotations

import logging
import os
import platform as _platform
import re
import shutil
import socket
import subprocess
import time
from pathlib import Path
from typing import Any

_LOG = logging.getLogger(__name__)

_CACHE_TTL_S = 30.0
_CACHE: dict[str, Any] = {'ts': 0.0, 'profile': None}

_EMBED_MARKERS = ('embed', 'nomic-embed', 'bge-', 'e5-', 'mxbai-embed')
_IGPU_MARKERS = (
    'intel(r) uhd', 'intel uhd', 'intel(r) hd', 'intel hd',
    'intel(r) iris', 'intel iris', 'microsoft basic', 'llvmpipe',
    'virtualbox', 'vmware', 'paravirtual', 'aspeed', 'matrox',
)


def _is_embed_model(name: str) -> bool:
    low = str(name or '').lower()
    return any(m in low for m in _EMBED_MARKERS)


def _classify_gpu(name: str, vram_mb: int | None) -> dict[str, Any]:
    low = str(name or '').lower()
    is_igpu = any(m in low for m in _IGPU_MARKERS)
    if 'nvidia' in low or 'geforce' in low or 'rtx' in low or 'quadro' in low or 'tesla' in low:
        vendor, backend, discrete = 'nvidia', 'cuda', not is_igpu
    elif 'amd' in low or 'radeon' in low or 'rx ' in low or 'instinct' in low:
        vendor = 'amd'
        discrete = not is_igpu and (vram_mb is None or vram_mb >= 4096)
        backend = 'rocm' if (_platform.system().lower() == 'linux' and discrete) else ('vulkan' if discrete else 'igpu')
    elif 'apple' in low and _platform.system().lower() == 'darwin':
        vendor, backend, discrete = 'apple', 'metal', True
    elif 'intel' in low:
        vendor = 'intel'
        discrete = ('arc' in low) and (vram_mb is None or vram_mb >= 4096)
        backend = 'vulkan' if discrete else 'igpu'
    else:
        vendor, backend, discrete = 'unknown', ('igpu' if is_igpu else 'unknown'), False
    if vram_mb is not None and vram_mb < 3072 and vendor != 'apple':
        discrete = False
        if backend in ('rocm', 'cuda', 'vulkan'):
            backend = 'igpu'
    return {
        'name': str(name or 'unknown').strip(),
        'vendor': vendor,
        'vram_mb': int(vram_mb) if isinstance(vram_mb, (int, float)) and vram_mb > 0 else None,
        'discrete': bool(discrete),
        'backend': backend,
    }


def _probe_host_dmi() -> tuple[str | None, str | None, str | None]:
    """Return (manufacturer, model, cpu_model) best-effort per OS."""
    sys_name = _platform.system().lower()
    if sys_name == 'linux':
        def _read(path: str) -> str | None:
            try:
                val = Path(path).read_text(encoding='utf-8', errors='ignore').strip()
                return val or None
            except OSError:
                return None

        mfg = _read('/sys/devices/virtual/dmi/id/sys_vendor')
        model = _read('/sys/devices/virtual/dmi/id/product_name')
        cpu_model = None
        try:
            for line in Path('/proc/cpuinfo').read_text(encoding='utf-8', errors='ignore').splitlines():
                if line.lower().startswith('model name'):
                    cpu_model = line.split(':', 1)[1].strip()
                    break
        except OSError:
            pass
        return mfg, model, cpu_model

    if sys_name == 'windows':
        mfg = model = cpu_model = None
        try:
            import winreg  # type: ignore[import-not-found]
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'HARDWARE\DESCRIPTION\System\BIOS') as k:
                try:
                    mfg = str(winreg.QueryValueEx(k, 'SystemManufacturer')[0]).strip() or None
                except OSError:
                    pass
                try:
                    model = str(winreg.QueryValueEx(k, 'SystemProductName')[0]).strip() or None
                except OSError:
                    pass
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as k:
                try:
                    cpu_model = str(winreg.QueryValueEx(k, 'ProcessorNameString')[0]).strip() or None
                except OSError:
                    pass
        except Exception:
            pass
        return mfg, model, cpu_model

    if sys_name == 'darwin':
        cpu_model = model = None
        try:
            out = subprocess.check_output(['sysctl', '-n', 'hw.model'], text=True, timeout=1.5).strip()
            model = out or None
        except Exception:
            pass
        try:
            out = subprocess.check_output(['sysctl', '-n', 'machdep.cpu.brand_string'], text=True, timeout=1.5).strip()
            cpu_model = out or None
        except Exception:
            pass
        return 'Apple', model, cpu_model

    return None, None, None


def _probe_gpus() -> list[dict[str, Any]]:
    sys_name = _platform.system().lower()
    gpus: list[dict[str, Any]] = []

    # NVIDIA via nvidia-smi (Linux / Windows)
    if shutil.which('nvidia-smi'):
        try:
            out = subprocess.check_output(
                ['nvidia-smi', '--query-gpu=name,memory.total', '--format=csv,noheader,nounits'],
                text=True, timeout=1.5, stderr=subprocess.DEVNULL,
            )
            for line in out.splitlines():
                parts = [p.strip() for p in line.split(',')]
                if len(parts) >= 2:
                    vram = int(float(parts[1])) if parts[1].replace('.', '', 1).isdigit() else None
                    gpus.append(_classify_gpu(parts[0], vram))
            if gpus:
                return gpus
        except Exception:
            pass

    if sys_name == 'linux':
        # AMD sysfs VRAM check
        try:
            for card in sorted(Path('/sys/class/drm').glob('card[0-9]*/device')):
                vram_file = card / 'mem_info_vram_total'
                vendor_file = card / 'vendor'
                if not vendor_file.exists():
                    continue
                vendor_hex = vendor_file.read_text().strip().lower()
                vram_mb = None
                if vram_file.exists():
                    try:
                        vram_mb = int(vram_file.read_text().strip()) // (1024 * 1024)
                    except (OSError, ValueError):
                        pass
                if vendor_hex == '0x1002':
                    name = 'AMD Radeon GPU'
                    try:
                        product = (card / 'product_name').read_text().strip()
                        if product:
                            name = product
                    except OSError:
                        pass
                    gpus.append(_classify_gpu(name, vram_mb))
                elif vendor_hex == '0x8086':
                    gpus.append(_classify_gpu('Intel Integrated Graphics', vram_mb))
        except Exception:
            pass
        return gpus

    if sys_name == 'windows':
        # Fast registry scan under Display class (avoids slow PowerShell/WMI spawns)
        try:
            import winreg  # type: ignore[import-not-found]
            base = r'SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}'
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base) as root:
                for i in range(16):
                    try:
                        subname = winreg.EnumKey(root, i)
                    except OSError:
                        break
                    if not subname.isdigit():
                        continue
                    try:
                        with winreg.OpenKey(root, subname) as sub:
                            desc = str(winreg.QueryValueEx(sub, 'DriverDesc')[0]).strip()
                            vram_mb = None
                            for val_name in ('HardwareInformation.qwMemorySize', 'HardwareInformation.MemorySize'):
                                try:
                                    raw_v = winreg.QueryValueEx(sub, val_name)[0]
                                    if isinstance(raw_v, int) and raw_v > 0:
                                        vram_mb = raw_v // (1024 * 1024)
                                        break
                                    if isinstance(raw_v, (bytes, bytearray)) and len(raw_v) in (4, 8):
                                        vram_mb = int.from_bytes(raw_v, 'little') // (1024 * 1024)
                                        break
                                except OSError:
                                    continue
                            if desc:
                                gpus.append(_classify_gpu(desc, vram_mb))
                    except OSError:
                        continue
        except Exception:
            pass
        return gpus

    if sys_name == 'darwin' and _platform.machine().lower() in ('arm64', 'aarch64'):
        gpus.append(_classify_gpu('Apple Silicon Unified GPU', None))

    return gpus


def _classify_tier(ram_total_mb: int | None, gpus: list[dict[str, Any]]) -> str:
    discrete_vram = max((int(g.get('vram_mb') or 0) for g in gpus if g.get('discrete')), default=0)
    has_apple_unified = any(g.get('vendor') == 'apple' and g.get('discrete') for g in gpus)
    ram_gb = (ram_total_mb or 0) / 1024.0
    if discrete_vram >= 12000 or (has_apple_unified and ram_gb >= 24):
        return 'gpu-workstation'
    if discrete_vram >= 4000 or (has_apple_unified and ram_gb >= 12):
        return 'gpu-node'
    if ram_gb >= 24:
        return 'cpu-workstation'
    if ram_gb >= 8:
        return 'potato-node'
    return 'edge-potato'


def probe_hardware() -> dict[str, Any]:
    """Return a cross-platform hardware fingerprint for this host."""
    mfg, model, cpu_model = _probe_host_dmi()
    cpu_cores = os.cpu_count() or 1
    cpu_threads = cpu_cores
    cpu_load_pct = None
    ram_total_mb = ram_free_mb = swap_total_mb = swap_used_mb = None

    try:
        import psutil  # type: ignore
        cpu_cores = psutil.cpu_count(logical=False) or cpu_cores
        cpu_threads = psutil.cpu_count(logical=True) or cpu_threads
        cpu_load_pct = round(float(psutil.cpu_percent(interval=0.05)), 1)
        vm = psutil.virtual_memory()
        ram_total_mb = int(vm.total // (1024 * 1024))
        ram_free_mb = int(vm.available // (1024 * 1024))
        sw = psutil.swap_memory()
        swap_total_mb = int(sw.total // (1024 * 1024))
        swap_used_mb = int(sw.used // (1024 * 1024))
    except Exception:
        pass

    disk_total_gb = disk_free_gb = None
    try:
        root_dir = os.environ.get('SWARM_ROOT') or os.getcwd()
        du = shutil.disk_usage(root_dir)
        disk_total_gb = round(du.total / (1024 ** 3), 1)
        disk_free_gb = round(du.free / (1024 ** 3), 1)
    except OSError:
        pass

    gpus = _probe_gpus()
    discrete_gpus = [g for g in gpus if g.get('discrete')]
    primary_backend = discrete_gpus[0]['backend'] if discrete_gpus else 'cpu'
    tier = _classify_tier(ram_total_mb, gpus)

    return {
        'hostname': socket.gethostname() or _platform.node() or 'unknown',
        'os': _platform.system().lower(),
        'os_release': _platform.release(),
        'arch': _platform.machine().lower(),
        'manufacturer': mfg,
        'model': model,
        'cpu_model': cpu_model or _platform.processor() or 'unknown',
        'cpu_cores': int(cpu_cores),
        'cpu_threads': int(cpu_threads),
        'cpu_load_pct': cpu_load_pct,
        'ram_total_mb': ram_total_mb,
        'ram_free_mb': ram_free_mb,
        'swap_total_mb': swap_total_mb,
        'swap_used_mb': swap_used_mb,
        'disk_total_gb': disk_total_gb,
        'disk_free_gb': disk_free_gb,
        'gpus': gpus,
        'has_discrete_gpu': bool(discrete_gpus),
        'primary_backend': primary_backend,
        'tier': tier,
    }


def _model_fit(size_gb: float, hardware: dict[str, Any]) -> str:
    """Classify whether a model fits comfortably on this host."""
    gpus = hardware.get('gpus') or []
    discrete_vram_gb = max(((g.get('vram_mb') or 0) / 1024.0 for g in gpus if g.get('discrete')), default=0.0)
    ram_total_gb = (hardware.get('ram_total_mb') or 0) / 1024.0

    if discrete_vram_gb >= 4.0:
        if size_gb <= discrete_vram_gb * 0.80:
            return 'fast'
        if size_gb <= max(discrete_vram_gb * 1.05, ram_total_gb * 0.60):
            return 'tight'
        return 'too-large'

    # CPU-only / iGPU potato node
    if ram_total_gb <= 0:
        return 'tight'
    if size_gb <= min(6.0, ram_total_gb * 0.30):
        return 'fast'
    if size_gb <= ram_total_gb * 0.65:
        return 'tight'
    return 'too-large'


def probe_runtimes(hardware: dict[str, Any] | None = None, *, timeout: float = 1.5) -> dict[str, Any]:
    """Probe local Ollama and llama-server endpoints for available models."""
    hw = hardware or probe_hardware()
    models: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    ollama_url = os.environ.get('OLLAMA_HOST', 'http://127.0.0.1:11434').rstrip('/')
    if not ollama_url.startswith(('http://', 'https://')):
        ollama_url = 'http://' + ollama_url

    ollama_online = False
    loaded_names: set[str] = set()

    try:
        import requests
    except ImportError:
        return {'ollama': {'online': False, 'url': ollama_url}, 'llama_servers': [], 'models': []}

    # 1. Ollama /api/ps (currently resident) and /api/tags (installed)
    try:
        r_ps = requests.get(f'{ollama_url}/api/ps', timeout=timeout)
        if r_ps.ok:
            for item in (r_ps.json() or {}).get('models', []):
                if isinstance(item, dict) and item.get('name'):
                    loaded_names.add(str(item['name']))
    except Exception:
        pass

    try:
        r_tags = requests.get(f'{ollama_url}/api/tags', timeout=timeout)
        if r_tags.ok:
            ollama_online = True
            for item in (r_tags.json() or {}).get('models', []):
                if not isinstance(item, dict) or not item.get('name'):
                    continue
                name = str(item['name'])
                size_gb = round(float(item.get('size') or 0) / (1024 ** 3), 2)
                details = item.get('details') if isinstance(item.get('details'), dict) else {}
                key = ('ollama', name.lower())
                if key in seen:
                    continue
                seen.add(key)
                models.append({
                    'name': name,
                    'provider': 'ollama',
                    'endpoint': ollama_url,
                    'size_gb': size_gb,
                    'family': details.get('family') or '',
                    'parameter_size': details.get('parameter_size') or '',
                    'quantization': details.get('quantization_level') or '',
                    'loaded': name in loaded_names,
                    'embed': _is_embed_model(name),
                    'fit': _model_fit(size_gb, hw),
                })
    except Exception:
        pass

    # 2. Local llama-server / OpenAI-compatible endpoints (e.g., :8080 on AMD rig)
    llama_servers: list[dict[str, Any]] = []
    candidate_endpoints: set[str] = {'http://127.0.0.1:8080'}
    try:
        from core.seven_llm import registry
        for entry in registry.list_models():
            if entry.endpoint and entry.endpoint.startswith(('http://127.0.0.1', 'http://localhost')):
                candidate_endpoints.add(entry.endpoint.rstrip('/'))
    except Exception:
        pass

    for ep in sorted(candidate_endpoints):
        try:
            r = requests.get(f'{ep}/v1/models', timeout=min(timeout, 0.8))
            if not r.ok:
                continue
            ep_models: list[str] = []
            for item in (r.json() or {}).get('data', []):
                if not isinstance(item, dict) or not item.get('id'):
                    continue
                mid = str(item['id'])
                ep_models.append(mid)
                key = ('llamacpp', mid.lower())
                if key not in seen:
                    seen.add(key)
                    models.append({
                        'name': mid,
                        'provider': 'llamacpp',
                        'endpoint': ep,
                        'size_gb': 0.0,
                        'family': '',
                        'parameter_size': '',
                        'quantization': '',
                        'loaded': True,
                        'embed': _is_embed_model(mid),
                        'fit': 'fast',
                    })
            llama_servers.append({'endpoint': ep, 'online': True, 'models': ep_models})
        except Exception:
            pass

    return {
        'ollama': {'online': ollama_online, 'url': ollama_url, 'loaded': sorted(loaded_names)},
        'llama_servers': llama_servers,
        'models': models,
    }


def _score_apex(m: dict[str, Any], has_gpu: bool) -> tuple:
    name = m['name'].lower()
    size = float(m.get('size_gb') or 0)
    fit = m.get('fit', 'tight')
    is_llama8080 = m.get('provider') == 'llamacpp' and str(m.get('endpoint', '')).endswith(':8080')
    if is_llama8080:
        return (0, 0, size, name)
    fit_rank = {'fast': 0, 'tight': 2, 'too-large': 5}.get(fit, 3)
    # Prefer strong instruction/coding models that stay responsive on this hardware
    family_bonus = (
        0 if 'qwen2.5' in name else
        1 if 'gemma3' in name else
        2 if 'mistral' in name else
        3 if 'gpt-oss' in name else
        4 if 'qwen' in name else
        5 if 'llama' in name else 6
    )
    if has_gpu:
        # On GPU, prefer larger fast-fit models
        return (1, fit_rank, -size if fit == 'fast' else size, family_bonus, name)
    # On CPU-only potato, sweet spot is 2.5–6 GB (responsive + capable)
    sweet_dist = abs(size - 4.0) if size > 0 else 4.0
    return (1, fit_rank, family_bonus, sweet_dist, name)


def _score_fred(m: dict[str, Any], ram_gb: float) -> tuple:
    name = m['name'].lower()
    size = float(m.get('size_gb') or 0)
    fit = m.get('fit', 'tight')
    # Fred is the deep thinker in RAM: prefer the strongest model that fits (not too-large)
    if name == 'fred-cpu:24b':
        return (0, 0, -size, name)
    # Cap Fred at ~62% of total RAM so OS + HB stay healthy
    fits_ram = (size == 0) or (ram_gb > 0 and size <= ram_gb * 0.62)
    fit_rank = 0 if (fits_ram and fit in ('fast', 'tight')) else 3
    # Prefer larger reasoning/general models within RAM cap
    return (1, fit_rank, -size, name)


def _score_hb(m: dict[str, Any]) -> tuple:
    name = m['name'].lower()
    size = float(m.get('size_gb') or 0)
    fit = m.get('fit', 'tight')
    fit_rank = {'fast': 0, 'tight': 2, 'too-large': 5}.get(fit, 3)
    # HB coordinator / homework wants the fastest small chat model (1–3.5 GB)
    small_pref = (
        0 if 'llama3.2' in name else
        1 if 'homework' in name else
        2 if re.match(r'^qwen(:|$)', name) else
        3 if 'gemma3' in name else
        4 if 'qwen2.5' in name else 5
    )
    return (fit_rank, small_pref, size if size > 0 else 99.0, name)


def recommend_role_models(hardware: dict[str, Any], runtimes: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Recommend local models for APEX, FRED, and HB based on probed hardware & models."""
    chat_models = [m for m in (runtimes.get('models') or []) if not m.get('embed')]
    has_gpu = bool(hardware.get('has_discrete_gpu'))
    ram_gb = (hardware.get('ram_total_mb') or 0) / 1024.0

    def _pack(m: dict[str, Any] | None, reason: str) -> dict[str, Any]:
        if not m:
            return {'model': None, 'provider': None, 'size_gb': None, 'fit': None, 'reason': reason}
        return {
            'model': m['name'],
            'provider': m.get('provider'),
            'size_gb': m.get('size_gb'),
            'fit': m.get('fit'),
            'reason': reason,
        }

    if not chat_models:
        msg = 'No local chat models detected (start Ollama or llama-server)'
        return {
            'apex': _pack(None, msg),
            'fred': _pack(None, msg),
            'hb': _pack(None, msg),
        }

    apex_pick = min(chat_models, key=lambda m: _score_apex(m, has_gpu))
    fred_pick = min(chat_models, key=lambda m: _score_fred(m, ram_gb))
    hb_pick = min(chat_models, key=_score_hb)

    apex_reason = (
        f"Resident GPU/llama-server model on {hardware.get('primary_backend')}"
        if apex_pick.get('provider') == 'llamacpp'
        else f"Best responsive {apex_pick.get('fit')}-fit interactive model for {hardware.get('tier')} ({ram_gb:.0f} GB RAM)"
    )
    fred_reason = f"Strongest deep-review model fitting in {ram_gb:.0f} GB RAM ({fred_pick.get('size_gb')} GB, {fred_pick.get('fit')})"
    hb_reason = f"Fastest lightweight coordinator/homework model ({hb_pick.get('size_gb')} GB, {hb_pick.get('fit')})"

    return {
        'apex': _pack(apex_pick, apex_reason),
        'fred': _pack(fred_pick, fred_reason),
        'hb': _pack(hb_pick, hb_reason),
    }


def build_shareable_manifest(
    hardware: dict[str, Any],
    runtimes: dict[str, Any],
    enrollment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the shareable capability manifest advertised to peer potato nodes."""
    enr = enrollment or {}
    share_cfg = enr.get('share') if isinstance(enr.get('share'), dict) else {}
    allowed_names = share_cfg.get('shared_models')
    allowed_set = {str(n).lower() for n in allowed_names} if isinstance(allowed_names, list) and allowed_names else None

    shared_models = []
    for m in (runtimes.get('models') or []):
        if allowed_set is not None and m['name'].lower() not in allowed_set:
            continue
        shared_models.append({
            'name': m['name'],
            'provider': m.get('provider'),
            'size_gb': m.get('size_gb'),
            'fit': m.get('fit'),
            'embed': bool(m.get('embed')),
            'loaded': bool(m.get('loaded')),
        })

    role_models = enr.get('models') if isinstance(enr.get('models'), dict) else {}
    return {
        'endpoint_url': enr.get('endpoint_url') or '',
        'role': enr.get('role') or 'worker',
        'tier': hardware.get('tier'),
        'primary_backend': hardware.get('primary_backend'),
        'accept_remote_jobs': bool(share_cfg.get('accept_remote_jobs', True)),
        'max_concurrent_jobs': int(share_cfg.get('max_concurrent_jobs', 1 if not hardware.get('has_discrete_gpu') else 2)),
        'ram_reserve_mb': int(share_cfg.get('ram_reserve_mb', 4096)),
        'role_models': {
            'apex': role_models.get('apex'),
            'fred': role_models.get('fred'),
            'hb': role_models.get('hb'),
        },
        'shared_models': shared_models,
    }


def collect_system_profile(*, force: bool = False) -> dict[str, Any]:
    """Return full cached system profile (hardware + runtimes + recommended models)."""
    now = time.time()
    if not force and _CACHE['profile'] is not None and (now - _CACHE['ts']) < _CACHE_TTL_S:
        return dict(_CACHE['profile'])

    hw = probe_hardware()
    rt = probe_runtimes(hw)
    rec = recommend_role_models(hw, rt)
    profile = {
        'ts': int(now),
        'hardware': hw,
        'runtimes': rt,
        'recommended_models': rec,
    }
    _CACHE['ts'] = now
    _CACHE['profile'] = profile
    return dict(profile)
