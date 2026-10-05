#!/usr/bin/env python3
"""serial_console.py — stdlib serial-console driver for itf guest installs.

Drives a guest's serial console (`qm terminal <vmid>`) from the dev system
without external dependencies (no expect/pexpect): spawns
`ssh -tt <user>@<base> sudo -n qm terminal <vmid>`, then performs a
SEQUENCE of wait/send steps -- each --wait regex is watched for in the
accumulated output and its --send string (sent verbatim — include an
explicit \\n when a newline is needed, e.g. an Escape keypress needs none)
is written once it appears.  The transcript keeps recording until the
--exit-after regex matches, the ssh process ends, or the timeout expires.
With no --wait steps the driver simply watches the console (transcript
plus exit pattern) — how journeys drive a custom-boot ISO that needs no
keystrokes at all.

Start the driver BEFORE powering the guest on so the boot output is
captured from the top (attaching after the bootloader has already drawn
its menu means the wait pattern never reappears).

Exit codes: 0 = the --exit-after pattern matched — the run reached its
expected ending (steps still pending when it matches are prompt answers
whose dialogs were simply never shown); 2 = the console ended or timed
out before all steps executed; 4 = all steps executed but the console
ended (EOF) or timed out WITHOUT the exit pattern matching — e.g. the
connection was lost or the guest stalled; 3 = could not spawn ssh.
"""

