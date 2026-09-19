#!/usr/bin/env bash
# install-test-deps — Install all dependencies needed to run the test suite.
#
# Single source of truth for the test environment: consumed by
# .devcontainer/Dockerfile (as root) and .github/workflows/tests.yml
# (via sudo on the GitHub runner). Run it from the repository root on a
# Debian/Ubuntu system:
#
#     sudo share/dev/install-test-deps.sh
#
# System packages cover the product's core prerequisites (zfsutils-linux, pv,
# rsync, smartmontools), the GTK/PyGObject stack the GUI tests import, git
# (documentation-integrity tests shell out to it), and shellcheck. Python
# packages come from requirements-dev.txt plus the documentation tooling
# (mkdocs is pinned <2; pyyaml is required by the docs-integrity suite).

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends \
    bash \
    ca-certificates \
    git \
    python3 \
    python3-pip \
    python3-gi \
    gir1.2-gtk-3.0 \
    rsync \
    shellcheck \
    smartmontools \
    pv \
    sudo \
    xvfb \
    xauth \
    zfsutils-linux

# --break-system-packages is required on Ubuntu 24.04's externally-managed
# Python; it is accepted harmlessly where not required.
python3 -m pip install --break-system-packages \
    -r "$repo_root/requirements-dev.txt" \
    pyyaml \
    "mkdocs<2" \
    mkdocs-material

# A container runs as root against a repo volume owned by the host user;
# without this, git refuses to operate ("detected dubious ownership") and
# every git-dependent test fails. Harmless elsewhere.
git config --system --add safe.directory '*'

# Several suites source bin scripts that refuse to load without node
# configuration (e.g. zfsdelfs FATALs without it). THIS_HOST resolves when
# the file is sourced so the same config works in any container or VM.
cat > /etc/zfsutilities-node.conf <<'EOF'
NODE_MODE="single-node"
THIS_HOST="$(hostname -s)"
EOF

# Suites resolve shared libraries through the deployed-layout symlinks
# (find_zfsutility_script falls back to /usr/local/lib/zfsutilities/bin and
# /usr/local/lib). Recreate that wiring against this checkout. This script is
# for CI/containers only — it must not be run on a machine with a real
# deployment.
zfslib=/usr/local/lib/zfsutilities
mkdir -p "$zfslib"
ln -sfn "$repo_root" "$zfslib/current"
ln -sfn current/bin "$zfslib/bin"
for lib in iscsi-lib.sh node-lib.sh two-node-lib.sh; do
    ln -sfn "$zfslib/current/lib/$lib" "/usr/local/lib/$lib"
done
ln -sfn "$zfslib/current/bin/rootcheck" /usr/local/lib/rootcheck

# test-list-vm-disks symlinks fake iSCSI by-path entries at /dev/loopN and
# checks they resolve to block devices; containers usually have no loop
# nodes. mknod may be denied on some runners — /dev/loop* normally exists
# there already, hence the tolerated failure.
for n in 0 1; do
    [[ -b /dev/loop$n ]] || mknod "/dev/loop$n" b 7 "$n" 2>/dev/null || true
done
