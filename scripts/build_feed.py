"""Write episodes/feed.xml, the podcast RSS feed, from every rendered episode.

Usage: python3 scripts/build_feed.py --base https://dg-devrel-deepgram-changelog.fly.dev

Every URL in the feed is absolute, so --base has to be the public origin the feed is served
from. The guid is the episode's directory URL and must never change once published, or every
subscriber's player sees a brand new episode.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EPISODES = Path(os.environ.get('EPISODES_DIR', ROOT / 'episodes'))
TITLE = 'The Deepgram Changelog'
DESCRIPTION = ('The Deepgram developer changelog, read back to you every Tuesday. Breaking changes '
               'first, then launches, then everything else that shipped the week before, with a '
               'link to the docs for every item. Voiced start to finish by Deepgram Flux TTS.')
AUTHOR = 'Deepgram DevRel'
OWNER_EMAIL = 'devrel@deepgram.com'
RELEASE_HOUR_UTC = 16  # Tuesday 9am Pacific


def item(base: str, ep: dict, ep_dir: Path) -> str:
    ep_url = f"{base}/episodes/{ep['id']}/"
    mp3 = ep_dir / 'episode.mp3'
    day = datetime.fromisoformat(ep['release_date']).replace(hour=RELEASE_HOUR_UTC, tzinfo=timezone.utc)
    notes = json.loads((ep_dir / 'chapters.json').read_text()).get('chapters', [])
    hosts = ep.get('hosts') or [ep.get('host', '')]
    names = ' and '.join(hosts) if len(hosts) < 3 else ', '.join(hosts[:-1]) + ', and ' + hosts[-1]
    body = [f"<p>Join {html.escape(names)} as they cover the week: {html.escape(ep.get('summary', ''))}</p>"]
    for c in notes:
        if c.get('links'):
            body.append(f"<p><strong>{html.escape(c['title'])}</strong></p><ul>")
            body += [f'<li><a href="{html.escape(l["url"])}">{html.escape(l["label"])}</a></li>'
                     for l in c['links']]
            body.append('</ul>')
    art = ''
    if (ep_dir / 'art.jpg').exists():
        art = f'\n      <itunes:image href="{ep_url}art.jpg"/>'
    transcript = ''
    if (ep_dir / 'transcript.vtt').exists():
        transcript = f'\n      <podcast:transcript url="{ep_url}transcript.vtt" type="text/vtt"/>'
    return f"""    <item>
      <title>{html.escape(ep['title'])}</title>
      <guid isPermaLink="false">{ep_url}</guid>
      <link>{base}/e/{ep['id']}</link>
      <pubDate>{format_datetime(day)}</pubDate>
      <description><![CDATA[{''.join(body)}]]></description>
      <itunes:summary>{html.escape(ep.get('summary', ''))}</itunes:summary>
      <enclosure url="{ep_url}episode.mp3" length="{mp3.stat().st_size}" type="audio/mpeg"/>
      <itunes:duration>{int(ep.get('duration_seconds', 0))}</itunes:duration>
      <itunes:episodeType>full</itunes:episodeType>{art}
      <podcast:chapters url="{ep_url}chapters.json" type="application/json+chapters"/>{transcript}
    </item>"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', required=True, help='public origin, no trailing slash')
    base = ap.parse_args().base.rstrip('/')
    eps = []
    for d in sorted(EPISODES.iterdir(), reverse=True):
        f = d / 'episode.json'
        if d.is_dir() and f.exists() and (d / 'episode.mp3').exists():
            e = json.loads(f.read_text())
            if not e.get('unlisted'):
                eps.append((e, d))
    cover = EPISODES / 'cover.png'
    if not cover.exists():
        raise SystemExit('episodes/cover.png is missing. Run scripts/make_art.py first.')
    # Players cache artwork by URL, so the query string changes whenever the image does.
    art = f"{base}/episodes/cover.png?v={hashlib.sha256(cover.read_bytes()).hexdigest()[:8]}"
    items = '\n'.join(item(base, e, d) for e, d in eps)
    feed = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:podcast="https://podcastindex.org/namespace/1.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{TITLE}</title>
    <link>{base}/</link>
    <atom:link href="{base}/episodes/feed.xml" rel="self" type="application/rss+xml"/>
    <description>{html.escape(DESCRIPTION)}</description>
    <language>en-us</language>
    <itunes:author>{AUTHOR}</itunes:author>
    <itunes:summary>{html.escape(DESCRIPTION)}</itunes:summary>
    <itunes:type>episodic</itunes:type>
    <itunes:explicit>false</itunes:explicit>
    <itunes:category text="Technology"/>
    <itunes:image href="{art}"/>
    <itunes:owner><itunes:name>{AUTHOR}</itunes:name><itunes:email>{OWNER_EMAIL}</itunes:email></itunes:owner>
    <image><url>{art}</url><title>{TITLE}</title><link>{base}/</link></image>
{items}
  </channel>
</rss>
"""
    (EPISODES / 'feed.xml').write_text(feed)
    # The site's episode list, folded here too so parallel renders cannot leave it stale.
    keys = ('id', 'title', 'summary', 'window', 'host', 'hosts', 'duration_seconds')
    (EPISODES / 'index.json').write_text(json.dumps(
        {'episodes': [{k: e.get(k) for k in keys} for e, _ in eps]}, indent=2) + '\n')
    print(f'wrote episodes/feed.xml with {len(eps)} episode(s) for {base}')


if __name__ == '__main__':
    main()