import argparse
import queue
import re
import subprocess
import sys
import threading
import time


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        epilog="example: --wait 'installer menu' --send $'\\x1b' "
               "--wait 'boot:' --send 'install auto=true ... ---\\n'",
    )
    ap.add_argument("--host", required=True, help="base host to ssh to")
    ap.add_argument("--user", required=True, help="ssh user on the base host")
    ap.add_argument("--vmid", required=True, help="guest VMID")
    ap.add_argument("--wait", action="append", default=[], metavar="REGEX",
                    help="pattern to wait for (repeatable)")
    ap.add_argument("--send", action="append", default=[], metavar="TEXT",
                    help="bytes sent once the matching --wait pattern is "
                    "seen (repeatable, sent verbatim)")
    ap.add_argument("--exit-after", default="",
                    help="stop capturing when this regex matches")
    ap.add_argument("--kick", default="",
                    help="bytes sent blindly when no output has arrived "
                    "within --kick-delay (e.g. a menu keypress that forces "
                    "a redraw when the console was attached after the "
                    "bootloader had already painted its screen)")
    ap.add_argument("--kick-delay", type=float, default=4.0,
                    help="seconds of total silence before --kick fires")
    ap.add_argument("--timeout", type=int, default=900,
                    help="overall timeout in seconds")
    ap.add_argument("--send-delay", type=float, default=2.0,
                    help="pause after a match, before sending")
    ap.add_argument("--step-timeout", type=float, default=0.0,
                    help="skip a step whose pattern has not appeared "
                         "within this many seconds of the step becoming "
                         "current (0 = wait forever) — lets an optional "
                         "prompt-answer step be skipped when its dialog "
                         "never shows")
    ap.add_argument("--send-chunk", type=int, default=16,
                    help="send keystrokes in chunks of this many bytes")
    ap.add_argument("--chunk-delay", type=float, default=0.08,
                    help="pause between chunks — a full line blasted down "
                         "the serial in one write can drop characters "
                         "(observed: 'url' swallowed, breaking auto=)")
    ap.add_argument("--log", required=True,
                    help="transcript log file (append)")
    args = ap.parse_args()

    if len(args.wait) != len(args.send):
        print("serial_console: --wait and --send must come in pairs",
              file=sys.stderr)
        return 3
    if not args.wait and not args.exit_after:
        print("serial_console: nothing to do — pass --wait/--send steps "
              "and/or --exit-after", file=sys.stderr)
        return 3

    cmd = [
        "ssh", "-tt",
        "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
        f"{args.user}@{args.host}",
        f"sudo -n qm terminal {args.vmid}",
    ]
    try:
        proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, bufsize=0,
        )
    except OSError as exc:
        print(f"serial_console: cannot spawn ssh: {exc}", file=sys.stderr)
        return 3

    steps = list(zip([re.compile(w) for w in args.wait], args.send))
    exit_re = re.compile(args.exit_after) if args.exit_after else None
    deadline = time.monotonic() + args.timeout

    def send_bytes(data: bytes) -> None:
        """Write to the console in paced chunks: one large write can
        overrun the bootloader's serial input and drop characters."""
        out = memoryview(data)
        while out:
            piece = out[:args.send_chunk]
            proc.stdin.write(piece)
            proc.stdin.flush()
            out = out[len(piece):]
            if out:
                time.sleep(args.chunk_delay)

    # A blocking read on a silent console would freeze the loop and the
    # kick/deadline logic with it — drain output through a reader thread
    # and poll it instead.
    out_q: queue.Queue = queue.Queue()

    def reader() -> None:
        while True:
            byte = proc.stdout.read(1)
            if not byte:
                out_q.put(None)
                return
            out_q.put(byte)

    threading.Thread(target=reader, daemon=True).start()

    # Unbuffered so monitoring tools can tail the transcript live.
    with open(args.log, "ab", buffering=0) as log:
        buf = b""
        step_idx = 0
        kicked = False
        eof = False
        started_at = time.monotonic()

        def note(text: str) -> None:
            log.write(f"\n[serial_console] {text}\n".encode())

        step_started = time.monotonic()
        while True:
            if not eof:
                try:
                    item = out_q.get(timeout=0.5)
                except queue.Empty:
                    item = b""
                if item is None:
                    eof = True
                    note(f"console ended "
                         f"({'steps incomplete' if step_idx < len(steps) else 'after steps'})")
                elif item:
                    buf += item
                    log.write(item)
                    if len(buf) > 65536:
                        buf = buf[-32768:]

            text = buf.decode("utf-8", errors="replace")

            # The exit pattern is authoritative whenever it appears — even
            # with prompt-answer steps still pending (their dialogs may
            # simply never have been shown, e.g. when the kernel command
            # line already supplied the answer).
            if exit_re and exit_re.search(text):
                note(f"exit reason: pattern ({step_idx}/{len(steps)} steps done)")
                rc = 0
                break

            # Decide the ending: without the exit pattern, a lost
            # connection or a timeout is not a success.  The reader thread
            # sets eof only after draining every queued byte, so eof —
            # never proc.poll() alone — marks the stream end.
            if eof or time.monotonic() > deadline:
                timed_out = time.monotonic() > deadline and not eof
                if timed_out:
                    note(f"exit reason: timeout without exit pattern "
                         f"({step_idx}/{len(steps)} steps done)")
                else:
                    note(f"exit reason: console ended without exit pattern "
                         f"({step_idx}/{len(steps)} steps done)")
                rc = 2 if step_idx < len(steps) else 4
                break

            # Silence breaker: if nothing at all has arrived, the screen
            # may already be painted (attached too late); a blind
            # keypress forces the bootloader to repaint.
            if args.kick and not kicked and not buf \
                    and time.monotonic() - started_at > args.kick_delay:
                send_bytes(args.kick.encode())
                kicked = True
                note(f"kicked silent console with {args.kick!r}")

            if step_idx < len(steps):
                wait_re, send_text = steps[step_idx]
                if args.step_timeout > 0 and \
                        time.monotonic() - step_started > args.step_timeout:
                    step_idx += 1
                    step_started = time.monotonic()
                    note(f"step {step_idx}/{len(steps)}: pattern not seen "
                         f"within {args.step_timeout:g}s — skipping")
                elif wait_re.search(text):
                    settled = time.monotonic()
                    while time.monotonic() - settled < args.send_delay:
                        if proc.poll() is not None:
                            break
                        time.sleep(0.1)
                    send_bytes(send_text.encode())
                    step_idx += 1
                    step_started = time.monotonic()
                    note(f"step {step_idx}/{len(steps)}: sent {send_text!r}")

        log.flush()

    proc.kill()
    proc.wait()
    return rc


if __name__ == "__main__":
    sys.exit(main())
