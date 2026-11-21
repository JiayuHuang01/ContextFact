"""ContextFact command line: run | prepare | build | retrieve | evaluate."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import re
import sys

from .io import digest, frozen, read, save, tokens, write_text

SAFE_ID = re.compile(r'[A-Za-z0-9_-]+')


def load_questions(path, *, conv=None, limit=None, gold=True):
    """Load questions, optionally filtered by conversation and limit."""
    path = Path(path)
    raw = read(path) if path.name.endswith(('.json', '.json.gz')) else [
        json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    keys = ('qid', 'conv', 'question', 'gold', 'category') if gold else ('qid', 'conv', 'question')
    rows = [{k: r[k] for k in keys} for r in raw]
    if conv:
        rows = [r for r in rows if r['conv'] in conv]
    if limit:
        rows = rows[:limit]
    if not rows or len(rows) != len({r['qid'] for r in rows}):
        raise SystemExit('Questions must be nonempty with unique qids')
    if any(not SAFE_ID.fullmatch(r['qid']) for r in rows):
        raise SystemExit('qids may contain only letters, digits, "_" and "-"')
    return rows


def cmd_prepare(a):
    """Convert LoCoMo QA into a question file."""
    rows = []
    for sample in json.loads(Path(a.locomo).read_text()):
        kept = [x for x in sample['qa'] if x.get('category') != 5]
        rows += [dict(qid=f"{sample['sample_id']}_q{i}", conv=sample['sample_id'], question=x['question'],
                      gold=str(x['answer']), category=x['category']) for i, x in enumerate(kept)]
    save(Path(a.out), rows)
    print(f'{len(rows)} questions -> {a.out}')


def cmd_build(a):
    """Build the memory bank."""
    from .construction.extract import extract
    rows = json.loads(Path(a.input).read_text())
    rows = [{k: r[k] for k in ('sample_id', 'conversation')} for r in rows]
    if a.conv:
        rows = [r for r in rows if r['sample_id'] in a.conv]
    if not rows:
        raise SystemExit('No conversations selected')
    if any(not SAFE_ID.fullmatch(r['sample_id']) for r in rows) or len({r['sample_id'] for r in rows}) != len(rows):
        raise SystemExit('Conversation IDs must be unique and safe')
    out = Path(a.out)
    frozen(out / 'build.json', dict(variant=a.variant, input_sha256=digest(Path(a.input).read_text()),
                                    conversations=[r['sample_id'] for r in rows]))
    print('CF bank:', extract(rows, out, a.workers))
    if a.variant == 'E':
        from .construction.entity.pipeline import build_entities
        print('Entity bank:', build_entities(out, a.workers))
    else:
        from .construction.entity.pipeline import session_dates
        save(out / 'bank/session_dates.json', session_dates(read(out / 'annotated_conversations.json')))
    print('Bank ready:', out / 'bank')


def cmd_retrieve(a):
    """Retrieve evidence for each question."""
    from .retrieval.bank import Bank
    from .retrieval.entity_bank import EntityBank
    from .retrieval import fact_only, guiding
    from .retrieval.search import Search
    from .retrieval.services import Services
    bank_dir = Path(a.bank)

    def bank_file(name):
        """Find a bank file, plain or gzipped."""
        for candidate in (bank_dir / f'{name}.json', bank_dir / f'{name}.json.gz'):
            if candidate.exists():
                return candidate
        raise SystemExit(f'Missing {name}.json(.gz) in {bank_dir}')
    facts, dates = bank_file('facts'), bank_file('session_dates')
    if a.variant == 'F':
        bank = fact_only.prepare(Bank(facts, dates), a.cf_format)
    else:
        bank = EntityBank(facts, bank_file('entity_bank'), dates)
    if a.query:
        if not a.conv or len(a.conv) != 1:
            raise SystemExit('--query needs exactly one --conv')
        rows = [dict(qid='query', conv=a.conv[0], question=a.query)]
    elif a.questions:
        rows = load_questions(a.questions, conv=a.conv, limit=a.limit, gold=False)
    else:
        raise SystemExit('Supply --questions, or --conv with --query')
    unknown = {r['conv'] for r in rows} - set(bank.cf_by_conv)
    if unknown:
        raise SystemExit(f'Conversations not in bank: {sorted(unknown)}')
    out = Path(a.out)
    services = Services(out / 'service_cache', offline=a.offline)
    frozen(out / 'retrieval.json', dict(
        variant=a.variant, bank=str(bank_dir), counts=bank.counts(), services=services.config(),
        cf_k=a.cf_k, entity_k=a.entity_k if a.variant == 'E' else 0, top_k=a.top_k,
        cf_format=a.cf_format if a.variant == 'F' else None, rrf_k=60,
        questions_sha256=None if a.query else digest(rows)))
    search = Search(bank, services, out / 'service_cache')
    search.build(sorted({r['conv'] for r in rows}), kinds=('cf',) if a.variant == 'F' else ('cf', 'entity'))

    def work(row):
        """Retrieve one question and save the result."""
        if a.variant == 'F':
            result = fact_only.retrieve(bank, row['conv'], row['question'], search, services.rerank,
                                        fmt=a.cf_format, cf_k=a.cf_k, top_k=a.top_k)
        else:
            result = guiding.retrieve(bank, row['conv'], row['question'], search, services.rerank,
                                      top_k=a.top_k, cf_k=a.cf_k, entity_k=a.entity_k)
        context = result.pop('context')
        result.update(row, evidence_tokens=tokens(context))
        write_text(out / 'contexts' / f"{row['qid']}.txt", context)
        save(out / 'selections' / f"{row['qid']}.json", result)
        return context

    errors = []
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        futures = {pool.submit(work, r): r['qid'] for r in rows}
        for n, future in enumerate(as_completed(futures), 1):
            try:
                context = future.result()
                if a.query:
                    print(context)
            except Exception as exc:
                errors.append(dict(qid=futures[future], error=f'{type(exc).__name__}: {exc}'))
            if not a.query:
                print(f'Retrieval: {n}/{len(rows)}, {len(errors)} failed', flush=True)
    save(out / 'errors.json', errors)
    if errors:
        raise SystemExit(f'{len(errors)} questions failed; see {out / "errors.json"} and rerun to resume')


def cmd_evaluate(a):
    """Answer, judge and report."""
    from .evaluation.answer import evaluate
    from .evaluation.metrics import print_report
    rows = load_questions(a.questions, conv=a.conv, limit=a.limit)
    report = evaluate(Path(a.retrieval), rows, Path(a.out), judge=not a.no_judge,
                      judge_seed=a.judge_seed, workers=a.workers)
    if report:
        print_report(report, a.out)


def cmd_run(a):
    """Build the memory once, then retrieve and evaluate each variant."""
    out = Path(a.out)
    conv = [x for c in a.conv or [] for x in ('--conv', c)]
    limit = ['--limit', str(a.limit)] if a.limit else []
    variants = ('F', 'E') if a.variant == 'FE' else (a.variant,)
    main(['build', '--input', a.input, '--variant', variants[-1], '--out', str(out / 'build'), *conv])
    for v in variants:
        main(['retrieve', '--bank', str(out / 'build/bank'), '--variant', v, '--questions', a.questions,
              '--out', str(out / f'retrieval_{v}'), *conv, *limit])
        main(['evaluate', '--retrieval', str(out / f'retrieval_{v}'), '--questions', a.questions,
              '--out', str(out / f'eval_{v}'), *conv, *limit, *(['--no-judge'] if a.no_judge else [])])


def main(argv=None):
    """Run the command line."""
    p = argparse.ArgumentParser(prog='python -m contextfact', description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='command', required=True)

    s = sub.add_parser('run', help='build -> retrieve -> evaluate in one command')
    s.add_argument('--input', default='data/locomo10.json')
    s.add_argument('--questions', default='data/questions.json')
    s.add_argument('--variant', choices=('F', 'E', 'FE'), default='FE')
    s.add_argument('--conv', action='append')
    s.add_argument('--limit', type=int)
    s.add_argument('--no-judge', action='store_true')
    s.add_argument('--out', default='runs/locomo')
    s.set_defaults(func=cmd_run)

    s = sub.add_parser('prepare', help='LoCoMo QA -> question file (category 5 excluded)')
    s.add_argument('--locomo', required=True, help='raw locomo10.json')
    s.add_argument('--out', required=True)
    s.set_defaults(func=cmd_prepare)

    s = sub.add_parser('build', help='construct a ContextFact bank (F) or CF + Entity bank (E)')
    s.add_argument('--input', required=True, help='LoCoMo-format conversations JSON')
    s.add_argument('--variant', choices=('F', 'E'), default='E')
    s.add_argument('--conv', action='append', help='restrict to these sample_ids (repeatable)')
    s.add_argument('--workers', type=int, default=10)
    s.add_argument('--out', required=True, help='build directory; rerun the same command to resume')
    s.set_defaults(func=cmd_build)

    s = sub.add_parser('retrieve', help='retrieve evidence for questions (no answering)')
    s.add_argument('--bank', required=True, help='<build>/bank')
    s.add_argument('--variant', choices=('F', 'E'), default='E')
    s.add_argument('--questions', help='question JSON/JSONL with qid, conv, question')
    s.add_argument('--query', help='ad-hoc question (needs one --conv); prints the context')
    s.add_argument('--conv', action='append')
    s.add_argument('--limit', type=int)
    s.add_argument('--cf-k', type=int, default=30, help='CF seeds from hybrid search')
    s.add_argument('--entity-k', type=int, default=30, help='Entity seeds (E only)')
    s.add_argument('--top-k', type=int, default=10, help='CFs (and Entities) given to the Reader')
    s.add_argument('--cf-format', choices=('numbered', 'plain'), default='numbered', help='F rendering')
    s.add_argument('--workers', type=int, default=16)
    s.add_argument('--offline', action='store_true', help='use cached service responses only')
    s.add_argument('--out', required=True)
    s.set_defaults(func=cmd_retrieve)

    s = sub.add_parser('evaluate', help='Reader + LLM judge over a retrieval directory')
    s.add_argument('--retrieval', required=True)
    s.add_argument('--questions', required=True, help='with gold and category')
    s.add_argument('--conv', action='append')
    s.add_argument('--limit', type=int)
    s.add_argument('--judge-seed', type=lambda value: None if value == 'none' else int(value),
                   default=42, help='Judge seed (default 42); use none to omit the seed')
    s.add_argument('--no-judge', action='store_true', help='answers + F1/BLEU-1 only')
    s.add_argument('--workers', type=int, default=16)
    s.add_argument('--out', required=True)
    s.set_defaults(func=cmd_evaluate)

    a = p.parse_args(argv)
    if getattr(a, 'workers', 1) < 1:
        p.error('--workers must be positive')
    return a.func(a) or 0


if __name__ == '__main__':
    sys.exit(main())
