#!/usr/bin/env bash
# Devcontainer entrypoint: provision the loop block devices that
# test-list-vm-disks requires (docker mounts a fresh /dev at container start,
# so build-time device nodes do not survive), then run the container command.
set -e

for n in 0 1; do
    if [[ ! -b /dev/loop$n ]]; then
        mknod "/dev/loop$n" b 7 "$n" 2>/dev/null || true
    fi
done

exec "$@"
