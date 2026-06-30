"""
Cron file management and human-readable interpreter.

Manages /etc/cron.d/zfsutilities as a drop-in file exclusively for zfsutilities.
"""

import os
import re
import shlex
from datetime import datetime, timedelta

from backup_config import log_msg

CRON_FILE = "/etc/cron.d/zfsutilities"

_HEADER = (
    "# /etc/cron.d/zfsutilities\n"
    "# Drop-in crontab for ZFS Utilities scheduled profiles.\n"
    "# DO NOT EDIT MANUALLY — this file is managed by zfsutilities_gui.py\n"
    "MAILTO=\"\"\n"
    "SHELL=/bin/sh\n"
    "PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin\n"
    "\n"
)


def write_cron_file(profiles, runner_path):
    """Regenerate the cron drop-in file from scratch.

    Args:
        profiles: list of profile dicts
        runner_path: absolute path to profile_runner.py
    """
    lines = [_HEADER]
    for profile in profiles:
        if not profile.get("active", False):
            continue
        line = generate_cron_line(profile, runner_path)
        if line:
            lines.append(line + "\n")

    content = "".join(lines)
    try:
        with open(CRON_FILE, "w") as f:
            f.write(content)
        os.chmod(CRON_FILE, 0o644)
        log_msg(f"INFO: Cron file updated: {CRON_FILE}")
    except OSError as e:
        log_msg(f"FATAL: Could not write cron file {CRON_FILE}: {e}")
        raise


def generate_cron_line(profile, runner_path):
    """Build a single crontab line for an active profile."""
    cron = profile.get("cron", {})
    minute = cron.get("minute", "*")
    hour = cron.get("hour", "*")
    day = cron.get("day", "*")
    month = cron.get("month", "*")
    weekday = cron.get("weekday", "*")
    # Standard cron does not understand weekday ordinals (e.g. 6#1). Strip
    # the ordinal suffix; profile_runner.py applies the guard at runtime.
    if "#" in weekday:
        weekday = weekday.split("#", 1)[0].strip()
    name = profile["profile_name"]
    quoted_runner = shlex_quote(runner_path)
    safe_name = re.sub(r"[^A-Za-z0-9_-]", "_", name)
    lock_path = shlex_quote(
        f"/run/lock/zfs/profiles/{safe_name}.lock"
    )
    inner = f"python3 {quoted_runner} run {shlex_quote(name)}"
    # flock -n -E 0 exits 0 when the lock is held so cron does not mail.
    return (
        f'{minute} {hour} {day} {month} {weekday} '
        f'root flock -n -E 0 {lock_path} -c {shlex_quote(inner)}'
    )


def shlex_quote(s):
    """Minimal shlex.quote equivalent (Python 3.3+ has shlex.quote)."""
    return shlex.quote(s)


# ---------------------------------------------------------------------------
# Human-readable cron interpreter
# ---------------------------------------------------------------------------

_WEEKDAYS = {
    0: "Sunday", 1: "Monday", 2: "Tuesday", 3: "Wednesday",
    4: "Thursday", 5: "Friday", 6: "Saturday", 7: "Sunday",
}

_MONTHS = {
    1: "January", 2: "February", 3: "March", 4: "April",
    5: "May", 6: "June", 7: "July", 8: "August",
    9: "September", 10: "October", 11: "November", 12: "December",
}


_ORDINAL_NAMES = {
    1: "first", 2: "second", 3: "third", 4: "fourth",
    5: "fifth", 6: "sixth",
}


def _parse_weekday(value):
    """Parse a weekday field that may include an ordinal suffix.

    Returns (base, ordinal_specs) where base is the weekday part before '#'
    and ordinal_specs is a list of specs. Each spec is either an integer
    tuple (start, end) or the string 'L' for "last".

    Examples:
        "6"      -> ("6", [])
        "6#1"    -> ("6", [(1, 1)])
        "6#1,3"  -> ("6", [(1, 1), (3, 3)])
        "6#3-5"  -> ("6", [(3, 5)])
        "6#L"    -> ("6", ['L'])
        "6#1,L"  -> ("6", [(1, 1), 'L'])

    Raises ValueError for invalid syntax.
    """
    if "#" not in value:
        return value, []
    base, suffix = value.split("#", 1)
    base = base.strip()
    if not base.isdigit() or not 0 <= int(base) <= 7:
        raise ValueError(
            f"Weekday ordinal requires a single weekday digit before '#': {value}"
        )

    specs = []
    for part in suffix.split(","):
        part = part.strip()
        if not part:
            raise ValueError(f"Empty ordinal in weekday expression: {value}")
        if part == "L":
            specs.append("L")
        elif "-" in part:
            start, end = part.split("-", 1)
            start = int(start.strip())
            end = int(end.strip())
            if start > end or start < 1:
                raise ValueError(f"Invalid ordinal range in weekday expression: {value}")
            specs.append((start, end))
        elif part.lstrip("-").isdigit():
            n = int(part)
            if n < 1:
                raise ValueError(f"Invalid ordinal in weekday expression: {value}")
            specs.append((n, n))
        else:
            raise ValueError(f"Invalid ordinal '{part}' in weekday expression: {value}")
    return base, specs


