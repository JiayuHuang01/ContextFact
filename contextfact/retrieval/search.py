"""Hybrid search: dense + BM25 with reciprocal-rank fusion."""
from concurrent.futures import ThreadPoolExecutor
import re
import threading

import numpy as np
from rank_bm25 import BM25Okapi

from ..io import digest, read, save


def lexical(text):
    """Tokenize for BM25."""
    return re.sub(r"[^a-z0-9 ]", " ", text.lower()).split()


def validate_vectors(vectors, rows, dimension=None):
    """Check embeddings and return them as float32."""
    vectors = np.asarray(vectors, dtype=np.float32)
    if (vectors.ndim != 2 or vectors.shape[0] != rows or not np.isfinite(vectors).all()
            or (dimension is not None and vectors.shape[1] != dimension)
            or (rows and (np.linalg.norm(vectors, axis=1) == 0).any())):
        raise ValueError("Invalid embedding dimensions or non-finite/zero vector")
    return vectors


class Search:
    def __init__(self, bank, services=None, cache=None, *, rrf_k=60):
        """Create an empty index."""
        if rrf_k <= 0:
            raise ValueError("rrf_k must be positive")
        self.bank, self.services, self.cache, self.rrf_k = bank, services, cache, rrf_k
        self.ids, self.vec, self.bm, self.qv = {}, {}, {}, {}
        self.lock = threading.Lock()
        self.query_locks = {}

    def add(self, conv, kind, ids, vectors, texts):
        """Add one index."""
        if len(ids) != len(set(ids)) or len(ids) != len(texts):
            raise ValueError("Corpus IDs must be unique and align with text")
        key = (conv, kind)
        self.ids[key] = list(ids)
        if not ids:
            self.vec[key], self.bm[key] = None, None
            return
        self.vec[key] = validate_vectors(vectors, len(ids))
        terms = [lexical(text) for text in texts]
        self.bm[key] = BM25Okapi(terms) if any(terms) else None

    def build(self, conversations=None, *, batch_size=16, workers=4, kinds=("cf", "entity", "memory")):
        """Build indexes for the given conversations."""
        if self.services is None:
            raise ValueError("Services are required to build missing indexes")
        if batch_size < 1 or workers < 1:
            raise ValueError("batch_size and workers must be positive")
        if not kinds or any(k not in ("cf", "entity", "memory") for k in kinds) or len(set(kinds)) != len(kinds):
            raise ValueError("Invalid index kinds")
        for conv in conversations or self.bank.cf_by_conv:
            for kind in kinds:
                ids, texts = self.bank.corpus(conv, kind)
                if not ids:
                    self.add(conv, kind, [], [], [])
                    continue
                identity = dict(ids=ids, text_sha256=digest(texts),
                                embedding=self.services.embedding_identity)
                path = self.cache / "indexes" / (digest(identity) + ".json") if self.cache else None
                if path and path.exists():
                    cached = read(path)
                    if cached["identity"] != identity:
                        raise ValueError("Cached index identity differs")
                    vectors = validate_vectors(cached["vectors"], len(ids))
                else:
                    chunks = [texts[i:i + batch_size] for i in range(0, len(texts), batch_size)]
                    with ThreadPoolExecutor(max_workers=workers) as pool:
                        vectors = np.concatenate(list(pool.map(self.services.embed, chunks)))
                    vectors = validate_vectors(vectors, len(ids))
                    if path:
                        save(path, dict(identity=identity, vectors=vectors.tolist()))
                self.add(conv, kind, ids, vectors, texts)

    def query_vector(self, query):
        """Embed a query once."""
        with self.lock:
            query_lock = self.query_locks.setdefault(query, threading.Lock())
        with query_lock:
            if query not in self.qv:
                if self.services is None:
                    raise ValueError("No cached query vector and no embedding service")
                self.qv[query] = self.services.embed([query])[0]
            return self.qv[query]

    def search(self, conv, query, kind, k=20):
        """Top-k IDs for a query."""
        if k < 1:
            raise ValueError("k must be positive")
        key = (conv, kind)
        if key not in self.ids:
            raise ValueError(f"Index not built: {key}")
        ids = self.ids[key]
        if not ids:
            return []
        vector = np.asarray(self.query_vector(query), dtype=np.float32)
        if vector.shape != (self.vec[key].shape[1],) or not np.isfinite(vector).all():
            raise ValueError("Query and document embedding dimensions differ")
        dense = np.argsort(-(self.vec[key] @ vector))
        scores = self.bm[key].get_scores(lexical(query)) if self.bm[key] else np.zeros(len(ids))
        sparse = np.argsort(-scores)
        reciprocal = 1.0 / (self.rrf_k + np.arange(len(ids)))
        fused = np.empty(len(ids), dtype=np.float64)
        fused[dense] = reciprocal
        fused[sparse] += reciprocal
        order = np.argsort(-fused, kind="stable")
        return [ids[i] for i in order[:k]]
