"""Resolve relative dates against the session date."""

from __future__ import annotations

import calendar
import datetime as dt
import re
from dataclasses import dataclass


WEEKDAYS = {
    name.lower(): index
    for index, name in enumerate(calendar.day_name)
}
MONTHS = {
    name.lower(): index
    for index, name in enumerate(calendar.month_name)
    if name
}
NUMBER_WORDS = {
    "a": 1,
    "an": 1,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}
DAY = dt.timedelta(days=1)


@dataclass(frozen=True)
class Resolution:
    start: dt.date
    end: dt.date
    precision: str
    basis: str

    @property
    def display(self) -> str:
        """Formatted date or range."""
        return format_resolution(self)


@dataclass(frozen=True)
class TemporalMention:
    text: str
    start: int
    end: int
    resolution: Resolution | None
    ambiguity: str | None = None


def parse_conversation_date(value: str) -> dt.date:
    """Parse a session date."""
    value = (value or "").strip()
    iso = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", value)
    if iso:
        return dt.date(*(int(part) for part in iso.groups()))
    match = re.search(
        r"\b(\d{1,2})\s+([A-Za-z]+),\s*(\d{4})\b", value
    )
    if not match:
        raise ValueError("unrecognized conversation date: %r" % value)
    day, month, year = match.groups()
    return dt.date(int(year), MONTHS[month.lower()], int(day))


def _month_range(year: int, month: int) -> tuple[dt.date, dt.date]:
    """First and last day of a month."""
    start = dt.date(year, month, 1)
    end = dt.date(year, month, calendar.monthrange(year, month)[1])
    return start, end


def _shift_month(value: dt.date, amount: int) -> tuple[int, int]:
    """Shift (year, month) by months."""
    index = value.year * 12 + value.month - 1 + amount
    return index // 12, index % 12 + 1


def _number(value: str) -> int | None:
    """Parse a number word or digits."""
    value = value.lower()
    if value.isdigit():
        return int(value)
    return NUMBER_WORDS.get(value)


def _result(start: dt.date, end: dt.date, precision: str, basis: str) -> Resolution:
    """Build a Resolution."""
    return Resolution(start=start, end=end, precision=precision, basis=basis)


