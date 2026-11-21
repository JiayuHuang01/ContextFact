"""Topic directory over entities."""
from ...io import save

MAX_TOKENS = 16384
MAX_DEPTH = 3


def cards(bank):
    """Short local IDs for entity cards."""
    entities = bank['entities']
    local = [dict(entity_id=f'E{i:03d}', name=e['name'], description=e['description'])
             for i, e in enumerate(entities, 1)]
    return local, {c['entity_id']: e['entity_id'] for c, e in zip(local, entities)}


def validate(groups, ids, depth=1):
    """Validate the directory."""
    if not isinstance(groups, list) or depth > MAX_DEPTH:
        raise ValueError('Directory must be a list of at most three levels')
    for g in groups:
        if not isinstance(g['name'], str) or not isinstance(g['description'], str):
            raise ValueError('Group name and description must be strings')
        if not set(g.get('entity_ids', [])) <= ids:
            raise ValueError('Unknown entity ID in directory')
        if g.get('children'):
            validate(g['children'], ids, depth + 1)


def organize(bank, template, chat, out, index=0, attempts=3):
    """Organize one conversation's entities into a topic directory."""
    local, id_map = cards(bank)
    save(out / 'id_map.json', id_map)
    text = '\n\n'.join(f"## {c['entity_id']}\nName: {c['name']}\nDescription: {c['description']}"
                       for c in local)
    body = chat.body(template.replace('{ENTITIES}', text), MAX_TOKENS)
    error = None
    for attempt in range(attempts):
        try:
            groups = chat.json(body, index=index, attempt=attempt)
            validate(groups['groups'], set(id_map))
            save(out / 'groups.json', groups)
            return groups, id_map
        except (ValueError, KeyError, TypeError) as exc:
            error = exc
    raise RuntimeError(f'Directory invalid after {attempts} attempts: {error}')
