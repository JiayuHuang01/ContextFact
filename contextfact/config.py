"""Model endpoint settings from environment variables or .env."""
from dataclasses import dataclass
import os
from pathlib import Path
from urllib.parse import urlsplit


def load_dotenv(path='.env'):
    """Load .env without overriding existing variables."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _get(role, name, default=None, fallback=None):
    """Read a role's environment variable, with fallback."""
    value = os.getenv(f'{role}_{name}') or None
    if value is None and fallback:
        value = os.getenv(f'{fallback}_{name}') or None
    return default if value is None else value


def _urls(value):
    """Parse a comma-separated list of base URLs."""
    urls = [u.strip().rstrip('/') for u in (value or '').split(',') if u.strip()]
    for url in urls:
        parsed = urlsplit(url)
        if (parsed.scheme not in ('http', 'https') or not parsed.hostname
                or parsed.username is not None or parsed.query or parsed.fragment):
            raise ValueError('Base URLs must be HTTP(S) URLs without credentials, queries or fragments')
    return urls


def _flag(value):
    """Parse a boolean environment value."""
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')


@dataclass
class Endpoint:
    urls: list
    model: str
    key: str | None
    disable_thinking: bool

    def url(self, index=0):
        """Base URL for a request, round-robin over replicas."""
        return self.urls[index % len(self.urls)]


def chat_endpoint(role='LLM'):
    """Chat endpoint for LLM, READER or JUDGE."""
    load_dotenv()
    fallback = 'LLM' if role == 'READER' else None
    if role == 'JUDGE':
        urls = _urls(_get('JUDGE', 'BASE_URL'))
        model = _get('JUDGE', 'MODEL', 'gpt-4o-mini')
        key = _get('JUDGE', 'API_KEY')
        if not key and urls == ['https://api.openai.com/v1']:
            key = os.getenv('OPENAI_API_KEY') or None
    else:
        urls = _urls(_get(role, 'BASE_URL', fallback=fallback))
        model = _get(role, 'MODEL', fallback=fallback)
        key = _get(role, 'API_KEY')
        if not key and fallback and urls == _urls(_get(fallback, 'BASE_URL')):
            key = _get(fallback, 'API_KEY')
    if role == 'JUDGE' and not urls:
        raise RuntimeError('Set JUDGE_BASE_URL to enable judging or pass --no-judge')
    if not urls or not model:
        raise RuntimeError(f'Set {role}_BASE_URL and {role}_MODEL (see .env.example)')
    thinking = _get(role, 'DISABLE_THINKING', fallback=fallback)
    disable = _flag(thinking) if thinking is not None else 'qwen3' in model.lower()
    return Endpoint(urls, model, key, disable)


def service(kind):
    """Endpoint for EMBEDDING or RERANK."""
    load_dotenv()
    urls = _urls(os.getenv(f'{kind}_BASE_URL'))
    default = {'EMBEDDING': 'Qwen/Qwen3-Embedding-8B', 'RERANK': 'IAAR-Shanghai/MemReranker-4B'}[kind]
    return urls, os.getenv(f'{kind}_MODEL') or default, os.getenv(f'{kind}_API_KEY') or None
