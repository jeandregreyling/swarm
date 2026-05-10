#!/usr/bin/env python3
import sys
sys.path.insert(0, '/home/seven/swarm')

from core.knowledge.projects import create_project, add_step, add_blackboard_note, update_step_status

# Create POTATOFARM project
project_id = create_project(
    'POTATOFARM — Multi-Platform Hive Node Farm',
    description='Deploy SWARM Hive agents across 5 devices: DELL Linux (primary), Samsung S9 FE (Android), MacBook M1 (macOS), DELL Windows (secondary SSD), iPhone 17 Pro (iOS). All nodes connected via Tailscale mesh.',
    owner='seven',
    methodology='mixed',
    tags='hive,potato-farm,multi-node,tailscale',
    idempotency_key='potatofarm-20260510',
)
print('Project created:', project_id)

steps = [
    ('potato-1 — DELL Linux (primary): verify leader running on 100.87.66.45:5050',
     'Verify SWARM terminal is healthy, Hive endpoints reachable, enrollment endpoint active.'),
    ('potato-2 — Samsung S9 FE (Android): build APK, install, enroll, verify NPU detection',
     'Build android/hive-agent APK, install via ADB/MTP, enroll as potato-2 with leader 100.87.66.45:5050, verify inference.npu + inference.gpu capabilities in telemetry.'),
    ('potato-3 — MacBook M1 (macOS): create installer, ship, enroll',
     'Package install_macos_m1.sh, ship to MacBook via Tailscale download, enroll as potato-3, verify launchd agent starts.'),
    ('potato-4 — DELL Windows (secondary SSD): fix installer, stage to NTFS',
     'Fix install_windows.ps1 gaps, copy to /mnt/llm shared NTFS, user reboots and runs installer, enrolls as potato-4.'),
    ('potato-5 — iPhone 17 Pro (iOS): scaffold Swift project, enroll',
     'Create ios/hive-agent Xcode project with Background Fetch + CoreML, build for device, enroll as potato-5.'),
    ('Termux task runner: create Python job executor for Android GPU/NPU tasks',
     'Build core/hive/termux_runner.py that polls /api/hive/policy, pulls jobs, executes TFLite inference on Samsung NPU, reports results.'),
    ('Cross-node task routing: capability-based scheduler',
     'Configure scheduler to route inference.npu -> potato-2, inference.coreml -> potato-5, inference.ollama -> potato-1, light CPU -> any available.'),
]

step_ids = []
for title, desc in steps:
    sid = add_step(project_id, title, description=desc, owner='agent-eighteen')
    step_ids.append(sid)
    print(f'  Step: {sid}')

note = add_blackboard_note(
    project_id,
    'POTATOFARM kickoff — May 10, 2026. 5-node Tailscale mesh: DELL Linux (100.87.66.45), Samsung S9 FE (100.96.126.121), MacBook M1 (100.105.212.27), DELL Windows (shared NTFS), iPhone 17 Pro (100.115.205.65). Leader: http://100.87.66.45:5050. Apple Developer account available for iOS.',
    author='agent-eighteen'
)
print('Blackboard note:', note)
print('Project ID:', project_id)
print('Steps:', step_ids)
