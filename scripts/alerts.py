"""Push the result of every weekly run to Pushover, success and failure alike.

Ported from hn-radio's alerts.py, Pushover only. The first character of the title and of the
message is the verdict, so a lock-screen glance is enough:

  ✅  ok      every episode was published (or there was nothing to make), on any attempt
  🔁  retry   an attempt failed and weekly_run.py is about to try again
  ❌  fail    every attempt failed

Final failures go out at Pushover priority 1, which sounds even during quiet hours. Everything
else is priority 0.

Needs CHANGELOG_PUSHOVER_TOKEN (the application token) and CHANGELOG_PUSHOVER_USER (the user or
group key), set as Fly secrets on the box, or in .env locally. With neither set every call is a
logged no-op; with one set and not the other, the missing half is named in the log.

Usage, to check the keys from the box:
  python scripts/alerts.py --test
"""

from __future__ import annotations

import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

TIMEOUT_SECONDS = 10
PUSHOVER_URL = 'https://api.pushover.net/1/messages.json'
SHOW = 'Deepgram Changelog'
MARKS = {'ok': '✅', 'retry': '🔁', 'fail': '❌'}


def env(name: str) -> str:
    # The environment wins; .env is the local fallback, read the same way render_episode.py does.
    value = os.environ.get(name)
    if value:
        return value.strip()
    try:
        for line in (ROOT / '.env').read_text().splitlines():
            if line.startswith(f'{name}='):
                return line.split('=', 1)[1].strip().strip('"\'')
    except OSError:
        pass
    return ''


def pushover_keys() -> tuple[str, str]:
    return env('CHANGELOG_PUSHOVER_TOKEN'), env('CHANGELOG_PUSHOVER_USER')


def notify(status: str, message: str, *, url: str = '', log=print) -> bool:
    """Best-effort push; status is 'ok', 'retry', or 'fail'. True if Pushover accepted it. Never
    raises: the caller may already be on a failure path, and an exception here would bury the
    failure it was trying to report."""
    mark = MARKS.get(status, MARKS['fail'])
    title = f'{mark} {SHOW}'
    text = f'{mark} {message}'
    log(f'[alert] {text}')
    token, user = pushover_keys()
    if not (token and user):
        if token or user:
            missing = 'CHANGELOG_PUSHOVER_USER' if token else 'CHANGELOG_PUSHOVER_TOKEN'
            log(f'[alert] pushover: {missing} is not set, so nothing was sent')
        else:
            log('[alert] CHANGELOG_PUSHOVER_TOKEN/USER are not set, so nothing was sent')
        return False
    fields = {'token': token, 'user': user, 'title': title, 'message': text,
              'priority': '1' if status == 'fail' else '0'}
    if url:
        fields['url'] = url
        fields['url_title'] = 'Open episode' if status == 'ok' else 'Open site'
    try:
        req = urllib.request.Request(PUSHOVER_URL, data=urllib.parse.urlencode(fields).encode(),
                                     method='POST',
                                     headers={'Content-Type': 'application/x-www-form-urlencoded'})
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            delivered = 200 <= resp.status < 300
        log(f"[alert] pushover: {'delivered' if delivered else 'refused it'}")
        return delivered
    except (urllib.error.URLError, OSError, ValueError) as e:
        log(f'[alert] pushover: could not deliver: {e}')
        return False


if __name__ == '__main__':
    if '--test' not in sys.argv:
        sys.exit('usage: python scripts/alerts.py --test')
    sent = [notify('ok', 'Test: this is what a published episode looks like'),
            notify('retry', 'Test: this is what a retry looks like'),
            notify('fail', 'Test: this is what a run that failed every attempt looks like')]
    sys.exit(0 if all(sent) else 1)
