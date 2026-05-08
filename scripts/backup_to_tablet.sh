#!/usr/bin/env bash
# scripts/backup_to_tablet.sh — manual-only Samsung tablet sync.
#
# MTP via gvfs is *not* a real filesystem and is unreliable for cron.
# Run this by hand when the tablet is plugged in and unlocked.
#
# It locates the newest local tarball under ~/swarm-backups/ and copies it
# (plus its sidecars) to the tablet's gvfs MTP path.

set -u

TABLET_GVFS="/run/user/$(id -u)/gvfs"
LOCAL_DIR="$HOME/swarm-backups"

if [[ ! -d "$LOCAL_DIR" ]]; then
  echo "[tablet] no local backup dir at $LOCAL_DIR — run scripts/backup_swarm.sh local first" >&2
  exit 1
fi

# Find a Samsung MTP mount under gvfs.
mount_dir="$(ls -1 "$TABLET_GVFS" 2>/dev/null | grep -i 'mtp.*SAMSUNG' | head -1)"
if [[ -z "$mount_dir" ]]; then
  echo "[tablet] no Samsung MTP mount found under $TABLET_GVFS" >&2
  echo "[tablet] plug in the tablet, unlock it, and accept the file-transfer prompt." >&2
  exit 2
fi

base="$TABLET_GVFS/$mount_dir"
echo "[tablet] mount: $base"

# Pick a writable storage on the tablet (Internal storage / SD card).
target_storage=""
for cand in "$base"/*/; do
  name="$(basename "$cand")"
  case "$name" in
    *Internal*|*Phone*|*Card*) target_storage="$cand"; break ;;
  esac
done
if [[ -z "$target_storage" ]]; then
  target_storage="$(ls -1d "$base"/*/ 2>/dev/null | head -1)"
fi
if [[ -z "$target_storage" ]]; then
  echo "[tablet] no storage found inside $base" >&2
  exit 3
fi

dest="$target_storage/SwarmBackups"
mkdir -p "$dest" 2>/dev/null || true
echo "[tablet] dest: $dest"

# Newest local tarball.
latest="$(ls -1t "$LOCAL_DIR"/swarm-*.tar.gz 2>/dev/null | head -1)"
if [[ -z "$latest" ]]; then
  echo "[tablet] no local tarball found in $LOCAL_DIR" >&2
  exit 4
fi
base_name="$(basename "$latest" .tar.gz)"

echo "[tablet] copying $base_name (this can take a few minutes over MTP)..."
cp "$latest"               "$dest/" || { echo "[tablet] copy failed (tarball)" >&2; exit 5; }
cp "${latest}.sha256"      "$dest/" 2>/dev/null || true
cp "$LOCAL_DIR/$base_name.manifest.json" "$dest/" 2>/dev/null || true

echo "[tablet] OK — $base_name → $dest"
