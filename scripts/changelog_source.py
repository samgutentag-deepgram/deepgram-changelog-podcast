"""Load a changelog as dated markdown entries, from an RSS or Atom feed or from an llms.txt index.

The rest of the pipeline only needs a list of (date, markdown body, public URL) per changelog
day, where each "## " heading in the body is one item. Two kinds of source produce that:

1. An RSS 2.0 or Atom feed (CHANGELOG_FEED_URL), which is what almost every changelog publishes
   and what the show reads by default. Each item needs a date and its full content
   (content:encoded, Atom content, or a description that holds the whole entry, not a teaser).
   The HTML is converted to plain markdown: headings, paragraphs, lists, links, and code survive;
   styling does not. Items on the same day merge into one body. If an item's content has no "## "
   heading of its own, the item title becomes one, unless the title is only a date (Deepgram's
   feed titles every item with its day).

2. An llms.txt-style index (CHANGELOG_INDEX_URL), an optional alternative: a markdown list of
   links, one per changelog day, each pointing at a clean markdown page. It skips the HTML
   conversion and adds no entries, so check it against the feed before switching: Deepgram's
   per-day pages carry only the first entry on a day with two. The day comes from the link's URL
   path (/2026/9/24.md) or, failing that, from its link text ("September 24, 2026").

Set one of the two environment variables to point the show at another changelog, not both. With
neither set, it reads Deepgram's RSS feed. Everything fetched is cached under .cache/changelog.
"""

from __future__ import annotations

import os
import re
import urllib.request
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / '.cache' / 'changelog'
DEFAULT_FEED_URL = 'https://developers.deepgram.com/changelog.rss'
INDEX_URL = os.environ.get('CHANGELOG_INDEX_URL')
FEED_URL = os.environ.get('CHANGELOG_FEED_URL') or (None if INDEX_URL else DEFAULT_FEED_URL)

Entry = tuple[date, str, str]  # (day, markdown body, public URL for that day)


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={'User-Agent': 'changelog-podcast/1.0'})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode()


def load_entries(refresh: bool = False) -> list[Entry]:
    if os.environ.get('CHANGELOG_INDEX_URL') and os.environ.get('CHANGELOG_FEED_URL'):
        raise SystemExit('set CHANGELOG_INDEX_URL or CHANGELOG_FEED_URL, not both')
    CACHE.mkdir(parents=True, exist_ok=True)
    return from_feed(FEED_URL, refresh) if FEED_URL else from_index(INDEX_URL, refresh)


# ---- llms.txt index ----------------------------------------------------------------------------

LINK = re.compile(r'\[([^\]]+)\]\((\S+?\.md)\)')
PATH_DATE = re.compile(r'/(\d{4})/(\d{1,2})/(\d{1,2})\.md$')


def link_date(text: str, url: str) -> date | None:
    m = PATH_DATE.search(url)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    for fmt in ('%B %d, %Y', '%b %d, %Y', '%Y-%m-%d'):
        try:
            return datetime.strptime(text.strip(), fmt).date()
        except ValueError:
            continue
    return None


def from_index(index_url: str, refresh: bool) -> list[Entry]:
    index = CACHE / 'llms.txt'
    if refresh or not index.exists():
        index.write_text(fetch(index_url))
    out = []
    for text, url in LINK.findall(index.read_text()):
        day = link_date(text, url)
        if not day:
            continue  # the index may also link non-entry pages; only dated ones are changelog days
        f = CACHE / f'{day.isoformat()}.md'
        if refresh or not f.exists():
            f.write_text(fetch(url))
        # llms.txt pages often open with ">" notes about the page itself; they are not content.
        body = '\n'.join(l for l in f.read_text().splitlines() if not l.startswith('>'))
        out.append((day, body, url[:-3]))
    return out


# ---- RSS / Atom feed ---------------------------------------------------------------------------

NS = {'content': 'http://purl.org/rss/1.0/modules/content/', 'atom': 'http://www.w3.org/2005/Atom'}


class _Markdown(HTMLParser):
    """Just enough HTML to markdown for a changelog entry. Unknown tags keep their text."""

    BLOCK = {'p', 'div', 'section', 'article', 'br', 'tr', 'table', 'blockquote'}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.href: list[str | None] = []
        self.pre = False

    def handle_starttag(self, tag: str, attrs) -> None:
        a = dict(attrs)
        if re.fullmatch(r'h[1-6]', tag):
            # Entry sections are H2 in the pipeline, whatever level the feed used for them.
            self.out.append('\n\n' + '#' * max(2, int(tag[1])) + ' ')
        elif tag in self.BLOCK:
            self.out.append('\n\n')
        elif tag == 'li':
            self.out.append('\n- ')
        elif tag == 'pre':
            self.pre = True
            self.out.append('\n\n```\n')
        elif tag == 'code' and not self.pre:
            self.out.append('`')
        elif tag == 'a':
            self.href.append(a.get('href'))
            self.out.append('[')

    def handle_endtag(self, tag: str) -> None:
        if re.fullmatch(r'h[1-6]', tag):
            self.out.append('\n\n')
        elif tag == 'pre':
            self.pre = False
            self.out.append('\n```\n\n')
        elif tag == 'code' and not self.pre:
            self.out.append('`')
        elif tag == 'a':
            href = self.href.pop() if self.href else None
            self.out.append(f']({href})' if href else ']')

    def handle_data(self, data: str) -> None:
        self.out.append(data if self.pre else re.sub(r'\s+', ' ', data))

    def text(self) -> str:
        md = ''.join(self.out)
        md = re.sub(r'[ \t]+\n', '\n', md)
        return re.sub(r'\n{3,}', '\n\n', md).strip()


def html_to_markdown(html: str) -> str:
    p = _Markdown()
    p.feed(html or '')
    return p.text()


def _day(value: str) -> date | None:
    value = (value or '').strip()
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).date()  # RSS pubDate
    except (TypeError, ValueError):
        pass
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).date()  # Atom updated
    except ValueError:
        return None


def from_feed(feed_url: str, refresh: bool) -> list[Entry]:
    cached = CACHE / 'feed.xml'
    if refresh or not cached.exists():
        cached.write_text(fetch(feed_url))
    root = ET.fromstring(cached.read_text())
    raw = []
    for it in root.iter('item'):  # RSS 2.0
        html = (it.findtext('content:encoded', namespaces=NS) or it.findtext('description') or '')
        raw.append((_day(it.findtext('pubDate')), it.findtext('title') or '', html, it.findtext('link') or feed_url))
    for it in root.iter(f"{{{NS['atom']}}}entry"):  # Atom
        link = it.find('atom:link', NS)
        html = it.findtext('atom:content', namespaces=NS) or it.findtext('atom:summary', namespaces=NS) or ''
        when = it.findtext('atom:published', namespaces=NS) or it.findtext('atom:updated', namespaces=NS)
        raw.append((_day(when), it.findtext('atom:title', namespaces=NS) or '', html,
                    link.get('href') if link is not None else feed_url))
    days: dict[date, list[tuple[str, str]]] = {}
    for day, title, html, link in raw:
        if not day:
            continue
        md = html_to_markdown(html)
        if not re.search(r'^## ', md, re.M) and not link_date(title, ''):
            md = f'## {title.strip()}\n\n{md}'
        days.setdefault(day, []).append((md, link))
    return [(day, '\n\n'.join(md for md, _ in parts), parts[0][1]) for day, parts in sorted(days.items())]
