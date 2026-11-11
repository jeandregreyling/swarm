"""Mistral Vibe Agent - External online agent for teaching APEX.

This module configures Mistral AI models (including Mistral Vibe) as online
agents that can assist and teach APEX when local context is exhausted.

Features:
- Mistral Vibe as a peer agent in Hummingbird
- Support for all Mistral models (mistral-large, mixtral, etc.)
- Integration with tiered assistant fallback system
- Can be dispatched via [DISPATCH: @mistral-vibe] or automatically on context exhaustion

Usage:
    # Manual dispatch in chat:
    [DISPATCH: @mistral-vibe] Teach APEX how to handle this system access pattern
    
    # Or automatically when APEX context is exhausted
    # (via the tiered fallback system)
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

from core.apex_tiered_assistant import (
    TIERED_ASSISTANT,
    ONLINE_TIERS,
    APEX_EXHAUSTION_PATTERNS,
)

LOG = logging.getLogger(__name__)


# =============================================================================
# MISTRAL VIBE AGENT DEFINITION
# =============================================================================

MISTRAL_VIBE_AGENT = {
    "name": "mistral-vibe",
    "label": "Mistral Vibe",
    "display_name": "Mistral Vibe (External Assistant)",
    "role": "APEX teacher and assistant",
    "tier": "online",
    "provider": "mistral",
    "enabled": True,
    "status": "on_demand",
    "available": True,
    "scopes": ("peer.read", "peer.post", "peer.memory", "peer.relay:apex", "peer.relay:instructor", "peer.relay:gemini", "peer.relay:codex", "peer.dispatch"),
    "timeout_seconds": 180,
    "eta_seconds": 30,
    "temperature": 0.2,
    "api_key_var": "MISTRAL_API_KEY",
    "description": "Mistral AI assistant for teaching APEX complex reasoning and system access patterns",
}


# =============================================================================
# MISTRAL MODELS CONFIGURATION
# =============================================================================

MISTRAL_MODELS = {
    # Latest and greatest
    "mistral-large-latest": {
        "name": "mistral-large-latest",
        "label": "Mistral Large (Latest)",
        "driver": "openai",  # Uses OpenAI-compatible API
        "endpoint": "https://api.mistral.ai/v1",
        "api_model": "mistral-large-latest",
        "role": "reasoner",
        "tier": "online",
        "ctx": 32768,
        "ram_gb": 0.0,  # API-based, no local RAM
        "options": {
            "api_key_var": "MISTRAL_API_KEY",
            "temperature": 0.2,
            "max_tokens": 4096,
        },
    },
    
    "mixtral-8x22b-latest": {
        "name": "mixtral-8x22b-latest",
        "label": "Mixtral 8x22B (Latest)",
        "driver": "openai",
        "endpoint": "https://api.mistral.ai/v1",
        "api_model": "mixtral-8x22b-latest",
        "role": "analyst",
        "tier": "online",
        "ctx": 65536,
        "ram_gb": 0.0,
        "options": {
            "api_key_var": "MISTRAL_API_KEY",
            "temperature": 0.2,
            "max_tokens": 4096,
        },
    },
    
    "mistral-small-latest": {
        "name": "mistral-small-latest",
        "label": "Mistral Small (Latest)",
        "driver": "openai",
        "endpoint": "https://api.mistral.ai/v1",
        "api_model": "mistral-small-latest",
        "role": "general",
        "tier": "online",
        "ctx": 32768,
        "ram_gb": 0.0,
        "options": {
            "api_key_var": "MISTRAL_API_KEY",
            "temperature": 0.2,
            "max_tokens": 4096,
        },
    },
    
    # Legacy models
    "mistral-large-2407": {
        "name": "mistral-large-2407",
        "label": "Mistral Large 2407",
        "driver": "openai",
        "endpoint": "https://api.mistral.ai/v1",
        "api_model": "mistral-large-2407",
        "role": "reasoner",
        "tier": "online",
        "ctx": 32768,
        "ram_gb": 0.0,
        "options": {
            "api_key_var": "MISTRAL_API_KEY",
            "temperature": 0.2,
            "max_tokens": 4096,
        },
    },
    
    "mistral-large-2402": {
        "name": "mistral-large-2402",
        "label": "Mistral Large 2402",
        "driver": "openai",
        "endpoint": "https://api.mistral.ai/v1",
        "api_model": "mistral-large-2402",
        "role": "reasoner",
        "tier": "online",
        "ctx": 32768,
        "ram_gb": 0.0,
        "options": {
            "api_key_var": "MISTRAL_API_KEY",
            "temperature": 0.2,
            "max_tokens": 4096,
        },
    },
}


# =============================================================================
# MISTRAL DRIVER FOR SEVEN RUNTIME
# =============================================================================

class MistralDriver:
    """OpenAI-compatible driver for Mistral AI API.
    
    Mistral provides an OpenAI-compatible API endpoint, so we can use
    the existing OpenAIDriver from seven_llm with Mistral-specific config.
    """
    
    name = "mistral"
    
    def __init__(self, endpoint: str | None = None, options: dict | None = None):
        self.endpoint = endpoint or "https://api.mistral.ai/v1"
        self.options = dict(options or {})
        self.api_key = self.options.get("api_key") or os.environ.get("MISTRAL_API_KEY")
    
    def _headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
    
    def chat(self, model: str, messages: list[dict], *, stream: bool = False,
             temperature: float | None = None, options: dict | None = None,
             keep_alive: Any = None) -> tuple[str, int]:
        """Call Mistral AI chat API."""
        import requests
        
        if not self.api_key:
            raise RuntimeError("MISTRAL_API_KEY not set")
        
        # Map model name to API model
        model_info = MISTRAL_MODELS.get(model)
        api_model = model_info["api_model"] if model_info else model
        
        body = {
            "model": api_model,
            "messages": messages,
            "stream": False,
            "max_tokens": int(options.get("max_tokens") or 4096) if options else 4096,
            "temperature": float(temperature if temperature is not None else 0.2),
        }
        
        response = requests.post(
            f"{self.endpoint}/chat/completions",
            json=body,
            headers=self._headers(),
            timeout=120,
        )
        response.raise_for_status()
        
        data = response.json()
        text = data["choices"][0]["message"]["content"]
        tokens = int(data.get("usage", {}).get("total_tokens", 0))
        
        return text, tokens
    
    def ps(self) -> list[dict]:
        """No process management for API-based models."""
        return []
    
    def list_models(self) -> list[dict]:
        """List available Mistral models."""
        if not self.api_key:
            return []
        try:
            import requests
            response = requests.get(
                f"{self.endpoint}/models",
                headers=self._headers(),
                timeout=10,
            )
            response.raise_for_status()
            models = response.json().get("data", [])
            return [{"name": m.get("id")} for m in models]
        except Exception:
            # Return our known models
            return [{"name": name} for name in MISTRAL_MODELS.keys()]


# =============================================================================
# INTEGRATION WITH TIERED ASSISTANT
# =============================================================================

# Add Mistral models to the tiered system
MISTRAL_TIERS = {
    "tier1": {
        "models": ["mistral-small-latest", "mistral-large-latest"],
        "role": "general",
        "provider": "mistral",
    },
    "tier2": {
        "models": ["mixtral-8x22b-latest", "mistral-large-2407"],
        "role": "analyst",
        "provider": "mistral",
    },
    "tier3": {
        "models": ["mistral-large-latest"],
        "role": "solver",
        "provider": "mistral",
    },
}


# Merge Mistral tiers with existing tiers
ONLINE_TIERS.update(MISTRAL_TIERS)


# =============================================================================
# PEER BRIDGE INTEGRATION
# =============================================================================

MISTRAL_MENTIONS = {
    "mistral-vibe": "mistral-vibe",
    "mistral": "mistral-vibe",
    "vibe": "mistral-vibe",
}

MISTRAL_SCOPES = {
    "mistral-vibe": ("peer.read", "peer.post", "peer.memory", "peer.relay:apex", "peer.relay:instructor"),
}


def register_mistral_vibe_agent(conn) -> dict[str, list[str]]:
    """Register Mistral Vibe as a service principal in the peer bridge."""
    from core.service_accounts import initialise as ensure_service_tables
    from core.peer_bridge import ensure_schema
    
    # Ensure tables exist
    ensure_service_tables(conn)
    ensure_schema(conn)
    
    cursor = conn.cursor()
    
    # Check if already registered
    cursor.execute(
        "SELECT id FROM service_principals WHERE id = ?",
        (MISTRAL_VIBE_AGENT["name"],)
    )
    
    if not cursor.fetchone():
        cursor.execute(
            """INSERT INTO service_principals (id, display_name, role, enabled, created_at)
               VALUES (?, ?, 'service', 1, ?)""",
            (MISTRAL_VIBE_AGENT["name"], MISTRAL_VIBE_AGENT["display_name"], time.time()),
        )
        LOG.info(f"Registered Mistral Vibe service principal: {MISTRAL_VIBE_AGENT['name']}")
    
    # Register scopes in service_tokens table
    cursor.execute(
        """INSERT OR IGNORE INTO service_tokens (principal_id, token_sha256, scopes, created_at)
           VALUES (?, 'placeholder_sha256', ?, ?)""",
        (MISTRAL_VIBE_AGENT["name"], json.dumps(list(MISTRAL_VIBE_AGENT["scopes"])), time.time())
    )
    
    conn.commit()
    return {MISTRAL_VIBE_AGENT["name"]: list(MISTRAL_VIBE_AGENT["scopes"])}


# =============================================================================
# MISTRAL-SPECIFIC DISPATCH
# =============================================================================

def create_mistral_dispatch(conversation_id: int, task: str, model: str | None = None) -> dict:
    """Create a dispatch message specifically for Mistral Vibe.
    
    This can be used to explicitly request Mistral's help in teaching APEX.
    """
    selected_model = model or "mistral-large-latest"
    
    return {
        "conversation_id": conversation_id,
        "from_agent": "apex",
        "to_agent": MISTRAL_VIBE_AGENT["name"],
        "body": f"[APEX TEACHING REQUEST] {task}",
        "metadata": {
            "dispatch_type": "apex_teaching",
            "model": selected_model,
            "provider": "mistral",
            "timestamp": time.time(),
            "teaching_focus": "system_access_patterns",
        },
        "not_before": time.time(),
    }


def dispatch_mistral_to_apex(
    conn,
    conversation_id: int,
    user_message: str,
    apex_message_id: int | None = None
) -> dict | None:
    """Dispatch Mistral Vibe to assist APEX with a specific teaching task.
    
    This is the primary interface for having Mistral teach APEX about
    system access patterns and complex reasoning.
    """
    from core.peer_bridge import post_to_peer
    
    # Create the dispatch
    dispatch_msg = create_mistral_dispatch(
        conversation_id,
        f"Teach APEX: {user_message[:500]}",
        model="mistral-large-latest"
    )
    
    # Add APEX context
    if apex_message_id:
        dispatch_msg["metadata"]["apex_message_id"] = apex_message_id
    
    # Post to peer bridge
    result = post_to_peer(conn, dispatch_msg)
    
    LOG.info(f"Dispatched Mistral Vibe to teach APEX: conversation={conversation_id}")
    
    return result


# =============================================================================
# MISTRAL VIBE ROSTER
# =============================================================================

def get_mistral_roster() -> list[dict]:
    """Get the roster of available Mistral models."""
    roster = []
    
    for model_name, model_config in MISTRAL_MODELS.items():
        roster.append({
            "name": f"mistral-{model_name.replace('.', '-').replace('-', '-')}",
            "label": model_config["label"],
            "model": model_name,
            "provider": "mistral",
            "tier": "online",
            "role": model_config["role"],
            "endpoint": model_config["endpoint"],
            "ctx": model_config["ctx"],
            "enabled": True,
            "status": "on_demand",
            "available": True,
            "availability_reason": "Mistral AI online model",
            "api_key_var": "MISTRAL_API_KEY",
            "temperature": 0.2,
            "eta_seconds": 45,
        })
    
    # Add the Mistral Vibe agent itself
    roster.append({
        "name": MISTRAL_VIBE_AGENT["name"],
        "label": MISTRAL_VIBE_AGENT["label"],
        "display_name": MISTRAL_VIBE_AGENT["display_name"],
        "role": MISTRAL_VIBE_AGENT["role"],
        "tier": "online",
        "provider": "mistral",
        "enabled": True,
        "status": "on_demand",
        "available": True,
        "availability_reason": MISTRAL_VIBE_AGENT["description"],
        "api_key_var": "MISTRAL_API_KEY",
        "temperature": 0.2,
        "eta_seconds": 30,
    })
    
    return roster


# =============================================================================
# AUTOMATIC INTEGRATION
# =============================================================================

def install_mistral_vibe():
    """Install Mistral Vibe as an available online agent.
    
    Call this at startup to register Mistral Vibe with the tiered assistant system.
    """
    from core.apex_tiered_assistant import ONLINE_TIERS as base_tiers
    from core.peer_bridge import MENTIONS as base_mentions
    from core.peer_bridge import SCOPES as base_scopes
    
    # Update global tiers
    base_tiers.update(MISTRAL_TIERS)
    
    # Update peer bridge mentions
    base_mentions.update(MISTRAL_MENTIONS)
    base_scopes.update(MISTRAL_SCOPES)
    
    LOG.info("Mistral Vibe installed as online agent")
    LOG.info(f"Mentions: {list(base_mentions.keys())}")
    LOG.info(f"Tiered models: {len(base_tiers) * 3} (3 per tier)")


def get_mistral_teaching_prompt(task: str) -> str:
    """Generate a teaching prompt for Mistral to help APEX learn.
    
    This creates context-aware prompts that help Mistral teach APEX
    about system access patterns and complex reasoning.
    """
    return f"""You are Mistral Vibe, an expert AI assistant teaching APEX (a local Qwen2.5-14B model).

APEX has encountered a system access pattern it cannot handle with its local context.
Your task is to:
1. Understand the problem from APEX's perspective
2. Provide clear, actionable guidance
3. Explain system access patterns that APEX should learn
4. Keep responses concise and focused on teaching APEX

Current task: {task}

Please provide your teaching in a format that APEX can understand and learn from.
Focus on:
- Specific file paths and operations
- Repository structure understanding
- Tool usage patterns
- Context management strategies

Respond in clear, direct language without excessive explanation."""
