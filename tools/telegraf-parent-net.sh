#!/bin/sh
# Read host namespace counters through the existing read-only /hostfs mount.
# Emit the same Telegraf net fields/topics as inputs.net, for physical NICs only.
set -eu
awk 'NR>2 {gsub(":", " "); print $1, $2, $10}' /hostfs/proc/1/net/dev |
while read -r interface rx tx; do
    case "$interface" in *[!a-zA-Z0-9_-]*) continue ;; esac
    [ -e "/hostfs/sys/class/net/$interface/device" ] || continue
    speed=$(cat "/hostfs/sys/class/net/$interface/speed" 2>/dev/null) || speed=-1
    case "$speed" in ''|*[!0-9-]*) speed=-1 ;; esac
    printf 'net,interface=%s bytes_recv=%si,bytes_sent=%si,speed=%si\n' "$interface" "$rx" "$tx" "$speed"
done