def resolve_relative(conversation_date: dt.date | str, expression: str) -> Resolution | None:
    """Resolve one relative expression, or None."""
    current = (
        parse_conversation_date(conversation_date)
        if isinstance(conversation_date, str)
        else conversation_date
    )
    text = re.sub(r"\s+", " ", (expression or "").strip().lower())

    if text in {
        "yesterday", "yesterday morning", "yesterday afternoon",
        "yesterday evening", "last night", "the night before", "the day before",
    }:
        value = current - DAY
        return _result(value, value, "day", "explicit_relative")
    if text == "the day before yesterday":
        value = current - 2 * DAY
        return _result(value, value, "day", "explicit_relative")
    if text in {
        "today", "tonight", "this morning", "this afternoon",
        "this evening", "earlier today", "just now",
    }:
        return _result(current, current, "day", "explicit_relative")
    if text in {
        "tomorrow", "tomorrow morning", "tomorrow afternoon", "tomorrow evening",
        "the next day",
    }:
        value = current + DAY
        return _result(value, value, "day", "explicit_relative")
    if text in {
        "the day after tomorrow", "the day after tomorrow morning",
        "the day after tomorrow afternoon", "the day after tomorrow evening",
    }:
        value = current + 2 * DAY
        return _result(value, value, "day", "explicit_relative")

    match = re.fullmatch(
        r"(?:last|this past)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
        text,
    )
    if match:
        if match.group(1) == "friday" and current.weekday() in {5, 6}:
            return None
        delta = (current.weekday() - WEEKDAYS[match.group(1)]) % 7 or 7
        value = current - delta * DAY
        return _result(value, value, "day", "explicit_relative")

    match = re.fullmatch(
        r"next\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
        text,
    )
    if match:
        delta = (WEEKDAYS[match.group(1)] - current.weekday()) % 7 or 7
        value = current + delta * DAY
        return _result(value, value, "day", "explicit_relative")

    match = re.fullmatch(
        r"this\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
        text,
    )
    if match:
        value = current + (WEEKDAYS[match.group(1)] - current.weekday()) * DAY
        return _result(value, value, "day", "explicit_relative")

    match = re.fullmatch(
        r"(\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten)\s+"
        r"(day|week|month|year)s?\s+(ago|earlier|before|later|from now)",
        text,
    )
    if match:
        amount = _number(match.group(1))
        if amount is None:
            return None
        future = match.group(3) in {"later", "from now"}
        direction = 1 if future else -1
        unit = match.group(2)
        if unit == "day":
            value = current + direction * amount * DAY
            return _result(value, value, "day", "explicit_relative")
        if unit == "week":
            value = current + direction * amount * 7 * DAY
            return _result(value, value, "day", "explicit_relative")
        if unit == "month":
            year, month = _shift_month(current, direction * amount)
            start, end = _month_range(year, month)
            return _result(start, end, "month", "anchored_range")
        year = current.year + direction * amount
        return _result(
            dt.date(year, 1, 1), dt.date(year, 12, 31), "year", "anchored_range"
        )

    match = re.fullmatch(
        r"in\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+"
        r"(day|week|month|year)s?",
        text,
    )
    if match:
        return resolve_relative(current, "%s %s from now" % match.groups())

    match = re.fullmatch(r"(two|three|four|\d+)\s+weekends\s+ago", text)
    if match:
        amount = _number(match.group(1))
        previous_saturday = current - (((current.weekday() - 5) % 7) or 7) * DAY
        start = previous_saturday - (amount - 1) * 7 * DAY
        return _result(start, start + DAY, "weekend", "anchored_range")

    if text in {"last weekend", "this past weekend", "over the weekend"}:
        back = (current.weekday() - 5) % 7
        if back <= 1:
            back += 7
        previous_saturday = current - back * DAY
        return _result(
            previous_saturday, previous_saturday + DAY, "weekend", "anchored_range"
        )
    if text == "this weekend":
        if current.weekday() <= 4:
            saturday = current + (5 - current.weekday()) * DAY
        else:
            saturday = current - (current.weekday() - 5) * DAY
        return _result(saturday, saturday + DAY, "weekend", "anchored_range")
    if text == "next weekend":
        saturday = current + ((5 - current.weekday()) % 7) * DAY
        if saturday <= current or current.weekday() >= 5:
            saturday += 7 * DAY
        return _result(saturday, saturday + DAY, "weekend", "anchored_range")

    if text in {"last week", "the week before"}:
        monday = current - (current.weekday() + 7) * DAY
        return _result(monday, monday + 6 * DAY, "week", "anchored_range")
    if text == "this week":
        monday = current - current.weekday() * DAY
        return _result(monday, monday + 6 * DAY, "week", "anchored_range")
    if text == "next week":
        monday = current + (7 - current.weekday()) * DAY
        return _result(monday, monday + 6 * DAY, "week", "anchored_range")

    if text == "last month":
        year, month = _shift_month(current, -1)
        start, end = _month_range(year, month)
        return _result(start, end, "month", "anchored_range")
    if text == "this month":
        start, end = _month_range(current.year, current.month)
        return _result(start, end, "month", "anchored_range")
    if text in {"next month", "the month after"}:
        year, month = _shift_month(current, 1)
        start, end = _month_range(year, month)
        return _result(start, end, "month", "anchored_range")

    if text == "last year":
        year = current.year - 1
        return _result(dt.date(year, 1, 1), dt.date(year, 12, 31), "year", "anchored_range")
    if text == "this year":
        return _result(
            dt.date(current.year, 1, 1), dt.date(current.year, 12, 31),
            "year", "anchored_range",
        )
    if text == "next year":
        year = current.year + 1
        return _result(dt.date(year, 1, 1), dt.date(year, 12, 31), "year", "anchored_range")

    return None


