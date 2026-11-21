"""ContextFact extraction."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import json

from .. import prompt
from ..io import digest, read, save
from ..llm import Chat, IncompleteOutput, parse_json
from .preprocess import prepare, sessions

MAX_TOKENS = 16000
ATTEMPTS = 3


def session_prompt(template, conv, sid):
    """Build the extraction prompt for one session."""
    date = conv[f'session_{sid}_date_time']
    weekday = datetime.strptime(date.split(' on ', 1)[1], '%d %B, %Y').strftime('%A')
    lines = []
    for t in conv[f'session_{sid}']:
        line = f"{t['dia_id']} {t['speaker']}: {t['text']}"
        if t.get('blip_caption') or t.get('query'):
            line += ' [IMG blip=' + json.dumps(t.get('blip_caption') or '', ensure_ascii=False)
            line += ' query=' + json.dumps(t.get('query') or '', ensure_ascii=False) + ']'
        lines.append(line)
    actual = '\n\n## Participants\n\n' + ', '.join([conv['speaker_a'], conv['speaker_b']])
    actual += '\n\n## Conversation Date\n\n' + date + ' (' + weekday + ')'
    actual += '\n\n## Raw Turns\n\n' + '\n'.join(lines) + '\n'
    return template.split('# Actual Session', 1)[0] + '# Actual Session' + actual


def validate(result, turns):
    """Validate one session's extraction output."""
    if set(result) != {'contextfacts', 'entities'}:
        raise ValueError('Expected contextfacts and entities')
    known = {t['dia_id'] for t in turns}
    ids = []
    for f in result['contextfacts']:
        ids.append(f['contextfact_id'])
        if not isinstance(f['content'], str) or not isinstance(f['title'], str):
            raise ValueError('Invalid fact text')
        if not isinstance(f['turn_ids'], list) or not set(f['turn_ids']) <= known:
            raise ValueError('Unknown turn ID')
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate CF ID')
    for e in result['entities']:
        if not isinstance(e['name'], str) or not isinstance(e['description'], str):
            raise ValueError('Invalid entity')
        if not isinstance(e['contextfact_ids'], list) or not set(e['contextfact_ids']) <= set(ids):
            raise ValueError('Unknown CF link')


def extract(samples, out, workers=10):
    """Extract ContextFacts for all sessions and write the CF bank."""
    chat = Chat(out / 'llm_cache' / 'extraction')
    template = prompt('extraction')
    data, edits = prepare(samples)
    save(out / 'annotated_conversations.json', data)
    save(out / 'time_annotations.json', edits)
    tasks = [(s['sample_id'], s['conversation'], sid) for s in data for sid in sessions(s['conversation'])]

    def work(i, task):
        """Extract one session."""
        cid, conv, sid = task
        body = chat.body(session_prompt(template, conv, sid), MAX_TOKENS, seed=None,
                         response_format={'type': 'json_object'})
        h = digest(body)
        target = out / 'sessions' / f'{cid}_S{sid:02d}.json'
        if target.exists():
            item = read(target)
            if item['request_sha256'] != h:
                raise ValueError(f'{target} was built with a different request; use a new output directory')
        else:
            for attempt in range(ATTEMPTS):
                response = chat.complete(body, index=i, attempt=attempt)
                try:
                    if response['choices'][0]['finish_reason'] != 'stop':
                        raise IncompleteOutput(f'Incomplete generation for {cid} session {sid}')
                    output = parse_json(response['choices'][0]['message']['content'])
                    validate(output, conv[f'session_{sid}'])
                    break
                except (ValueError, KeyError, TypeError):
                    if attempt + 1 == ATTEMPTS:
                        raise
            item = dict(conv=cid, sid=sid, request_sha256=h, response=response, output=output)
            save(target, item)
        validate(item['output'], conv[f'session_{sid}'])
        return item

    done = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(work, i, t) for i, t in enumerate(tasks)]
        for f in as_completed(futures):
            done.append(f.result())
            print(f'ContextFact extraction: {len(done)}/{len(tasks)} sessions', flush=True)
    done.sort(key=lambda x: (x['conv'], x['sid']))
    bank = [dict(conv=s['conv'], sid=s['sid'], facts=[dict(
                contextfact_id=f"{s['conv']}_S{s['sid']:02d}_{f['contextfact_id']}",
                title=f['title'], fact=f['content'], evidence=f['turn_ids'])
                for f in s['output']['contextfacts']]) for s in done]
    save(out / 'bank/facts.json', {'sessions': bank})
    save(out / 'bank/contextfacts_entities.json',
         {'sessions': [dict(conv=s['conv'], sid=s['sid'], **s['output']) for s in done]})
    return dict(sessions=len(done), contextfacts=sum(len(s['facts']) for s in bank))
