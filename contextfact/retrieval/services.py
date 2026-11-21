"""Embedding and reranker clients with a response cache."""
import json
import math
from pathlib import Path
import threading
import time

import numpy as np

from ..config import service
from ..io import digest, read, save
from ..llm import send_json
from .search import validate_vectors


def checked_scores(raw, size):
    """Scores from a rerank response."""
    if raw.get("truncated") or len(raw["results"]) != size:
        raise ValueError("Reranker truncated input or omitted candidate scores")
    scores = {int(row["index"]): float(row["relevance_score"]) for row in raw["results"]}
    if set(scores) != set(range(size)) or not all(math.isfinite(v) for v in scores.values()):
        raise ValueError("Reranker must return exactly one finite score per candidate")
    return [scores[i] for i in range(size)]


class Services:
    def __init__(self, cache, *, offline=False, timeout=480, attempts=6, concurrent_requests=8):
        """Set up embedding and reranker clients."""
        self.cache = Path(cache)
        self.offline, self.timeout, self.attempts = offline, timeout, attempts
        if timeout <= 0 or attempts < 1 or concurrent_requests < 1:
            raise ValueError("timeout, attempts, and concurrency must be positive")
        embedding, self.embedding_model, embedding_key = service("EMBEDDING")
        rerank, self.rerank_model, rerank_key = service("RERANK")
        self.embedding_dimensions = None
        self.endpoints = dict(embedding=[u + "/embeddings" for u in embedding],
                              rerank=[u + "/rerank" for u in rerank])
        self.keys = dict(embedding=embedding_key, rerank=rerank_key)
        self.guard, self.locks = threading.Lock(), {}
        self.semaphores = {stage: threading.BoundedSemaphore(concurrent_requests) for stage in self.endpoints}
        self.counters = {stage: 0 for stage in self.endpoints}

    @property
    def embedding_identity(self):
        """Cache key for embeddings."""
        return dict(model=self.embedding_model)

    def config(self):
        """Service settings for the run config."""
        return dict(endpoints=self.endpoints, embedding_model=self.embedding_model,
                    reranker_model=self.rerank_model, timeout_seconds=self.timeout,
                    transport_attempts=self.attempts)

    def request(self, stage, payload, check):
        """Send a cached request."""
        urls = self.endpoints[stage]
        if not urls:
            raise ValueError(f"Set {stage.upper()}_BASE_URL (see .env.example)")
        h = digest(payload)
        path = self.cache / "requests" / stage / (h + ".json")
        with self.guard:
            lock = self.locks.setdefault(h, threading.Lock())
            index = self.counters[stage]
            self.counters[stage] += 1
        with lock:
            if path.exists():
                record = read(path)
                if "request" in record and record["request"] != payload:
                    raise ValueError("Request cache identity mismatch")
                check(record["response"])
                return record["response"]
            if self.offline:
                raise RuntimeError(f"Offline cache miss: {stage}/{h}")
            headers = {"Content-Type": "application/json"}
            if self.keys[stage]:
                headers["Authorization"] = "Bearer " + self.keys[stage]
            data = json.dumps(payload).encode()
            for attempt in range(self.attempts):
                url = urls[(index + attempt) % len(urls)]
                try:
                    with self.semaphores[stage]:
                        raw = send_json(url, data, headers, self.timeout)
                except OSError as exc:
                    status = getattr(exc, 'code', None)
                    if attempt + 1 == self.attempts or (status and status < 500 and status != 429):
                        raise RuntimeError(f"{stage} transport failed (HTTP {status})" if status
                                           else f"{stage} transport failed") from exc
                    time.sleep(min(2 ** attempt, 10))
                    continue
                check(raw)
                save(path, dict(response=raw))
                return raw

    def embed(self, texts):
        """Embed texts."""
        def check(raw):
            """Validate an embedding response."""
            if raw.get("truncated") or sorted(r["index"] for r in raw["data"]) != list(range(len(texts))):
                raise ValueError("Embedding response missing/duplicating inputs or reporting truncation")
            validate_vectors([r["embedding"] for r in raw["data"]], len(texts), self.embedding_dimensions)
        payload = dict(model=self.embedding_model, input=list(texts))
        raw = self.request("embedding", payload, check)
        arr = np.asarray([r["embedding"] for r in sorted(raw["data"], key=lambda r: r["index"])], dtype=np.float32)
        if self.embedding_dimensions is None:
            self.embedding_dimensions = arr.shape[1]
        return arr / (np.linalg.norm(arr, axis=1, keepdims=True) + 1e-9)

    def rerank(self, query, ids, texts):
        """Order IDs by reranker score."""
        if len(ids) != len(set(ids)) or len(ids) != len(texts):
            raise ValueError("Reranker IDs/texts differ")
        if not ids:
            return []
        payload = dict(model=self.rerank_model, query=query, documents=list(texts), top_n=len(ids))
        raw = self.request("rerank", payload, lambda r: checked_scores(r, len(ids)))
        scores = checked_scores(raw, len(ids))
        return [ids[i] for i in sorted(range(len(ids)), key=lambda i: (-scores[i], i))]
