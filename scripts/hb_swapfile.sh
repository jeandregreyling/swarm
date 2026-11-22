#!/bin/bash
# HB swap file on the NVMe (owner 14 Nov 2026). Run by JD through pkexec only - HB never runs this itself.
#   hb_swapfile.sh create <GB>   make and switch on /srv/hb-swapfile (1-64 GB)
#   hb_swapfile.sh remove        switch it off and delete it
#   hb_swapfile.sh status
set -euo pipefail
FILE=/srv/hb-swapfile
case "${1:-status}" in
  create)
    GB="${2:-}"
    [[ "$GB" =~ ^[0-9]+$ ]] && [ "$GB" -ge 1 ] && [ "$GB" -le 64 ] || { echo "size must be 1-64 (GB)"; exit 2; }
    [ -e "$FILE" ] && { echo "$FILE already exists; remove it first"; exit 3; }
    FREE=$(df --output=avail -BG /srv | tail -1 | tr -dc '0-9')
    [ "$FREE" -ge $((GB + 20)) ] || { echo "not enough disk: ${FREE} GB free, need $((GB + 20))"; exit 4; }
    fallocate -l "${GB}G" "$FILE"; chmod 600 "$FILE"; mkswap "$FILE" >/dev/null; swapon --priority -10 "$FILE"
    echo "swap on: ${GB} GB at $FILE (not in fstab: it is gone after a reboot until created again)";;
  remove)
    [ -e "$FILE" ] || { echo "no $FILE"; exit 0; }
    swapoff "$FILE" 2>/dev/null || true; rm -f "$FILE"; echo "swap off and $FILE deleted";;
  status)
    swapon --show=NAME,SIZE,USED --noheadings | grep -F "$FILE" || echo "no HB swap file";;
  *) echo "use: create <GB> | remove | status"; exit 2;;
esac
