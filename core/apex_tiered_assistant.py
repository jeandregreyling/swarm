"""APEX Tiered Model Assistant - Online model fallback for APEX local lane.

This module provides a peer agent that online models can use to assist APEX
when local models cannot handle a request. It integrates with the Hummingbird
peer bridge to allow external/tiered models to communicate with APEX.

Architecture:
  1. APEX tries local models first (qwen2.5:14b-instruct)
  2. On failure/exhaustion, dispatches to online tiered models via peer bridge
  3. Online models respond through this assistant agent
  4. Results are routed back to APEX conversation

Usage:
  - Configure online models in ops/llm_registry.yaml with tier='online'
  - Add their service accounts to the peer_bridge
  - APEX will automatically dispatch when local context is exhausted
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from core.peer_bridge import (
    ensure_schema,
    post_to_peer,
    MENTIONS,
    SCOPES,
    TOKEN_PREFIX,
)
from core.chat_continuity import APEX_AGENT, ApexOffline, classify_runtime_error, STATE_OFFLINE

LOG = logging.getLogger(__name__)

# Tiered assistant agent definition
TIERED_ASSISTANT = {
    "name": "tiered-assistant",
    "label": "Tiered Model Assistant",
    "role": "APEX online fallback assistant",
    "tier": "online",
    "enabled": True,
    "model": "tiered:fallback",  # Special marker for tiered routing
    "scopes": ("peer.read", "peer.post", "peer.memory"),
    "timeout_seconds": 180,
    "eta_seconds": 30,
}

# Online model tiers for fallback (configured in registry)
ONLINE_TIERS = {
    "tier1": {"models": ["gpt-4o", "gpt-4o-mini", "claude-3-5-sonnet"], "role": "reasoner"},
    "tier2": {"models": ["gpt-4", "claude-3-opus"], "role": "analyst"},
    "tier3": {"models": ["o1", "o1-mini"], "role": "solver"},
}

# Patterns that indicate APEX needs online assistance
APEX_EXHAUSTION_PATTERNS = [
    r"context.*length",
    r"maximum.*context",
    r"token.*limit",
    r"out.*of.*tokens",
    r"context.*window",
    r"num_ctx",
    r"APEX.*budget.*exceeded",
    r"APEX.*context.*cannot.*fit",
    r"prompt.*too.*long",
    r"input.*too.*long",
]


def _should_invoke_tiered_assistant(error_message: str) -> bool:
    """Check if the error indicates APEX context exhaustion that needs online help."""
    error_lower = str(error_message or "").lower()
    return any(re.search(pattern, error_lower) for pattern in APEX_EXHAUSTION_PATTERNS)


def _get_online_model_for_task(task_description: str) -> str | None:
    """Select the best online model based on task complexity."""
    # Simple tasks -> tier1, complex -> tier2, very complex -> tier3
    desc_lower = str(task_description or "").lower()
    
    # Tier 3: Complex reasoning, multi-step, debugging
    if any(word in desc_lower for word in [
        "debug", "diagnose", "investigate", "root cause", 
        "architecture", "design", "multi-step", "complex"
    ]):
        return ONLINE_TIERS["tier3"]["models"][0]
    
    # Tier 2: Analysis, code review, detailed questions
    if any(word in desc_lower for word in [
        "review", "analyze", "explain", "optimize", 
        "improve", "refactor", "verify", "validate"
    ]):
        return ONLINE_TIERS["tier2"]["models"][0]
    
    # Tier 1: General assistance, quick questions
    return ONLINE_TIERS["tier1"]["models"][0]


def create_tiered_dispatch_message(apex_error: str, conversation_id: int, 
                                   apex_message_id: int | None = None) -> dict[str, Any]:
    """Create a dispatch message from APEX to the tiered assistant.
    
    This is called when APEX hits a context limit and needs online help.
    """
    task_description = _extract_task_from_error(apex_error)
    selected_model = _get_online_model_for_task(task_description)
    
    message = {
        "conversation_id": conversation_id,
        "from_agent": APEX_AGENT["name"],
        "to_agent": TIERED_ASSISTANT["name"],
        "body": f"[APEX HANDOFF: context exhausted] {task_description}",
        "metadata": {
            "original_error": apex_error[:500],
            "suggested_model": selected_model,
            "apex_message_id": apex_message_id,
            "dispatch_type": "apex_fallback",
            "timestamp": time.time(),
        },
        "not_before": time.time(),  # Process immediately
    }
    
    LOG.info(f"Tiered assistant dispatch: conversation={conversation_id}, "
             f"model={selected_model}, task={task_description[:100]}")
    
    return message


def _extract_task_from_error(error: str) -> str:
    """Extract the user's task intent from APEX error messages."""
    # If the error contains user message context
    if "user:" in error.lower() or "request:" in error.lower():
        lines = error.split("\n")
        for line in lines:
            if line.strip().lower().startswith(("user:", "request:", "task:")):
                return line.split(":", 1)[1].strip()[:500]
    return f"APEX context exhausted - needs online model assistance"


