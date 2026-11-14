# HB Operating Index

This document serves as a concise index of the core HB files and their functionalities, as well as an overview of the capabilities that are yet to be verified.

## Core Files

- **core/hb_tasks.py**: Manages durable identities and evidence.
- **core/peer_turns.py**: Handles continuation and decisions.
- **core/apex_turn_queue.py**: Implements a single-model FIFO queue.
- **core/hb_local_jobs.py**: Manages background work.
- **core/peer_coordination.py**: Supervises workers.
- **core/apex_tools.py**: Provides schemas, patch, and test tools.
- **core/apex_knowledge.py**: Manages Knowledge Centre reads.
- **core/hb_workflow.py**: Manages backlog and runtime.

## Frontend Files

- **frontend/blueprints/shell.py**: Manages the terminal.
- **lib/system/monitor.py**: Provides system sensors.
- **frontend/static/js/views/chat.js**: Manages the chat UI.
- **frontend/static/js/views/home-chat.js**: Manages the home chat UI.
- **frontend/static/js/views/terminal.js**: Manages the terminal UI.
- **frontend/static/js/views/trace.js**: Manages the tracer tool.
- **frontend/static/js/core/theme.js**: Manages themes.
- **frontend/blueprints/email_bp.py**: Manages the inbox.

## Unverified Capabilities

- **Queueing questions and tasks for HB**.
- **System awareness (RAM status, CPU usage, GPU usage, temperature, fan speed, network activity, errors recorded in the tracer tool)**.
- **Fixing and making the HB terminal usable**.
- **Inspecting tiles and applying themes**.
- **Removing redundant system tabs**.
- **Improving the Knowledge Centre's functionality**.
- **Teaching how to check emails**.

## Child Steps

- **Queue**: S-1F190850A6
- **Telemetry**: S-8242AA2C1C
- **Terminal**: S-1CD2512277
- **Tiles/Themes**: S-915FA2DD12
- **Knowledge Centre**: S-8E9A07CFD9
- **Training**: S-28AAD5F64E
