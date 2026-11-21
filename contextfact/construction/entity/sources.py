"""Inputs for entity construction."""
import json
import re

CONTEXT_RADIUS = 2


def render_source_turn(turn):
    """Render one turn as text."""
    line = f"[{turn['turn_id']}][{turn['speaker']}]{turn['text']}"
    fields = [f"{label}={json.dumps(turn[key], ensure_ascii=False)}"
              for key, label in (('blip_caption', 'blip'), ('query', 'query'))
              if turn.get(key) not in (None, '')]
    if fields:
        line += ' [IMG ' + ' '.join(fields) + ']'
    return line


def session_ids(conversation):
    """Session numbers in order."""
    return sorted(int(k.split('_')[1]) for k in conversation if re.fullmatch(r'session_\d+', k))


def load_sources(conversations, extraction, facts, namespace):
    """Build per-conversation turns, ContextFacts and entity records."""
    extracted = {(s['conv'], int(s['sid'])): s for s in extraction['sessions']}
    bank = {(s['conv'], int(s['sid'])): s for s in facts['sessions']}
    sources = {}
    for sample in conversations:
        cid, dialogue = sample['sample_id'], sample['conversation']
        participants = [dialogue['speaker_a'], dialogue['speaker_b']]
        turns, sessions, contextfacts, records = {}, [], [], []
        for sid in session_ids(dialogue):
            time_text = dialogue[f'session_{sid}_date_time']
            order = []
            for turn in dialogue[f'session_{sid}']:
                tid = turn['dia_id']
                if tid in turns or not tid.startswith(f'D{sid}:'):
                    raise ValueError(f'Duplicate or cross-session turn: {cid}/{tid}')
                turns[tid] = dict(turn_id=tid, speaker=turn['speaker'], text=turn['text'],
                                  session_id=sid, session_time_text=time_text)
                for key in ('blip_caption', 'query'):
                    if key in turn:
                        turns[tid][key] = turn[key]
                order.append(tid)
            sessions.append(dict(session_id=sid, session_time_text=time_text, turn_ids=order))
            if (cid, sid) not in extracted:
                raise ValueError(f'Missing extracted session: {cid}/{sid}')
            session, retrieval = extracted[cid, sid], bank[cid, sid]['facts']
            if len(session['contextfacts']) != len(retrieval):
                raise ValueError(f'CF count mismatch: {cid}/{sid}')
            positions = {tid: i for i, tid in enumerate(order)}
            local = {}
            for index, (fact, stored) in enumerate(zip(session['contextfacts'], retrieval)):
                if fact['title'] != stored['title'] or fact['content'] != stored['fact']:
                    raise ValueError(f'CF content mismatch: {cid}/{sid}/{index}')
                local[fact['contextfact_id']] = dict(
                    fact_id=f'{cid}_s{sid}_f{index}', title=fact['title'], content=fact['content'],
                    turn_ids=list(fact['turn_ids']), session_id=sid, session_time_text=time_text)
                contextfacts.append(local[fact['contextfact_id']])
            for index, entity in enumerate(session['entities'], 1):
                linked = [local[f] for f in entity['contextfact_ids']]
                candidate = sorted({t for f in linked for t in f['turn_ids']}, key=positions.__getitem__)
                window = sorted({i for t in candidate
                                 for i in range(max(0, positions[t] - CONTEXT_RADIUS),
                                                min(len(order), positions[t] + CONTEXT_RADIUS + 1))})
                context = [order[i] for i in window]
                records.append(dict(
                    record_id=f'{namespace}/{cid}_S{sid:02d}_E{index:03d}',
                    name=entity['name'], description=entity['description'],
                    session_id=sid, session_time_text=time_text,
                    contextfact_ids=[f['fact_id'] for f in linked],
                    candidate_turn_ids=candidate, context_turn_ids=context,
                    evidence=[render_source_turn(turns[t]) for t in context],
                    contextfacts=linked))
        sources[cid] = dict(conversation_id=cid, participants=participants, records=records,
                            turns=turns, sessions=sessions, contextfacts=contextfacts)
    return sources
