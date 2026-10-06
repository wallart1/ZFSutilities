"""Registry of outstanding numbered input requests (MVS console model).

Prompts raised by GUI-launched jobs are held here with stable action
numbers: the operator replies "N answer" and the answer is routed to the
runner that owns request N.  Pure logic — no GTK imports — so the routing
ladder is unit-testable with fake runners (a runner is any object with
``label``, ``running``, ``step_active`` and ``send_input``).
"""

import re

# Regex: ^\s*(\d+)(?:\s+(.*))?$   (with re.DOTALL)
# Purpose: Split an operator reply in the info-panel Input box into the
#          held-message number it addresses and the answer text that
#          follows it.  A bare number means "send an empty line to that
#          message".  DOTALL lets an answer keep its embedded newlines.
# Group 1: Message number   e.g. "3"
# Group 2: Answer text      e.g. "y", "" for a bare number
# Examples:
#   "3 y"        -> number=3, answer="y"
#   "3"          -> number=3, answer=""
#   "3 path/x\n" -> number=3, answer="path/x\n"
#   "yes"        -> no match (returned as bare text)
_NUMBERED_RE = re.compile(r"^\s*(\d+)(?:\s+(.*))?$", re.DOTALL)


class InputRequest:
    """One outstanding prompt: a number, its owning runner, and its text."""

    def __init__(self, number, uuid, runner, prompt):
        self.number = number
        self.uuid = uuid
        self.runner = runner
        self.prompt = prompt

    @property
    def label(self):
        return getattr(self.runner, "label", "?")

    def row_text(self):
        """Render the held-message row shown in the action strip."""
        return f"{self.number}  [{self.label}]  {self.prompt}"


class InputRequestRegistry:
    """Assigns monotonic numbers and tracks outstanding input requests.

    Numbers start at 1 and are never reused within the session, so a
    number always refers to the same question.  A REQ for an already
    registered uuid updates the held prompt text in place (validation
    loops re-ask under the same number).
    """

    def __init__(self):
        self._next_number = 1
        self._by_number = {}
        self._by_uuid = {}

    def register(self, runner, uuid, prompt):
        """Hold a new request (or update a known one) and return it."""
        request = self._by_uuid.get(uuid)
        if request is not None:
            request.prompt = prompt
            request.runner = runner
            return request
        request = InputRequest(self._next_number, uuid, runner, prompt)
        self._next_number += 1
        self._by_number[request.number] = request
        self._by_uuid[uuid] = request
        return request

    def release_uuid(self, uuid):
        """Release the request for *uuid*; returns it or None."""
        request = self._by_uuid.pop(uuid, None)
        if request is not None:
            del self._by_number[request.number]
        return request

    def release_runner(self, runner):
        """Release every request owned by *runner*; returns them."""
        released = [r for r in self._by_number.values() if r.runner is runner]
        for request in released:
            self.release_uuid(request.uuid)
        return released

    def release_all(self):
        """Release everything (GUI shutdown)."""
        self._by_number.clear()
        self._by_uuid.clear()

    def by_number(self, number):
        return self._by_number.get(number)

    def by_uuid(self, uuid):
        return self._by_uuid.get(uuid)

    def outstanding(self):
        """Outstanding requests in number order."""
        return [self._by_number[n] for n in sorted(self._by_number)]

    def sole_outstanding(self):
        """The single outstanding request, or None when 0 or 2+ are held."""
        requests = self.outstanding()
        return requests[0] if len(requests) == 1 else None


def parse_user_input(text):
    """Split operator input into (number, answer).

    "3 y" -> (3, "y"); "3" -> (3, ""); "y" -> (None, "y").  A leading
    number with nothing after it means "send an empty line to request N".
    """
    match = _NUMBERED_RE.match(text)
    if match:
        return int(match.group(1)), match.group(2) or ""
    return None, text


def sole_live_runner(runners):
    """The single runner with a live step, or None when 0 or 2+ are live.

    Backstop for prompts raised by jobs that do not use the input-hold
    helpers (e.g. user-supplied pre/post-backup scripts): bare input goes
    to that one live task.  Never resolves between multiple live tasks —
    that would reintroduce silent priority routing.
    """
    live = [runner for runner in runners if getattr(runner, "step_active", False)]
    return live[0] if len(live) == 1 else None
