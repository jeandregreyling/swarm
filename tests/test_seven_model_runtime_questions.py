def test_model_question_bypasses_deterministic_identity(monkeypatch):
    from agents.seven import seven_agent

    monkeypatch.setattr(seven_agent, "_load_identity_beliefs", lambda *args, **kwargs: [])

    answer, tokens = seven_agent._compose(
        "What model are you?",
        {"tickets": 3, "proposals": 31, "local_agents": ["Seven"]},
        [],
    )

    assert answer is None
    assert tokens == 0


def test_model_question_uses_direct_llm_path(monkeypatch):
    from agents.seven import seven_agent

    stages = []
    calls = {}

    monkeypatch.setattr(seven_agent, "SEVEN_MODEL", "seven-direct:daily")
    monkeypatch.setattr(seven_agent, "_read_state", lambda: {"tickets": 0, "proposals": 0, "local_agents": ["Seven"]})
    monkeypatch.setattr(seven_agent, "_load_memory", lambda _message: [])
    monkeypatch.setattr(seven_agent, "_load_kc_context", lambda *args, **kwargs: [])
    monkeypatch.setattr(seven_agent, "_load_identity_beliefs", lambda *args, **kwargs: [])
    monkeypatch.setattr(seven_agent, "_load_open_curiosity", lambda *args, **kwargs: [])
    monkeypatch.setattr(seven_agent, "_load_pillars_context", lambda: {})

    def fake_gateway(model, messages, **kwargs):
        calls["model"] = model
        calls["system"] = messages[0]["content"]
        return "I am running through seven-direct:daily on Seven Runtime.", 9

    monkeypatch.setattr("core.llm.chat_via_gateway", fake_gateway)

    answer, tokens = seven_agent.chat(
        "What model are you?",
        stage_cb=lambda text, _eta=None: stages.append(text),
    )

    assert calls["model"] == "seven-direct:daily"
    assert "SEVEN_MODEL=seven-direct:daily" in calls["system"]
    assert "thinking · seven merged model" in stages
    assert "seven-direct:daily" in answer
    assert tokens == 9


def test_wrapped_model_question_uses_compact_latest_user_message(monkeypatch):
    from agents.seven import seven_agent

    calls = {}
    wrapped = (
        "=== Shared conversation thread (latest) ===\n"
        "USER -> SEVEN: What model are you?\n"
        "SEVEN -> USER: Observing from the nervous system:\\nOpen tickets: 3\n\n"
        "=== New user message ===\n"
        "What model are you?"
    )

    monkeypatch.setattr(seven_agent, "SEVEN_MODEL", "seven-direct:daily")
    monkeypatch.setattr(seven_agent, "_read_state", lambda: {"tickets": 3, "proposals": 31, "local_agents": ["Seven"]})
    monkeypatch.setattr(seven_agent, "_load_memory", lambda _message: [])
    monkeypatch.setattr(seven_agent, "_load_kc_context", lambda *args, **kwargs: [])
    monkeypatch.setattr(seven_agent, "_load_identity_beliefs", lambda *args, **kwargs: [])
    monkeypatch.setattr(seven_agent, "_load_open_curiosity", lambda *args, **kwargs: [])
    monkeypatch.setattr(seven_agent, "_load_pillars_context", lambda: {})

    def fake_gateway(model, messages, **kwargs):
        calls["model"] = model
        calls["messages"] = messages
        return "I am seven-direct:daily.", 5

    monkeypatch.setattr("core.llm.chat_via_gateway", fake_gateway)

    answer, tokens = seven_agent.chat(
        wrapped,
        conversation_history=[{"role": "assistant", "content": "old deterministic state"}],
    )

    assert calls["model"] == "seven-direct:daily"
    assert calls["messages"][-1]["content"] == "What model are you?"
    assert all("old deterministic state" not in msg["content"] for msg in calls["messages"])
    assert "seven-direct:daily" in answer
    assert tokens == 5


