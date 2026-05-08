"""Lock the leaked '[Auto Relay: ENABLED|DISABLED]' banner stripper.

Regression for STEP-LOCAL-AGENT-ANSWER-BANNER-CLEANUP-20260430.

Local agents (Gemma, LLaMA) sometimes echo the orchestrator system-prompt
banner at the top of their final answer, polluting creative output (songs,
stories). The banner is a system artefact and never user-facing, so the
stripper is unconditional.
"""
from frontend.services.chat_relay import _strip_auto_relay_banner


class TestAutoRelayBannerStrip:
    def test_strips_enabled_prefix(self):
        msg = "[Auto Relay: ENABLED]\nVerse 1\nThe night is young…"
        out = _strip_auto_relay_banner(msg)
        assert out.startswith("Verse 1")
        assert "Auto Relay" not in out

    def test_strips_disabled_prefix(self):
        msg = "[Auto Relay: DISABLED]\nHere is your answer."
        out = _strip_auto_relay_banner(msg)
        assert out == "Here is your answer."

    def test_strips_lowercase_variant(self):
        msg = "[auto relay: enabled]\nbody"
        assert _strip_auto_relay_banner(msg) == "body"

    def test_strips_with_internal_whitespace(self):
        msg = "[ Auto  Relay : Enabled ]\nbody"
        assert _strip_auto_relay_banner(msg) == "body"

    def test_strips_on_off_synonyms(self):
        assert _strip_auto_relay_banner("[Auto Relay: ON]\nx") == "x"
        assert _strip_auto_relay_banner("[Auto Relay: OFF]\ny") == "y"

    def test_strips_when_banner_appears_mid_text_on_own_line(self):
        msg = "First line.\n[Auto Relay: ENABLED]\nSecond line."
        out = _strip_auto_relay_banner(msg)
        assert out == "First line.\nSecond line."

    def test_idempotent(self):
        msg = "[Auto Relay: ENABLED]\nbody"
        once = _strip_auto_relay_banner(msg)
        twice = _strip_auto_relay_banner(once)
        assert once == twice == "body"

    def test_passthrough_when_no_banner(self):
        msg = "Just a regular answer with [brackets] and colons: yes."
        assert _strip_auto_relay_banner(msg) == msg

    def test_does_not_strip_legit_bracketed_content(self):
        # Defensive: a song lyric or note that just happens to contain
        # the words "auto" and "relay" in different brackets must survive.
        msg = "[Verse]\nAutomatic relays click in the night."
        assert _strip_auto_relay_banner(msg) == msg

    def test_empty_input_returns_empty(self):
        assert _strip_auto_relay_banner("") == ""
        assert _strip_auto_relay_banner(None) is None  # type: ignore[arg-type]

    def test_banner_only_returns_original(self):
        # If the entire message is the banner, the fallback returns the
        # original (never empty) so callers don't see a blank reply.
        msg = "[Auto Relay: ENABLED]"
        out = _strip_auto_relay_banner(msg)
        assert "Auto Relay" in out  # fallback intact

    def test_leaked_banner_in_song_output_regression(self):
        # The original Gemma symptom: lyrics with banner at the top.
        song = (
            "[Auto Relay: ENABLED]\n"
            "Verse 1:\n"
            "Walking through the swarm tonight\n"
            "Every agent shining bright\n"
        )
        out = _strip_auto_relay_banner(song)
        assert out.startswith("Verse 1:")
        assert "[Auto Relay" not in out
        assert "Walking through" in out

    def test_preserves_trailing_newlines_in_body(self):
        msg = "[Auto Relay: ENABLED]\nbody\n\n"
        out = _strip_auto_relay_banner(msg)
        assert out.startswith("body")

    def test_export_through_services_namespace(self):
        # Ensure it's exposed via `from services import *` so chat.py
        # picks it up without an explicit import.
        from frontend import services
        assert hasattr(services, "_strip_auto_relay_banner")
        assert "_strip_auto_relay_banner" in services.__all__
