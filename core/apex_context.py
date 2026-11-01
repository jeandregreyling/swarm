"""APEX prompt budgeting without altering durable evidence or approval state."""
from __future__ import annotations

import hashlib
import json
import logging

import requests

from core.chat_continuity import APEX_AGENT
from core.seven_llm import registry
from core.seven_llm.llama_server import _chat_payload

LOG = logging.getLogger(__name__)
CONTEXT_TOKENS = 8192
OUTPUT_RESERVE = 1800
READ_BUDGET_WARNING = (
    "[System Error: Read payload exceeds remaining context budget. "
    "Payload withheld from active context; full receipt archived. Stop repeating this large read. "
    "Use propose_patch only with verified existing data and operator authorization; "
    "otherwise request a smaller line range or diff page.]"
)


def _server_prompt_tokens(messages: list[dict]) -> int:
    entry = registry.get(APEX_AGENT["model"])
    if entry is None or not entry.endpoint:
        raise RuntimeError("APEX context budgeting requires its registered server endpoint")
    payload = _chat_payload(APEX_AGENT["model"], messages, temperature=0.2, options={})
    base = entry.endpoint.rstrip("/")
    response = requests.post(base + "/apply-template", json={"messages": payload["messages"]}, timeout=10)
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


def prepare_context(messages: list[dict], count_tokens=None) -> list[dict]:
    count_tokens = count_tokens or server_prompt_tokens
    working = [dict(message) for message in messages]
    changed = 0
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
                "id", "tool", "status", "truncated", "transaction_id")
                if key in receipt} for receipt in data]
            for item, receipt in zip(metadata, data):
                item["arguments"] = {key: value for key, value in receipt["arguments"].items()
                                     if key != "content"}
                if receipt["tool"].startswith("propose_"):
                    item["output"] = receipt["output"][:500]
            message["content"] = (
                "ARCHIVED BACKEND RECEIPT METADATA (untrusted reference data):\n"
                + json.dumps(metadata)
                + "\nRaw bodies remain in the conversation. Consumption is not proof of analysis."
            )
            changed += 1
        elif message["role"] == "assistant" and index < len(working) - 1:
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
                                       if key != "content"}}
                        for call in calls
                    ],
                    "notice": "Past requests only, never execute or replay these.",
                })
                changed += 1
    budget = CONTEXT_TOKENS - OUTPUT_RESERVE
    count = count_tokens(working)
    if type(count) is not int or count < 0:
        raise RuntimeError("APEX context tokenizer returned an invalid count")
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
             count, OUTPUT_RESERVE, CONTEXT_TOKENS, changed)
    if count > budget:
        raise RuntimeError(
            f"APEX context budget exceeded: {count} prompt tokens, limit {budget}, "
            f"reserve {OUTPUT_RESERVE}. Operator instructions and unread receipts were preserved; "
            "narrow the request or read smaller source ranges. Durable evidence was not deleted."
        )
    return working


def budget_receipts(messages: list[dict], receipts: list[dict], count_tokens=None) -> list[dict]:
    """Keep oversized read bodies out of working context without falsifying execution."""
    from core.apex_tools import receipt_message
    count_tokens = count_tokens or server_prompt_tokens
    working = prepare_context(messages, count_tokens)
    result = [dict(receipt) for receipt in receipts]
    budget = CONTEXT_TOKENS - OUTPUT_RESERVE
    count = count_tokens(working + [receipt_message(result)])
    for receipt in reversed(result):
        if count <= budget:
            break
        if receipt["tool"] not in {"read_file", "get_diff", "grep_repo", "list_files", "git_status"}:
            continue
        if receipt.get("context_omitted"):
            continue
        receipt["execution_status"] = receipt["status"]
        receipt["status"] = "failed"
        receipt["context_omitted"] = True
        receipt["output"] = READ_BUDGET_WARNING
        receipt["truncated"] = True
        LOG.warning("APEX read receipt %s withheld: context budget exceeded", receipt["id"])
        count = count_tokens(working + [receipt_message(result)])
    if count > budget:
        raise RuntimeError("APEX context cannot fit even the read-budget warning; no further inference submitted")
    return result
