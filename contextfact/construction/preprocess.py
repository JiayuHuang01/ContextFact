"""Inline date annotation."""
from copy import deepcopy
import re
from .time.inline_rule_time_calendar import annotate

def sessions(conversation):
    """Session numbers in order."""
    return sorted((int(k.split('_')[1]) for k in conversation if re.fullmatch(r'session_\d+', k)))

def prepare(samples):
    """Annotate dates in all conversations."""
    data=deepcopy([{'sample_id':s['sample_id'],'conversation':s['conversation']} for s in samples])
    changes=[]
    for sample in data:
        conv=sample['conversation']
        for sid in sessions(conv):
            prior=[]
            for turn in conv[f'session_{sid}']:
                original=turn['text']
                text,edits,skipped=annotate(original,conv[f'session_{sid}_date_time'],prior)
                turn['text']=text
                if edits:
                    changes.append(dict(conv=sample['sample_id'],turn_id=turn['dia_id'],edits=edits))
                prior.append(dict(text=original,turn_id=turn['dia_id']))
    return data,changes
