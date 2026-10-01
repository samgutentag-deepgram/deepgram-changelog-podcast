"""Serve the site: web/ at /, episodes/ at /episodes/, and /e/<id> as the short episode URL.

Usage: python3 scripts/serve.py [--port 8010]

Stdlib only. Supports HTTP Range requests, which the audio element needs to seek; the plain
http.server module does not, and without it a click on the scrub bar restarts the episode.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from show import ATTRIBUTION_TEXT, SHOW, attribution_url

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / 'web'
# On Fly the episodes live on a volume (EPISODES_DIR=/data/episodes) so the weekly run can add to
# them without a redeploy. Locally they are the repo's episodes/ directory.
EPISODES = Path(os.environ.get('EPISODES_DIR', ROOT / 'episodes'))
# The episode directory also holds internal files (script.md with writer's notes, render and
# readback reports). Only these names are ever served from it.
SERVED = re.compile(r'^(?:feed\.xml|index\.json|catalog\.json|cover\.(?:png|jpg)|'
                    r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}/(?:episode\.(?:mp3|json)|chapters\.json|script\.json|'
                    r'transcript\.vtt|art\.(?:png|jpg)))$')
PAGES = {'/back-catalog': 'back-catalog.html'}
SITE_URL = os.environ.get('SITE_URL', '').rstrip('/')
SITE_TITLE = SHOW['name']
# The pages are written with the Deepgram show's name in them, so they read as finished HTML in
# the repo. Serving swaps in show.json's name, and adds the credit line when attribution is on.
PAGE_NAME = 'The Deepgram Changelog'
# Checked before the id touches a path, so a separator can never sneak in.
ID_OK = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')
LEDE = re.compile(r'(<p class="lede" id="show-lede">).*?</p>', re.S)
SHORT = re.compile(r'^/e/([^/?#]+)/?(?:[?#].*)?$')


def meta(attr: str, key: str, value: str) -> str:
    return f'<meta {attr}="{key}" content="{html.escape(value, quote=True)}">'


class Handler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map,
                      '.js': 'text/javascript', '.mp3': 'audio/mpeg', '.json': 'application/json'}

    def translate_path(self, path: str) -> str:
        clean = path.split('?', 1)[0].split('#', 1)[0]
        if clean.rstrip('/') in PAGES:
            return str(WEB / PAGES[clean.rstrip('/')])
        if clean.startswith('/episodes/'):
            base, rest = EPISODES, clean[len('/episodes/'):]
            if not SERVED.match(rest):
                return str(base / '__forbidden__')
        else:
            base, rest = WEB, clean.lstrip('/')
        target = (base / rest).resolve()
        if base.resolve() not in target.parents and target != base.resolve():
            return str(base / '__forbidden__')
        return str(target)

    def end_headers(self) -> None:
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Accept-Ranges', 'bytes')
        super().end_headers()

    def do_GET(self) -> None:
        if self.short_page() or self.html_page():
            return
        super().do_GET()

    def do_HEAD(self) -> None:
        if self.short_page(head_only=True) or self.html_page(head_only=True):
            return
        super().do_HEAD()

    def html_page(self, head_only: bool = False) -> bool:
        path = Path(self.translate_path(self.path))
        if path.is_dir():
            path = path / 'index.html'
        if path.suffix != '.html' or not path.is_file() or WEB.resolve() not in path.resolve().parents:
            return False
        self.send_page(path.read_text(), head_only)
        return True

    def send_page(self, page: str, head_only: bool) -> None:
        page = page.replace(PAGE_NAME, html.escape(SITE_TITLE))
        if SITE_TITLE != PAGE_NAME and SHOW['description']:
            # A renamed show gets its own description in place of the Deepgram show's lede.
            page = LEDE.sub(lambda m: m.group(1) + html.escape(SHOW['description']) + '</p>', page, count=1)
        if SHOW['attribution']:
            base = SITE_URL or f'http://{self.headers.get("Host", "localhost")}'
            credit = (f'\n  &middot; <a class="credit" href="{html.escape(attribution_url(base), quote=True)}" '
                      f'target="_blank" rel="noopener">{ATTRIBUTION_TEXT}</a>\n</footer>')
            page = page.replace('\n</footer>', credit, 1)
        body = page.encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        if not head_only:
            self.wfile.write(body)

    def short_page(self, head_only: bool = False) -> bool:
        """Serve episode.html for /e/<id> with that episode's title and unfurl tags in the head.
        Mirrors HN Radio's /e/ route, so a pasted link previews in Slack."""
        m = SHORT.match(self.path)
        if not m:
            return False
        ep_id = m.group(1)
        f = EPISODES / ep_id / 'episode.json'
        if not ID_OK.match(ep_id) or not f.is_file():
            self.send_error(404, 'no such episode')
            return True
        try:
            ep = json.loads(f.read_text())
        except (OSError, ValueError):
            self.send_error(404, 'no such episode')
            return True
        base = SITE_URL or f'http://{self.headers.get("Host", "localhost")}'
        title = ep.get('title') or SITE_TITLE
        summary = (ep.get('summary') or '').strip()
        head = '\n'.join([
            # Assets in episode.html are relative and this page is one segment deep.
            '<base href="/">',
            meta('name', 'description', summary),
            meta('property', 'og:type', 'article'),
            meta('property', 'og:site_name', SITE_TITLE),
            meta('property', 'og:title', f'{SITE_TITLE}: {title}'),
            meta('property', 'og:description', summary),
            meta('property', 'og:url', f'{base}/e/{ep_id}'),
            meta('property', 'og:image', f'{base}/episodes/{ep_id}/art.jpg' if (EPISODES / ep_id / 'art.jpg').exists()
                 else f'{base}/episodes/cover.png'),
            meta('name', 'twitter:card', 'summary'),
        ])
        page = (WEB / 'episode.html').read_text().replace(
            f'<title>{PAGE_NAME}: Episode</title>',
            f'<title>{PAGE_NAME}: {html.escape(title)}</title>\n{head}', 1)
        self.send_page(page, head_only)
        return True

    def send_head(self):
        rng = self.headers.get('Range')
        path = self.translate_path(self.path)
        if not rng or not os.path.isfile(path):
            return super().send_head()
        m = re.match(r'bytes=(\d*)-(\d*)$', rng.strip())
        size = os.path.getsize(path)
        if not m or (not m.group(1) and not m.group(2)):
            self.send_error(416)
            return None
        if m.group(1):
            start = int(m.group(1))
            end = int(m.group(2)) if m.group(2) else size - 1
        else:
            start, end = max(0, size - int(m.group(2))), size - 1
        if start >= size or start > end:
            self.send_response(416)
            self.send_header('Content-Range', f'bytes */{size}')
            self.end_headers()
            return None
        end = min(end, size - 1)
        f = open(path, 'rb')
        f.seek(start)
        self.send_response(206)
        self.send_header('Content-Type', self.guess_type(path))
        self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        self.send_header('Content-Length', str(end - start + 1))
        self.end_headers()
        self._remaining = end - start + 1
        return f

    def copyfile(self, source, outputfile) -> None:
        remaining = getattr(self, '_remaining', None)
        if remaining is None:
            return super().copyfile(source, outputfile)
        while remaining > 0:
            chunk = source.read(min(64 * 1024, remaining))
            if not chunk:
                break
            outputfile.write(chunk)
            remaining -= len(chunk)
        self._remaining = None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=int(os.environ.get('PORT', 8010)))
    ap.add_argument('--host', default=os.environ.get('HOST', '127.0.0.1'))
    args = ap.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), partial(Handler, directory=str(WEB)))
    print(f'serving http://{args.host}:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
