"""ContextFact memory bank."""
from collections import defaultdict
from datetime import datetime

from ..io import read, unique


def load_dates(path):
    """Load session dates."""
    data = read(path)
    if isinstance(data, dict):
        return {(conv, int(sid)): date for conv, sessions in data.items()
                for sid, date in sessions.items()}
    return {(sample["sample_id"], int(key[len("session_"):-len("_date_time")])): value
            for sample in data for key, value in sample["conversation"].items()
            if key.startswith("session_") and key.endswith("_date_time")}


class Bank:
    """ContextFacts per conversation."""

    def __init__(self, cf_path, dates_path):
        """Load ContextFacts."""
        dates = load_dates(dates_path)
        self.docs, self.entities, self.cards, self.memories = {}, {}, {}, {}
        self.cf_by_conv, self.e_by_conv, self.m_by_conv = (defaultdict(list) for _ in range(3))
        self.e2m, self.cf2m = {}, defaultdict(list)
        aliases = {}
        seen_sessions = set()
        for session in read(cf_path)["sessions"]:
            conv, sid = session["conv"], int(session["sid"])
            if (conv, sid) in seen_sessions:
                raise ValueError(f"Duplicate CF session: {conv}/{sid}")
            seen_sessions.add((conv, sid))
            if (conv, sid) not in dates:
                raise ValueError(f"Missing session date: {conv}/{sid}")
            date = datetime.strptime(dates[conv, sid], "%I:%M %p on %d %B, %Y")
            for i, fact in enumerate(session["facts"]):
                fid = f"{conv}_s{sid}_f{i}"
                if fid in self.docs:
                    raise ValueError(f"Duplicate CF ID: {fid}")
                title, content = fact.get("title", ""), fact["fact"]
                weekday = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")[date.weekday()]
                text = f"[Memory recorded on: {date:%d %B %Y}, {weekday}] {title}\n{content}"
                self.docs[fid] = dict(id=fid, conv=conv, kind="cf", name=title,
                                      text=text, content=content, sid=sid)
                self.cf_by_conv[conv].append(fid)
                for alias in (fid, fact.get("contextfact_id", fid)):
                    if (conv, alias) in aliases and aliases[conv, alias] != fid:
                        raise ValueError(f"Ambiguous source CF ID: {conv}/{alias}")
                    aliases[conv, alias] = fid

    def linked_cf(self, mids):
        """ContextFacts cited by the given records."""
        return unique(fid for mid in mids for fid in self.memories[mid]["contextfact_ids"])

    def corpus(self, conv, kind):
        """IDs and texts to index."""
        if kind == "cf":
            ids = self.cf_by_conv[conv]
            return ids, [self.docs[i]["text"] for i in ids]
        if kind == "entity":
            ids = self.e_by_conv[conv]
            return ids, [self.cards[i]["text"] for i in ids]
        if kind == "memory":
            ids = self.m_by_conv[conv]
            return ids, [self.memories[i]["text"] for i in ids]
        raise ValueError(kind)

    def counts(self):
        """Bank size statistics."""
        return dict(conversations=len(self.cf_by_conv), contextfacts=len(self.docs),
                    entities=len(self.entities), memories=len(self.memories),
                    linked_contextfacts=sum(bool(mids) for mids in self.cf2m.values()))
