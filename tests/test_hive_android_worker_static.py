import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_hive_worker_supports_dynamic_join_deep_link():
    manifest = (ROOT / "android/hive-agent/app/src/main/AndroidManifest.xml").read_text()
    main = (ROOT / "android/hive-agent/app/src/main/java/com/swarm/hive/MainActivity.kt").read_text()

    assert 'android:scheme="swarmhive"' in manifest
    assert 'android:host="join"' in manifest
    assert 'parseJoinIntent' in main
    assert re.search(r'DEFAULT_LEADER = "http://[0-9.]+:5050"', main)   # the Tailscale address changes; the form does not
    assert 'node_id' in main


def test_hive_worker_reports_gpu_capacity_proof():
    service = (ROOT / "android/hive-agent/app/src/main/java/com/swarm/hive/HiveAgentService.kt").read_text()
    sampler = (ROOT / "android/hive-agent/app/src/main/java/com/swarm/hive/AndroidSampler.kt").read_text()
    probe = (ROOT / "android/hive-agent/app/src/main/java/com/swarm/hive/GpuProbe.kt").read_text()

    assert '"tflite.gpu"' in service
    assert '"tiny.gpu.benchmark"' in service
    assert 'put("gpu_probe", GpuProbe.run(' in service
    assert 'put("capacity_score", capacityScore(models))' in probe
    assert '"seven-app.gpu.capsule"' in sampler


def test_hive_worker_uses_apex_node_chat_contract():
    main = (ROOT / "android/hive-agent/app/src/main/java/com/swarm/hive/MainActivity.kt").read_text()
    node = (ROOT / "android/hive-agent/app/src/main/java/com/swarm/hive/ApexNode.kt").read_text()
    payload = (ROOT / "android/hive-agent/app/src/main/java/com/swarm/hive/ApexPayloadBuilder.kt").read_text()
    client = (ROOT / "android/hive-agent/app/src/main/java/com/swarm/hive/ApexClient.kt").read_text()
    strings = (ROOT / "android/hive-agent/app/src/main/res/values/strings.xml").read_text()

    assert 'sendChatButton.setOnClickListener { sendApexChat() }' in main
    assert 'apex.handle(sessionId, prompt)' in main
    assert 'ApexClient.complete(builder.build(sessionId))' in node
    assert '/v1/chat/completions' in payload
    assert 'ApexPayloadBuilder.ENDPOINT' in client
    assert '"gpt-oss:20B"' in payload
    assert '"/api/localai/ollama/shared-chat"' not in main
    assert 'Dell Ollama' not in strings
