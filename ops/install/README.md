# Swarm Hive — node install

Ship a node in three commands. Pick your platform.

The agent ships in this repo as a single std-lib Python file
([`ops/hive_agent.py`](../hive_agent.py)) and three idempotent installers.
The leader runs the existing Swarm terminal service on port 5050 and
exposes `/api/hive/*`.

## Linux (systemd user unit)

```bash
git clone <swarm-repo> ~/swarm && cd ~/swarm
SWARM_HIVE_LEADER=http://leader.local:5050 ops/install/install_linux.sh
```

The script registers `swarm-hive-agent.service` under your user
systemd, enrols with the leader, and starts the sampling loop. Tail it
with `journalctl --user -u swarm-hive-agent.service -f`.

## macOS (launchd LaunchAgent)

```bash
git clone <swarm-repo> ~/swarm && cd ~/swarm
SWARM_HIVE_LEADER=http://leader.local:5050 ops/install/install_macos.sh
```

Plist lands at `~/Library/LaunchAgents/com.swarm.hive.agent.plist`. Logs
in `~/Library/Logs/swarm-hive/agent.{out,err}.log`.

## Windows (Task Scheduler)

```powershell
git clone <swarm-repo> $HOME\swarm; cd $HOME\swarm
$env:SWARM_HIVE_LEADER = "http://leader.local:5050"
.\ops\install\install_windows.ps1
```

Creates a per-user logon task `SwarmHiveAgent`. Inspect with
`Get-ScheduledTask SwarmHiveAgent | Get-ScheduledTaskInfo`.

## Manual / one-shot

Without an installer:

```bash
ops/hive_agent.py --enrol --leader http://leader.local:5050
ops/hive_agent.py --run    --leader http://leader.local:5050 --interval 30
```

`--once` posts a single sample and exits. `--show` prints the contract
envelope without sending anything.

## Configuration

Per-user state lives in:

- Linux:   `~/.config/swarm-hive/agent.json`
- macOS:   `~/Library/Application Support/swarm-hive/agent.json`
- Windows: `%APPDATA%\swarm-hive\agent.json`

Override with `$SWARM_HIVE_AGENT_DIR`. The file is mode `0600` and holds
the leader URL, node id, and enrolment token.

Environment overrides (highest priority first):

| Var                        | Purpose                                   |
| -------------------------- | ----------------------------------------- |
| `SWARM_HIVE_LEADER`        | Leader URL (default `http://localhost:5050`) |
| `SWARM_HIVE_TOKEN`         | Enrolment token (overrides config file)   |
| `SWARM_NODE_ID`            | Pin a stable node id                      |
| `SWARM_HIVE_INTERVAL`      | Seconds between samples (installers only) |
| `SWARM_HIVE_AGENT_DIR`     | Per-user state directory                  |

Leader-side:

| Var                                  | Purpose                                  |
| ------------------------------------ | ---------------------------------------- |
| `SWARM_HIVE_DB`                      | Path to registry SQLite                  |
| `SWARM_HIVE_TOKENS`                  | Path to enrolment token store            |
| `SWARM_HIVE_REQUIRE_TOKEN=1`         | Reject `/api/hive/telemetry` without a valid token |
| `SWARM_HIVE_DISABLE_SELF_SAMPLER=1`  | Don't auto-sample the leader's own host  |
| `SWARM_HIVE_SELF_INTERVAL`           | Seconds between leader self-samples (default 30) |

## What the leader sees

After install, your node shows up in:

- `GET /api/hive/nodes` — list view
- `GET /api/hive/node/<node_id>` — detail + recent events
- `/ui` → Monitor tile → "Hive · Thermal & Performance" panel

The Monitor panel auto-refreshes every 20 s. Each card surfaces CPU
peak temp, fan rpm/PWM/mode, RAM%, on-battery state, and a
green→amber→red thermal-pressure dot.

## Uninstall

Linux:

```bash
systemctl --user disable --now swarm-hive-agent.service
rm ~/.config/systemd/user/swarm-hive-agent.service
```

macOS:

```bash
launchctl bootout gui/$(id -u)/com.swarm.hive.agent
rm ~/Library/LaunchAgents/com.swarm.hive.agent.plist
```

Windows:

```powershell
Unregister-ScheduledTask -TaskName SwarmHiveAgent -Confirm:$false
```

Then `DELETE /api/hive/node/<node_id>` from the leader to remove the
registry entry.