def test_weather_question_uses_local_weather_proxy(monkeypatch):
    from agents.seven import seven_agent
    from frontend.blueprints import weather_bp

    monkeypatch.setattr(
        weather_bp,
        "_get_cached",
        lambda city: {"temperature": 12.3, "windspeed": 9.0, "description": "Overcast"},
    )

    answer, tokens = seven_agent._compose(
        "what is the weather like today where you are?",
        {"tickets": 0, "proposals": 0, "local_agents": ["Seven"]},
        [],
    )

    assert tokens == 0
    assert "Melbourne" in answer
    assert "Overcast" in answer
    assert "12.3 C" in answer


def test_fridays_chat_verification_prompt_is_deterministic():
    from agents.seven import seven_agent

    prompts = [
        (
            "Seven live smoke from Codex: reply with LIVE_SEVEN_OK and one short sentence "
            "about whether this came through Fridays chat."
        ),
        (
            "Seven UI click test from Codex: reply with CLICK_SEVEN_OK_0606 and confirm "
            "this was sent by clicking the visible Fridays home chat send button."
        ),
    ]
    for prompt in prompts:
        answer, tokens = seven_agent._compose(
            prompt,
            {"tickets": 0, "proposals": 0, "local_agents": ["Seven"]},
            [],
        )

        assert tokens == 0
        assert "This came through Fridays chat and was answered by Seven directly." in answer

    assert prompts[0].split("reply with ", 1)[1].split(" ", 1)[0] in seven_agent._fridays_chat_verification_response(prompts[0])
    assert "CLICK_SEVEN_OK_0606" in seven_agent._fridays_chat_verification_response(prompts[1])


def test_creative_fallback_answers_short_story_when_model_is_down(monkeypatch):
    from agents.seven import seven_agent

    monkeypatch.setattr(seven_agent, "_read_state", lambda: {"tickets": 0, "proposals": 0, "local_agents": ["Seven"]})
    monkeypatch.setattr(seven_agent, "_load_memory", lambda _message: [])
    monkeypatch.setattr(seven_agent, "_llm_chat", lambda *args, **kwargs: (None, 0))

    answer, tokens = seven_agent.chat("Hello Seven, tell me a story made of 12 words")

    assert tokens == 0
    assert "state read only" not in answer
    assert len(answer.split()) == 12


def test_about_yourself_question_uses_identity_path(monkeypatch):
    from agents.seven import seven_agent

    monkeypatch.setattr(seven_agent, "_load_identity_beliefs", lambda *args, **kwargs: [])

    answer, tokens = seven_agent._compose(
        "Tell me something interesting about yourself?",
        {"tickets": 0, "proposals": 0, "local_agents": ["Seven"]},
        [],
    )

    assert tokens == 0
    assert answer is not None
    assert "Tell me something interesting about yourself?" not in answer
    assert "Seven" in answer


def test_wrapped_about_yourself_question_uses_latest_user_message(monkeypatch):
    from agents.seven import seven_agent

    monkeypatch.setattr(seven_agent, "_load_identity_beliefs", lambda *args, **kwargs: [])
    monkeypatch.setattr(seven_agent, "_read_state", lambda: {"tickets": 0, "proposals": 0, "local_agents": ["Seven"]})
    monkeypatch.setattr(seven_agent, "_load_memory", lambda _message: [])

    wrapped = (
        "=== Shared conversation thread (latest) ===\n"
        "USER -> SEVEN: Tell me something interesting about yourself?\n"
        "SEVEN -> USER: Tell me something interesting about yourself?\n\n"
        "=== New user message ===\n"
        "Tell me something interesting about yourself?"
    )

    answer, tokens = seven_agent.chat(wrapped)

    assert tokens == 0
    assert "Tell me something interesting about yourself?" not in answer
    assert "Seven" in answer


def test_echo_response_is_rejected():
    from agents.seven import seven_agent

    assert seven_agent._is_echo_response(
        "Tell me something interesting about yourself?",
        "Tell me something interesting about yourself?",
    )
    assert not seven_agent._is_echo_response(
        "Tell me something interesting about yourself?",
        "I am Seven, the local swarm companion.",
    )
