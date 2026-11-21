"""Evaluation metrics: J, F1, BLEU-1."""
import nltk
from nltk.translate.bleu_score import sentence_bleu, SmoothingFunction


def _ensure_punkt():
    """Download NLTK punkt data if missing."""
    try:
        nltk.data.find("tokenizers/punkt_tab")
    except LookupError:
        nltk.download("punkt_tab", quiet=True)


CATS = [(4, "Single"), (1, "Multi"), (2, "Temporal"), (3, "Open"), (None, "Overall")]


def simple_tokenize(text):
    """Tokenize for F1."""
    return (text or "").lower().replace(".", " ").replace(",", " ") \
        .replace("!", " ").replace("?", " ").split()


def token_f1(pred, ref):
    """Token F1."""
    p, r = set(simple_tokenize(pred)), set(simple_tokenize(ref))
    if not p or not r:
        return 0.0
    c = len(p & r)
    if c == 0:
        return 0.0
    prec, rec = c / len(p), c / len(r)
    return 2 * prec * rec / (prec + rec)


def bleu1(pred, ref):
    """BLEU-1."""
    _ensure_punkt()
    return sentence_bleu([nltk.word_tokenize((ref or "").lower())],
                         nltk.word_tokenize((pred or "").lower()),
                         weights=(1, 0, 0, 0),
                         smoothing_function=SmoothingFunction().method1)


def aggregate(rows, token_key="mem_tok", units_key="n_units"):
    """Per-category scores."""
    import statistics as st
    def sel(c):
        """Rows of one category."""
        return rows if c is None else [x for x in rows if x["category"] == c]
    rep = {"n": len(rows),
           "token": round(st.mean([r[token_key] for r in rows])),
           "units": round(st.mean([r[units_key] for r in rows]), 1)}
    for c, nm in CATS:
        s = sel(c)
        rep[nm] = {"J": round(100 * sum(x["correct"] for x in s) / len(s), 2),
                   "B1": round(100 * st.mean([x["b1"] for x in s]), 2),
                   "F1": round(100 * st.mean([x["f1"] for x in s]), 2)} if s else None
    return rep


def print_report(rep, title=""):
    """Print the report."""
    print("\n=== %s ===  token=%s units=%s n=%s" % (title, rep["token"], rep["units"], rep["n"]))
    print("%-10s %8s %7s %7s" % ("Category", "LLM-J", "B1", "F1"))
    for _, nm in CATS:
        c = rep.get(nm)
        if c:
            print("%-10s %8.2f %7.2f %7.2f" % (nm, c["J"], c["B1"], c["F1"]))