def _match_weekday_ordinal(date, weekday, specs):
    """Return True if date satisfies any of the ordinal specs for weekday.

    weekday is the cron-style weekday (0=Sunday, 6=Saturday).
    specs is the list returned by _parse_weekday.
    """
    pos = ((date.day - 1) // 7) + 1
    next_week = date + timedelta(days=7)
    is_last = next_week.month != date.month or next_week.year != date.year

    for spec in specs:
        if spec == "L":
            if is_last:
                return True
        else:
            start, end = spec
            if start <= pos <= end:
                return True
    return False


def _format_ordinal_specs(specs):
    """Convert ordinal specs into a human-readable phrase."""
    def fmt(spec):
        if spec == "L":
            return "last"
        start, end = spec
        if start == end:
            return _ORDINAL_NAMES.get(start, f"{start}th")
        return f"{_ORDINAL_NAMES.get(start, f'{start}th')} through " \
               f"{_ORDINAL_NAMES.get(end, f'{end}th')}"

    parts = [fmt(spec) for spec in specs]
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return ", ".join(parts[:-1]) + ", and " + parts[-1]


def interpret_cron(minute, hour, day, month, weekday):
    """Return a human-readable sentence describing a cron expression."""
    # Time phrase
    time_str = _interpret_time(minute, hour)

    # Month
    month_str = _interpret_month(month)

    # Day handling: if both day and weekday are *, only say "every day" once.
    # If one is * and the other is specific, only mention the specific one.
    # If both are specific, mention both (rare but valid).
    dom_str = _interpret_day_of_month(day)
    dow_str = _interpret_day_of_week(weekday)

    day_parts = []
    if day == "*" and weekday == "*":
        day_parts.append("every day")
    elif day != "*" and weekday == "*":
        day_parts.append(dom_str)
    elif day == "*" and weekday != "*":
        day_parts.append(dow_str)
    else:
        day_parts.append(dom_str)
        day_parts.append(dow_str)

    # Assemble
    fragments = [time_str]
    if month_str:
        fragments.append(month_str)
    fragments.extend(day_parts)

    result = " ".join(fragments)
    result = result.replace("every day every month", "every day")
    # Only uppercase the very first letter, leave the rest as-is
    if result:
        result = result[0].upper() + result[1:]
    return result


def _interpret_time(minute, hour):
    """Interpret minute + hour into a time phrase."""
    if minute == "*" and hour == "*":
        return "every minute"

    # Step in minute (e.g. */5)
    if "/" in minute:
        step = minute.split("/")[-1]
        if hour == "*":
            return f"every {step} minutes"
        else:
            h = _format_hour(hour)
            return f"every {step} minutes during hour {h}"

    if minute == "*":
        h = _interpret_field(hour, "hour", "hours")
        return f"every minute during {h}"
    if hour == "*":
        m = _format_minute(minute)
        return f"at {m} every hour"
    # Both specific (or hour is a range)
    m = _format_minute(minute)
    h = _format_hour(hour)
    if "-" in h or "," in h:
        if m == "00":
            return f"on the hour during hours {h}"
        return f"at {m} past hours {h}"
    return f"at {h}:{m}"


def _format_minute(m):
    """Format a minute value with leading zero."""
    if m.isdigit():
        return f"{int(m):02d}"
    return m


def _format_hour(h):
    """Format an hour value."""
    if h.isdigit():
        return f"{int(h):02d}"
    return h


def _interpret_month(value):
    """Interpret month field."""
    if value == "*":
        return ""
    if value.isdigit():
        name = _MONTHS.get(int(value), value)
        return f"in {name}"
    if "," in value:
        names = []
        for v in value.split(","):
            v = v.strip()
            if v.isdigit():
                names.append(_MONTHS.get(int(v), v))
            else:
                names.append(v)
        return f"in {', '.join(names)}"
    # Range or step
    return f"in month {value}"


def _interpret_day_of_month(value):
    """Interpret day-of-month field."""
    if value == "*":
        return "every day"
    if value.isdigit():
        suffix = _day_suffix(int(value))
        return f"on the {value}{suffix} of every month"
    if "," in value:
        days = []
        for v in value.split(","):
            v = v.strip()
            if v.isdigit():
                suffix = _day_suffix(int(v))
                days.append(f"{v}{suffix}")
            else:
                days.append(v)
        return f"on the {', '.join(days)} of every month"
    # Range or step
    return f"on day {value} of the month"


def _interpret_day_of_week(value):
    """Interpret day-of-week field."""
    if value == "*":
        return ""
    if "#" in value:
        try:
            base, specs = _parse_weekday(value)
        except ValueError:
            return f"on weekdays {value}"
        name = _WEEKDAYS.get(int(base), base)
        ordinal_phrase = _format_ordinal_specs(specs)
        single_spec = (
            len(specs) == 1 and (
                (isinstance(specs[0], tuple) and specs[0][0] == specs[0][1]) or
                specs[0] == "L"
            )
        )
        if single_spec:
            return f"on the {ordinal_phrase} {name} of the month"
        return f"on the {ordinal_phrase} {name}s of the month"
    if value.isdigit():
        name = _WEEKDAYS.get(int(value), value)
        return f"on {name}s"
    if "," in value:
        names = []
        for v in value.split(","):
            v = v.strip()
            if v.isdigit():
                names.append(_WEEKDAYS.get(int(v), v) + "s")
            else:
                names.append(v)
        if len(names) > 1:
            joined = ", ".join(names[:-1]) + " and " + names[-1]
        else:
            joined = names[0]
        return f"on {joined}"
    # Range or step
    return f"on weekdays {value}"


def _day_suffix(n):
    if 11 <= n % 100 <= 13:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


def _interpret_field(value, singular, plural):
    """Generic field interpreter."""
    if value == "*":
        return f"every {singular}"
    if value.isdigit():
        return f"{singular} {value}"
    if "," in value:
        items = [v.strip() for v in value.split(",")]
        return f"{plural} {', '.join(items)}"
    return f"{plural} {value}"


# ---------------------------------------------------------------------------
# Next-run computation
# ---------------------------------------------------------------------------


def next_run_times(minute, hour, day, month, weekday, count=3):
    """Return the next `count` datetimes matching the cron expression."""
    matches = []
    current = datetime.now().replace(second=0, microsecond=0)
    # Start from next minute to avoid matching "now" if we are exactly on the minute
    current += timedelta(minutes=1)

    # Parse each field into a set of valid values or None for *
    def parse_field(value, min_val, max_val):
        if value == "*":
            return None
        result = set()
        for part in value.split(","):
            part = part.strip()
            if "/" in part:
                base, step = part.split("/", 1)
                step = int(step)
                if base == "*":
                    start = min_val
                    end = max_val
                elif "-" in base:
                    start, end = map(int, base.split("-", 1))
                else:
                    start = int(base)
                    end = max_val
                for v in range(start, end + 1, step):
                    if min_val <= v <= max_val:
                        result.add(v)
            elif "-" in part:
                start, end = map(int, part.split("-", 1))
                for v in range(start, end + 1):
                    if min_val <= v <= max_val:
                        result.add(v)
            else:
                v = int(part)
                if min_val <= v <= max_val:
                    result.add(v)
        return result

    minute_set = parse_field(minute, 0, 59)
    hour_set = parse_field(hour, 0, 23)
    day_set = parse_field(day, 1, 31)
    month_set = parse_field(month, 1, 12)
    try:
        weekday_base, ordinal_specs = _parse_weekday(weekday)
    except ValueError:
        return []
    weekday_set = parse_field(weekday_base, 0, 7)

    # Safety: don't search more than 4 years ahead
    max_search = current + timedelta(days=1461)

    while len(matches) < count and current <= max_search:
        m_match = minute_set is None or current.minute in minute_set
        h_match = hour_set is None or current.hour in hour_set
        d_match = day_set is None or current.day in day_set
        mo_match = month_set is None or current.month in month_set
        wd = current.weekday() + 1  # cron: 0=Sun, 1=Mon; python: 0=Mon
        if current.weekday() == 6:
            wd = 0
        wd_match = weekday_set is None or wd in weekday_set

        if m_match and h_match and d_match and mo_match and wd_match:
            if ordinal_specs:
                if _match_weekday_ordinal(current, wd, ordinal_specs):
                    matches.append(current)
            else:
                matches.append(current)

        current += timedelta(minutes=1)

    return matches


def format_next_runs(minute, hour, day, month, weekday, count=3):
    """Return a formatted string listing next run times."""
    times = next_run_times(minute, hour, day, month, weekday, count)
    if not times:
        return "No upcoming runs found (schedule may be invalid or too restrictive)."
    lines = ["Next runs:"]
    for t in times:
        lines.append(f"  • {t.strftime('%a %b %d %Y %H:%M')}")
    return "\n".join(lines)
