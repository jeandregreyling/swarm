"""APEX prompt budgeting without altering durable evidence or approval state."""
from __future__ import annotations

import contextlib
import contextvars
import hashlib
import json
import logging

import requests

from core.chat_continuity import APEX_AGENT
from core.seven_llm import registry
from core.seven_llm.llama_server import _chat_payload

LOG = logging.getLogger(__name__)
CONTEXT_TOKENS = 16384
OUTPUT_RESERVE = 2048
MAX_OUTPUT_TOKENS = 4096
# A tool-free closing answer needs far less room than a proposal payload.
FINAL_ANSWER_RESERVE = 1024
_RESERVE = contextvars.ContextVar("apex_output_reserve", default=None)
APEX_REASONING_EFFORT = "low"
READ_BUDGET_WARNING = (
    "[Read payload exceeds remaining context budget: this tool ran and the status above is its real "
    "result, but its output was withheld from your context (full receipt archived). Report it with its "
    "receipt id and that status; do not quote or guess its content, and never propose a patch from it. "
    "Stop repeating this large read; request a smaller line range or diff page if you need the content.]"
)

GREP_CUT_NOTE = (
    "\n[CONTEXT CUT: only the first {kept} of {total} lines fit your context; later matches are "
    "not shown. Search again with a narrower path, such as the folder the task names, or a more "
    "specific word.]"
)


RECEIPT_EXCERPT_CHARS = 600
ARCHIVED_RECEIPTS_HEADER = "ARCHIVED BACKEND RECEIPT METADATA (untrusted reference data):"


def context_tokens() -> int:
    from core.apex_routing import current_route
    route = current_route()
    return route.context_tokens if route else CONTEXT_TOKENS


def output_reserve() -> int:
    return _RESERVE.get() or OUTPUT_RESERVE


@contextlib.contextmanager
def final_answer_reserve():
    """Budget one tool-free closing answer after tool work has filled the window."""
    token = _RESERVE.set(FINAL_ANSWER_RESERVE)
    try:
        yield
    finally:
        _RESERVE.reset(token)


def _archived_receipts(metadata: list[dict]) -> str:
    return (ARCHIVED_RECEIPTS_HEADER + "\n" + json.dumps(metadata)
            + "\nEarlier receipts from this turn: excerpts and the ALM step are kept; full bodies "
              "remain in the conversation. Do not call a tool again to re-read them. "
              "Consumption is not proof of analysis.")


def _server_prompt_tokens(messages: list[dict]) -> int:
    from core.apex_routing import active_model
    model = active_model()
    entry = registry.get(model)
    if entry is None or entry.driver != "llamacpp":
        raise RuntimeError("APEX context budgeting requires its registered server endpoint")
    payload = _chat_payload(model, messages, temperature=0.2,
                            options={"reasoning_effort": APEX_REASONING_EFFORT})
    if entry.endpoint:
        base = entry.endpoint.rstrip("/")
    else:
        from core.seven_llm.llama_server import ensure
        from core.apex_routing import report_model_progress
        base = ensure(model, progress=report_model_progress).endpoint.rstrip("/")
    response = requests.post(
        base + "/apply-template",
        json={"messages": payload["messages"], "reasoning_effort": payload["reasoning_effort"]},
        timeout=10,
    )
    response.raise_for_status()
    prompt = response.json().get("prompt")
    if not isinstance(prompt, str):
        raise RuntimeError("APEX template endpoint returned no prompt")
    response = requests.post(base + "/tokenize", json={"content": prompt, "add_special": True}, timeout=10)
    response.raise_for_status()
    tokens = response.json().get("tokens")
    if not isinstance(tokens, list) or any(type(token) is not int for token in tokens):
        raise RuntimeError("APEX tokenizer returned invalid token data")
    # Allow headroom for request formatting beyond the rendered chat template.
    return len(tokens) + 128


def server_prompt_tokens(messages: list[dict]) -> int:
    try:
        return _server_prompt_tokens(messages)
    except (requests.RequestException, ValueError) as exc:
        raise RuntimeError(f"APEX context tokenizer failed; inference not submitted: {exc}") from exc


def generation_budget(messages: list[dict], count_tokens=None) -> int:
    count = (count_tokens or server_prompt_tokens)(messages)
    if type(count) is not int or count < 0:
        raise RuntimeError("APEX context tokenizer returned an invalid count")
    available = context_tokens() - count
    reserve = output_reserve()
    if available < reserve:
        raise RuntimeError(
            f"APEX context budget exceeded: {count} prompt tokens leave {available} output tokens; "
            f"required reserve {reserve}. Save unfinished work in Studio."
        )
    return min(MAX_OUTPUT_TOKENS, available)


