"""Entity construction: binding, directory, leaf reconstruction."""
from concurrent.futures import ThreadPoolExecutor, as_completed

from ... import prompt
from ...io import read, save
from ...llm import Chat, usage
from ...retrieval.entity_bank import EntityBank
from ...retrieval.services import Services
from . import binding, directory, leaves
from .sources import load_sources, session_ids

STAGES = ('binding', 'directory', 'leaf')


def parallel(items, work, workers, label):
    """Run work over items in a thread pool."""
    results, errors = {}, {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(work, i, item): key for i, (key, item) in enumerate(items.items())}
        for future in as_completed(futures):
            key = futures[future]
            try:
                results[key] = future.result()
            except Exception as exc:
                errors[key] = f'{type(exc).__name__}: {exc}'
            print(f'Entity {label}: {len(results)}/{len(items)} done, {len(errors)} failed', flush=True)
    if errors:
        raise RuntimeError(f'{label} failed: {errors}')
    return results


def session_dates(conversations):
    """Session dates per conversation."""
    return {s['sample_id']: {str(sid): s['conversation'][f'session_{sid}_date_time']
                             for sid in session_ids(s['conversation'])}
            for s in conversations}


def build_entities(out, workers=10):
    """Build the Entity bank."""
    templates = {name: prompt(name) for name in STAGES}
    work_dir = out / 'entity'
    chat = Chat(out / 'llm_cache' / 'entity')
    conversations = read(out / 'annotated_conversations.json')
    sources = load_sources(conversations, read(out / 'bank/contextfacts_entities.json'),
                           read(out / 'bank/facts.json'), 'cf')
    for cid, source in sources.items():
        save(work_dir / 'sources' / f'{cid}.json', source)

    embed = binding.Embedder(Services(out / 'service_cache'))

    def bind(i, source):
        """Bind one conversation."""
        target = work_dir / 'binding' / source['conversation_id']
        if (target / 'bank.json').exists():
            return read(target / 'bank.json')
        return binding.bind(source, templates['binding'], chat, embed, target)
    banks = parallel(sources, bind, workers, 'binding')

    def organize(i, conv):
        """Build one conversation's directory."""
        target = work_dir / 'directory' / conv
        if (target / 'groups.json').exists():
            return read(target / 'groups.json'), read(target / 'id_map.json')
        return directory.organize(banks[conv], templates['directory'], chat, target, index=i)
    directories = parallel({c: c for c in banks}, organize, workers, 'directory')

    tasks, kept = {}, []
    for conv, (groups, id_map) in sorted(directories.items()):
        placed = set()
        for n, (path, group) in enumerate(leaves.leaves(groups['groups']), 1):
            text, meta = leaves.build_input(conv, path, group, groups['groups'], banks[conv], id_map)
            tasks[f'{conv}__L{n:03d}'] = (text, meta)
            placed.update(group['entity_ids'])
        kept += leaves.unassigned(conv, banks[conv], id_map, placed)

    def reconstruct(i, task):
        """Reconstruct one leaf."""
        target = work_dir / 'leaf' / f'{task}.json'
        if target.exists():
            return read(target)['entities']
        text, meta = tasks[task]
        entities = leaves.reconstruct(task, text, meta, templates['leaf'], chat, index=i)
        save(target, dict(input=text, meta=meta, entities=entities))
        return entities
    reconstructed = parallel({t: t for t in tasks}, reconstruct, workers, 'leaf reconstruction')

    entities = [e for task in sorted(reconstructed) for e in reconstructed[task]] + kept
    entities.sort(key=lambda e: e['conv'])
    if len(entities) != len({e['entity_id'] for e in entities}):
        raise ValueError('Duplicate Entity ID')
    bank_dir = out / 'bank'
    save(bank_dir / 'entity_bank.json', dict(schema_version='aspect_entity_v1', complete=True, entities=entities))
    save(bank_dir / 'session_dates.json', session_dates(conversations))
    bank = EntityBank(bank_dir / 'facts.json', bank_dir / 'entity_bank.json', bank_dir / 'session_dates.json')
    save(bank_dir / 'manifest.json', dict(
        counts=bank.counts(), model=chat.model, leaf_tasks=len(tasks),
        unassigned_entities=len(kept),
        binding_warnings=sum(len(b['warnings']) for b in banks.values()),
        llm_usage=usage(out / 'llm_cache' / 'entity')))
    return bank.counts()
