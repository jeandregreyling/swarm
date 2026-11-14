"""Tests for Mistral Vibe integration with APEX."""

import pytest
import sqlite3
import tempfile
import os

# Ensure SWARM_ROOT is in path
import sys
SWARM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SWARM_ROOT)


class TestMistralVibeAgent:
    """Test suite for Mistral Vibe agent configuration."""

    def test_mistral_vibe_agent_constants(self):
        """Test that Mistral Vibe agent constants are defined."""
        from core.mistral_vibe_agent import (
            MISTRAL_VIBE_AGENT,
            MISTRAL_MODELS,
            MISTRAL_TIERS,
            MISTRAL_MENTIONS,
            MISTRAL_SCOPES,
        )
        
        # Check agent definition
        assert MISTRAL_VIBE_AGENT["name"] == "mistral-vibe"
        assert MISTRAL_VIBE_AGENT["tier"] == "online"
        assert MISTRAL_VIBE_AGENT["provider"] == "mistral"
        assert "peer.read" in MISTRAL_VIBE_AGENT["scopes"]
        assert "peer.relay:apex" in MISTRAL_VIBE_AGENT["scopes"]
        
        # Check models
        assert "mistral-large-latest" in MISTRAL_MODELS
        assert "mixtral-8x22b-latest" in MISTRAL_MODELS
        assert "mistral-small-latest" in MISTRAL_MODELS
        
        # Check tiers
        assert "tier1" in MISTRAL_TIERS
        assert "tier2" in MISTRAL_TIERS
        
        # Check mentions
        assert "mistral-vibe" in MISTRAL_MENTIONS
        assert "mistral" in MISTRAL_MENTIONS
        assert "vibe" in MISTRAL_MENTIONS

    def test_mistral_roster(self):
        """Test generation of Mistral roster."""
        from core.mistral_vibe_agent import get_mistral_roster
        
        roster = get_mistral_roster()
        
        assert isinstance(roster, list)
        assert len(roster) > 0
        
        # Check mistral-vibe agent is in roster
        agent_names = [r["name"] for r in roster]
        assert "mistral-vibe" in agent_names
        
        # Check models are in roster
        model_names = [r["model"] for r in roster if "model" in r]
        assert "mistral-large-latest" in model_names
        assert "mixtral-8x22b-latest" in model_names

    def test_mistral_driver_initialization(self):
        """Test MistralDriver can be initialized."""
        from core.mistral_vibe_agent import MistralDriver
        
        # Without API key (should still initialize)
        driver = MistralDriver()
        assert driver.name == "mistral"
        assert driver.endpoint == "https://api.mistral.ai/v1"
        
        # With custom endpoint
        driver2 = MistralDriver(endpoint="https://custom.endpoint.com/v1")
        assert driver2.endpoint == "https://custom.endpoint.com/v1"

    def test_create_mistral_dispatch(self):
        """Test creation of Mistral dispatch messages."""
        from core.mistral_vibe_agent import create_mistral_dispatch
        
        msg = create_mistral_dispatch(
            conversation_id=12345,
            task="Teach APEX about system access",
            model="mistral-large-latest"
        )
        
        assert msg["conversation_id"] == 12345
        assert msg["from_agent"] == "apex"
        assert msg["to_agent"] == "mistral-vibe"
        assert "APEX TEACHING REQUEST" in msg["body"]
        assert "system access" in msg["body"]
        assert msg["metadata"]["model"] == "mistral-large-latest"
        assert msg["metadata"]["provider"] == "mistral"
        assert msg["metadata"]["dispatch_type"] == "apex_teaching"

    def test_mistral_teaching_prompt(self):
        """Test generation of teaching prompts."""
        from core.mistral_vibe_agent import get_mistral_teaching_prompt
        
        prompt = get_mistral_teaching_prompt("complex task")
        
        assert "Mistral Vibe" in prompt
        assert "APEX" in prompt
        assert "system access" in prompt
        assert "complex task" in prompt