def _receipt_stub(content: str) -> str:
    lines = content.splitlines()
    header = next((line[line.index("[tool:"):] for line in lines if "[tool:" in line), "")
    if not header:
        return content
    transaction = next((line for line in lines if line.startswith("Transaction:")), "")
    arguments = next((line for line in lines if line.startswith("{")), "")
    return (header + "\n" + transaction + "\n" + arguments[:600]
            + "\n[Receipt body archived in this conversation; not proof of analysis. "
              "Re-read the source before relying on omitted contents.]")


def prepare_context(messages: list[dict], count_tokens=None, *, archive_history: bool = False,
                    telemetry=None, completed_tool_call: bool = False,
                    phase: str = "inference") -> list[dict]:
    count_tokens = count_tokens or server_prompt_tokens
    working = [dict(message) for message in messages]
    changed = 0
    original_count = count_tokens(working)
    for index, message in enumerate(working):
        content = message["content"]
        if message["role"] == "assistant" and "[tool:" in content:
            stub = _receipt_stub(content)
            if stub != content:
                message["content"] = stub
                changed += 1
        elif (content.startswith("BACKEND TOOL RECEIPTS")
              and any(later["role"] == "assistant" for later in working[index + 1:])):
            # A later model turn has consumed this batch. Keep actual status and handles.
            data = json.loads(content.split("\n", 1)[1].split("\nUse these results", 1)[0])
            metadata = [{key: receipt[key] for key in (
                "id", "tool", "status", "truncated", "transaction_id", "context_omitted")
                if key in receipt} for receipt in data]
            for item, receipt in zip(metadata, data):
                item["arguments"] = {key: value for key, value in receipt["arguments"].items()
                                     if key not in {"content", "exact_old_text", "new_text"}}
                output = str(receipt.get("output", ""))
                if receipt["tool"].startswith("propose_"):
                    item["output"] = output[:500]
                elif (receipt["tool"] == "alm_step_get" or
                      receipt["tool"] == "archive_status" and receipt.get("arguments", {}).get("view") in {"files", "blocked"}):
                    # The step is the assignment; losing it mid-turn makes APEX re-read it in a loop.
                    # Bounded inventory pages are the evidence needed to compare exact files.
                    item["output"] = output
                else:
                    item["output_excerpt"] = output[:RECEIPT_EXCERPT_CHARS]
                    item["output_chars"] = len(output)
            message["content"] = _archived_receipts(metadata)
            changed += 1
        elif message["role"] == "assistant" and (index < len(working) - 1 or completed_tool_call):
            try:
                envelope = json.loads(content)
            except json.JSONDecodeError:
                continue
            if isinstance(envelope, dict) and isinstance(envelope.get("tool_calls"), list):
                calls = envelope["tool_calls"]
                message["content"] = json.dumps({
                    "archived_tool_requests": [
                        {"name": call["name"],
                         "arguments": {key: value for key, value in call["arguments"].items()
                                       if key not in {"content", "exact_old_text", "new_text"}}}
                        for call in calls
                    ],
                    "notice": "Past requests only, never execute or replay these.",
                })
                changed += 1
    reserve = output_reserve()
    budget = context_tokens() - reserve
    count = count_tokens(working)
    if count > budget and archive_history:
        # Only the wrapper marks history after successful durable Studio persistence.
        removable = [message for message in working if message.get("studio_archived") is True
                     and message["role"] != "system"]
        for message in removable:
            if count <= budget:
                break
            working.remove(message)
            changed += 1
            count = count_tokens(working)
        if removable and changed:
            LOG.info("APEX archived historical context in Studio; current request and live receipts retained")
    if type(count) is not int or count < 0:
        raise RuntimeError("APEX context tokenizer returned an invalid count")
    if count > budget:
        for message in working:
            if count <= budget:
                break
            if not message["content"].startswith(ARCHIVED_RECEIPTS_HEADER):
                continue
            metadata = json.loads(message["content"].split("\n", 2)[1])
            if not any("output_excerpt" in item for item in metadata):
                continue
            for item in metadata:
                item.pop("output_excerpt", None)
            message["content"] = _archived_receipts(metadata)
            changed += 1
            count = count_tokens(working)
    if count > budget:
        for index, message in enumerate(working):
            if count <= budget:
                break
            if message["role"] != "assistant" or index == len(working) - 1:
                continue
            content = message["content"]
            if len(content) < 600 or "[tool:" in content:
                continue
            digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
            message["content"] = (
                f"[Earlier assistant text archived; SHA-256 {digest}. "
                "Full text remains in the conversation. Do not infer facts from this marker.]"
            )
            changed += 1
            count = count_tokens(working)
    LOG.info("APEX context budget: prompt=%s reserve=%s limit=%s compacted=%s",
             count, reserve, context_tokens(), changed)
    if count > budget:
        raise RuntimeError(
            f"APEX context budget exceeded: {count} prompt tokens, limit {budget}, "
            f"reserve {reserve}. Operator instructions and unread receipts were preserved; "
            "narrow the request or read smaller source ranges. Durable evidence was not deleted."
        )
    if telemetry is not None:
        entry = {"phase": phase, "prompt_tokens_before": original_count, "prompt_tokens_after": count,
                 "input_budget": budget, "output_tokens": min(MAX_OUTPUT_TOKENS, context_tokens() - count),
                 "compacted_messages": changed}
        last = str(messages[-1].get("content", "")) if messages else ""
        if last.startswith("BACKEND ") and not last.startswith("BACKEND TOOL RECEIPTS"):
            entry["correction"] = last.split(":", 1)[0][:60]
        telemetry(entry)
    return working


