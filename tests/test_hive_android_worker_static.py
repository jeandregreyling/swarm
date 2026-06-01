from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_hive_worker_supports_dynamic_join_deep_link():
    manifest = (ROOT / "android/hive-agent/app/src/main/AndroidManifest.xml").read_text()
    main = (ROOT / "android/hive-agent/app/src/main/java/com/swarm/hive/MainActivity.kt").read_text()

    assert 'android:scheme="swarmhive"' in manifest
    assert 'android:host="join"' in manifest
    assert 'parseJoinIntent' in main
    assert 'DEFAULT_LEADER = "http://100.87.66.45:5050"' in main
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
