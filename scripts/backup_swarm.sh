#!/usr/bin/env bash
# scripts/backup_swarm.sh — PACKET-10A backup driver.
#
# Captures a hot-safe snapshot of the swarm state to a chosen destination.
# Targets:
#   local  → ~/swarm-backups/                         (always available)
#   ntfs   → /mnt/llm/swarm-backups/                  (if NTFS partition mounted)
#   usb    → /media/seven/462B-E832/swarm-backups/    (if USB plugged in)
#   all    → all of the above whose destinations are reachable
#
# Output per run, per target:
#   swarm-YYYYMMDD-HHMMSS-<host>.tar.gz
#   swarm-YYYYMMDD-HHMMSS-<host>.tar.gz.sha256
#   swarm-YYYYMMDD-HHMMSS-<host>.manifest.json
#
# Retention (per target):
#   keep last 14 most-recent tarballs.
#
# Audit:
#   appends one JSONL line per (target, outcome) to runtime/backups/log.jsonl.
#
# Exit codes:
#   0 = at least one target succeeded
#   1 = caller error (unknown target, repo not found)
#   2 = all reachable targets failed
#
# Safe to run while the Flask app + Vortex are live: uses sqlite3 .backup for
# the DB snapshot (online-consistent) and never modifies the source tree.

set -u

REPO="${SWARM_ROOT:-/home/seven/swarm}"
LOG_DIR="$REPO/runtime/backups"
LOG_FILE="$LOG_DIR/log.jsonl"
EXCLUDES="$REPO/scripts/backup_excludes.txt"
RETENTION="${SWARM_BACKUP_RETENTION:-14}"
HOST="$(hostname -s 2>/dev/null || echo host)"
STAMP="$(date +%Y%m%d-%H%M%S)"

# ── targets ────────────────────────────────────────────────────────────────
declare -A TARGETS=(
  [local]="$HOME/swarm-backups"
  [ntfs]="/mnt/llm/swarm-backups"
  [usb]="/media/seven/462B-E832/swarm-backups"
)

usage() {
  cat <<EOF
backup_swarm.sh — PACKET-10A backup driver

Usage:
  $0 <target>
  $0 all

Targets:
  local   ~/swarm-backups/
  ntfs    /mnt/llm/swarm-backups/    (skipped if /mnt/llm not mounted)
  usb     /media/seven/462B-E832/swarm-backups/ (skipped if not mounted)
  all     every reachable target above

Env:
  SWARM_ROOT               (default: /home/seven/swarm)
  SWARM_BACKUP_RETENTION   (default: 14)

Exit:
  0 ok · 1 caller error · 2 all reachable targets failed
EOF
}

if [[ $# -lt 1 ]]; then usage; exit 1; fi
SELECTED="$1"

if [[ ! -d "$REPO" ]]; then
  echo "[backup] FATAL: repo not found at $REPO" >&2
  exit 1
fi

if [[ ! -f "$EXCLUDES" ]]; then
  echo "[backup] FATAL: excludes file missing at $EXCLUDES" >&2
  exit 1
fi

mkdir -p "$LOG_DIR"

# ── per-target validators ──────────────────────────────────────────────────
target_reachable() {
  local key="$1"
  local dest="${TARGETS[$key]}"
  case "$key" in
    local)
      mkdir -p "$dest" 2>/dev/null && [[ -w "$dest" ]]
      ;;
    ntfs)
      # /mnt/llm uses systemd autofs — touching it triggers mount.
      ls /mnt/llm >/dev/null 2>&1 && \
        mountpoint -q /mnt/llm && \
        mkdir -p "$dest" 2>/dev/null && [[ -w "$dest" ]]
      ;;
    usb)
      mountpoint -q "/media/seven/462B-E832" 2>/dev/null && \
        mkdir -p "$dest" 2>/dev/null && [[ -w "$dest" ]]
      ;;
    *) return 1 ;;
  esac
}

# ── audit log writer ───────────────────────────────────────────────────────
log_event() {
  local target="$1" outcome="$2" payload="$3"
  local ts
  ts="$(date -Is)"
  printf '{"ts":"%s","host":"%s","target":"%s","outcome":"%s",%s}\n' \
    "$ts" "$HOST" "$target" "$outcome" "$payload" >> "$LOG_FILE"
}

# ── DB hot-snapshot (online consistent) ────────────────────────────────────
snapshot_db() {
  local base_dir="$1"
  # Snapshot lives at <tmp>/db-snapshot/ — that is the path inside the tarball.
  local out_dir="$base_dir/db-snapshot"
  mkdir -p "$out_dir"
  local rc=0
  if [[ -f "$REPO/swarm_memory.db" ]]; then
    sqlite3 "$REPO/swarm_memory.db" ".backup '$out_dir/swarm_memory.db'" || rc=$?
    if [[ $rc -ne 0 ]]; then
      echo "[backup] WARN: sqlite3 .backup failed rc=$rc" >&2
      return $rc
    fi
    # Integrity-check the snapshot before we tar it up.
    local check
    check="$(sqlite3 "$out_dir/swarm_memory.db" 'PRAGMA integrity_check;' 2>&1 | head -1)"
    if [[ "$check" != "ok" ]]; then
      echo "[backup] FATAL: snapshot integrity_check returned: $check" >&2
      return 9
    fi
    echo "[backup] DB snapshot ok ($(stat -c%s "$out_dir/swarm_memory.db" 2>/dev/null || echo ? ) bytes)"
  fi
  if [[ -f "$REPO/swarm.db" ]]; then
    cp "$REPO/swarm.db" "$out_dir/swarm.db"
  fi
  return 0
}

