"""Plan the backfill: one episode per window (a week, two weeks, or a month, per show.json's
"cadence") that has changelog entries, with a draft guess at which segments each episode would
have. Writes research/backfill-plan.json, research/backfill-review.html, and research/cadence.json,
which recommends a cadence from the feed's recent history.

Usage: python3 scripts/backfill_plan.py [--through YYYY-MM-DD] [--refresh]

The segment guesses are keyword rules over each entry's heading and body, applied in running
order so an item lands in exactly one segment, the way the show airs it. They are a first pass for
review, not a script. Launches come from the changelog alone, guessed from headings like
"Introducing" or "Generally Available".

Changelog entries are cached under .cache/changelog, so a re-run is offline unless --refresh.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

import changelog_source
from cadence import CADENCE, recommend

ROOT = Path(__file__).resolve().parent.parent
EPISODES = Path(os.environ.get('EPISODES_DIR', ROOT / 'episodes'))
SEGMENTS = ['Breaking changes and action required', 'Launches', 'Quick hits', 'Voice Agent',
            'Speech-to-Text', 'Text-to-Speech', 'Developer experience']
SHORT = {'Breaking changes and action required': 'Breaking', 'Launches': 'Launches',
         'Quick hits': 'Quick hits', 'Voice Agent': 'Voice Agent', 'Speech-to-Text': 'STT',
         'Text-to-Speech': 'TTS', 'Developer experience': 'DX'}
COST_PER_EPISODE = 0.18  # episode one, 2026-09-22, multi-voice

BREAKING = re.compile(
    r'breaking change|action required|not backwards?[- ]compatible|deprecat|will be removed|'
    r'has been removed|have been removed|\bremoves\b|\bremoved from\b|return(?:s)? (?:an? )?(?:HTTP )?4\d\d|'
    r'sessions? (?:now )?close automatically|must be updated', re.I)
NOT_BREAKING = re.compile(r'no breaking changes?|additive change|backward[- ]compatible\b(?! with previous)|'
                          r'no existing fields are removed|remain as deprecated aliases', re.I)
LAUNCH_HEAD = re.compile(r'\bintroducing\b|generally available|general availability|\blaunch', re.I)
QUICK_HEAD = re.compile(r'self-hosted|nova-\d (?:model )?(?:update|improve|adds)|improved models|new models|'
                        r'language|numerals|profanity|endpoint now generally available|concurrency|pricing|'
                        r'now available$|\bmodels? support\b|llm models?|model updates', re.I)
VOICE_AGENT = re.compile(r'voice agent|\bagent\b|\bllm\b|think|updatelisten|update ?listen|injectagent|'
                         r'function call|claude|gemini|openai|nvidia|cartesia', re.I)
STT = re.compile(r'\bnova\b|nova-\d|\bflux\b(?! tts)|diariz|redact|entit|transcri|speech-to-text|keyterm|'
                 r'language detection|topic|summar|sentiment|intelligence|smart format|\bstt\b', re.I)
TTS = re.compile(r'\baura\b|aura-\d|\btts\b|text-to-speech|\bspeak\b|voice controls|expressivity', re.I)
ROLLUP = re.compile(r'sdk releases|sdk support|\bcli\b|@deepgram/react', re.I)
DX = re.compile(r'\bsdk\b|\bcli\b|react|docs?\b|documentation|correction|saga|\bmcp\b|playground|console|'
                r'api key|token|developer', re.I)


def load_entries(refresh: bool) -> list[tuple[date, str, str]]:
    """(day, markdown body, public URL) per changelog day. See changelog_source.py for the two
    kinds of source it reads, an RSS/Atom feed or an llms.txt index."""
    return changelog_source.load_entries(refresh)


def items(day: date, body: str) -> list[dict]:
    parts = re.split(r'^## ', body, flags=re.M)[1:]
    if not parts and body.strip():
        # A few older entries have no H2 at all and open on a deeper heading, so the whole page
        # is one item. Name it after that heading, or after a self-hosted release number.
        rel = re.search(r'release[- ](\d{6})', body)
        head = re.search(r'^#{1,6}\s+(.+)$', body, re.M)
        title = f'Deepgram Self-Hosted Release ({rel.group(1)})' if rel else \
            (head.group(1).strip() if head else f'Changelog entry for {day:%B} {day.day}, {day.year}')
        return [{'date': day.isoformat(), 'title': title, 'body': body.strip()}]
    return [{'date': day.isoformat(), 'title': p.partition('\n')[0].strip(), 'body': p.partition('\n')[2]}
            for p in parts]


def segment_for(item: dict, launches_by_week: set[str]) -> str:
    head, body = item['title'], item['body']
    text = head + '\n' + body
    is_correction = head.lower().startswith('correction')
    if not is_correction:
        hits = [s for s in re.split(r'(?<=[.!?\n])\s+', text) if BREAKING.search(s) and not NOT_BREAKING.search(s)]
        if hits:
            return SEGMENTS[0]
    if not is_correction and 'self-hosted' not in head.lower() and 'endpoint' not in head.lower():
        if LAUNCH_HEAD.search(head) or head in launches_by_week:
            return SEGMENTS[1]
    if QUICK_HEAD.search(head) and not re.search(r'\bsdk\b|\bcli\b', head, re.I):
        return SEGMENTS[2]
    for seg, rx in ((SEGMENTS[3], VOICE_AGENT), (SEGMENTS[4], STT), (SEGMENTS[5], TTS)):
        if rx.search(head):
            return seg
    if DX.search(head):
        return SEGMENTS[6]
    for seg, rx in ((SEGMENTS[3], VOICE_AGENT), (SEGMENTS[4], STT), (SEGMENTS[5], TTS), (SEGMENTS[6], DX)):
        if rx.search(body):
            return seg
    return SEGMENTS[2]


def last_saturday(today: date | None = None) -> date:
    """The most recent Saturday whose week has ended. On a Saturday that is the week before."""
    today = today or date.today()
    return today - timedelta(days=(today.weekday() - 5) % 7 or 7)


def sunday_of(d: date) -> date:
    return d - timedelta(days=(d.weekday() + 1) % 7)


def human_range(a: date, b: date) -> str:
    if a.year != b.year:
        return f'{a:%B} {a.day}, {a.year} to {b:%B} {b.day}, {b.year}'
    if a.month == b.month:
        return f'{a:%B} {a.day} to {b.day}, {b.year}'
    return f'{a:%B} {a.day} to {b:%B} {b.day}, {b.year}'


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--through', default=CADENCE.latest_end().isoformat(),
                    help='last day to include (default: the end of the most recent finished window)')
    ap.add_argument('--refresh', action='store_true')
    args = ap.parse_args()
    through = date.fromisoformat(args.through)

    weeks: dict[date, list[dict]] = {}
    entries = load_entries(args.refresh)
    for day, body, _url in entries:
        if day <= through:
            weeks.setdefault(CADENCE.window_of(day)[0], []).extend(items(day, body))

    published = {p.name for p in EPISODES.iterdir() if (p / 'episode.mp3').exists()}
    plan = []
    for start in sorted(weeks, reverse=True):
        end = CADENCE.window_of(start)[1]
        release = CADENCE.release_for(end)
        segs: dict[str, list[str]] = {s: [] for s in SEGMENTS}
        for it in weeks[start]:
            seg = segment_for(it, set())
            segs[seg].append(f"{it['date']}: {it['title']}")
            # Roll-up entries (SDK and CLI releases) carry several products at once, and the show
            # splits them across segments, so they also tick the product segments they discuss.
            if ROLLUP.search(it['title']):
                for s, rx in ((SEGMENTS[3], VOICE_AGENT), (SEGMENTS[4], STT), (SEGMENTS[5], TTS)):
                    if s != seg and len(rx.findall(it['body'])) >= 2:
                        segs[s].append(f"{it['date']}: {it['title']} (part)")
        real = EPISODES / release.isoformat() / 'chapters.json'
        if real.exists():
            # A published episode shows what actually aired, not the guess.
            aired = json.loads(real.read_text())['chapters']
            segs = {s: [f'aired: {s}'] for s in SEGMENTS if any(c['title'] == s for c in aired)}
        plan.append({
            'id': release.isoformat(), 'title': CADENCE.title(start, end),
            'start': start.isoformat(), 'end': end.isoformat(), 'release': release.isoformat(),
            'entries': len(weeks[start]), 'published': release.isoformat() in published,
            'segments': {s: v for s, v in segs.items() if v},
        })

    out = ROOT / 'research'
    (out / 'backfill-plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    write_html(plan, out / 'backfill-review.html', through)
    rec = recommend(entries, CADENCE.release_day)
    rec['current'] = CADENCE.name
    (out / 'cadence.json').write_text(json.dumps(rec, indent=2) + '\n')
    print(f'{len(plan)} episodes ({CADENCE.adjective}, released {CADENCE.day_name}s), '
          f'{sum(p["published"] for p in plan)} already published. '
          f'Wrote research/backfill-plan.json, backfill-review.html, and cadence.json')
    if rec['cadence'] != CADENCE.name:
        print(f"Recommended cadence: {rec['cadence']} (show.json says {CADENCE.name}). "
              "python3 scripts/cadence.py explains why.")


def write_html(plan: list[dict], path: Path, through: date) -> None:
    by_year = Counter(p['start'][:4] for p in plan)
    seg_counts = Counter(s for p in plan for s in p['segments'])
    todo = [p for p in plan if not p['published']]
    rows = []
    for p in plan:
        cells = []
        for s in SEGMENTS:
            got = p['segments'].get(s)
            tip = html.escape('\n'.join(got)) if got else ''
            cells.append(f'<td class="c" title="{tip}">{"&#10003;" if got else ""}</td>')
        status = '<span class="pill">published</span>' if p['published'] else ''
        detail = ''.join(f'<li><b>{SHORT[s]}</b> {html.escape(x)}</li>'
                         for s, xs in p['segments'].items() for x in xs)
        rows.append(
            f'<tr data-year="{p["start"][:4]}"><td><details><summary>{html.escape(p["title"])} {status}</summary>'
            f'<ul>{detail}</ul></details></td><td class="nw">{p["start"]} to {p["end"]}</td>'
            f'<td class="nw">Tue {p["release"]}</td><td class="n">{p["entries"]}</td>{"".join(cells)}</tr>')
    years = ''.join(f'<button type="button" data-y="{y}">{y} <span>{n}</span></button>'
                    for y, n in sorted(by_year.items(), reverse=True))
    heads = ''.join(f'<th class="c">{SHORT[s]}<span>{seg_counts[s]}</span></th>' for s in SEGMENTS)
    doc = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Backfill Review</title>
<style>
  :root {{ --bg: #fafaff; --ink: #111116; --muted: #5c5c66; --line: #dcdce4; --accent: #0a8f58; --card: #fff; --zebra: #f3f3f8; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --bg: #000; --ink: #fbfbff; --muted: #949498; --line: #26262e; --accent: #13ef95; --card: #0a0a0f; --zebra: #0c0c12; }} }}
  body {{ margin: 0; background: var(--bg); color: var(--ink); font: 14px/1.45 system-ui, sans-serif; }}
  main {{ max-width: 80rem; margin: 0 auto; padding: 1.6rem 16px 3rem; }}
  h1 {{ font-size: 1.5rem; margin: 0 0 .3rem; }}
  p {{ color: var(--muted); margin: 0 0 .8rem; max-width: 60rem; }}
  .stats {{ display: flex; flex-wrap: wrap; gap: .6rem; margin: 1rem 0; }}
  .stat {{ background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: .6rem .9rem; }}
  .stat b {{ display: block; font-size: 1.4rem; color: var(--accent); }}
  .years {{ display: flex; flex-wrap: wrap; gap: .4rem; margin: .4rem 0 1rem; }}
  .years button {{ font: inherit; color: var(--ink); background: var(--card); border: 1px solid var(--line); border-radius: 999px; padding: .25rem .75rem; cursor: pointer; }}
  .years button[aria-pressed="true"] {{ border-color: var(--accent); color: var(--accent); }}
  .years span {{ color: var(--muted); }}
  .wrap {{ overflow-x: auto; border: 1px solid var(--line); border-radius: 10px; background: var(--card); }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ padding: .45rem .6rem; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }}
  th {{ position: sticky; top: 0; background: var(--card); font-size: .8rem; }}
  th span {{ display: block; color: var(--muted); font-weight: 400; }}
  tbody tr:nth-child(even) {{ background: var(--zebra); }}
  .c {{ text-align: center; color: var(--accent); font-weight: 700; width: 4.5rem; }}
  .n {{ text-align: right; }}
  .nw {{ white-space: nowrap; }}
  details summary {{ cursor: pointer; }}
  details ul {{ margin: .4rem 0 .2rem; padding-left: 1.1rem; color: var(--muted); font-size: .82rem; }}
  details b {{ color: var(--ink); font-weight: 600; margin-right: .3rem; }}
  .pill {{ font-size: .72rem; border: 1px solid var(--accent); color: var(--accent); border-radius: 999px; padding: 0 .45rem; margin-left: .3rem; }}
</style>
</head>
<body>
<main>
  <h1>Backfill review</h1>
  <p>One episode per Sunday-to-Saturday week with changelog entries, through Saturday {through.isoformat()}, released
  the following Tuesday. Newest first. A check means the draft rules put at least one item in that segment; hover a
  check for the items, or open a row for the full list. These are keyword guesses for triage, not scripts.
  Launches are guessed from changelog headings.</p>
  <div class="stats">
    <div class="stat"><b>{len(plan)}</b>episodes total</div>
    <div class="stat"><b>{len(todo)}</b>to backfill</div>
    <div class="stat"><b>${len(todo) * COST_PER_EPISODE:.2f}</b>est. Flux TTS for all of them</div>
    <div class="stat"><b>{by_year.get("2026", 0)}</b>in 2026</div>
    <div class="stat"><b>{sum(n for y, n in by_year.items() if y >= "2025")}</b>since 2025</div>
  </div>
  <div class="years"><button type="button" data-y="all" aria-pressed="true">All <span>{len(plan)}</span></button>{years}</div>
  <div class="wrap"><table>
    <thead><tr><th>Episode</th><th>Date range</th><th>Release</th><th class="n">Entries</th>{heads}</tr></thead>
    <tbody>{"".join(rows)}</tbody>
  </table></div>
</main>
<script>
  var buttons = document.querySelectorAll('.years button')
  buttons.forEach(function (b) {{
    b.addEventListener('click', function () {{
      buttons.forEach(function (x) {{ x.setAttribute('aria-pressed', String(x === b)) }})
      document.querySelectorAll('tbody tr').forEach(function (r) {{
        r.hidden = b.dataset.y !== 'all' && r.dataset.year !== b.dataset.y
      }})
    }})
  }})
</script>
</body>
</html>
'''
    path.write_text(doc)


if __name__ == '__main__':
    main()
