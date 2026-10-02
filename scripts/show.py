"""The show's identity, read from show.json at the repo root.

Usage: from show import SHOW; SHOW['name']

One place for the name, links, and art text, so a fork changes show.json instead of strings in
ten files. Environment variables still win where they already existed (SITE_URL,
CHANGELOG_FEED_URL), so the Fly box and one-off runs keep working unchanged.
"""

from __future__ import annotations

import json
import os
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTS = {
    'name': 'The Deepgram Changelog',
    'wordmark': ['The Deepgram', 'Changelog'],
    'description': '',
    'author': '',
    'owner_email': '',
    'site_url': 'http://localhost:8010',
    'changelog_url': '',
    'feed_url': 'https://developers.deepgram.com/changelog.rss',
    'attribution': True,
}
ATTRIBUTION_TEXT = 'Voiced with Deepgram Flux TTS'
ATTRIBUTION_URL = 'https://deepgram.com/product/text-to-speech'


def load_env(path: Path = ROOT / '.env') -> None:
    """Read .env into the environment without overriding anything already set. Every script imports
    this module, so each one finds the keys on its own, with no `set -a` step and no wrapper."""
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def write_atomic(path: Path, text: str) -> None:
    """Write a file other processes may be reading, or writing too: renders that run side by side
    all rebuild the same catalog, feed, and index. Each writer gets its own temp file and swaps it
    in whole, so nobody reads half a file and two writers never share a temp."""
    tmp = path.with_name(f'.{path.name}.{os.getpid()}.tmp')
    tmp.write_text(text)
    tmp.replace(path)


def load(path: Path = ROOT / 'show.json') -> dict:
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        data = {}
    except ValueError as e:
        raise SystemExit(f'{path} is not valid JSON: {e}')
    show = {**DEFAULTS, **{k: v for k, v in data.items() if not k.startswith('_')}}
    if os.environ.get('SITE_URL'):
        show['site_url'] = os.environ['SITE_URL']
    show['site_url'] = show['site_url'].rstrip('/')
    words = show['wordmark']
    if not (isinstance(words, list) and len(words) == 2 and all(isinstance(w, str) for w in words)):
        raise SystemExit(f'{path}: "wordmark" must be two strings, a small line and a big line')
    return show


def attribution_url(site_url: str, placement: str = 'footer') -> str:
    """The credit link, tagged with the site it came from (and where on the page it sits) so
    Deepgram can see which shows exist and which link people click."""
    host = urllib.parse.urlparse(site_url).netloc or 'unknown'
    query = urllib.parse.urlencode({'utm_source': host, 'utm_medium': 'podcast-template',
                                    'utm_campaign': 'changelog-podcast', 'utm_content': placement})
    return f'{ATTRIBUTION_URL}?{query}'


load_env()
SHOW = load()
