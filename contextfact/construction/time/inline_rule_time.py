"""Base rules for inline dates."""
import datetime as dt
import re

from . import time_resolver as TR

UNANCHORED={'the night before','the day before','the next day','the week before','the month after'}
EXTRA=re.compile(r'\b(?:on (?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)|'
    r'(?:\d+|one|two|three|four) weekends? later|the weekend)\b',re.I)

def annotate(text,session_date):
    """Insert resolved dates after relative expressions."""
    anchor=TR.parse_conversation_date(session_date)
    mentions=TR.find_temporal_mentions(text,anchor)
    edits=[];skipped=[]
    for m in mentions:
        expression=re.sub(r'\s+',' ',m.text.lower())
        if re.match(r'\s*\([^()\n]*\b\d{4}\b[^()\n]*\)',text[m.end:]):
            skipped.append(dict(expression=m.text,reason='already_annotated'));continue
        if expression in UNANCHORED or re.search(r'\b(?:earlier|before|later)$',expression):
            skipped.append(dict(expression=m.text,reason='needs_another_temporal_anchor'));continue
        resolution=m.resolution
        weekday=re.fullmatch(r'(?:last|this past) (monday|tuesday|wednesday|thursday|friday|saturday|sunday)',expression)
        if weekday:
            delta=(anchor.weekday()-TR.WEEKDAYS[weekday[1]])%7 or 7
            d=anchor-dt.timedelta(days=delta)
            resolution=TR.Resolution(d,d,'day','nearest_strictly_previous_weekday')
        weeks=re.fullmatch(r'(\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten) weeks? (ago|from now)',expression)
        if weeks:
            n=TR._number(weeks[1]);direction=-1 if weeks[2]=='ago' else 1
            monday=anchor-dt.timedelta(days=anchor.weekday())+dt.timedelta(weeks=direction*n)
            resolution=TR.Resolution(monday,monday+dt.timedelta(days=6),'week','calendar_week_precision')
        inweeks=re.fullmatch(r'in (\d+|one|two|three|four|five|six|seven|eight|nine|ten) weeks?',expression)
        if inweeks:
            monday=anchor-dt.timedelta(days=anchor.weekday())+dt.timedelta(weeks=TR._number(inweeks[1]))
            resolution=TR.Resolution(monday,monday+dt.timedelta(days=6),'week','calendar_week_precision')
        if expression=='next weekend':
            monday=anchor-dt.timedelta(days=anchor.weekday())+dt.timedelta(days=7)
            resolution=TR.Resolution(monday+dt.timedelta(days=5),monday+dt.timedelta(days=6),'weekend','next_calendar_weekend')
        if resolution is None:
            skipped.append(dict(expression=m.text,reason='vague_seasonal_or_ambiguous'));continue
        edits.append(dict(start=m.start,end=m.end,expression=m.text,resolved=resolution.display,
            insertion=' ('+resolution.display+')'))
    for m in EXTRA.finditer(text):
        if not any(m.start()<x.end and x.start<m.end() for x in mentions):
            skipped.append(dict(expression=m[0],reason='needs_context_or_direction'))
    result=text
    for e in reversed(edits):result=result[:e['end']]+e['insertion']+result[e['end']:]
    restored=result;offsets=[];shift=0
    for e in edits:
        offsets.append((e['end']+shift,len(e['insertion'])));shift+=len(e['insertion'])
    for start,length in reversed(offsets):restored=restored[:start]+restored[start+length:]
    assert restored==text
    return result,edits,skipped
