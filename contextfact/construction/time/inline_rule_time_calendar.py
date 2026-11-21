"""Inline dates for weekdays and follow-up expressions."""
import datetime as dt
import re

from .inline_rule_time import TR, annotate as base_annotate
from .inline_rule_time_context import annotate as context_annotate

DAYS = '|'.join(TR.WEEKDAYS)
WEEKDAY = re.compile(r'\b(?:on\s+)?(' + DAYS + r')\b', re.I)
ANNOTATION = re.compile(r'\s*\([^()\n]*\b\d{4}\b[^()\n]*\)')
PAST = re.compile(
    r'\b(?:won|went|met|visited|returned|finished|completed|bought|adopted|'
    r'arrived|left|lost|attended|received|submitted|started|happened|was|were|'
    r'did|had|got|took|saw|found|sent|watched|enrolled|applied|played|'
    r'joined|moved|began|decided|celebrated|travelled|traveled)\b', re.I)
FUTURE = re.compile(
    r"\b(?:will|shall|gonna|going to|plan to|planning to|plans to|scheduled to)\b"
    r"|\b\w+['’]ll\b|\b(?:am|is|are|['’]m) going on\b", re.I)
NUMBER = r'(?:\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten)'
FOLLOWUP = re.compile(r'\b(?:(?:the|a) (?:next|following) day|the (?:day|night) before|'
                         + NUMBER + r' (?:days?|weeks?) (?:later|earlier))\b', re.I)


def _sentence(text, start, end):
    """Sentence text before and after a match."""
    left = re.split(r'[.!?;\n]', text[:start])[-1]
    right = re.split(r'[.!?;\n]', text[end:])[0]
    return left, right


def _direction(left, right):
    """Infer past or future from tense."""
    clause = left if re.search(r'\b(?:I|we|he|she|they|you|it)\b', left, re.I) else right
    past, future = bool(PAST.search(clause)), bool(FUTURE.search(clause))
    if past != future:
        return -1 if past else 1
    return None


def _day_edit(match, day, basis):
    """Build an edit that inserts a date."""
    value = TR.format_date(day)
    return dict(start=match.start(), end=match.end(), expression=match[0],
                resolved=value, insertion=' (' + value + ')', basis=basis)


def _explicit_day_anchor(prefix, date):
    """Last date mentioned in `prefix`."""
    hits = []
    for m in TR.find_temporal_mentions(prefix, date):
        if re.search(r'\b(?:earlier|later|before)$', m.text, re.I):
            continue
        _, edits, _ = base_annotate(m.text, date)
        if not edits:
            continue
        try:
            day = dt.datetime.strptime(edits[0]['resolved'], '%B %d, %Y').date()
        except ValueError:
            continue
        hits.append((m.end, day))
    months = '|'.join(TR.MONTHS)
    for m in re.finditer(r'\b(' + months + r') (\d{1,2}), (\d{4})\b', prefix, re.I):
        try:
            hits.append((m.end(), dt.date(int(m[3]), TR.MONTHS[m[1].lower()], int(m[2]))))
        except ValueError:
            pass
    return max(hits, default=(None, None), key=lambda x: x[0])[1]


def annotate(text, session_date, previous_turns=()):
    """Annotate all relative dates in a turn."""
    anchor = TR.parse_conversation_date(session_date)
    _, edits, skipped = context_annotate(text, session_date, previous_turns)
    edits = [e for e in edits if not re.fullmatch(r'on\s+(' + DAYS + r')', e['expression'], re.I)]

    def covered(match):
        """Whether the match is already annotated."""
        return (bool(ANNOTATION.match(text[match.end():])) or
                any(match.start() < e['end'] and e['start'] < match.end() for e in edits))

    for m in WEEKDAY.finditer(text):
        if covered(m):
            continue
        if re.search(r'\b(?:last|next|this|every|each|on)\s*$', text[:m.start()], re.I):
            continue
        if re.match(r'\s+(?:mornings|afternoons|evenings|nights)\b', text[m.end():], re.I):
            continue
        left, right = _sentence(text, m.start(), m.end())
        direction = _direction(left, right)
        if direction is None:
            skipped.append(dict(expression=m[0], reason='weekday_direction_not_established'))
            continue
        target = TR.WEEKDAYS[m[1].lower()]
        if (direction == -1 and target == anchor.weekday()
                and re.match(r'\s+(?:night|evening)\b', text[m.end():], re.I)):
            skipped.append(dict(expression=m[0], reason='same_day_past_night_ambiguous'))
            continue
        delta = ((target - anchor.weekday()) % 7 if direction == 1
                 else -((anchor.weekday() - target) % 7))
        edits.append(_day_edit(m, anchor + dt.timedelta(days=delta),
                              'weekday_future_inclusive' if direction == 1 else 'weekday_past_inclusive'))

    for m in FOLLOWUP.finditer(text):
        if covered(m):
            continue
        prefix = re.split(r'[.!?;\n]', text[:m.start()])[-1]
        source = _explicit_day_anchor(prefix, session_date)
        if source is None:
            continue
        expression = m[0].lower()
        numeric = re.fullmatch('(' + NUMBER + r') (day|week)s? (later|earlier)', expression)
        if numeric:
            amount = TR._number(numeric[1]) * (1 if numeric[3] == 'later' else -1)
            if numeric[2] == 'week':
                start = source - dt.timedelta(days=source.weekday()) + dt.timedelta(weeks=amount)
                value = TR.Resolution(start, start + dt.timedelta(days=6), 'week', 'explicit_local_anchor').display
                edits.append(dict(start=m.start(), end=m.end(), expression=m[0], resolved=value,
                                  insertion=' (' + value + ')', basis='explicit_local_anchor'))
                continue
            delta = amount
        else:
            delta = -1 if expression.endswith('before') else 1
        edits.append(_day_edit(m, source + dt.timedelta(days=delta), 'explicit_local_day_anchor'))

    edits.sort(key=lambda e: e['start'])
    for a, b in zip(edits, edits[1:]):
        assert a['end'] <= b['start'], (a, b)
    resolved = {e['expression'].lower() for e in edits}
    skipped = [s for s in skipped if s['expression'].lower() not in resolved]
    skipped = list({(s['expression'], s['reason']): s for s in skipped}.values())
    result = text
    for e in reversed(edits):
        result = result[:e['end']] + e['insertion'] + result[e['end']:]
    offset = 0
    positions = []
    for e in edits:
        positions.append((e['end'] + offset, len(e['insertion'])))
        offset += len(e['insertion'])
    recovered = result
    for pos, length in reversed(positions):
        recovered = recovered[:pos] + recovered[pos + length:]
    assert recovered == text
    return result, edits, skipped
