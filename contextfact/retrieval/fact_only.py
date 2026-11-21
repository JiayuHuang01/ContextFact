"""ContextFact-F retrieval."""
FORMATS = ('numbered', 'plain')


def prepare(bank, fmt='numbered'):
    """Prepare CF texts for the chosen format."""
    if fmt not in FORMATS:
        raise ValueError(f'format must be one of {FORMATS}')
    if fmt == 'numbered':
        for doc in bank.docs.values():
            doc['text'] = doc['text'].replace('[Memory recorded on: ', '[', 1)
    return bank


def render(bank, ids, fmt='numbered'):
    """Render CFs as Reader context."""
    if fmt == 'plain':
        return '\n\n'.join(bank.docs[f]['text'] for f in ids)
    lines = ['# ContextFacts']
    for i, f in enumerate(ids, 1):
        d = bank.docs[f]
        lines.append(f"## F{i} · {d['name']}\n{d['text'].split(']', 1)[0] + ']'}\n{d['content']}")
    return '\n\n'.join(lines)


def retrieve(bank, conv, query, search, reranker, *, fmt='numbered', cf_k=30, top_k=10):
    """Retrieve CFs for a query."""
    seeds = search.search(conv, query, 'cf', cf_k)
    ranked = reranker(query, seeds, [bank.docs[f]['text'] for f in seeds])
    ids = ranked[:top_k]
    return dict(context=render(bank, ids, fmt), fact_ids=ids, entity_ids=[], record_ids=[],
                candidate_pool=dict(cf_ids=seeds), cf_rerank_order=ranked)
