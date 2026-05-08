# Listener Restart Timeout Runbook (S-1C7E3AC503)

> Last updated: 2026-05-02 — Session 28 backlog burndown

## Symptom

`systemctl restart swarm-listener` (or the `pkill -f core/pipeline/listener`
+ relaunch pattern) takes >30 s to return, times out, or leaves a zombie
listener process hanging on a stuck IMAP socket.

Typical surfaces:
- Approval reply not picked up for 60+ seconds after restart.
- `journalctl -u swarm-listener` shows `IMAP4 connection timed out` then
  retries indefinitely.
- `/api/health/services` reports `listener` with a stale `last_beat_at`.

## Quick triage

1. **Confirm it's actually stuck:**
   ```bash
   ps -ef | grep -E 'listener\.py' | grep -v grep
   ```
   If you see two PIDs older than ~10 s, the prior process did not exit.

2. **Check current heartbeat:**
   ```bash
   sqlite3 /home/seven/swarm/swarm_memory.db \
     "SELECT service_name, last_beat_at, restart_count FROM service_heartbeat;"
   ```
   `last_beat_at` more than ~120 s old means the loop is wedged.

3. **Force-kill the wedged listener:**
   ```bash
   pkill -9 -f 'core/pipeline/listener.py'
   sleep 1
   pgrep -f 'core/pipeline/listener.py' || echo 'listener fully stopped'
   ```

## Restart sequence

```bash
cd /home/seven/swarm
pkill -f 'core/pipeline/listener.py' 2>/dev/null
sleep 1
nohup python3 -u core/pipeline/listener.py \
  > /tmp/swarm-listener.log 2>&1 < /dev/null & disown
sleep 2
pgrep -f 'core/pipeline/listener.py' | head -1
tail -n 20 /tmp/swarm-listener.log
```

Expected: a single PID and a log line like `[Listener] startup complete`.

## Root-cause checks

| Symptom in log                        | Likely cause                     | Action                                    |
|---------------------------------------|----------------------------------|-------------------------------------------|
| `imaplib.IMAP4.abort: socket error`   | Network blip / Gmail rate limit  | Wait 30 s, restart again, no change to code |
| `OperationalError: database is locked`| Long-running query in another svc| Restart `swarm-terminal` first, then listener |
| `RecursionError`                      | Bad config in `utils/config.py`  | Roll back last config commit              |
| `ImportError: agents.ghost.duck`      | Stale `__pycache__`              | `find . -name __pycache__ -exec rm -rf {} +` |
| Listener exits 0 immediately          | Missing env var (e.g. `GMAIL_*`) | Re-source `~/.config/swarm/env`           |

## When to escalate

- Three restarts in 5 minutes → flag `service_heartbeat.restart_count` warning.
- Listener cannot reach the DB → check `SWARM_DB_PATH` is set and the file exists.
- IMAP login fails repeatedly → app password rotated; re-read `utils/config.py`
  comments around `GMAIL_LISTENER_PASSWORD`.

## Verification

After restart:
```bash
curl -s --max-time 4 http://127.0.0.1:5050/api/health/services \
  | python3 -m json.tool
```
Look for the `listener` row with a fresh `last_beat_at` and zero
`warnings` entries naming the listener.
