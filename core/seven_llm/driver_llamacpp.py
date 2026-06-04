"""core/llm/driver_llamacpp.py — in-process llama-cpp-python driver.

Keeps GGUF models resident in the Swarm process. Chosen when `driver` field in
registry entry is ``llamacpp``. Requires the optional ``llama-cpp-python``
package; if missing, the driver reports an import error on first use and is
skipped by the runtime (Ollama stays primary).
"""
from __future__ import annotations

import threading
import time
import os
import re
import subprocess
from typing import Any, Optional

from .driver_base import Driver
from . import registry as _reg
from .prompt_profiles import default_stops, get_profile


class LlamaCppDriver(Driver):
    name = "llamacpp"

    _instances: dict[str, Any] = {}
    _lock = threading.RLock()

    @staticmethod
    def _default_cli() -> str:
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        bundled = os.path.join(root, "agents", "seven", "llama.cpp", "build", "bin", "llama-cli")
        return os.environ.get("SEVEN_LLAMA_CLI") or bundled

    def _load(self, model: str):
        with self._lock:
            inst = self._instances.get(model)
            if inst is not None:
                return inst
            try:
                from llama_cpp import Llama  # type: ignore
            except ImportError as exc:
                raise RuntimeError("llama-cpp-python not installed") from exc
            meta = _reg.get(model)
            if not meta or not meta.path:
                raise RuntimeError(f"no GGUF path registered for model '{model}'")
            inst = Llama(model_path=meta.path, n_ctx=meta.ctx, verbose=False)
            self._instances[model] = inst
        return inst

    def _chat_cli(self, model, messages, *, temperature=None, options=None):
        meta = _reg.get(model)
        if not meta or not meta.path:
            raise RuntimeError(f"no GGUF path registered for model '{model}'")
        binary = str((meta.options or {}).get("cli") or self._default_cli())
        if not os.path.isfile(binary):
            raise RuntimeError(f"llama.cpp CLI not found: {binary}")
        opts = dict(meta.options or {})
        opts.update(options or {})
        profile = get_profile(model, explicit=str(opts.get("profile") or ""))
        prompt = profile.format_messages(messages)
        n_predict = int(opts.get("num_predict") or opts.get("n_predict") or 128)
        ctx = int(opts.get("ctx") or meta.ctx or 2048)
        timeout = int(opts.get("timeout") or os.environ.get("SEVEN_LLAMA_TIMEOUT", "180"))
        cmd = [
            binary,
            "-m", str(meta.path),
            "-p", prompt,
            "-n", str(n_predict),
            "--ctx-size", str(ctx),
            "--temp", str(0.7 if temperature is None else temperature),
            "--no-display-prompt",
            "--single-turn",
            "--simple-io",
            "--log-disable",
        ]
        stops = opts.get("stop") or default_stops(model, explicit=str(opts.get("profile") or ""))
        if isinstance(stops, str):
            stops = [stops]
        for stop in stops:
            if str(stop):
                cmd.extend(["--reverse-prompt", str(stop)])
        if "threads" in opts:
            cmd.extend(["--threads", str(int(opts["threads"]))])
        started = time.time()
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        elapsed = time.time() - started
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()[:500]
            raise RuntimeError(f"llama.cpp exited {proc.returncode}: {detail}")
        text = _extract_cli_answer(proc.stdout, prompt, profile=profile.name)
        if not text:
            text = _extract_cli_answer(proc.stderr, prompt, profile=profile.name)
        if not text:
            raise RuntimeError(f"llama.cpp returned empty output after {elapsed:.1f}s")
        return text, max(1, len(text.split()))

    def chat(self, model, messages, *, stream=False, temperature=None,
             options=None, keep_alive=None, on_token=None):
        opts = dict(options or {})
        mode = str(opts.pop("mode", "") or (_reg.get(model).options or {}).get("mode") or os.environ.get("SEVEN_LLAMA_MODE", "server")).lower()
        if mode == "server":
            from . import llama_server
            return llama_server.chat(model, messages, temperature=temperature, options=opts, on_token=on_token)
        try:
            inst = self._load(model)
        except RuntimeError as exc:
            if "llama-cpp-python not installed" not in str(exc):
                raise
            return self._chat_cli(model, messages, temperature=temperature, options=options)
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


def _messages_to_prompt(messages: list[dict]) -> str:
    return get_profile("generic").format_messages(messages)


def _extract_cli_answer(output: str, prompt: str = "", *, profile: str = "generic") -> str:
    text = str(output or "").replace("\r", "")
    text = re.sub(r"(?s).*available commands:.*?\n\n", "", text)
    if prompt and prompt in text:
        text = text.split(prompt, 1)[-1]
    if "Assistant:" in text:
        text = text.split("Assistant:", 1)[-1]
    text = get_profile(explicit=profile).trim_response(text)
    text = re.sub(r"\[ Prompt:.*?\]\s*", "", text, flags=re.DOTALL)
    text = text.replace("Exiting...", "")
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(">"):
            continue
        if stripped.startswith("Loading model") or stripped.startswith("build"):
            continue
        if stripped.startswith("model") or stripped.startswith("modalities"):
            continue
        if stripped.startswith("▄▄") or stripped.startswith("██") or stripped.startswith("▀▀"):
            continue
        if stripped.startswith("/exit") or stripped.startswith("/regen") or stripped.startswith("/clear"):
            continue
        lines.append(line)
    return "\n".join(lines).strip()
