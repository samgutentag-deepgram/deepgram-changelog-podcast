"""Render an episode script.md to a chaptered MP3 with Flux TTS batch, plus the site data.

Usage: python3 scripts/render_episode.py episodes/2026-09-22 [--voice flux-brooke-en --host Brooke]

Reads the spoken part of script.md (from "## Intro" to the first "---" rule), renders one
/v2/speak call per paragraph, joins the raw PCM with short silences, and writes episode.mp3 next
to the script. It also writes what web/ reads: episode.json, script.json (one row per paragraph,
with its start time), chapters.json (segment starts plus that segment's show-note links), and
re-folds episodes/index.json across every rendered episode. Rendered paragraphs are cached by
sha256(voice + text) under .cache/, so a re-run only pays for changed text.

Stdlib only. Needs ffmpeg on PATH and DEEPGRAM_API_KEY in the environment or a .env file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from show import SHOW  # noqa: E402
from cadence import CADENCE  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
EPISODES = Path(os.environ.get('EPISODES_DIR', ROOT / 'episodes'))
SAMPLE_RATE = 24000
RATE_USD_PER_1K = 0.045  # Flux TTS, Pay As You Go, deepgram.com/pricing
PRICING_AS_OF = '2026-09-25'
# Words Flux misreads, respelled only in the text sent to /v2/speak. The page keeps the real
# spelling. "Changelog" came out as "changegog" in 2 of 4 test renders (nova-3 transcripts,
# 2026-09-25); "change log" read correctly 4 of 4. Add to this only with that kind of evidence.
SPOKEN_FORMS = [
    (re.compile(r'\b([Cc])hangelog'), lambda m: m.group(1) + 'hange log'),
]
PARAGRAPH_GAP_S = 0.45
SEGMENT_GAP_S = 1.1


def load_key() -> str:
    key = os.environ.get('DEEPGRAM_API_KEY')
    if key:
        return key
    for env in (ROOT / '.env',):
        if env.exists():
            for line in env.read_text().splitlines():
                if line.startswith('DEEPGRAM_API_KEY='):
                    return line.split('=', 1)[1].strip().strip('"\'')
    sys.exit('DEEPGRAM_API_KEY not set and not found in .env')


def parse_segments(script: str) -> list[tuple[str, list[str]]]:
    if '## Intro' not in script:
        sys.exit('script.md has no "## Intro" heading')
    spoken = '## Intro' + script.split('## Intro', 1)[1].split('\n---\n', 1)[0]
    segments = []
    for block in re.split(r'^## ', spoken, flags=re.M)[1:]:
        title, _, body = block.partition('\n')
        paras = [re.sub(r'\s+', ' ', p).strip() for p in re.split(r'\n\s*\n', body)]
        paras = [p for p in paras if p]
        if paras:
            segments.append((title.strip(), paras))
    return segments


def speak(text: str, voice: str, key: str, expressivity: int = 0) -> bytes:
    query = {'model': voice, 'encoding': 'linear16', 'container': 'none', 'sample_rate': SAMPLE_RATE}
    if expressivity:
        query['expressivity'] = expressivity
    params = urllib.parse.urlencode(query)
    req = urllib.request.Request(
        f'https://api.deepgram.com/v2/speak?{params}',
        data=json.dumps({'text': text}).encode(),
        headers={'Authorization': f'Token {key}', 'Content-Type': 'application/json'},
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                audio = r.read()
            break
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors='replace')[:300]
            if e.code < 500 and e.code != 429:
                raise RuntimeError(f'Flux {e.code} for {text[:60]!r}: {body}') from e
            err = e
        except urllib.error.URLError as e:
            err = e
        time.sleep(2 ** attempt)
    else:
        raise RuntimeError(f'Flux failed after retries for {text[:60]!r}: {err}')
    if audio[:4] == b'RIFF':
        audio = audio[44:]
    if not audio:
        raise RuntimeError(f'Flux returned empty audio for {text[:60]!r}')
    return audio


def spoken_form(text: str) -> str:
    for pattern, repl in SPOKEN_FORMS:
        text = pattern.sub(repl, text)
    return text


def cache_key(voice: str, said: str, expressivity: int = 0) -> str:
    # Expressivity 0 keeps the original key shape so existing cached renders stay valid.
    tag = f'{voice}\n{said}' if not expressivity else f'{voice}|x{expressivity}\n{said}'
    return hashlib.sha256(tag.encode()).hexdigest()


def silence(seconds: float) -> bytes:
    return b'\x00\x00' * int(SAMPLE_RATE * seconds)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('episode_dir')
    ap.add_argument('--voice', default='flux-brooke-en')
    ap.add_argument('--host', default='Brooke')
    ap.add_argument('--expressivity', type=int, default=None,
                    help='Flux TTS expressivity, -2 to 2 (beta). Defaults to cast.json, else 0')
    ap.add_argument('--cast', default=str(ROOT / 'docs' / 'cast.json'),
                    help='cast.json mapping segments to voices (default docs/cast.json); '
                         'pass --cast "" for a single-voice render with --voice/--host')
    ap.add_argument('--clean-cache', action='store_true',
                    help='delete this episode\'s cached paragraph audio and exit (after publishing)')
    ap.add_argument('--unlisted', action='store_true',
                    help='render and publish the page, but leave it out of index.json and the feed')
    args = ap.parse_args()

    ep = Path(args.episode_dir).resolve()
    script_md = (ep / 'script.md').read_text()
    segments = parse_segments(script_md)
    cast = json.loads(Path(args.cast).read_text()) if args.cast else None
    if cast:
        args.voice, args.host = cast['anchor']['voice'], cast['anchor']['name']
    if args.expressivity is None:
        args.expressivity = int(json.loads((ROOT / 'docs' / 'cast.json').read_text()).get('expressivity', 0))

    def voice_for(title: str) -> tuple[str, str]:
        if cast and title in cast['segments']:
            s = cast['segments'][title]
            return s['voice'], s['name']
        return args.voice, args.host
    rows = []
    key = None
    cache = ROOT / '.cache' / 'tts'
    cache.mkdir(parents=True, exist_ok=True)
    if args.clean_cache:
        n = 0
        for title, paras in segments:
            voice, _ = voice_for(title)
            for text in paras:
                f = cache / (cache_key(voice, spoken_form(text), args.expressivity) + '.pcm')
                if f.exists():
                    f.unlink()
                    n += 1
        print(f'removed {n} cached clips')
        return

    pcm = bytearray()
    chapters = []
    chars = 0
    calls = 0
    for i, (title, paras) in enumerate(segments):
        if i:
            pcm += silence(SEGMENT_GAP_S)
        start = len(pcm) / 2 / SAMPLE_RATE
        voice, speaker = voice_for(title)
        for j, text in enumerate(paras):
            if j:
                pcm += silence(PARAGRAPH_GAP_S)
            said = spoken_form(text)
            chars += len(said)
            f = cache / (cache_key(voice, said, args.expressivity) + '.pcm')
            if not f.exists():
                key = key or load_key()
                print(f'  render  {title}: {text[:50]}...', flush=True)
                f.write_bytes(speak(said, voice, key, args.expressivity))
                calls += 1
            rows.append({'role': 'host', 'speaker_key': speaker, 'voice_id': voice,
                         'expressivity': args.expressivity,
                         'chapter': title, 'text': text,
                         'start_seconds': round(len(pcm) / 2 / SAMPLE_RATE, 3)})
            pcm += f.read_bytes()
        chapters.append({'title': title, 'start': round(start, 3)})
    duration = len(pcm) / 2 / SAMPLE_RATE
    for a, b in zip(chapters, chapters[1:] + [{'start': duration}]):
        a['end'] = round(b['start'], 3)

    raw = ep / '.episode.pcm'
    raw.write_bytes(pcm)
    meta = ep / '.chapters.ffmeta'
    lines = [';FFMETADATA1', f"title={SHOW['name']}"]
    for c in chapters:
        lines += ['[CHAPTER]', 'TIMEBASE=1/1000', f'START={int(c["start"] * 1000)}',
                  f'END={int(c["end"] * 1000)}', f'title={c["title"]}']
    meta.write_text('\n'.join(lines) + '\n')
    try:
        subprocess.run(
            # -nostdin: without it ffmpeg reads the terminal and eats keystrokes meant for a prompt.
            ['ffmpeg', '-nostdin', '-y', '-loglevel', 'error', '-f', 's16le', '-ar', str(SAMPLE_RATE), '-ac', '1',
             '-i', str(raw), '-i', str(meta), '-map_metadata', '1', '-map_chapters', '1',
             '-codec:a', 'libmp3lame', '-b:a', '64k', str(ep / 'episode.mp3')],
            check=True,
        )
    finally:
        raw.unlink(missing_ok=True)
        meta.unlink(missing_ok=True)

    usd = chars / 1000 * RATE_USD_PER_1K
    (ep / 'render.json').write_text(json.dumps({
        'voice': args.voice, 'cast': args.cast, 'expressivity': args.expressivity, 'characters': chars, 'duration_s': round(duration, 1),
        'cost_usd': round(usd, 4), 'rate_usd_per_1k': RATE_USD_PER_1K, 'plan': 'payg',
        'episodes_per_200_credit': int(200 / usd), 'new_calls_this_run': calls,
    }, indent=2) + '\n')
    write_site_data(ep, script_md, rows, chapters, duration, chars, usd, args)
    print(f'done: {duration / 60:.1f} min, {chars} chars, ${usd:.2f}, {calls} new calls')


def parse_show_notes(script: str) -> dict[str, list[dict]]:
    if '## Show notes' not in script:
        return {}
    notes = script.split('## Show notes', 1)[1].split('\n## ', 1)[0]
    out, current = {}, None
    for line in notes.splitlines():
        head = re.match(r'^\*\*(.+?)\*\*\s*$', line.strip())
        if head:
            current = head.group(1)
            out[current] = []
            continue
        link = re.match(r'^- \[(.+?)\]\((.+?)\)', line.strip())
        if link and current:
            out[current].append({'label': link.group(1).replace('`', ''), 'url': link.group(2)})
    return out


def write_site_data(ep: Path, script_md: str, rows, chapters, duration, chars, usd, args) -> None:
    head = re.search(r'(?:week|weeks|month) of (\d{4}-\d{2}-\d{2}) to (\d{4}-\d{2}-\d{2})', script_md)
    summary = re.search(r'^\*\*Summary:\*\*\s*(.+)$', script_md, re.M)
    if not head:
        sys.exit('script.md title must contain "week of YYYY-MM-DD to YYYY-MM-DD"')
    start, end = head.groups()
    notes = parse_show_notes(script_md)
    # Notes headings match chapter titles one to one, except the outro's two blocks.
    outro_keys = [k for k in notes if k not in {c['title'] for c in chapters}]
    hn_chapters = []
    for c in chapters:
        links = list(notes.get(c['title'], []))
        if c['title'] == 'Outro':
            for k in outro_keys:
                links += notes[k]
        hn_chapters.append({'title': c['title'], 'startTime': c['start'], 'endTime': c['end'],
                            'links': links})
    episode = {
        'id': ep.name, 'release_date': ep.name[:10], 'window': {'start': start, 'end': end},
        'title': CADENCE.title(date.fromisoformat(start), date.fromisoformat(end)),
        'summary': summary.group(1).strip() if summary else '',
        'host': args.host, 'voice_id': args.voice, 'duration_seconds': round(duration, 1),
        'cast': sorted({r['speaker_key'] for r in rows} - {args.host}),
        # Everyone who speaks, anchor first, then in order of first appearance.
        'hosts': list(dict.fromkeys([args.host] + [r['speaker_key'] for r in rows])),
        'unlisted': bool(args.unlisted),
        'cost': {
            'characters': chars, 'usd': round(usd, 5), 'rate_usd_per_1k': RATE_USD_PER_1K,
            'plan': 'payg', 'credit_usd': 200.0, 'episodes_per_credit': int(200 / usd),
            'episodes_per_year': CADENCE.per_year, 'year_usd': round(usd * CADENCE.per_year, 2),
            'cadence': CADENCE.name,
            # Writing the script with Claude, when writer.json recorded it. Kept separate from
            # the Flux TTS figure, which is the one the outro says out loud.
            'writer_usd': (json.loads((ep / 'writer.json').read_text()).get('usd')
                           if (ep / 'writer.json').exists() else None),
            # True when writer.json is a reconstruction (estimate_writer_cost.py), not a real bill.
            'writer_estimated': (bool(json.loads((ep / 'writer.json').read_text()).get('estimated'))
                                 if (ep / 'writer.json').exists() else False),
            'pricing_url': 'https://deepgram.com/pricing', 'pricing_as_of': PRICING_AS_OF,
        },
    }
    (ep / 'episode.json').write_text(json.dumps(episode, indent=2) + '\n')
    (ep / 'script.json').write_text(json.dumps(rows, indent=2) + '\n')
    # `version` makes this a valid Podcasting 2.0 chapters file, so players read it from the feed.
    (ep / 'chapters.json').write_text(json.dumps({'version': '1.2.0', 'chapters': hn_chapters},
                                                 indent=2) + '\n')
    write_vtt(ep, rows, duration)

    listing = []
    for d in sorted(EPISODES.iterdir(), reverse=True):
        f = d / 'episode.json'
        if f.exists() and (d / 'episode.mp3').exists():
            e = json.loads(f.read_text())
            if e.get('unlisted'):
                continue
            listing.append({k: e.get(k) for k in
                            ('id', 'title', 'summary', 'window', 'host', 'duration_seconds')})
    (EPISODES / 'index.json').write_text(json.dumps({'episodes': listing}, indent=2) + '\n')


def write_vtt(ep: Path, rows, duration: float) -> None:
    def ts(s: float) -> str:
        h, rem = divmod(s, 3600)
        m, sec = divmod(rem, 60)
        return f'{int(h):02d}:{int(m):02d}:{sec:06.3f}'
    cues = ['WEBVTT', '']
    for row, nxt in zip(rows, rows[1:] + [None]):
        end = nxt['start_seconds'] if nxt else duration
        cues += [f"{ts(row['start_seconds'])} --> {ts(end)}", f"<v {row['speaker_key']}>{row['text']}", '']
    (ep / 'transcript.vtt').write_text('\n'.join(cues))


def human_range(start: str, end: str) -> str:
    from datetime import date
    a, b = date.fromisoformat(start), date.fromisoformat(end)
    if a.month == b.month:
        return f'{a:%B} {a.day} to {b.day}, {b.year}'
    return f'{a:%B} {a.day} to {b:%B} {b.day}, {b.year}'


if __name__ == '__main__':
    main()
