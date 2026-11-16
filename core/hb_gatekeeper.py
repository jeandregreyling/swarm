"""Model gatekeeper (owner 14 Nov 2026): the GPU model has priority on the card; a smaller model may run beside it only when it
fits and does not interfere. Two co-loaded models crashed the card twice in one week: the second one was squeezed onto a busy card.

decide() is the whole rule, in plain Python:
  - a CPU model stays on the CPU;
  - an empty card: load as registered (today's behaviour, including models that spread over GPU and RAM);
  - a busy card: the new model joins it only if all of it fits in the free VRAM with MARGIN_GB to spare;
    otherwise it runs in RAM (CPU) when RAM allows, and is refused when neither fits.
The loader (core/seven_llm/llama_server.ensure) asks before every load. Nothing here loads, stops or kills anything."""
import glob

MARGIN_GB = 1.5        # free VRAM that must remain after the newcomer is loaded
BUSY_GB = 2.0          # a card with more than this in use already carries a model
RAM_RESERVE_GB = 4.0   # host RAM that must remain free


def vram():
    """(total_gb, used_gb) of the biggest card from sysfs, or (None, None) when it cannot be read."""
    best = (None, None)
    for path in glob.glob('/sys/class/drm/card*/device/mem_info_vram_total'):
        try:
            total = int(open(path).read()) / 1024 ** 3
            used = int(open(path.replace('_total', '_used')).read()) / 1024 ** 3
        except (OSError, ValueError):
            continue
        if best[0] is None or total > best[0]:
            best = (total, used)
    return best


def decide(model_gb, uses_gpu, vram_total_gb, vram_used_gb, ram_available_gb):
    """{'placement': 'gpu' | 'cpu' | 'refuse', 'why': plain words}."""
    model_gb = float(model_gb or 4.0)
    if not uses_gpu:
        return {'placement': 'cpu', 'why': 'registered as a CPU model'}
    if vram_total_gb is None or vram_used_gb is None:
        return {'placement': 'gpu', 'why': 'the card could not be read; loaded as registered'}
    free = vram_total_gb - vram_used_gb
    if vram_used_gb <= BUSY_GB:
        return {'placement': 'gpu', 'why': f'the card is free ({free:.1f} GB)'}
    if model_gb + MARGIN_GB <= free:
        return {'placement': 'gpu', 'why': f'fits beside the GPU model: needs {model_gb:.1f} GB, {free:.1f} GB free'}
    if model_gb + RAM_RESERVE_GB <= float(ram_available_gb or 0.0):
        return {'placement': 'cpu', 'why': f'the card is busy ({vram_used_gb:.1f} of {vram_total_gb:.1f} GB used) and {model_gb:.1f} GB does not fit '
                                           f'in the {free:.1f} GB free, so it runs in RAM and leaves the card to the GPU model'}
    return {'placement': 'refuse', 'why': f'the card is busy ({free:.1f} GB free) and RAM has only {float(ram_available_gb or 0.0):.1f} GB available '
                                          f'for a {model_gb:.1f} GB model; it waits instead of crashing the card'}
