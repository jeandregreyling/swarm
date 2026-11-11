"""APEX Tiered Configuration - Setup script for online model fallback.

This script configures the tiered assistant agent and integrates it with
the Hummingbird peer bridge to enable online model assistance for APEX.

Run this once to set up the tiered fallback system:
    python ops/apex_tiered_config.py

Or import and call configure_tiered_assistant() from your code.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Add swarm root to path
SWARM_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SWARM_ROOT))

from core.apex_tiered_assistant import (
    TIERED_ASSISTANT,
    register_tiered_assistant_scopes,
    install_tiered_fallback,
    get_tiered_assistant_roster,
)

LOG = logging.getLogger(__name__)


def configure_tiered_assistant():
    """Configure the tiered assistant for APEX fallback.
    
    This sets up:
    1. Service principal for tiered assistant in peer bridge
    2. Monkey-patches APEX to support tiered fallback
    3. Registers online model roster
    """
    from database import get_connection
    
    LOG.info("Configuring tiered assistant for APEX fallback...")
    
    # Register with peer bridge
    try:
        conn = get_connection()
        scopes = register_tiered_assistant_scopes(conn)
        LOG.info(f"Registered tiered assistant with scopes: {scopes}")
        conn.close()
    except Exception as e:
        LOG.error(f"Failed to register tiered assistant: {e}")
        # Continue anyway - the monkey patch will still work
    
    # Install the fallback patch
    install_tiered_fallback()
    LOG.info("Tiered fallback installed for APEX")
    
    # Get the online roster
    roster = get_tiered_assistant_roster()
    LOG.info(f"Configured {len(roster)} tiered online models: {[r['name'] for r in roster]}")
    
    return {
        "status": "configured",
        "tiered_assistant": TIERED_ASSISTANT["name"],
        "online_models": [r["name"] for r in roster],
        "scopes": list(TIERED_ASSISTANT["scopes"]),
    }


def create_apex_fallback_dispatch(conversation_id: int, user_message: str) -> dict:
    """Create a dispatch from APEX to tiered assistant when context is exhausted.
    
    Use this in your chat handlers when APEX reports context exhaustion.
    
    Example:
        if "context exhausted" in response:
            dispatch = create_apex_fallback_dispatch(conv_id, user_message)
            # Send to peer bridge
    """
    from core.apex_tiered_assistant import create_tiered_dispatch_message
    
    return create_tiered_dispatch_message(
        f"APEX context exhausted for: {user_message[:200]}",
        conversation_id
    )


# Peer bridge integration
PEER_MENTIONS_UPDATE = {
    "tiered-assistant": "tiered-assistant",
    "tiered": "tiered-assistant",
    "online": "tiered-assistant",
    "assistant": "tiered-assistant",  # Be careful with this one
}

PEER_SCOPES_UPDATE = {
    "tiered-assistant": ("peer.read", "peer.post", "peer.memory", "peer.relay:apex"),
}


def extend_peer_bridge():
    """Extend the peer bridge to include the tiered assistant."""
    from core.peer_bridge import MENTIONS, SCOPES
    
    # Add tiered assistant to mentions
    MENTIONS.update(PEER_MENTIONS_UPDATE)
    SCOPES.update(PEER_SCOPES_UPDATE)
    
    LOG.info(f"Extended peer bridge: MENTIONS={list(MENTIONS.keys())}, SCOPES={list(SCOPES.keys())}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 70)
    print("APEX Tiered Assistant Configuration")
    print("=" * 70)
    
    # Configure
    result = configure_tiered_assistant()
    print(f"\nConfiguration: {result}")
    
    # Extend peer bridge
    extend_peer_bridge()
    
    print("\n" + "=" * 70)
    print("Setup complete! APEX will now fall back to online models when")
    print("local context is exhausted.")
    print("\nTo use:")
    print("  1. In chat, use [DISPATCH: @tiered-assistant] for online help")
    print("  2. Or let APEX auto-dispatch when context is exhausted")
    print("=" * 70)
