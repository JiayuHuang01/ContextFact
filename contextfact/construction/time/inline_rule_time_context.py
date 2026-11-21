"""Inline date rules for weekdays and weekends."""
import datetime as dt
import re
from .inline_rule_time import annotate as base_annotate, TR

WEEKDAY=re.compile(r'\bon (Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b',re.I)
LATER=re.compile(r'\b(\d+|one|two|three|four|five|six) weekends? later\b',re.I)
PAST=re.compile(r'\b(?:won|went|met|visited|returned|finished|completed|bought|adopted|arrived|left|lost|attended|received|submitted|started|happened|was|were|did|had)\b',re.I)
FUTURE=re.compile(r"\b(?:will|shall|going to|plan to|planning to|plans to|scheduled to)|\b\w+'ll\b",re.I)

def annotate(text,session_date,previous_turns=()):
    """Add weekday and weekend rules to the base rules."""
    _,edits,skipped=base_annotate(text,session_date)
    anchor=TR.parse_conversation_date(session_date)
    added=[]
    for m in WEEKDAY.finditer(text):
        if re.match(r'\s*\([^()\n]*\d{4}[^()\n]*\)',text[m.end():]):continue
        clause=re.split(r'[.!?;\n]',text[:m.start()])[-1]
        future=bool(FUTURE.search(clause));past=bool(PAST.search(clause))
        if future==past:continue
        target=TR.WEEKDAYS[m[1].lower()]
        delta=(target-anchor.weekday())%7 if future else -((anchor.weekday()-target)%7)
        d=anchor+dt.timedelta(days=delta)
        resolution=TR.Resolution(d,d,'day','clause_future' if future else 'clause_past')
        added.append(dict(start=m.start(),end=m.end(),expression=m[0],resolved=resolution.display,
            insertion=' ('+resolution.display+')',basis=resolution.basis))
    for m in LATER.finditer(text):
        if re.match(r'\s*\([^()\n]*\d{4}[^()\n]*\)',text[m.end():]):continue
        prior=[dict(text=text[:m.start()],turn_id='same turn')]+list(reversed(list(previous_turns)[-3:]))
        antecedent=None
        for turn in prior:
            hits=list(re.finditer(r'\b(last|this|next) weekend\b',turn['text'],re.I))
            if not hits:continue
            h=hits[-1];word=h[1].lower()
            if word=='next':
                start=anchor-dt.timedelta(days=anchor.weekday())+dt.timedelta(days=12)
            else:start=TR.resolve_relative(anchor,h[0]).start
            antecedent=(start,turn.get('dia_id',turn.get('turn_id')),h[0]);break
        if antecedent is None:continue
        amount=TR._number(m[1]);start=antecedent[0]+dt.timedelta(weeks=amount)
        resolution=TR.Resolution(start,start+dt.timedelta(days=1),'weekend','explicit_previous_weekend')
        added.append(dict(start=m.start(),end=m.end(),expression=m[0],resolved=resolution.display,
            insertion=' ('+resolution.display+')',basis=resolution.basis,anchor_turn=antecedent[1],anchor_expression=antecedent[2]))
    expressions={e['expression'].lower() for e in added}
    skipped=[x for x in skipped if x['expression'].lower() not in expressions]
    edits=sorted(edits+added,key=lambda e:e['start']);result=text
    for e in reversed(edits):result=result[:e['end']]+e['insertion']+result[e['end']:]
    restored=result;shift=0;offsets=[]
    for e in edits:offsets.append((e['end']+shift,len(e['insertion'])));shift+=len(e['insertion'])
    for start,length in reversed(offsets):restored=restored[:start]+restored[start+length:]
    assert restored==text
    return result,edits,skipped
