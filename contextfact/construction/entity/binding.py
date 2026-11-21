"""Cross-session entity binding."""
from collections import defaultdict
from datetime import datetime
import json

import numpy as np
from rank_bm25 import BM25Okapi

from ...io import save
from ...retrieval.search import lexical

DENSE_THRESHOLD = 0.60
BM25_MIN_SCORE = 6
MAX_TOKENS = 24576


def chronological(session):
    """Sort key for sessions by time."""
    return datetime.strptime(session['session_time_text'], '%I:%M %p on %d %B, %Y')


def speaker_lexical(text, participants):
    """BM25 tokens without speaker names."""
    tokens = lexical(text)
    names = sorted((lexical(name) for name in participants), key=len, reverse=True)
    out, i = [], 0
    while i < len(tokens):
        match = next((n for n in names if n and tokens[i:i + len(n)] == n), None)
        if match:
            i += len(match)
        else:
            out.append(tokens[i])
            i += 1
    return out


def select(dense, sparse):
    """Pick candidate entities by dense and BM25 scores."""
    by_bm25 = sorted((i for i, score in enumerate(sparse) if score >= BM25_MIN_SCORE),
                     key=lambda i: (-float(sparse[i]), i))
    by_dense = [i for i, v in enumerate(dense) if v >= DENSE_THRESHOLD]
    return list(dict.fromkeys(by_dense + by_bm25))


class Embedder:
    """In-memory embedding cache."""

    def __init__(self, services, batch_size=16):
        """Wrap an embedding service."""
        self.services, self.batch_size, self.vectors = services, batch_size, {}

    def __call__(self, texts):
        """Embed texts."""
        missing = [t for t in dict.fromkeys(texts) if t not in self.vectors]
        for start in range(0, len(missing), self.batch_size):
            chunk = missing[start:start + self.batch_size]
            self.vectors.update(zip(chunk, self.services.embed(chunk)))
        return np.asarray([self.vectors[t] for t in texts], dtype=np.float32)


def render_prompt(template, candidates, payload, rmap, emap):
    """Fill the binding prompt."""
    entities = '\n\n'.join(
        f"## {emap[e['entity_id']]}\nName: {e['name']}\nDescription: {e['description']}\n"
        f"Session times: {'; '.join(e['session_times'])}" for e in candidates)
    records = '\n\n'.join(
        f"## {rmap[r['record_id']]}\nName: {r['name']}\nDescription: {r['description']}\nContextFacts:\n"
        + '\n'.join(f"- {f['session_time']} | {f['title']}" for f in r['contextfacts'])
        + '\nCandidate entities: ' + ', '.join(emap[e] for e in r['candidate_entity_ids'])
        for r in payload)
    return template.replace('{CANDIDATE_ENTITIES}', entities).replace('{NEW_RECORDS}', records)


def decide(chat, prompt, index, attempts=3):
    """Ask the model for binding decisions."""
    body = chat.body(prompt, MAX_TOKENS, top_p=1)
    for attempt in range(attempts):
        try:
            return chat.json(body, index=index, attempt=attempt)
        except json.JSONDecodeError:
            if attempt + 1 == attempts:
                raise


def bind(source, template, chat, embed, out):
    """Bind one conversation's records into entities."""
    checkpoint = out / 'checkpoint.json'
    state = (json.loads(checkpoint.read_text()) if checkpoint.exists()
             else dict(entities=[], seen=[], warnings=[]))
    participants = source['participants']
    facts = {f['fact_id']: f for f in source['contextfacts']}
    sessions = sorted(source['sessions'], key=chronological)
    rank = {s['session_id']: i for i, s in enumerate(sessions)}
    records = {r['record_id']: r for r in source['records']}
    by_session = defaultdict(list)
    for record in source['records']:
        by_session[record['session_id']].append(record)
    for index, session in enumerate(sessions):
        sid = session['session_id']
        if sid in state['seen']:
            continue
        new = by_session[sid]
        old = state['entities']
        byid = {e['entity_id']: e for e in old}
        decisions, allowed = {}, {}
        if old and new:
            texts = [e['name'] + '\n' + e['description'] for e in old]
            queries = [r['name'] + '\n' + r['description'] for r in new]
            old_vectors, new_vectors = embed(texts), embed(queries)
            terms = [speaker_lexical(t, participants) for t in texts]
            bm25 = BM25Okapi(terms) if any(terms) else None
            selected, payload = set(), []
            for r, q, v in zip(new, queries, new_vectors):
                sparse = (bm25.get_scores(speaker_lexical(q, participants)) if bm25
                          else np.zeros(len(old)))
                chosen = select(old_vectors @ v, sparse)
                selected.update(chosen)
                candidate_ids = [old[i]['entity_id'] for i in chosen]
                allowed[r['record_id']] = set(candidate_ids)
                payload.append(dict(
                    record_id=r['record_id'], name=r['name'], description=r['description'],
                    contextfacts=[dict(session_time=facts[f]['session_time_text'], title=facts[f]['title'])
                                  for f in r['contextfact_ids']],
                    candidate_entity_ids=candidate_ids))
            candidates = [{k: e[k] for k in ('entity_id', 'name', 'description')}
                          for i, e in enumerate(old) if i in selected]
            for candidate in candidates:
                entity = byid[candidate['entity_id']]
                members = sorted((records[rid] for rid in entity['record_ids']),
                                 key=lambda r: rank[r['session_id']])
                candidate['session_times'] = list(dict.fromkeys(
                    facts[f]['session_time_text'] for r in members for f in r['contextfact_ids']))
            rmap = {r['record_id']: f'r{i + 1}' for i, r in enumerate(new)}
            emap = {e['entity_id']: f'e{i + 1}' for i, e in enumerate(candidates)}
            prompt = render_prompt(template, candidates, payload, rmap, emap)
            local = decide(chat, prompt, index)
            reverse_r = {v: k for k, v in rmap.items()}
            reverse_e = {v: k for k, v in emap.items()}
            for d in local.get('decisions', []):
                if not isinstance(d, dict):
                    continue
                rid, target = d.get('record_id'), d.get('entity_id')
                if not isinstance(rid, str):
                    continue
                rid = reverse_r.get(rid, rid)
                target = reverse_e.get(target, target) if isinstance(target, str) else None
                decisions[rid] = {**d, 'record_id': rid, 'entity_id': target}
        for r in new:
            d = decisions.get(r['record_id'], {})
            target = d.get('entity_id')
            if d.get('action') == 'add' and target in allowed.get(r['record_id'], ()):
                entity = byid[target]
                entity['record_ids'].append(r['record_id'])
                for key in ('name', 'description'):
                    if isinstance(d.get(key), str) and d[key].strip():
                        entity[key] = d[key]
                    else:
                        state['warnings'].append(dict(session=sid, record_id=r['record_id'],
                                                      issue='missing_updated_' + key))
            else:
                if decisions and d.get('action') != 'new':
                    state['warnings'].append(dict(session=sid, record_id=r['record_id'],
                                                  issue='unusable_decision', decision=d))
                entity = dict(entity_id=r['record_id'], name=r['name'],
                              description=r['description'], record_ids=[r['record_id']])
                old.append(entity)
        state['seen'].append(sid)
        save(checkpoint, state)
    bank = dict(records=source['records'], entities=state['entities'], warnings=state['warnings'])
    save(out / 'bank.json', bank)
    return bank
