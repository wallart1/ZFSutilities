"""input_hold — numbered input-hold prompts for jobs launched by the GUI.

This is the Python twin of the bash input-hold helpers in bin/bashinit.
The GUI runner sets ZFSUTILITIES_INPUT_HOLD=Y for the jobs it launches and
intercepts two side-channel marker lines from the merged output stream:

    ZFSU-INPUT-REQ|<uuid>|<prompt text>   a prompt is now waiting for input
    ZFSU-INPUT-ACK|<uuid>                 the read returned; release the hold

The GUI holds each request on screen with an action number and routes the
operator reply "N answer" to the exact process that asked.  When the env
var is unset (plain terminal, cron, Run Now) the helpers prompt normally
via input() and never emit markers.

This module runs inside child processes, not the GUI: it must stay
dependency-free (no gi, no zfsutilities package imports) so any Python
script the GUI launches can use it after `import input_hold`.
"""

import builtins
import os
import sys
import uuid as _uuid

_REQ = "ZFSU-INPUT-REQ|{id}|{prompt}\n"
_ACK = "ZFSU-INPUT-ACK|{id}\n"


def hold_active():
    """Return True when running under the GUI input-hold protocol."""
    return os.environ.get("ZFSUTILITIES_INPUT_HOLD", "") == "Y"


def _emit_req(request_id, prompt):
    if not hold_active():
        return
    sys.stderr.write(_REQ.format(id=request_id, prompt=prompt))
    sys.stderr.flush()


def _emit_ack(request_id):
    if not hold_active():
        return
    sys.stderr.write(_ACK.format(id=request_id))
    sys.stderr.flush()


def _read_line():
    # input("") prints nothing; under the protocol the held message on the
    # GUI console is the prompt, so the line must come back bare.
    return builtins.input("")


def ask_yn(prompt, default=False):
    """Ask a yes/no question; return True for yes, False for no.

    Mirrors bash ask_yn: invalid answers re-ask (the held message keeps its
    action number), Enter selects *default*.
    """
    suffix = " [Y/n]: " if default else " [y/N]: "
    display = f"{prompt}{suffix}"
    request_id = str(_uuid.uuid4())
    while True:
        _emit_req(request_id, display)
        if hold_active():
            response = _read_line()
        else:
            response = builtins.input(display)
        if response == "":
            response = "Y" if default else "N"
        lowered = response.lower()
        if lowered in ("y", "yes"):
            _emit_ack(request_id)
            return True
        if lowered in ("n", "no"):
            _emit_ack(request_id)
            return False
        sys.stderr.write("  Please answer y or n.\n")


def ask_line(prompt):
    """Ask one free-text question and return the answer line.

    Mirrors bash ask_line: the answer is returned verbatim (no stripping).
    """
    request_id = str(_uuid.uuid4())
    _emit_req(request_id, prompt)
    if hold_active():
        response = _read_line()
    else:
        response = builtins.input(prompt)
    _emit_ack(request_id)
    return response
