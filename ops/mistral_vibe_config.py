"""Mistral Vibe Configuration - Setup script for Mistral AI as online agent.

This script configures Mistral Vibe (and all Mistral models) as online agents
that can assist and teach APEX when local context is exhausted.

Run this after setting up the tiered assistant:
    python ops/mistral_vibe_config.py

Or call install_mistral_vibe() from your code.
"""

import logging
import sys
from pathlib import Path

# Add swarm root to path
SWARM_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SWARM_ROOT))
sys.path.insert(0, str(SWARM_ROOT / "utils"))

from core.mistral_vibe_agent import (
    MISTRAL_VIBE_AGENT,
    MISTRAL_MODELS,
    register_mistral_vibe_agent,
    install_mistral_vibe,
    get_mistral_roster,
    MistralDriver,
)

LOG = logging.getLogger(__name__)


def configure_mistral_vibe():
    """Configure Mistral Vibe as an online agent for APEX.
    
    This sets up:
    1. Service principal for mistral-vibe
    2. Peer bridge integration
    3. Tiered assistant configuration
    4. Model roster
    """
    from database import get_connection
    
    LOG.info("Configuring Mistral Vibe as online agent...")
    
    # Register with database
    try:
        conn = get_connection()
        scopes = register_mistral_vibe_agent(conn)
        LOG.info(f"Registered Mistral Vibe with scopes: {scopes}")
        conn.close()
    except Exception as e:
        LOG.error(f"Failed to register Mistral Vibe: {e}")
        # Continue anyway - the rest will still work
    
    # Install into tiered system
    install_mistral_vibe()
    LOG.info("Mistral Vibe installed into tiered assistant system")
    
    # Get the roster
    roster = get_mistral_roster()
    LOG.info(f"Configured {len(roster)} Mistral models: {[r['name'] for r in roster]}")
    
    return {
        "status": "configured",
        "agent": MISTRAL_VIBE_AGENT["name"],
        "models": [r["name"] for r in roster],
        "scopes": list(MISTRAL_VIBE_AGENT["scopes"]),
        "api_key_var": MISTRAL_VIBE_AGENT["api_key_var"],
    }


def test_mistral_connection():
    """Test connection to Mistral API."""
    import os
    from core.mistral_vibe_agent import MistralDriver
    
    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        LOG.warning("MISTRAL_API_KEY not set - cannot test connection")
        return {"status": "skipped", "reason": "No API key"}
    
    try:
        driver = MistralDriver()
        models = driver.list_models()
        LOG.info(f"Connected to Mistral API: {len(models)} models available")
        return {
            "status": "connected",
            "models": [m["name"] for m in models],
        }
    except Exception as e:
        LOG.error(f"Failed to connect to Mistral API: {e}")
        return {"status": "failed", "error": str(e)}


def create_mistral_dispatch_example():
    """Show example dispatch messages for Mistral Vibe."""
    from core.mistral_vibe_agent import create_mistral_dispatch
    
    examples = [
        ("Teach APEX about system file access patterns", 12345),
        ("Explain how to use git tools in APEX context", 12346),
        ("Help APEX understand repository structure", 12347),
    ]
    
    messages = []
    for task, conv_id in examples:
        msg = create_mistral_dispatch(conv_id, task)
        messages.append(msg)
    
    return messages


def generate_llm_registry_entries():
    """Generate llm_registry.yaml entries for Mistral models."""
    from core.mistral_vibe_agent import MISTRAL_MODELS
    
    entries = []
    for model_name, config in MISTRAL_MODELS.items():
        entries.append(f"""
  - name: {model_name}
    driver: mistral
    role: {config['role']}
    tier: online
    endpoint: {config['endpoint']}
    options:
      api_key_var: MISTRAL_API_KEY
      api_model: {config['api_model']}
      temperature: 0.2
      max_tokens: 4096
""")
    
    return """# Mistral Models for llm_registry.yaml
# Add these to your ops/llm_registry.yaml file:
""" + "\n".join(entries)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 70)
    print("Mistral Vibe Agent Configuration")
    print("=" * 70)
    
    # Configure
    result = configure_mistral_vibe()
    print(f"\nConfiguration: {result}")
    
    # Test connection
    conn_result = test_mistral_connection()
    print(f"\nMistral API Test: {conn_result}")
    
    # Show examples
    print("\n" + "=" * 70)
    print("Example Dispatch Messages:")
    print("=" * 70)
    for msg in create_mistral_dispatch_example():
        print(f"\nConversation {msg['conversation_id']}:")
        print(f"  To: {msg['to_agent']}")
        print(f"  Body: {msg['body'][:80]}...")
    
    # Generate registry entries
    print("\n" + "=" * 70)
    print("llm_registry.yaml Entries:")
    print("=" * 70)
    print(generate_llm_registry_entries())
    
    print("\n" + "=" * 70)
    print("Setup complete!")
    print("\nTo use Mistral Vibe:")
    print("  1. Set MISTRAL_API_KEY environment variable")
    print("  2. Add registry entries to ops/llm_registry.yaml")
    print("  3. Dispatch with: [DISPATCH: @mistral-vibe] teach APEX about...")
    print("  4. Or let APEX auto-dispatch when context is exhausted")
    print("=" * 70)
