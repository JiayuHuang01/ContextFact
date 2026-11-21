"""ContextFact: context-preserving conversational memory."""
from pathlib import Path

__version__ = '0.1.0'
PROMPTS = Path(__file__).resolve().parent / 'prompts'


def prompt(name):
    """Read a prompt template."""
    return (PROMPTS / f'{name}.md').read_text()
