"""ContextFact-E memory bank: ContextFacts plus Entities."""
from ..io import read, unique
from .bank import Bank


class EntityBank(Bank):
    def __init__(self, cf_path, entity_path, dates_path):
        """Load ContextFacts and Entities."""
        super().__init__(cf_path, dates_path)
        for doc in self.docs.values():
            doc['text'] = doc['text'].replace('[Memory recorded on: ', '[', 1)
        source = read(entity_path)
        if source.get('schema_version') != 'aspect_entity_v1':
            raise ValueError('Expected aspect_entity_v1 bank')
        for original in source['entities']:
            eid, conv = original['entity_id'], original['conv']
            if eid in self.entities or conv not in self.cf_by_conv:
                raise ValueError('Duplicate Entity ID or unknown conversation: '+eid)
            entity = dict(entity_id=eid, conv=conv, name=original['name'],
                          summary=original['summary'], records=[])
            self.entities[eid] = entity
            self.e_by_conv[conv].append(eid)
            self.e2m[eid] = []
            for r in original['records']:
                rid = r['record_id']
                if rid in self.memories:
                    raise ValueError('Duplicate record ID: '+rid)
                links = unique(r['contextfact_ids'])
                if any(f not in self.docs or self.docs[f]['conv'] != conv for f in links):
                    raise ValueError('Unknown or cross-conversation CF link: '+rid)
                record = dict(record_id=rid, name=r['name'], description=r['description'],
                              contextfact_ids=links)
                entity['records'].append(record)
                text = f"Entity: {entity['name']}\nRecord: {r['name']}\nDescription: {r['description']}"
                self.memories[rid] = dict(id=rid, conv=conv, kind='memory',
                                         entity_id=eid, text=text, **record)
                self.e2m[eid].append(rid)
                self.m_by_conv[conv].append(rid)
                for fid in links:
                    self.cf2m[fid].append(rid)
            if not entity['records']:
                raise ValueError('Entity has no records: '+eid)
            self.cards[eid] = dict(entity_id=eid, text=self.entity_text(entity))

    @staticmethod
    def entity_text(entity):
        """Render a whole Entity as text."""
        lines = ['Entity: '+entity['name'], 'Summary: '+entity['summary']]
        for i, r in enumerate(entity['records'], 1):
            lines.extend(['', f"Record {i}: {r['name']}", 'Description: '+r['description']])
        return '\n'.join(lines)

    def corpus(self, conv, kind):
        """IDs and texts to index."""
        if kind == 'entity':
            ids = self.e_by_conv[conv]
            return ids, [f"Name: {self.entities[e]['name']}\nSummary: {self.entities[e]['summary']}"
                         for e in ids]
        return super().corpus(conv, kind)

    def counts(self):
        """Bank size statistics."""
        counts = super().counts()
        counts['records'] = counts.pop('memories')
        return counts

    def context_with_mapping(self, cf_ids, entity_ids):
        """Render the Reader context and the CF short-ID map."""
        mapping = {}
        def short(fid):
            """Short ID for a CF."""
            if fid not in mapping:
                mapping[fid] = f'F{len(mapping)+1}'
            return mapping[fid]
        for fid in cf_ids:
            short(fid)
        for eid in entity_ids:
            for r in self.entities[eid]['records']:
                for fid in r['contextfact_ids']:
                    short(fid)
        lines = ['# ContextFacts', '']
        for fid in cf_ids:
            doc = self.docs[fid]
            date_header = doc['text'].split(']', 1)[0]+']'
            lines.extend([f"## {short(fid)} · {doc['name']}", date_header,
                          doc['content'], ''])
        lines.extend(['# Supplementary Entity Memories', '',
            'Source CFs identify supporting ContextFacts. Repeated IDs refer to the same source, '
            'not necessarily the same event. Some sources are referenced without their full text above.', ''])
        for entity_index, eid in enumerate(entity_ids, 1):
            e = self.entities[eid]
            lines.extend([f"## E{entity_index} · {e['name']}", '', 'Summary: '+e['summary']])
            for i, r in enumerate(e['records'], 1):
                lines.extend(['', f"### R{i} · {r['name']}", '', r['description'], '',
                              'Source CFs: '+(', '.join(short(f) for f in r['contextfact_ids']) or '[]')])
            lines.append('')
        return '\n'.join(lines).rstrip(), mapping

    def context(self, cf_ids, entity_ids):
        """Render the Reader context."""
        return self.context_with_mapping(cf_ids, entity_ids)[0]
