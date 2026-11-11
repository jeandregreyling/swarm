"""Per-turn HB model selection. APEX stays the actor; only a local backend changes."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from pathlib import Path
import re
from urllib.parse import urlsplit

import requests

from core.routing import _classify_category
from core.seven_llm import registry


@dataclass(frozen=True)
class LocalRoute:
    model: str
    category: str
    context_tokens: int
    reason: str

    def as_dict(self):
        return asdict(self)


_CURRENT = ContextVar('apex_local_model_route', default=None)
_PROGRESS = ContextVar('apex_local_model_progress', default=None)


def current_route():
    return _CURRENT.get()


def active_model():
    from core.chat_continuity import APEX_AGENT
    route = current_route()
    return route.model if route else APEX_AGENT['model']


@contextmanager
def use_model(route, progress=None):
    token = _CURRENT.set(route)
    progress_token = _PROGRESS.set(progress)
    try:
        yield route
    finally:
        _PROGRESS.reset(progress_token)
        _CURRENT.reset(token)


def report_model_progress(event):
    callback = _PROGRESS.get()
    if callback:
        callback(dict(event))


def _loopback(endpoint):
    try:
        parsed = urlsplit(endpoint)
        return (parsed.scheme in {'http','https'} and parsed.hostname in {'127.0.0.1','localhost','::1'}
                and parsed.username is None and parsed.password is None)
    except ValueError:
        return False


def select_local_model(message, entries, endpoint_models=None, *, exists=None, available_gb=None):
    """Pure policy over a supplied catalogue and verified endpoint identities.

    Managed GGUFs load through the existing resource-admitted llama.cpp pool.
    Endpoint aliases qualify only when that endpoint actually advertises them.
    No paid provider, download, or peer dispatch is part of this selection.
    """
    exists = exists or (lambda path: Path(path).is_file())
    endpoint_models = endpoint_models or {}
    text = str(message or '').lower()
    category = _classify_category(text)
    if re.search(r'\b(code|python|javascript|typescript|traceback|syntax|epipe|broken pipe)\b'
                 r'|\b[\w./-]+\.(py|js|ts|tsx|jsx|rs|go|java|cpp)\b', text):
        category = 'coder'
    elif re.search(r'\b(test|check|verify|tools?|permissions?|audit)\b', text):
        category = 'auditor'
    elif re.search(r'\b(memory|memories|recall|remember)\b', text):
        category = 'memory'
    elif re.search(r'\b(reconnect|connect|install|deploy|restart)\b', text):
        category = 'orchestrator'
    light_chat = bool(re.fullmatch(
        r'(?:@apex\s+)?(?:hi|hello|hey|thanks|thank you|good morning|good evening)'
        r'(?:[ ,]+(?:apex|there|again))?[.!? ]*', text.strip()))
    complex_task = (len(str(message or '')) > 1500 or bool(re.search(
        r'\b(architecture|architect|reasoning|tradeoffs?|analyse|analyze|multi.step|design a system)\b',
        str(message or ''), re.I)))
    preferred = (('qwen2.5:14b-instruct', 'qwen2.5:7b-instruct', 'apex-direct:7b') if complex_task else
                 ('apex-direct:7b', 'qwen2.5-coder:7b', 'qwen2.5:14b-instruct') if category == 'coder' else
                 ('gemma-direct:3', 'gemma3:latest', 'llama-direct:3.2', 'llama3.2:latest') if light_chat else
                 ('qwen2.5:14b-instruct', 'qwen2.5:7b-instruct', 'apex-direct:7b'))
    candidates = []
    for entry in entries:
        if (entry.driver != 'llamacpp' or entry.role == 'embed' or int(entry.ctx) < 16384
                or entry.options.get('raw_completion') or not entry.path or not exists(entry.path)):
            continue
        if entry.endpoint:
            if not _loopback(entry.endpoint):
                continue
            expected = str(entry.options.get('api_model') or entry.name)
            if expected not in endpoint_models.get(entry.endpoint.rstrip('/'), set()):
                continue
        # The pool performs authoritative admission when loading. This prefilter
        # avoids choosing a known oversized model when a smaller local one fits.
        if available_gb is not None and float(entry.ram_gb or 0) + 2 > available_gb:
            continue
        preferred_rank = preferred.index(entry.name) if entry.name in preferred else len(preferred)
        role_rank = 0 if entry.role == ('coder' if category == 'coder' else 'general') else 1
        candidates.append(((preferred_rank, role_rank, float(entry.ram_gb), entry.name), entry))
    if not candidates:
        raise RuntimeError('No eligible local chat model is available in the HB harness; no online agent was invoked')
    entry = min(candidates, key=lambda item: item[0])[1]
    reason = ('complex task' if complex_task else category) + '; local catalogue and resource policy'
    return LocalRoute(entry.name, category, int(entry.ctx), reason)


def choose_local_model(message):
    entries = registry.list_models()
    identities = {}
    for endpoint in {entry.endpoint.rstrip('/') for entry in entries
                     if entry.driver == 'llamacpp' and entry.endpoint and _loopback(entry.endpoint)}:
        identities[endpoint] = set()
        try:
            response = requests.get(endpoint + '/v1/models', timeout=1)
            response.raise_for_status()
            for item in response.json().get('data', []):
                if isinstance(item, dict):
                    if isinstance(item.get('id'), str):
                        identities[endpoint].add(item['id'])
                    identities[endpoint].update(alias for alias in item.get('aliases', []) if isinstance(alias, str))
        except (requests.RequestException, ValueError, TypeError, AttributeError):
            pass
    available = None
    try:
        available = next(int(line.split()[1]) / 1024**2 for line in Path('/proc/meminfo').read_text().splitlines()
                         if line.startswith('MemAvailable:'))
    except (OSError, ValueError, StopIteration):
        pass
    return select_local_model(message, entries, identities, available_gb=available)


def assigned_local_model(name,*,available_gb=None):
    """Trusted HB repair invitations can use the installed CPU reviewer as APEX."""
    if name!='fred-cpu:24b':raise PermissionError('Only the fixed existing CPU24B local escalation is allowed')
    entry=registry.get(name)
    if not entry or entry.driver!='llamacpp' or entry.endpoint or entry.options.get('ngl')!=0 or not entry.path or not Path(entry.path).is_file() or entry.ctx<8192:
        raise RuntimeError('The assigned larger local backend is unavailable; no online fallback')
    from core.seven_llm import llama_server
    warm=any(row['model']==name for row in llama_server.resource_snapshot().get('residents',[]))
    available=available_gb if available_gb is not None else next(int(line.split()[1])/1024**2 for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:'))
    if available<(0 if warm else entry.ram_gb)+8:raise RuntimeError('Insufficient physical RAM for assigned local24B plus8GiB headroom')
    return LocalRoute(name,'local-repair',int(entry.ctx),'HB assigned larger local repair; no online delegation')
