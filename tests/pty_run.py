#!/usr/bin/env python3
"""Run a command with a pseudo-terminal on stdin and script its input.

The bash suites run with stdin and stderr on pipes, so code gated on a
terminal (``[[ -t 0 ]]``) never executes under test.  This helper gives a
child the descriptors a real session has, then plays a scripted
conversation against it.

Usage:
    pty_run.py [--shape gui|terminal] [--timeout SECONDS] STEP... -- CMD [ARG...]

Shapes:
    gui       stdin is the PTY; stdout and stderr share one pipe.  This is
              what the GUI runner gives every step
              (``backup_runner._spawn_process``).  Default.
    terminal  stdin, stdout and stderr are all the PTY, like a command typed
              in a terminal window.

Steps run in the order given:
    --expect TEXT   wait until TEXT appears in the output, after the
                    previous match
    --send TEXT     type TEXT followed by Enter
    --send-eof      type Ctrl+D (end of input)
    --run COMMAND   run a shell command, for example to stop a lock holder

The child's output is copied to stdout, followed by trailer lines:
    PTYRUN-RC=<child exit status>     the child exited
    PTYRUN-UNMET=<step>               the child exited before this step ran
    PTYRUN-TIMEOUT=<step>             the step was still pending at the timeout
Exit status: the child's own, or 124 on timeout.
"""

import argparse
import errno
import os
import pty
import select
import signal
import subprocess
import sys
import termios
import time

_POLL_SECONDS = 0.05
_READ_BYTES = 4096
_EOF_BYTE = b"\x04"
_TIMEOUT_RC = 124


class _Step(argparse.Action):
    """Collect the step options into one list, in command-line order."""

    def __call__(self, parser, namespace, values, option_string=None):
        steps = getattr(namespace, "steps", None) or []
        kind = option_string.lstrip("-")
        steps.append((kind, values if isinstance(values, str) else ""))
        namespace.steps = steps


def _parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Run a command with a pseudo-terminal on stdin and script its input.",
        allow_abbrev=False,
    )
    parser.add_argument("--shape", choices=("gui", "terminal"), default="gui")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--expect", action=_Step, metavar="TEXT")
    parser.add_argument("--send", action=_Step, metavar="TEXT")
    parser.add_argument("--send-eof", action=_Step, nargs=0)
    parser.add_argument("--run", action=_Step, metavar="COMMAND")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    if not args.command:
        parser.error("no command given")
    args.steps = getattr(args, "steps", None) or []
    return args


def _spawn(command, shape):
    """Start the child; return (process, PTY master fd, fd carrying its output)."""
    master_fd, slave_fd = pty.openpty()
    # Typed input must not be echoed back into the output being matched.
    attrs = termios.tcgetattr(master_fd)
    attrs[3] &= ~termios.ECHO
    termios.tcsetattr(master_fd, termios.TCSANOW, attrs)
    try:
        if shape == "gui":
            proc = subprocess.Popen(
                command,
                stdin=slave_fd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            output_fd = proc.stdout.fileno()
        else:
            proc = subprocess.Popen(command, stdin=slave_fd, stdout=slave_fd, stderr=slave_fd)
            output_fd = master_fd
    finally:
        os.close(slave_fd)
    return proc, master_fd, output_fd


def _read_chunk(fd):
    """Return the next bytes from fd, or None at end of stream."""
    try:
        data = os.read(fd, _READ_BYTES)
    except OSError as exc:
        # A PTY master reports EIO once the child has closed the other side.
        if exc.errno == errno.EIO:
            return None
        raise
    return data or None


def _describe(step):
    kind, value = step
    return f"{kind} {value}".rstrip()


def _play(proc, master_fd, output_fd, steps, deadline):
    """Play the steps against the child.

    Returns (output bytes, unmet step or None, timed-out flag).
    """
    output = bytearray()
    matched_to = 0
    pending = list(steps)
    stream_open = True
    while True:
        while pending:
            kind, value = pending[0]
            if kind == "expect":
                found = output.find(value.encode(), matched_to)
                if found < 0:
                    break
                matched_to = found + len(value.encode())
            elif kind == "send":
                os.write(master_fd, value.encode() + b"\n")
            elif kind == "send-eof":
                os.write(master_fd, _EOF_BYTE)
            else:
                # The deadline bounds the hook too, so a stuck command
                # cannot hang the suite.
                try:
                    subprocess.run(
                        value,
                        shell=True,
                        check=False,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=max(deadline - time.monotonic(), _POLL_SECONDS),
                    )
                except subprocess.TimeoutExpired:
                    return output, pending[0], True
            pending.pop(0)

        if not stream_open and proc.poll() is not None:
            return output, (pending[0] if pending else None), False
        if time.monotonic() > deadline:
            return output, (pending[0] if pending else ("wait", "child exit")), True

        if stream_open:
            readable, _, _ = select.select([output_fd], [], [], _POLL_SECONDS)
            if readable:
                chunk = _read_chunk(output_fd)
                if chunk is None:
                    stream_open = False
                else:
                    output.extend(chunk)
        else:
            try:
                proc.wait(timeout=_POLL_SECONDS)
            except subprocess.TimeoutExpired:
                pass


def main(argv=None):
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    # Give the child the interrupt disposition a real session starts with.
    # A suite launched in the background inherits SIGINT ignored, the child
    # would inherit that from this process, and bash cannot trap a signal
    # that was ignored when it started.
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    proc, master_fd, output_fd = _spawn(args.command, args.shape)
    try:
        output, unmet, timed_out = _play(
            proc, master_fd, output_fd, args.steps, time.monotonic() + args.timeout
        )
        if timed_out:
            proc.kill()
        rc = proc.wait()
    finally:
        os.close(master_fd)

    text = output.decode(errors="replace").replace("\r\n", "\n")
    sys.stdout.write(text)
    if text and not text.endswith("\n"):
        sys.stdout.write("\n")
    if timed_out:
        sys.stdout.write(f"PTYRUN-TIMEOUT={_describe(unmet)}\n")
        return _TIMEOUT_RC
    if unmet is not None:
        sys.stdout.write(f"PTYRUN-UNMET={_describe(unmet)}\n")
    sys.stdout.write(f"PTYRUN-RC={rc}\n")
    return rc if rc >= 0 else 128 - rc


if __name__ == "__main__":
    sys.exit(main())
