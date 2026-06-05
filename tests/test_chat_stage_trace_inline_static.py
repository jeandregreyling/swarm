from pathlib import Path


def test_completed_server_traces_are_not_replayed_as_bottom_bubbles():
    src = Path("frontend/static/js/views/chat.js").read_text(encoding="utf-8")

    assert "window.__fridaysInlineJobTraceIds = inlineJobIds" in src
    assert "if (inlineJobIds.has(jobId)) return;" in src
    assert "if (status === 'completed') return;" in src
    assert "stageTrace: inlineTraceByMessageId[msgId] || []" in src


def test_server_trace_matching_uses_response_message_time():
    src = Path("frontend/static/js/views/chat.js").read_text(encoding="utf-8")

    assert "const inlineTraceByMessageId = (() => {" in src
    assert "const jobTime = Date.parse" in src
    assert "const rowTime = Date.parse" in src
    assert "bestDelta <= 180000" in src


def test_running_pending_bubbles_survive_thread_rerender():
    src = Path("frontend/static/js/views/chat.js").read_text(encoding="utf-8")

    assert "const carriedPending = []" in src
    assert "activeJobIds.has(jobId)" in src
    assert "carriedPending.forEach(node => messages.appendChild(node));" in src


def test_pending_bubbles_use_friendly_stage_labels():
    js = Path("frontend/static/js/views/chat.js").read_text(encoding="utf-8")
    css = Path("frontend/static/css/views/chat.css").read_text(encoding="utf-8")

    assert "function _friendlyThinkingStage" in js
    assert "Opening the local line" in js
    assert "Recovering the reply" in js
    assert "chat-thinking-visual" in js
    assert "@keyframes chat-thinking-spark" in css


def test_main_chat_adds_optimistic_pending_bubble_before_server_ack():
    src = Path("frontend/static/js/views/chat.js").read_text(encoding="utf-8")

    assert "const optimisticJobId = source === 'user'" in src
    assert "'pending-ui-'" in src
    assert "_appendThinkingBubble(selectedAgents[0] || 'agent', '', {" in src
    assert "_remapThinkingBubbleJobId(optimisticJobId, firstPending.job_id" in src
    assert "if (optimisticJobId) _removeThinkingBubbleById(optimisticJobId);" in src
    assert "jobId.startsWith('pending-ui-') && !jobsByID.has(jobId)" in src
    assert "if (jobId.startsWith('pending-ui-')) return false;" in src
