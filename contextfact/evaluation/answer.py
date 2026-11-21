"""Reader answers and Judge scoring."""
from concurrent.futures import ThreadPoolExecutor, as_completed

from .. import prompt
from ..io import read, save, tokens
from ..llm import Chat
from . import metrics

READER_MAX_TOKENS = 1024
JUDGE_MAX_TOKENS = 256


def evaluate(retrieval_dir, questions, out, *, judge=True, judge_seed=42, workers=16):
    """Answer, judge and score all questions."""
    reader = Chat(out / 'llm_cache' / 'reader', role='READER')
    grader = Chat(out / 'llm_cache' / 'judge', role='JUDGE') if judge else None
    reader_template, judge_template = prompt('reader'), prompt('judge')

    def work(i, row):
        """Answer and score one question."""
        qid = row['qid']
        context = (retrieval_dir / 'contexts' / f'{qid}.txt').read_text()
        selection = read(retrieval_dir / 'selections' / f'{qid}.json')
        if any(selection.get(key) != row[key] for key in ('qid', 'conv', 'question')):
            raise ValueError('Retrieval selection does not match the evaluation question')
        body = reader.body(reader_template.format(memories=context, question=row['question']),
                           READER_MAX_TOKENS)
        choice = reader.complete(body, index=i)['choices'][0]
        if choice['finish_reason'] not in ('stop', 'length'):
            raise ValueError('Unexpected Reader finish reason: ' + str(choice['finish_reason']))
        answer = choice['message']['content'].strip()
        record = dict(row, pred=answer, f1=metrics.token_f1(answer, row['gold']),
                      b1=metrics.bleu1(answer, row['gold']), mem_tok=tokens(context),
                      n_units=len(selection['fact_ids']) + len(selection['entity_ids']),
                      finish_reason=choice['finish_reason'])
        if grader:
            body = grader.body(judge_template.format(question=row['question'], gold_answer=row['gold'],
                                                     generated_answer=answer),
                               JUDGE_MAX_TOKENS, seed=judge_seed, response_format={'type': 'json_object'})
            label = grader.json(body, index=i)['label'].upper()
            if label not in ('CORRECT', 'WRONG'):
                raise ValueError('Unexpected Judge label: ' + label)
            record['correct'] = int(label == 'CORRECT')
        save(out / 'answers' / f'{qid}.json', record)
        return record

    done, errors = {}, []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(work, i, r): r['qid'] for i, r in enumerate(questions)}
        for future in as_completed(futures):
            try:
                done[futures[future]] = future.result()
            except Exception as exc:
                errors.append(dict(qid=futures[future], error=f'{type(exc).__name__}: {exc}'))
            print(f'Evaluation: {len(done)}/{len(questions)} done, {len(errors)} failed', flush=True)
    save(out / 'errors.json', errors)
    if errors:
        raise RuntimeError(f'{len(errors)} questions failed; see {out / "errors.json"} and rerun to resume')
    rows = [done[r['qid']] for r in questions]
    save(out / 'predictions.json', rows)
    if not judge:
        return None
    report = metrics.aggregate(rows)
    save(out / 'report.json', report)
    return report
