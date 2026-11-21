"""Leaf reconstruction into final Entities."""
import json
import re

MAX_TOKENS = 16384
SHOWN_ABOVE = '[原文已在上方展示]'


def leaves(groups, path=()):
    """Yield the groups that list entities."""
    for g in groups:
        current = (*path, g['name'])
        if g.get('entity_ids'):
            yield current, g
        yield from leaves(g.get('children', []), current)


def build_input(conv, path, group, groups, bank, id_map):
    """Build the reconstruction input for one leaf."""
    entities = {e['entity_id']: e for e in bank['entities']}
    records = {r['record_id']: r for r in bank['records']}
    chosen, fact_map, turns = [], {}, {}
    rindex = 0
    for eid in group['entity_ids']:
        e = entities[id_map[eid]]
        members = []
        for rid in e['record_ids']:
            rindex += 1
            r = records[rid]
            members.append({'local_id': f'r{rindex}', **r})
            for cf in r['contextfacts']:
                fact_map[cf['fact_id']] = cf
            for raw in r['evidence']:
                match = re.match(r'^\[(D\d+:\d+)\]', raw)
                if match:
                    turns[match[1]] = raw
        chosen.append({'local_id': eid, **e, 'members': members})
    facts = sorted(fact_map.values(), key=lambda f: (
        f['session_id'], min(int(t.split(':')[1]) for t in f['turn_ids'])))
    fmap = {f['fact_id']: f'f{i + 1}' for i, f in enumerate(facts)}
    lines = ['# Global Entity Directory', '', *['- ' + g['name'] for g in groups],
             '', '# Current Topic', '', 'Path: ' + ' > '.join(path), '',
             'Description: ' + group['description'], '',
             '# Original Evidence in Session Order', '']
    shown, missing = set(), []
    for f in facts:
        lines.extend(['## ' + fmap[f['fact_id']] + ' ' + f['title'], '',
                      f['session_time_text'].split(' on ')[-1], ''])
        for tid in f['turn_ids']:
            if tid in shown:
                lines.extend([f'{tid}: {SHOWN_ABOVE}', ''])
                continue
            if tid not in turns:
                missing.append(tid)
                continue
            shown.add(tid)
            raw = re.sub(r'^\[(D\d+:\d+)\]\[([^]]+)\]', r'\1 \2:\n', turns[tid])
            lines.extend([raw, ''])
    lines.extend(['# Entities and Member Records', ''])
    for e in chosen:
        lines.extend(['## ' + e['local_id'], ''])
        single = len(e['members']) == 1 and all(
            e[k] == e['members'][0][k] for k in ('name', 'description'))
        if not single:
            lines.extend(['Name: ' + e['name'], 'Description: ' + e['description'],
                          '', 'Member records:', ''])
        for r in e['members']:
            lines.extend([('Member record: ' if single else '### ') + r['local_id'],
                          'Evidence Source: ' + ', '.join(fmap[c['fact_id']] for c in r['contextfacts']),
                          'Date: ' + r['session_time_text'].split(' on ')[-1],
                          'Name: ' + r['name'], 'Description: ' + r['description'], ''])
    meta = dict(conversation=conv, path=list(path),
                fact_map=fmap, entities={e['local_id']: e['entity_id'] for e in chosen})
    if missing:
        raise ValueError(f'Leaf evidence is missing CF turns: {missing}')
    return '\n'.join(lines), meta


def correction(entity_ids, fact_ids):
    """Retry instructions listing the allowed IDs."""
    return ('\n\n# Structural validation requirements for this retry\n'
            'Previous outputs failed source-ID validation. Return the same requested JSON schema. '
            'Each output entity must have a nonempty source_entity_ids list containing only exact IDs from the input entity inventory; '
            'for a split, reuse the valid parent entity ID, not a composite entity:record ID. '
            'Do not invent lineage for an additional referent that is not represented by an input entity or its member records. '
            'Each record must have nonempty contextfact_ids containing only the supplied ContextFact IDs. '
            'Do not invent IDs or infer missing evidence. Preserve supported input referents and the original task requirements.\n'
            'Allowed source_entity_ids: ' + json.dumps(sorted(entity_ids)) + '\n'
            'Allowed contextfact_ids: ' + json.dumps(sorted(fact_ids)) + '\n')