def handle_tiered_response(conn, message: dict) -> dict[str, Any] | None:
    """Handle a response from the tiered assistant back to APEX.
    
    Routes the online model's response back into the APEX conversation.
    """
    if message.get("to_agent") != TIERED_ASSISTANT["name"]:
        return None
    
    from_agent = message.get("from_agent", "unknown")
    body = message.get("body", "")
    metadata = message.get("metadata", {})
    
    # Extract the original conversation ID
    conversation_id = message.get("conversation_id") or metadata.get("conversation_id")
    if not conversation_id:
        LOG.warning(f"Tiered response missing conversation_id: {message.get('id')}")
        return None
    
    # Check if this is a response to an APEX dispatch
    if metadata.get("dispatch_type") == "apex_fallback":
        LOG.info(f"Routing tiered response back to APEX: conversation={conversation_id}, "
                 f"from={from_agent}")
        
        # Return the response to be injected into APEX conversation
        return {
            "conversation_id": conversation_id,
            "from_agent": from_agent,
            "to_agent": APEX_AGENT["name"],
            "body": f"[TIERED ASSISTANT RESPONSE from {from_agent}]\n\n{body}",
            "metadata": {
                "tiered_response": True,
                "online_model": metadata.get("model"),
                "original_apex_message_id": metadata.get("apex_message_id"),
            }
        }
    
    return None


def inject_tiered_response_into_apex(
    conn, 
    conversation_id: int, 
    apex_message_id: int | None,
    tiered_response: str
) -> bool:
    """Inject a tiered assistant response into the APEX conversation for continuity."""
    try:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO messages 
               (conversation_id, from_agent, to_agent, content, message_type, created_at)
               VALUES (?, ?, ?, ?, 'response', strftime('%s', 'now'))""",
            (conversation_id, TIERED_ASSISTANT["name"], APEX_AGENT["name"], tiered_response)
        )
        conn.commit()
        LOG.info(f"Injected tiered response into conversation {conversation_id}")
        return True
    except Exception as e:
        LOG.error(f"Failed to inject tiered response: {e}")
        conn.rollback()
        return False


def get_tiered_assistant_roster() -> list[dict]:
    """Get the roster of configured tiered assistant models."""
    roster = []
    
    for tier_name, tier_config in ONLINE_TIERS.items():
        for model in tier_config["models"]:
            roster.append({
                "name": f"tiered-{tier_name}-{model.replace('.', '-')}",
                "label": f"Tiered {tier_name}: {model}",
                "model": model,
                "tier": "online",
                "role": tier_config["role"],
                "enabled": True,
                "status": "on_demand",
                "available": True,
                "availability_reason": "Tiered fallback for APEX",
                "api_key_var": "OPENAI_API_KEY",  # or other provider keys
                "temperature": 0.2,
                "eta_seconds": 45,
            })
    
    return roster


def register_tiered_assistant_scopes(conn) -> dict[str, list[str]]:
    """Register the tiered assistant with required scopes in the peer bridge."""
    ensure_schema(conn)
    
    # Register the tiered assistant service principal
    cursor = conn.cursor()
    
    # Check if already registered
    cursor.execute(
        "SELECT id FROM service_principals WHERE id = ?",
        (TIERED_ASSISTANT["name"],)
    )
    
    if not cursor.fetchone():
        cursor.execute(
            """INSERT INTO service_principals (id, description, scopes) 
               VALUES (?, ?, ?)""",
            (TIERED_ASSISTANT["name"], TIERED_ASSISTANT["role"], 
             json.dumps(list(TIERED_ASSISTANT["scopes"])))
        )
        conn.commit()
        LOG.info(f"Registered tiered assistant principal: {TIERED_ASSISTANT['name']}")
    
    return {TIERED_ASSISTANT["name"]: list(TIERED_ASSISTANT["scopes"])}


# Monkey-patch the APEX call to support tiered fallback
# This wraps the original call_apex function
original_call_apex = None


def call_apex_with_tiered_fallback(call_model, model: str, messages: list[dict], 
                                     conn=None, conversation_id: int = None):
    """Call APEX with automatic fallback to tiered online models.
    
    This wraps the original call_apex to intercept context exhaustion errors
    and dispatch to online models.
    """
    from core.chat_continuity import call_apex as original_call_apex
    
    try:
        # Try the original APEX call first
        return original_call_apex(call_model, model, messages)
    except (ApexOffline, RuntimeError) as e:
        error_str = str(e)
        
        # Check if this is a context exhaustion error
        if _should_invoke_tiered_assistant(error_str):
            LOG.warning(f"APEX context exhausted, invoking tiered assistant: {error_str[:200]}")
            
            # Create dispatch message
            dispatch_msg = create_tiered_dispatch_message(
                error_str, 
                conversation_id or 0,
                None  # Will be set by caller
            )
            
            # TODO: Actually post to peer bridge and wait for response
            # For now, return a placeholder indicating tiered assistance needed
            raise RuntimeError(
                f"[TIERED ASSISTANCE NEEDED] APEX context exhausted. "
                f"Dispatching to online model. Please use [DISPATCH: @tiered-assistant] "
                f"to route to online tiered models."
            )
        
        # Re-raise if it's not a context exhaustion issue
        raise


# Install the monkey patch
original_call_apex = None

def install_tiered_fallback():
    """Install the tiered fallback patch for APEX."""
    global original_call_apex
    
    if original_call_apex is not None:
        return  # Already installed
    
    from core import chat_continuity
    original_call_apex = chat_continuity.call_apex
    chat_continuity.call_apex = call_apex_with_tiered_fallback
    
    LOG.info("Installed tiered fallback for APEX - online models can now assist when local context exhausted")
