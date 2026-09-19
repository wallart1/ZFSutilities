FROM ubuntu:24.04

# The install script is the single source of truth for test dependencies;
# it is also used by .github/workflows/tests.yml. Copy it (and the manifest
# it reads) at the same relative depth as in the repo so its repo-root
# resolution works.
COPY requirements-dev.txt /workspace/requirements-dev.txt
COPY share/dev/install-test-deps.sh /workspace/share/dev/install-test-deps.sh
RUN /workspace/share/dev/install-test-deps.sh \
    && rm -rf /workspace/share /workspace/requirements-dev.txt

# Test suites bootstrap via `source ~/bashinit` (the development-machine
# convention); the repo is mounted at /workspace at run time.
RUN ln -s /workspace/bin/bashinit /root/bashinit

# Provision loop block devices at container start (docker mounts a fresh
# /dev, so device nodes cannot be baked into the image).
COPY share/dev/devcontainer-entrypoint.sh /usr/local/bin/devcontainer-entrypoint
RUN chmod +x /usr/local/bin/devcontainer-entrypoint
ENTRYPOINT ["devcontainer-entrypoint"]

WORKDIR /workspace
CMD ["bash"]
