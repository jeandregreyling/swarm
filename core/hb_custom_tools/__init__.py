"""Guarded drop-in plugin loader so APEX can propose and author new tools in 1 file + 1 test.

Contract for any approved plugin placed in `core/hb_custom_tools/custom_<name>.py`:
  TOOL_SPEC = {
      'name': 'custom_<name>',          # must match ^custom_[a-z][a-z0-9_]{1,40}$
      'summary': 'One-line purpose',
      'arguments': {'arg': 'what it takes'},
  }
  def run(args: dict) -> dict:
      ...
Every plugin enters the repo only through HB's proposal/test check + JD's Approve button.
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

PLUGINS_DIR = Path(__file__).resolve().parent
NAME_RE = re.compile(r'^custom_[a-z][a-z0-9_]{1,40}$')


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location(f'hb_custom_plugin_{path.stem}', str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Could not load custom tool module: {path.name}')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def list_tools(directory: Path | None = None) -> list[dict]:
    """Discover all valid approved custom_* tool plugins."""
    root = Path(directory or PLUGINS_DIR)
    if not root.is_dir():
        return []
    found = []
    for path in sorted(root.glob('custom_*.py')):
        if not path.is_file() or path.is_symlink():
            continue
        try:
            mod = _load_module(path)
            meta = getattr(mod, 'TOOL_SPEC', None)
            fn = getattr(mod, 'run', None)
            if not isinstance(meta, dict) or not callable(fn):
                continue
            name = str(meta.get('name') or '').strip()
            if not NAME_RE.fullmatch(name):
                continue
            found.append({
                'name': name,
                'file': path.name,
                'summary': str(meta.get('summary') or '')[:240],
                'arguments': meta.get('arguments') if isinstance(meta.get('arguments'), dict) else {},
            })
        except Exception:
            continue
    return found


def invoke(name: str, args: dict | None = None, *, directory: Path | None = None) -> dict:
    """Execute one approved custom_* tool plugin by name."""
    if not isinstance(name, str) or not NAME_RE.fullmatch(name.strip()):
        raise ValueError('Custom tool name must match custom_<lowercase_name>')
    name = name.strip()
    args = {} if args is None else args
    if not isinstance(args, dict):
        raise ValueError('Custom tool arguments must be a JSON object')
    root = Path(directory or PLUGINS_DIR)
    for path in sorted(root.glob('custom_*.py')):
        if not path.is_file() or path.is_symlink():
            continue
        mod = _load_module(path)
        meta = getattr(mod, 'TOOL_SPEC', None)
        fn = getattr(mod, 'run', None)
        if isinstance(meta, dict) and meta.get('name') == name and callable(fn):
            result = fn(dict(args))
            return result if isinstance(result, dict) else {'ok': True, 'result': result}
    raise ValueError(f'Unknown custom tool {name!r}. Call hb_custom_tool list to see approved plugins, or propose one via studio_proposal.')
