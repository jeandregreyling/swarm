"""Prompt profiles for Seven-owned direct model drivers."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PromptProfile:
    name: str
    system_label: str = "System"
    user_label: str = "User"
    assistant_label: str = "Assistant"
    stops: tuple[str, ...] = ("\nUser:", "\nSystem:", "\nAssistant:")

    def format_messages(self, messages: list[dict]) -> str:
        parts: list[str] = []
        for msg in messages or []:
            role = str((msg or {}).get("role") or "user").strip().lower()
            content = str((msg or {}).get("content") or "").strip()
            if not content:
                continue
            if role == "system":
                parts.append(f"{self.system_label}: {content}")
            elif role == "assistant":
                parts.append(f"{self.assistant_label}: {content}")
            else:
                parts.append(f"{self.user_label}: {content}")
        parts.append(f"{self.assistant_label}:")
        return "\n".join(parts)

    def trim_response(self, text: str) -> str:
        out = str(text or "").replace("\r", "")
        for stop in self.stops:
            if stop and stop in out:
                out = out.split(stop, 1)[0]
        return out.strip()


GENERIC = PromptProfile("generic")
CHATML = PromptProfile(
    "chatml",
    system_label="<|im_start|>system",
    user_label="<|im_start|>user",
    assistant_label="<|im_start|>assistant",
    stops=("<|im_end|>", "<|im_start|>user", "<|im_start|>system", "\nUser:"),
)
GEMMA = PromptProfile(
    "gemma",
    system_label="<start_of_turn>user",
    user_label="<start_of_turn>user",
    assistant_label="<start_of_turn>model",
    stops=("<end_of_turn>", "<start_of_turn>user"),
)
LLAMA3 = PromptProfile(
    "llama3",
    system_label="<|start_header_id|>system<|end_header_id|>",
    user_label="<|start_header_id|>user<|end_header_id|>",
    assistant_label="<|start_header_id|>assistant<|end_header_id|>",
    stops=("<|eot_id|>", "<|start_header_id|>", "<|end_header_id|>"),
)


def get_profile(model: str = "", *, explicit: str | None = None) -> PromptProfile:
    key = (explicit or model or "").strip().lower()
    if key in {"chatml", "qwen", "qwen2", "qwen2.5", "seven"}:
        return CHATML
    if key in {"gemma", "gemma3"} or "gemma" in key:
        return GEMMA
    if key in {"llama3", "llama3.2"} or "llama" in key:
        return LLAMA3
    if "qwen" in key or "seven" in key:
        return CHATML
    return GENERIC


def default_stops(model: str = "", *, explicit: str | None = None) -> list[str]:
    return list(get_profile(model, explicit=explicit).stops)
