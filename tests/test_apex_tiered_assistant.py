"""Tests for APEX Tiered Assistant fallback system."""

import pytest
import json
import sqlite3
import tempfile
import os

# Ensure SWARM_ROOT is in path
import sys
SWARM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SWARM_ROOT)


class TestTieredAssistant:
    """Test suite for tiered assistant functionality."""

    def test_tiered_assistant_constants(self):
        """Test that tiered assistant constants are defined."""
        from core.apex_tiered_assistant import (
            TIERED_ASSISTANT,
            ONLINE_TIERS,
            APEX_EXHAUSTION_PATTERNS,
        )
        
        # Check tiered assistant definition
        assert TIERED_ASSISTANT["name"] == "tiered-assistant"
        assert TIERED_ASSISTANT["tier"] == "online"
        assert "peer.read" in TIERED_ASSISTANT["scopes"]
        
        # Check online tiers
        assert "tier1" in ONLINE_TIERS
        assert "tier2" in ONLINE_TIERS
        assert "tier3" in ONLINE_TIERS
        assert len(ONLINE_TIERS["tier1"]["models"]) > 0
        
        # Check patterns
        assert len(APEX_EXHAUSTION_PATTERNS) > 0

    def test_should_invoke_tiered_assistant(self):
        """Test detection of context exhaustion errors."""
        from core.apex_tiered_assistant import _should_invoke_tiered_assistant
        
        # Should trigger on context exhaustion
        assert _should_invoke_tiered_assistant("APEX context budget exceeded")
        assert _should_invoke_tiered_assistant("Context length exceeded")
        assert _should_invoke_tiered_assistant("Maximum context size reached")
        assert _should_invoke_tiered_assistant("Out of tokens")
        assert _should_invoke_tiered_assistant("APEX context cannot fit")
        assert _should_invoke_tiered_assistant("num_ctx=16384")
        assert _should_invoke_tiered_assistant("Prompt is too long")
        
        # Should not trigger on other errors
        assert not _should_invoke_tiered_assistant("Connection timeout")
        assert not _should_invoke_tiered_assistant("Model not found")
        assert not _should_invoke_tiered_assistant("File not found")

    def test_model_selection_logic(self):
        """Test automatic model selection based on task."""
        from core.apex_tiered_assistant import _get_online_model_for_task
        
        # Tier 3 - Complex tasks
        tier3_tasks = [
            "debug this complex system",
            "diagnose the root cause",
            "investigate the architecture issue",
            "multi-step reasoning problem",
        ]
        for task in tier3_tasks:
            model = _get_online_model_for_task(task)
            assert model == "o1", f"Expected o1 for tier3 task: {task}"
        
        # Tier 2 - Analysis tasks
        tier2_tasks = [
            "review this code",
            "analyze the performance",
            "explain how this works",
            "optimize this algorithm",
        ]
        for task in tier2_tasks:
            model = _get_online_model_for_task(task)
            assert model == "gpt-4", f"Expected gpt-4 for tier2 task: {task}"
        
        # Tier 1 - General tasks
        tier1_tasks = [
            "what is python",
            "help me with this",
            "quick question",
        ]
        for task in tier1_tasks:
            model = _get_online_model_for_task(task)
            assert model == "gpt-4o", f"Expected gpt-4o for tier1 task: {task}"

    def test_dispatch_message_creation(self):
        """Test creation of dispatch messages."""
        from core.apex_tiered_assistant import create_tiered_dispatch_message
        
        msg = create_tiered_dispatch_message(
            "Context exhausted",
            conversation_id=12345,
            apex_message_id=67890
        )
        
        assert msg["conversation_id"] == 12345
        assert msg["from_agent"] == "apex"
        assert msg["to_agent"] == "tiered-assistant"
        assert "APEX HANDOFF" in msg["body"]
        assert msg["metadata"]["dispatch_type"] == "apex_fallback"
        assert msg["metadata"]["apex_message_id"] == 67890

    def test_tiered_roster(self):
        """Test generation of tiered assistant roster."""
        from core.apex_tiered_assistant import get_tiered_assistant_roster
        
        roster = get_tiered_assistant_roster()
        
        assert isinstance(roster, list)
        assert len(roster) > 0
        
        # Check that all entries have required fields
        for entry in roster:
            assert "name" in entry
            assert "model" in entry
            assert entry["tier"] == "online"
            assert "enabled" in entry

    def test_service_accounts_includes_tiered_assistant(self):
        """Test that tiered-assistant is in service accounts."""
        import sqlite3
        import tempfile
        from core.service_accounts import initialise
        
        # Create a temporary database
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        
        try:
            conn = sqlite3.connect(db_path)
            initialise(conn)
            conn.commit()
            
            # Check that tiered-assistant was created
            cursor = conn.execute(
                "SELECT id, display_name FROM service_principals WHERE id = 'tiered-assistant'"
            )
            row = cursor.fetchone()
            
            assert row is not None, "tiered-assistant not found in service_principals"
            assert row[0] == "tiered-assistant"
            assert row[1] == "Tiered Model Assistant"
            
            conn.close()
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_register_tiered_assistant_scopes(self):
        """Test registration of tiered assistant scopes."""
        import sqlite3
        import tempfile
        import os
        from core.apex_tiered_assistant import register_tiered_assistant_scopes
        from core.service_accounts import initialise
        
        # Create a temporary database
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        
        try:
            conn = sqlite3.connect(db_path)
            initialise(conn)
            
            # Register scopes
            scopes = register_tiered_assistant_scopes(conn)
            conn.commit()
            
            # Check scopes were registered
            assert "tiered-assistant" in scopes
            assert "peer.read" in scopes["tiered-assistant"]
            
            conn.close()
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_extract_task_from_error(self):
        """Test extraction of task from error messages."""
        from core.apex_tiered_assistant import _extract_task_from_error
        
        # Error with user message
        error1 = "User: Please help me with this complex task"
        task1 = _extract_task_from_error(error1)
        assert "complex task" in task1.lower()
        
        # Error without user message
        error2 = "APEX context budget exceeded"
        task2 = _extract_task_from_error(error2)
        assert "APEX context exhausted" in task2
        
        # Long error message
        error3 = "... lots of text ... User: My request is to debug this ..."
        task3 = _extract_task_from_error(error3)
        assert "debug" in task3.lower() or "context exhausted" in task3.lower()

    def test_call_apex_with_tiered_fallback(self):
        """Test the fallback wrapper function."""
        from core.apex_tiered_assistant import call_apex_with_tiered_fallback
        from core.chat_continuity import ApexOffline
        
        # Mock call_model that always fails
        def mock_call_model_failure(model, messages):
            raise RuntimeError("APEX context budget exceeded: 16384 tokens")
        
        # Should trigger tiered fallback
        with pytest.raises(RuntimeError) as exc_info:
            call_apex_with_tiered_fallback(
                mock_call_model_failure,
                "qwen2.5:14b-instruct",
                [{"role": "user", "content": "test"}]
            )
        
        error_msg = str(exc_info.value)
        assert "TIERED ASSISTANCE NEEDED" in error_msg
        assert "APEX context exhausted" in error_msg


class TestPeerBridgeIntegration:
    """Test integration with peer bridge."""

    def test_peer_mentions_updated(self):
        """Test that tiered-assistant can be added to MENTIONS."""
        from core.peer_bridge import MENTIONS as OriginalMENTIONS
        from ops.apex_tiered_config import PEER_MENTIONS_UPDATE
        
        # Create updated mentions
        updated = dict(OriginalMENTIONS)
        updated.update(PEER_MENTIONS_UPDATE)
        
        assert "tiered-assistant" in updated
        assert "tiered" in updated

    def test_peer_scopes_updated(self):
        """Test that tiered-assistant can be added to SCOPES."""
        from core.peer_bridge import SCOPES as OriginalSCOPES
        from ops.apex_tiered_config import PEER_SCOPES_UPDATE
        
        # Create updated scopes
        updated = dict(OriginalSCOPES)
        updated.update(PEER_SCOPES_UPDATE)
        
        assert "tiered-assistant" in updated
        assert "peer.read" in updated["tiered-assistant"]
        assert "peer.relay:apex" in updated["tiered-assistant"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