def schema(entity_ids, fact_ids):
    """Strict JSON schema for the last attempt."""
    record = dict(type='object', additionalProperties=False,
                  required=['name', 'description', 'contextfact_ids'],
                  properties=dict(name=dict(type='string'), description=dict(type='string'),
                                  contextfact_ids=dict(type='array', minItems=1,
                                                       items=dict(type='string', enum=sorted(fact_ids)))))
    entity = dict(type='object', additionalProperties=False,
                  required=['entity_id', 'source_entity_ids', 'name', 'summary', 'records'],
                  properties=dict(entity_id=dict(type='string'),
                                  source_entity_ids=dict(type='array', minItems=1,
                                                         items=dict(type='string', enum=sorted(entity_ids))),
                                  name=dict(type='string'), summary=dict(type='string'),
                                  records=dict(type='array', items=record, minItems=1)))
    return dict(type='json_schema', json_schema=dict(
        name='source_grounded_entities', strict=True,
        schema=dict(type='object', additionalProperties=False, required=['entities'],
                    properties=dict(entities=dict(type='array', items=entity, minItems=1)))))


def validate(result, entity_ids, fact_ids):
    """Validate reconstructed entities."""
    es = result['entities']
    if not isinstance(es, list) or not es or len({e['entity_id'] for e in es}) != len(es):
        raise ValueError('Entities must be a nonempty list with unique local IDs')
    for e in es:
        if not all(isinstance(e[k], str) and e[k].strip() for k in ('entity_id', 'name', 'summary')):
            raise ValueError('Entity text fields must be nonempty strings')
        if not e['source_entity_ids'] or not set(e['source_entity_ids']) <= entity_ids:
            raise ValueError('source_entity_ids must be nonempty input IDs')
        if not e['records']:
            raise ValueError('Each entity needs records')
        for r in e['records']:
            if not all(isinstance(r[k], str) and r[k].strip() for k in ('name', 'description')):
                raise ValueError('Record text fields must be nonempty strings')
            if not r['contextfact_ids'] or not set(r['contextfact_ids']) <= fact_ids:
                raise ValueError('contextfact_ids must be nonempty supplied IDs')


def reconstruct(task, text, meta, template, chat, index=0):
    """Reconstruct one leaf into final Entities."""
    prompt = template.split('# Global Entity Directory\n', 1)[0] + text
    local_facts = {v: k for k, v in meta['fact_map'].items()}
    entity_ids, fact_ids = set(meta['entities']), set(local_facts)
    error = None
    for attempt in range(5):
        current = prompt + (correction(entity_ids, fact_ids) if attempt >= 3 else '')
        extra = dict(response_format=schema(entity_ids, fact_ids)) if attempt == 4 else {}
        try:
            result = chat.json(chat.body(current, MAX_TOKENS, **extra), index=index, attempt=attempt)
            validate(result, entity_ids, fact_ids)
            break
        except (ValueError, KeyError, TypeError) as exc:
            error = exc
    else:
        raise RuntimeError(f'Leaf {task} invalid after 5 attempts: {error}')
    entities = []
    for e in result['entities']:
        eid = task + '__' + e['entity_id']
        entities.append(dict(
            entity_id=eid, conv=meta['conversation'], name=e['name'], summary=e['summary'],
            source_entity_ids=[meta['entities'][i] for i in e['source_entity_ids']],
            origin='leaf_refined',
            records=[dict(record_id=f'{eid}::R{i:03d}', name=r['name'], description=r['description'],
                          contextfact_ids=list(dict.fromkeys(local_facts[f] for f in r['contextfact_ids'])))
                     for i, r in enumerate(e['records'], 1)]))
    return entities


def unassigned(conv, bank, id_map, placed):
    """Keep entities the directory did not place."""
    records = {r['record_id']: r for r in bank['records']}
    byid = {e['entity_id']: e for e in bank['entities']}
    out = []
    for local in sorted(set(id_map) - placed):
        e = byid[id_map[local]]
        out.append(dict(
            entity_id=e['entity_id'], conv=conv, name=e['name'], summary=e['description'],
            source_entity_ids=[e['entity_id']], origin='unassigned_original',
            records=[dict(record_id=f"{e['entity_id']}::R{i:03d}", name=records[rid]['name'],
                          description=records[rid]['description'],
                          contextfact_ids=list(dict.fromkeys(records[rid]['contextfact_ids'])),
                          source_record_ids=[rid])
                     for i, rid in enumerate(e['record_ids'], 1)]))
    return out
