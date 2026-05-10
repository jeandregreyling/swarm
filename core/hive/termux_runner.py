#!/usr/bin/env python3
"""core.hive.termux_runner — Python task executor for Android (Termux).

Polls the SWARM leader for jobs, executes TFLite inference on Samsung
NPU/GPU via NNAPI delegates, and reports results back.

Usage in Termux:
    pkg install python python-pip
    pip install requests numpy
    python termux_runner.py --leader http://100.87.66.45:5050 --node-id potato-2
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from typing import Any, Dict, Optional

import requests

_LOG = logging.getLogger(__name__)

# Capability advertisement for this runner
CAPABILITIES = ["inference.cpu", "inference.tflite", "inference.gpu", "inference.npu"]


def _is_termux() -> bool:
    return "/com.termux/" in os.environ.get("PREFIX", "")


def _get_battery() -> dict:
    """Best-effort battery status via termux-battery-status."""
    import shutil
    import subprocess
    exe = shutil.which("termux-battery-status")
    if not exe:
        return {}
    try:
        out = subprocess.run([exe], capture_output=True, text=True, timeout=4)
        if out.returncode == 0:
            return json.loads(out.stdout or "{}")
    except Exception:
        pass
    return {}


def _build_telemetry(node_id: str) -> dict:
    """Contract-v0 telemetry for Termux path."""
    from core.hive.providers.android import AndroidProvider
    p = AndroidProvider()
    sample = p.sample()
    return {
        "contract": "node.resource/v0",
        "node_id": node_id,
        "platform": "android",
        "ts": int(time.time()),
        **sample,
        "capabilities": p.capabilities(),
    }


def _enrol(leader: str, node_id: str) -> str:
    """Enrol with leader, return token."""
    url = leader.rstrip("/") + "/api/hive/enrol"
    body = {"node_id": node_id, "platform": "android"}
    resp = requests.post(url, json=body, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    token = data.get("token", "")
    _LOG.info("Enrolled: node_id=%s token=%s...", node_id, token[:8])
    return token


def _post_telemetry(leader: str, token: str, payload: dict) -> None:
    url = leader.rstrip("/") + "/api/hive/telemetry"
    headers = {"X-Hive-Token": token}
    resp = requests.post(url, json=payload, headers=headers, timeout=15)
    if not resp.ok:
        _LOG.warning("Telemetry POST failed: %s %s", resp.status_code, resp.text[:200])


def _fetch_policy(leader: str, token: str, node_id: str) -> dict:
    """Fetch current policy for this node."""
    url = leader.rstrip("/") + f"/api/hive/node/{node_id}"
    headers = {"X-Hive-Token": token}
    resp = requests.get(url, headers=headers, timeout=10)
    if resp.ok:
        data = resp.json()
        return data.get("node", {}).get("policy", {})
    return {}


def _fetch_job(leader: str, token: str, node_id: str) -> Optional[dict]:
    """Pull next job from leader. Returns None if no work."""
    # TODO: implement /api/hive/jobs/next when scheduler is ready
    # For now, stub — real implementation will come in scheduler phase
    return None


def _run_tflite_job(job: dict) -> dict:
    """Execute a TFLite inference job. Uses NNAPI delegate when available."""
    model_path = job.get("model_path")
    input_data = job.get("input")
    if not model_path or not os.path.exists(model_path):
        return {"ok": False, "error": f"model not found: {model_path}"}

    try:
        import tensorflow as tf
        interpreter = tf.lite.Interpreter(
            model_path=model_path,
            experimental_delegates=[tf.lite.experimental.load_delegate("libnnapi.so")],
        )
        interpreter.allocate_tensors()
        input_details = interpreter.get_input_details()
        output_details = interpreter.get_output_details()
        interpreter.set_tensor(input_details[0]["index"], input_data)
        interpreter.invoke()
        output = interpreter.get_tensor(output_details[0]["index"])
        return {"ok": True, "output": output.tolist()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _report_result(leader: str, token: str, node_id: str, job_id: str, result: dict) -> None:
    """Report job completion back to leader."""
    url = leader.rstrip("/") + "/api/hive/jobs/report"
    headers = {"X-Hive-Token": token}
    body = {"node_id": node_id, "job_id": job_id, "result": result}
    resp = requests.post(url, json=body, headers=headers, timeout=15)
    if not resp.ok:
        _LOG.warning("Job report failed: %s", resp.status_code)


def main() -> int:
    parser = argparse.ArgumentParser(description="Termux Hive task runner")
    parser.add_argument("--leader", default="http://localhost:5050", help="SWARM leader URL")
    parser.add_argument("--node-id", default="potato-2", help="Node ID")
    parser.add_argument("--interval", type=int, default=30, help="Telemetry interval (seconds)")
    parser.add_argument("--token", default="", help="Existing enrollment token")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if not _is_termux():
        _LOG.warning("Not running in Termux; some features may not work.")

    token = args.token or _enrol(args.leader, args.node_id)
    _LOG.info("Termux runner started: leader=%s node_id=%s", args.leader, args.node_id)

    while True:
        try:
            # 1. Post telemetry
            telem = _build_telemetry(args.node_id)
            _post_telemetry(args.leader, token, telem)

            # 2. Check policy
            policy = _fetch_policy(args.leader, token, args.node_id)
            if policy.get("accept_jobs") is False:
                _LOG.info("Policy says pause; sleeping.")
                time.sleep(args.interval)
                continue

            # 3. Check battery before heavy work
            batt = _get_battery()
            pct = batt.get("percentage")
            plugged = (batt.get("plugged") or "").upper()
            on_battery = not plugged.startswith("PLUGGED")
            if on_battery and isinstance(pct, int) and pct < 20:
                _LOG.info("Battery low (%d%%); skipping job poll.", pct)
                time.sleep(args.interval)
                continue

            # 4. Fetch and run job
            job = _fetch_job(args.leader, token, args.node_id)
            if job:
                _LOG.info("Running job: %s", job.get("job_id"))
                result = _run_tflite_job(job)
                _report_result(args.leader, token, args.node_id, job["job_id"], result)

        except Exception as e:
            _LOG.exception("Tick failed: %s", e)

        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
