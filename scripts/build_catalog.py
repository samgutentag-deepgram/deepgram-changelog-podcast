"""Build <episodes_dir>/catalog.json, the data behind the public /back-catalog page: one row per
weekly episode, newest first, planned or published, with what each rendered episode cost.

Usage: python3 scripts/build_catalog.py [--plan research/backfill-plan.json]
       EPISODES_DIR=/data/episodes python3 scripts/build_catalog.py --plan /app/research/backfill-plan.json

Why a separate file instead of serving backfill-plan.json: the plan is a research artifact, and
catalog.json is served publicly, so this script is the filter. It keeps a segment's check, keeps
public changelog headlines, and drops every other kind of plan line.

Published episodes (an episode.json with an episode.mp3 next to it) override the plan with what
actually aired: the segments come from chapters.json and the headlines from its show-note links.
Episodes on disk but not in the plan still get a row, so the page never hides a real episode.
Episodes marked "unlisted" are skipped. A missing plan file is fine: the catalog is then built
from the episodes on disk alone. Run it after every render; stdlib only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cadence import CADENCE  # noqa: E402
from segments import SEGMENTS as _NAMES, SHORT  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SEGMENTS = [(name, SHORT[name]) for name in _NAMES]
SEGMENT_NAMES = {name for name, _ in SEGMENTS}
ID_OK = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')
DATED = re.compile(r'^(\d{4}-\d{2}-\d{2}): (.+)$')
PART = re.compile(r'\s*\(part\)$')


def read_json(path: Path) -> object | None:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as e:
        print(f'warning: skipping unreadable {path}: {e}', file=sys.stderr)
        return None


def public_items(raw: list[str]) -> list[dict]:
    """Plan item strings to public headlines. Only lines shaped "YYYY-MM-DD: <changelog heading>"
    survive; "aired:" markers and anything else unrecognized are dropped, so a new kind of plan
    line added later fails closed instead of leaking."""
    out = []
    for s in raw:
        m = DATED.match(s)
        if not m:
            continue
        title = m.group(2)
        item: dict = {'date': m.group(1), 'title': PART.sub('', title)}
        if PART.search(title):
            item['part'] = True
        out.append(item)
    return out


def human_range(a: date, b: date) -> str:
    if a.year != b.year:
        return f'{a:%B} {a.day}, {a.year} to {b:%B} {b.day}, {b.year}'
    if a.month == b.month:
        return f'{a:%B} {a.day} to {b.day}, {b.year}'
    return f'{a:%B} {a.day} to {b:%B} {b.day}, {b.year}'


def planned_row(week: dict) -> dict:
    segs = {}
    for name, _ in SEGMENTS:
        raw = week.get('segments', {}).get(name)
        if raw:
            # The check stays even when no item behind it is a public headline.
            segs[name] = public_items(raw)
    return {
        'id': week['id'], 'title': week['title'], 'start': week['start'], 'end': week['end'],
        'release': week['release'], 'entries': week.get('entries'), 'published': False,
        'url': None, 'cost_usd': None, 'writer_usd': None, 'writer_estimated': False,
        'duration_seconds': None, 'segments': segs,
    }


def published_row(ep_dir: Path, ep: dict, base: dict | None) -> dict:
    window = ep.get('window') or {}
    start, end = window.get('start'), window.get('end')
    release = ep.get('release_date') or ep_dir.name
    if not (start and end):
        # Same rule as the show: the window this release date publishes (cadence.py).
        try:
            window = CADENCE.window_for_release(date.fromisoformat(release))
        except ValueError:
            window = None
        start, end = (window[0].isoformat(), window[1].isoformat()) if window else (None, None)
    title = ep.get('title')
    if not title and start and end:
        title = CADENCE.title(date.fromisoformat(start), date.fromisoformat(end))
    chapters = (read_json(ep_dir / 'chapters.json') or {}).get('chapters') or []
    segs = {}
    for c in chapters:
        name = c.get('title')
        if name not in SEGMENT_NAMES:
            continue  # Intro, Outro, and anything the renderer adds later
        segs[name] = [{'title': l['label'], 'url': l['url']} for l in c.get('links') or []
                      if l.get('label') and l.get('url')]
    cost = (ep.get('cost') or {}).get('usd')
    writer = (ep.get('cost') or {}).get('writer_usd')
    return {
        'id': ep_dir.name, 'title': title or ep_dir.name, 'start': start, 'end': end, 'release': release,
        'entries': base.get('entries') if base else None, 'published': True,
        'url': f'/e/{ep_dir.name}', 'cost_usd': round(cost, 5) if isinstance(cost, (int, float)) else None,
        'writer_usd': round(writer, 5) if isinstance(writer, (int, float)) else None,
        'writer_estimated': bool((ep.get('cost') or {}).get('writer_estimated')),
        'duration_seconds': ep.get('duration_seconds'),
        'segments': {name: segs[name] for name, _ in SEGMENTS if name in segs},
    }


def build(episodes_dir: Path, plan_path: Path) -> dict:
    plan = read_json(plan_path)
    if plan is None:
        print(f'note: no plan at {plan_path}, building from episodes on disk only', file=sys.stderr)
        plan = []
    rows: dict[str, dict] = {w['id']: planned_row(w) for w in plan if ID_OK.match(str(w.get('id', '')))}
    plan_by_id = {w['id']: w for w in plan if 'id' in w}

    if episodes_dir.is_dir():
        for d in sorted(episodes_dir.iterdir()):
            if not d.is_dir() or not ID_OK.match(d.name):
                continue
            ep = read_json(d / 'episode.json')
            if not isinstance(ep, dict):
                continue
            if ep.get('unlisted'):
                rows.pop(d.name, None)
                continue
            if not (d / 'episode.mp3').exists():
                continue  # still rendering, or failed: the planned row stands
            rows[d.name] = published_row(d, ep, plan_by_id.get(d.name))

    episodes = sorted(rows.values(), key=lambda r: r['release'] or r['id'], reverse=True)
    published = [r for r in episodes if r['published']]
    costs = [r['cost_usd'] for r in published if r['cost_usd'] is not None]
    return {
        'generated_at': datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        'segments': [{'name': name, 'short': short} for name, short in SEGMENTS],
        'cadence': {'name': CADENCE.name, 'release_day': CADENCE.day_name, 'period': CADENCE.period,
                    'describe': CADENCE.describe()},
        'totals': {
            'episodes': len(episodes),
            'published': len(published),
            'planned': len(episodes) - len(published),
            'cost_usd_published': round(sum(costs), 5),
            'avg_cost_usd': round(sum(costs) / len(costs), 5) if costs else None,
            'writer_usd_published': round(sum(r['writer_usd'] for r in published if r['writer_usd'] is not None), 5),
            'writer_tracked': sum(1 for r in published if r['writer_usd'] is not None),
            'writer_estimated': sum(1 for r in published if r['writer_estimated']),
            'writer_usd_estimated': round(sum(r['writer_usd'] for r in published
                                              if r['writer_estimated'] and r['writer_usd'] is not None), 5),
            'segments': {name: sum(1 for r in episodes if name in r['segments']) for name, _ in SEGMENTS},
        },
        'episodes': episodes,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--plan', type=Path, default=ROOT / 'research' / 'backfill-plan.json')
    args = ap.parse_args()
    episodes_dir = Path(os.environ.get('EPISODES_DIR', ROOT / 'episodes'))
    episodes_dir.mkdir(parents=True, exist_ok=True)

    catalog = build(episodes_dir, args.plan)
    out = episodes_dir / 'catalog.json'
    tmp = out.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(catalog, indent=1) + '\n')
    # The page polls this file while episodes render, so swap it in whole rather than let a
    # reader catch it half-written.
    tmp.replace(out)
    t = catalog['totals']
    print(f"{t['episodes']} episodes, {t['published']} published, ${t['cost_usd_published']:.4f} spent. Wrote {out}")


if __name__ == '__main__':
    main()
