"""ContextFact-E retrieval."""
from ..io import unique


def pool_from_seeds(bank, cf_seeds, entity_seeds, record_seeds=()):
    """Expand seeds one hop through record links."""
    cf, direct, records = map(list, (cf_seeds, entity_seeds, record_seeds))
    associated = [bank.memories[m]['entity_id'] for f in cf
                  for m in bank.cf2m.get(f, ())]
    eids = unique(associated + direct + [bank.memories[m]['entity_id'] for m in records])
    mids = [m for e in eids for m in bank.e2m[e]]
    fids = unique(cf + bank.linked_cf(mids))
    return dict(cf_ids=fids, entity_ids=eids, record_ids=mids,
                cf_seed_ids=cf, entity_seed_ids=direct, record_seed_ids=records)


def discover(bank, conv, query, search, *, cf_k=30, entity_k=30, memory_k=0):
    """Find seed CFs and Entities and expand them."""
    if cf_k < 1 or entity_k < 0 or memory_k < 0:
        raise ValueError('CF seeds must be positive; Entity/Record seeds nonnegative')
    cf = search.search(conv, query, 'cf', cf_k)
    entities = search.search(conv, query, 'entity', entity_k) if entity_k else []
    records = search.search(conv, query, 'memory', memory_k) if memory_k else []
    pool = pool_from_seeds(bank, cf, entities, records)
    pool['seed_counts'] = dict(cf=cf_k, entity=entity_k, record=memory_k)
    return pool


def select_pool(bank, query, pool, reranker, *, top_k=10):
    """Rerank the pools and render the context."""
    if top_k < 1:
        raise ValueError('top_k must be positive')
    cf_ranked = reranker(query, pool['cf_ids'], [bank.docs[f]['text'] for f in pool['cf_ids']])
    e_ranked = reranker(query, pool['entity_ids'], [bank.cards[e]['text'] for e in pool['entity_ids']])
    fids, eids = cf_ranked[:top_k], e_ranked[:top_k]
    context, mapping = bank.context_with_mapping(fids, eids)
    return dict(context=context, source_cf_map=mapping, fact_ids=fids, entity_ids=eids,
                record_ids=[m for e in eids for m in bank.e2m[e]], candidate_pool=pool,
                cf_rerank_order=cf_ranked, entity_rerank_order=e_ranked)


def retrieve(bank, conv, query, search, reranker, *, top_k=10,
             cf_k=30, entity_k=30, memory_k=0):
    """Retrieve CFs and Entities for a query."""
    pool = discover(bank, conv, query, search, cf_k=cf_k,
                    entity_k=entity_k, memory_k=memory_k)
    return select_pool(bank, query, pool, reranker, top_k=top_k)
