"""Chat-completion client with a response cache."""
import json
from pathlib import Path
import time
import urllib.request

from .config import chat_endpoint
from .io import digest, read, save


class IncompleteOutput(ValueError):
    """The model stopped before finishing."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        """Do not follow redirects."""
        return None


def send_json(url, data, headers, timeout):
    """POST JSON and return the JSON response."""
    request = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=timeout) as response:
        return json.load(response)


def post(url, body, key=None, attempts=5, timeout=1200):
    """POST with retries."""
    headers = {'Content-Type': 'application/json'}
    if key:
        headers['Authorization'] = 'Bearer ' + key
    data = json.dumps(body).encode()
    for attempt in range(attempts):
        try:
            return send_json(url, data, headers, timeout)
        except (OSError, ValueError) as exc:
            status = getattr(exc, 'code', None)
            if attempt + 1 == attempts or (status and status < 500 and status != 429):
                raise
            time.sleep(min(2 ** attempt, 16))


def parse_json(content):
    """Parse a model reply as JSON."""
    text = content.strip()
    if text.startswith('```'):
        text = text.split('\n', 1)[1].rsplit('```', 1)[0].strip()
    return json.loads(text)


class Chat:
    def __init__(self, cache, role='LLM'):
        """Client for the LLM, READER or JUDGE endpoint."""
        self.endpoint = chat_endpoint(role)
        self.model = self.endpoint.model
        self.cache = Path(cache)

    def body(self, prompt, max_tokens, *, seed=42, **extra):
        """Build a request body."""
        body = dict(model=self.model, messages=[dict(role='user', content=prompt)],
                    temperature=0, max_tokens=max_tokens, **extra)
        if seed is not None:
            body['seed'] = seed
        if self.endpoint.disable_thinking:
            body['chat_template_kwargs'] = {'enable_thinking': False}
        return body

    def complete(self, body, *, index=0, attempt=0):
        """Return the response, using the cache."""
        target = self.cache / f'{digest(body)}_{attempt}.json'
        if target.exists():
            return read(target)['response']
        response = post(self.endpoint.url(index + attempt) + '/chat/completions', body, self.endpoint.key)
        save(target, dict(response=response))
        return response

    def json(self, body, *, index=0, attempt=0):
        """Return the response parsed as JSON."""
        choice = self.complete(body, index=index, attempt=attempt)['choices'][0]
        if choice['finish_reason'] != 'stop':
            raise IncompleteOutput('Incomplete model output: ' + str(choice['finish_reason']))
        return parse_json(choice['message']['content'])


def usage(cache):
    """Sum token usage over cached responses."""
    totals = dict(calls=0, prompt_tokens=0, completion_tokens=0)
    for p in Path(cache).glob('*.json'):
        u = read(p)['response'].get('usage') or {}
        totals['calls'] += 1
        totals['prompt_tokens'] += u.get('prompt_tokens', 0) or 0
        totals['completion_tokens'] += u.get('completion_tokens', 0) or 0
    return totals