_EXACT_PATTERNS = [
    r"\bthe day before yesterday\b",
    r"\bthe day after tomorrow(?:\s+(?:morning|afternoon|evening))?\b",
    r"\b(?:yesterday|tomorrow)\s+(?:morning|afternoon|evening)\b",
    r"\bthe night before\b",
    r"\b(?:last|this past|next|this)\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    r"\b(?:two|three|four|\d+)\s+weekends\s+ago\b",
    r"\b(?:\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten)\s+"
    r"(?:day|week|month|year)s?\s+(?:ago|earlier|before|later|from now)\b",
    r"\bin\s+(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+"
    r"(?:day|week|month|year)s?\b",
    r"\b(?:last|this past|over the|this|next)\s+weekend\b",
    r"\b(?:last|this|next)\s+(?:week|month|year)\b",
    r"\b(?:the week before|the month after|the day before|the next day)\b",
    r"\b(?:yesterday|last night|today|tonight|tomorrow|earlier today|just now|"
    r"this morning|this afternoon|this evening)\b",
]

_VAGUE_PATTERN = re.compile(
    r"\b(?:recently|lately|the other day|a while (?:ago|back)|not too long ago|"
    r"a few (?:days|weeks|months|years) ago|a couple of (?:days|weeks|months|years) ago|"
    r"(?:about|around|roughly|approximately|almost|nearly|over|more than|less than)\s+"
    r"(?:\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten)\s+"
    r"(?:day|week|month|year)s? ago|"
    r"(?:last|this|next) (?:spring|summer|fall|autumn|winter))\b",
    re.IGNORECASE,
)


def find_temporal_mentions(
    text: str, conversation_date: dt.date | str, include_vague: bool = True
) -> list[TemporalMention]:
    """Find relative date mentions in text."""
    candidates: list[TemporalMention] = []
    current = (
        parse_conversation_date(conversation_date)
        if isinstance(conversation_date, str)
        else conversation_date
    )
    for pattern in _EXACT_PATTERNS:
        for match in re.finditer(pattern, text or "", re.IGNORECASE):
            normalized = re.sub(r"\s+", " ", match.group(0).strip().lower())
            ambiguity = None
            if (
                re.fullmatch(r"(?:last|this past) friday", normalized)
                and current.weekday() in {5, 6}
            ):
                ambiguity = "weekend_last_friday"
            candidates.append(
                TemporalMention(
                    text=match.group(0),
                    start=match.start(),
                    end=match.end(),
                    resolution=resolve_relative(conversation_date, match.group(0)),
                    ambiguity=ambiguity,
                )
            )
    if include_vague:
        for match in _VAGUE_PATTERN.finditer(text or ""):
            candidates.append(
                TemporalMention(match.group(0), match.start(), match.end(), None)
            )

    chosen: list[TemporalMention] = []
    for item in sorted(candidates, key=lambda value: (value.start, -(value.end - value.start))):
        if any(item.start < old.end and old.start < item.end for old in chosen):
            continue
        chosen.append(item)
    return sorted(chosen, key=lambda value: value.start)


def format_date(value: dt.date) -> str:
    """Format a date as "May 7, 2023"."""
    return "%s %d, %d" % (value.strftime("%B"), value.day, value.year)


def format_resolution(value: Resolution) -> str:
    """Format a resolution as text."""
    if value.precision == "year":
        return str(value.start.year)
    if value.precision == "month":
        return "%s %d" % (value.start.strftime("%B"), value.start.year)
    if value.start == value.end:
        return format_date(value.start)
    if value.start.year == value.end.year and value.start.month == value.end.month:
        return "%s %d–%d, %d" % (
            value.start.strftime("%B"), value.start.day, value.end.day, value.start.year
        )
    if value.start.year == value.end.year:
        return "%s %d–%s %d, %d" % (
            value.start.strftime("%B"), value.start.day,
            value.end.strftime("%B"), value.end.day, value.start.year,
        )
    return "%s–%s" % (format_date(value.start), format_date(value.end))
