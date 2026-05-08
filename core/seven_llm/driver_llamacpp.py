"""core/llm/driver_llamacpp.py — in-process llama-cpp-python driver.

Keeps GGUF models resident in the Swarm process. Chosen when `driver` field in
registry entry is ``llamacpp``. Requires the optional ``llama-cpp-python``
package; if missing, the driver reports an import error on first use and is
skipped by the runtime (Ollama stays primary).
"""
from __future__ import annotations

import threading
import time
from typing import Any, Optional

from .driver_base import Driver
from . import registry as _reg


class LlamaCppDriver(Driver):
    name = "llamacpp"

    _instances: dict[str, Any] = {}
    _lock = threading.RLock()

    def _load(self, model: str):
        with self._lock:
            inst = self._instances.get(model)
            if inst is not None:
                return inst
            try:
                from llama_cpp import Llama  # type: ignore
            except ImportError as exc:
                raise RuntimeError(
                    "llama-cpp-python not installed; run `pip install llama-cpp-python`"
                ) from exc
            meta = _reg.get(model)
            if not meta or not meta.path:
                raise RuntimeError(f"no GGUF path registered for model '{model}'")
            inst = Llama(model_path=meta.path, n_ctx=meta.ctx, verbose=False)
            self._instances[model] = inst
            return inst

    def chat(self, model, messages, *, stream=False, temperature=None,
             options=None, keep_alive=None):
        inst = self._load(model)
        kwargs: dict = {}
        if temperature is not None:
            kwargs["temperature"] = float(temperature)
        t0 = time.time()
        out = inst.create_chat_completion(messages=messages, stream=False, **kwargs)
        text = out["choices"][0]["message"]["content"]
        tokens = int(out.get("usage", {}).get("total_tokens", 0))
        _ = time.time() - t0
        return text, tokens

    def ps(self):
        return [{"model": m, "driver": "llamacpp"} for m in self._instances]

    def list_models(self):
        return [{"name": m.name, "path": m.path} for m in _reg.list_models() if m.driver == "llamacpp"]

    def unload(self, model):
        with self._lock:
            return self._instances.pop(model, None) is not None