# ── one full backup to one destination ─────────────────────────────────────
do_target() {
  local key="$1"
  local dest="${TARGETS[$key]}"
  local archive="$dest/swarm-${STAMP}-${HOST}.tar.gz"
  local sha_file="${archive}.sha256"
  local manifest="${archive%.tar.gz}.manifest.json"
  local tmp_db
  tmp_db="$(mktemp -d -t swarm-backup-db.XXXXXX)"
  local rc=0

  echo "[backup:$key] starting → $archive"
  local started_at
  started_at="$(date +%s)"

  # Phase 1: DB snapshot (online-consistent).
  if ! snapshot_db "$tmp_db"; then
    rc=$?
    rm -rf "$tmp_db"
    log_event "$key" "fail_db_snapshot" \
      "\"archive\":\"$archive\",\"error\":\"sqlite3_backup_rc=$rc\""
    return 1
  fi

  # Phase 2: tar repo + DB snapshot together.
  # We pass two transform-rooted sources: the repo (excluding hot DB) and the
  # DB snapshot dir, renamed to live at top-level inside the archive.
  local exit_tar=0
  tar \
    --warning=no-file-changed \
    --warning=no-file-removed \
    --exclude-from="$EXCLUDES" \
    -czf "$archive" \
    -C "$REPO" . \
    -C "$tmp_db" ./db-snapshot \
    2> >(tee /tmp/swarm-backup-tar.err >&2) || exit_tar=$?

  rm -rf "$tmp_db"

  # tar exit 1 = "files changed while reading" — acceptable for live ledger
  # files; the DB snapshot itself was already integrity-checked. Treat 0/1 ok,
  # everything else as fail.
  if [[ $exit_tar -ne 0 && $exit_tar -ne 1 ]]; then
    log_event "$key" "fail_tar" \
      "\"archive\":\"$archive\",\"error\":\"tar_rc=$exit_tar\""
    rm -f "$archive"
    return 1
  fi

  # Phase 3: SHA256 sidecar.
  ( cd "$dest" && sha256sum "$(basename "$archive")" > "$sha_file" )

  # Phase 4: manifest.
  local size
  size="$(stat -c%s "$archive" 2>/dev/null || echo 0)"
  local file_count
  file_count="$(tar -tzf "$archive" 2>/dev/null | wc -l)"
  local finished_at
  finished_at="$(date +%s)"
  local duration=$(( finished_at - started_at ))

  cat > "$manifest" <<JSON
{
  "stamp":          "$STAMP",
  "host":           "$HOST",
  "repo":           "$REPO",
  "target":         "$key",
  "archive":        "$archive",
  "size_bytes":     $size,
  "file_count":     $file_count,
  "tar_exit_code":  $exit_tar,
  "started_at":     $started_at,
  "finished_at":    $finished_at,
  "duration_s":     $duration,
  "swarm_branch":   "$(cd "$REPO" && git branch --show-current 2>/dev/null || echo unknown)",
  "swarm_commit":   "$(cd "$REPO" && git rev-parse --short HEAD 2>/dev/null || echo unknown)"
}
JSON

  echo "[backup:$key] ok → $size bytes · $file_count files · ${duration}s"

  # Phase 5: retention prune.
  prune_target "$dest"

  log_event "$key" "ok" \
    "\"archive\":\"$archive\",\"size\":$size,\"files\":$file_count,\"duration_s\":$duration,\"tar_rc\":$exit_tar"
  return 0
}

prune_target() {
  local dest="$1"
  # Keep $RETENTION newest .tar.gz; remove their stale siblings (.sha256,
  # .manifest.json) that no longer have a partner archive.
  local kept=()
  while IFS= read -r f; do kept+=("$f"); done < <(
    ls -1t "$dest"/swarm-*.tar.gz 2>/dev/null | head -n "$RETENTION"
  )
  local keep_names=" "
  for f in "${kept[@]}"; do keep_names+="$(basename "${f%.tar.gz}") "; done

  # Drop any older tar.gz + sidecars.
  for f in "$dest"/swarm-*.tar.gz; do
    [[ -f "$f" ]] || continue
    local base; base="$(basename "${f%.tar.gz}")"
    if [[ "$keep_names" != *" $base "* ]]; then
      rm -f "$f" "${f}.sha256" "${f%.tar.gz}.manifest.json"
    fi
  done
}

# ── main dispatch ──────────────────────────────────────────────────────────
declare -a TO_RUN
case "$SELECTED" in
  all)
    for k in local ntfs usb; do
      if target_reachable "$k"; then
        TO_RUN+=("$k")
      else
        echo "[backup:$k] unreachable, skipping"
        log_event "$k" "skip_unreachable" "\"reason\":\"destination_not_mounted_or_unwritable\""
      fi
    done
    ;;
  local|ntfs|usb)
    if target_reachable "$SELECTED"; then
      TO_RUN+=("$SELECTED")
    else
      echo "[backup:$SELECTED] unreachable" >&2
      log_event "$SELECTED" "skip_unreachable" "\"reason\":\"destination_not_mounted_or_unwritable\""
      exit 2
    fi
    ;;
  *) usage; exit 1 ;;
esac

if [[ ${#TO_RUN[@]} -eq 0 ]]; then
  echo "[backup] nothing reachable — no targets ran" >&2
  exit 2
fi

succeeded=0
for k in "${TO_RUN[@]}"; do
  if do_target "$k"; then
    succeeded=$((succeeded+1))
  fi
done

if [[ $succeeded -gt 0 ]]; then
  exit 0
else
  exit 2
fi
