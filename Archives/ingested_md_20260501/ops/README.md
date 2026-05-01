# Swarm Ops Scripts

Boot is owned by systemd, not shell scripts. The legacy `start_stage*.sh` and
`startswarm.sh` launchers have been removed.

## Start / stop stages

| Stage            | Port | Unit                         | Command                                  |
|------------------|------|------------------------------|------------------------------------------|
| PROD             | 5050 | `swarm-terminal.service`     | `sudo systemctl start swarm-terminal`    |
| UAT  (asleep)    | 5053 | `swarm-terminal-uat.service` | `make wake-uat` / `make sleep-uat`       |
| DEV  (asleep)    | 5051 | `swarm-terminal-dev.service` | `make wake-dev` / `make sleep-dev`       |

`make status` prints the enabled/active state of every swarm unit.
`killswitch.sh` stops everything at once.

## Stage env files

`stage1.env`, `stage2.env`, `stage3.env` hold per-stage environment vars that
the systemd units load via `EnvironmentFile=`.