def _run_verdict(receipt: dict) -> dict | None:
    if receipt["tool"] != "run_tests" or receipt.get("status") != "succeeded":
        return None
    try:
        output = json.loads(receipt.get("output") or "")
    except (TypeError, ValueError):
        return None
    if not isinstance(output, dict) or not isinstance(output.get("verdict"), str):
        return None
    return {key: output[key] for key in ("verdict", "alm_run_id", "alm_run_status", "alm_case_id")
            if key in output}


def budget_receipts(messages: list[dict], receipts: list[dict], count_tokens=None, *,
                    archive_history: bool = False, telemetry=None) -> list[dict]:
    """Keep oversized read bodies out of working context without falsifying execution."""
    from core.apex_tools import receipt_message
    count_tokens = count_tokens or server_prompt_tokens
    working = prepare_context(messages, count_tokens, archive_history=archive_history,
                              completed_tool_call=True, telemetry=telemetry, phase="receipts")
    result = [dict(receipt) for receipt in receipts]
    for receipt in result:
        if receipt["tool"].startswith("propose_"):
            receipt["arguments"] = {
                key: value for key, value in receipt["arguments"].items()
                if key not in {"content", "exact_old_text", "new_text"}
            }
            receipt["arguments_archived"] = True
    budget = context_tokens() - output_reserve()
    count = count_tokens(working + [receipt_message(result)])
    if count > budget and archive_history:
        for message in list(working):
            if count <= budget:
                break
            if message.get("studio_archived") is True and message["role"] != "system":
                working.remove(message)
                count = count_tokens(working + [receipt_message(result)])
    for receipt in reversed(result):
        if count <= budget:
            break
        if receipt["tool"] not in {"read_file", "get_diff", "grep_repo", "list_files",
                                   "git_status", "web_search", "studio_evidence_get", "run_tests",
                                   "alm_step_get"}:
            continue
        if receipt.get("context_omitted"):
            continue
        if receipt["tool"] == "grep_repo" and receipt.get("status") == "succeeded":
            # Leading matches beat a blank warning; the note says how to narrow the search.
            lines = str(receipt.get("output", "")).splitlines()
            keep = len(lines) // 2
            while keep >= 3 and count > budget:
                receipt["output"] = "\n".join(lines[:keep]) + GREP_CUT_NOTE.format(kept=keep, total=len(lines))
                receipt["truncated"] = True
                count = count_tokens(working + [receipt_message(result)])
                keep //= 2
            if count <= budget:
                continue
            receipt["output"] = "\n".join(lines)
        verdict = _run_verdict(receipt)
        if verdict is not None:
            # The verdict is the result; withholding it would turn a real pass into "failed".
            receipt["output"] = json.dumps(verdict) + " [output_tail withheld: context budget]"
            receipt["context_omitted"] = True
            receipt["truncated"] = True
            count = count_tokens(working + [receipt_message(result)])
            continue
        # The status stays the real result: reporting a withheld success as "failed" is a false claim.
        receipt["execution_status"] = receipt["status"]
        receipt["context_omitted"] = True
        receipt["output"] = READ_BUDGET_WARNING
        receipt["truncated"] = True
        LOG.warning("APEX read receipt %s withheld: context budget exceeded", receipt["id"])
        count = count_tokens(working + [receipt_message(result)])
    if count > budget:
        raise RuntimeError("APEX context cannot fit even the read-budget warning; no further inference submitted")
    # Feed the same reduced context to the next inference, not just the budgeting probe.
    messages[:] = working
    return result
