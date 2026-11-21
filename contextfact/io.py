"""File helpers."""
import hashlib
import gzip
import json
from pathlib import Path
import uuid


def read(path):
    """Load a JSON or JSON.gz file."""
    path = Path(path)
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == ".gz" else raw)


def digest(value):
    """SHA-256 of a value."""
    if not isinstance(value, (str, bytes)):
        value = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def write_text(path, text):
    """Write text atomically."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def save(path, value):
    """Write JSON."""
    write_text(path, json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def frozen(path, value):
    """Save a run config, or check it matches the saved one."""
    if Path(path).exists():
        if read(path) != value:
            raise ValueError(f"Existing run configuration differs: {path}. Use a new output directory.")
    else:
        save(path, value)


def unique(values):
    """Deduplicate, keeping order."""
    return list(dict.fromkeys(values))


def tokens(text):
    """Count o200k_base tokens."""
    import tiktoken
    return len(tiktoken.get_encoding("o200k_base").encode(text, disallowed_special=()))