class TestMistralVibeServiceAccounts:
    """Test Mistral Vibe service account registration."""

    def test_service_accounts_includes_mistral_vibe(self):
        """Test that mistral-vibe is in service accounts."""
        import sqlite3
        import tempfile
        import os
        from core.service_accounts import initialise
        
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        
        try:
            conn = sqlite3.connect(db_path)
            initialise(conn)
            conn.commit()
            
            cursor = conn.execute(
                "SELECT id, display_name FROM service_principals WHERE id = 'mistral-vibe'"
            )
            row = cursor.fetchone()
            
            assert row is not None, "mistral-vibe not found in service_principals"
            assert row[0] == "mistral-vibe"
            assert row[1] == "Mistral Vibe"
            
            conn.close()
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)


class TestMistralVibePeerBridge:
    """Test Mistral Vibe peer bridge integration."""

    def test_peer_mentions_include_mistral(self):
        """Test that Mistral mentions are in peer bridge."""
        from core.peer_bridge import MENTIONS
        
        assert "mistral-vibe" in MENTIONS
        assert "mistral" in MENTIONS
        assert "vibe" in MENTIONS

    def test_peer_scopes_include_mistral(self):
        """Test that Mistral scopes are in peer bridge."""
        from core.peer_bridge import SCOPES
        
        assert "mistral-vibe" in SCOPES
        assert "peer.read" in SCOPES["mistral-vibe"]
        assert "peer.relay:apex" in SCOPES["mistral-vibe"]

    def test_mention_regex_includes_mistral(self):
        """Test that mention regex includes Mistral patterns."""
        from core.peer_bridge import _MENTION_RE
        import re
        
        # Test various mentions
        test_cases = [
            "@mistral-vibe",
            "@mistral",
            "@vibe",
        ]
        
        for mention in test_cases:
            # Should match with word boundaries
            test_string = f"Some text {mention} more text"
            assert _MENTION_RE.search(test_string), f"Mention regex should match: {mention}"

    def test_dispatch_regex_includes_mistral(self):
        """Test that dispatch regex includes Mistral patterns."""
        from core.peer_bridge import _DISPATCH_RE
        
        test_cases = [
            "[DISPATCH: @mistral-vibe] teach APEX",
            "[DISPATCH: @mistral] help with this",
            "[DISPATCH: @vibe] explain",
        ]
        
        for dispatch in test_cases:
            match = _DISPATCH_RE.match(dispatch)
            assert match is not None, f"Dispatch regex should match: {dispatch}"
            assert match.group(1) in ["mistral-vibe", "mistral", "vibe"]


class TestMistralVibeTiers:
    """Test Mistral tiers integration with tiered assistant."""

    def test_mistral_tiers_in_online_tiers(self):
        """Test that Mistral tiers are in ONLINE_TIERS."""
        from core.apex_tiered_assistant import ONLINE_TIERS
        from core.mistral_vibe_agent import MISTRAL_TIERS
        
        # Check Mistral tiers were merged
        assert "tier1" in ONLINE_TIERS
        assert "tier2" in ONLINE_TIERS
        
        # Check Mistral models are in the tiers
        tier1_models = ONLINE_TIERS["tier1"]["models"]
        tier2_models = ONLINE_TIERS["tier2"]["models"]
        
        # Should have Mistral models
        all_models = tier1_models + tier2_models
        mistral_models = [m for m in all_models if "mistral" in m.lower()]
        assert len(mistral_models) > 0


class TestMistralVibeIntegration:
    """Test end-to-end integration."""

    def test_full_integration(self):
        """Test that all Mistral Vibe components integrate properly."""
        # Import all components
        from core.mistral_vibe_agent import (
            MISTRAL_VIBE_AGENT,
            MISTRAL_MODELS,
            MISTRAL_TIERS,
            get_mistral_roster,
            create_mistral_dispatch,
        )
        from core.apex_tiered_assistant import ONLINE_TIERS
        from core.peer_bridge import MENTIONS, SCOPES
        
        # Verify agent
        assert MISTRAL_VIBE_AGENT["name"] == "mistral-vibe"
        
        # Verify models
        assert len(MISTRAL_MODELS) > 0
        
        # Verify tiers
        assert len(MISTRAL_TIERS) > 0
        
        # Verify peer bridge
        assert "mistral-vibe" in MENTIONS
        assert "mistral-vibe" in SCOPES
        
        # Verify roster
        roster = get_mistral_roster()
        assert len(roster) > 0
        
        # Verify dispatch
        msg = create_mistral_dispatch(123, "test")
        assert msg["to_agent"] == "mistral-vibe"
        
        # Verify tiers merged
        assert "tier1" in ONLINE_TIERS
        
        return True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
