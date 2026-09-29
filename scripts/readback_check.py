"""Readback check: transcribe every rendered paragraph with Deepgram STT and diff it against the
words that were sent to Flux.

Usage: python3 scripts/readback_check.py episodes/2026-09-22 [--json out.json]

Works from the per-paragraph TTS cache, so each paragraph is checked in isolation and a flag
points at exactly one render. For each paragraph it reports a word error rate and every
mismatched span, with the time in the episode where it happens.

A flag is a lead, not a verdict. STT has its own errors, mostly on identifiers like SpeakV2Speed,
so a flag means "a human should listen here", and a span that also has low STT confidence is the
strongest signal that Flux actually misspoke.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_episode import ROOT, SAMPLE_RATE, cache_key, load_key, speak, spoken_form  # noqa: E402

LOW_CONFIDENCE = 0.6

# Differences that are STT formatting, not Flux misspeaking. Both sides are compared after this,
# so these never flag. Each entry is (expected span, what nova-3 writes for a correct reading).
EQUIVALENT = [
    ('3', 'three'), ('healthcare', 'health care'), ('deepgram', 'deep gram'), ('on to', 'onto'),
    ('barge in', 'bargain'), ('ttl', 't t l'), ('too', 'two'), ('signup', 'sign up'),
    ('microphoneoptions', 'microphone options'), ('v1', 'v one'), ('v2', 'v two'), ('oh', 'o'),
]


def equivalent(expected: str, heard: str) -> bool:
    return any(expected == a and heard == b for a, b in EQUIVALENT) or expected.replace(' ', '') == heard.replace(' ', '')


def words(text: str) -> list[str]:
    text = text.lower().replace('-', ' ')
    return re.findall(r"[a-z0-9]+(?:'[a-z]+)?", text)


def transcribe(pcm: bytes, key: str) -> list[dict]:
    req = urllib.request.Request(
        f'https://api.deepgram.com/v1/listen?model=nova-3&encoding=linear16&sample_rate={SAMPLE_RATE}',
        data=pcm, headers={'Authorization': f'Token {key}', 'Content-Type': 'audio/raw'},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        alt = json.load(r)['results']['channels'][0]['alternatives'][0]
    return alt.get('words', [])


def check(text: str, pcm: bytes, key: str) -> dict:
    heard = transcribe(pcm, key)
    ref = words(text)
    hyp = [re.sub(r"[^a-z0-9']", '', w['word'].lower()) for w in heard]
    sm = difflib.SequenceMatcher(a=ref, b=hyp, autojunk=False)
    spans, errors = [], 0
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == 'equal' or equivalent(' '.join(ref[i1:i2]), ' '.join(hyp[j1:j2])):
            continue
        errors += max(i2 - i1, j2 - j1)
        hit = heard[j1:j2]
        spans.append({
            'expected': ' '.join(ref[i1:i2]), 'heard': ' '.join(hyp[j1:j2]),
            'at': hit[0]['start'] if hit else (heard[j1 - 1]['end'] if j1 and heard else 0.0),
            'min_confidence': round(min((w['confidence'] for w in hit), default=1.0), 2),
        })
    return {'wer': round(errors / max(1, len(ref)), 3), 'spans': spans}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('episode_dir')
    ap.add_argument('--json', help='write the full report here')
    ap.add_argument('--retake', type=int, default=0,
                    help='re-render each flagged paragraph up to N more times and keep the take with '
                         'the lowest WER. Run render_episode.py afterward to rebuild the MP3.')
    args = ap.parse_args()
    ep = Path(args.episode_dir).resolve()
    rows = json.loads((ep / 'script.json').read_text())
    key = load_key()
    cache = ROOT / '.cache' / 'tts'

    report = []
    for row in rows:
        said = spoken_form(row['text'])
        f = cache / (cache_key(row['voice_id'], said, row.get('expressivity', 0)) + '.pcm')
        if not f.exists():
            sys.exit(f'no cached render for: {said[:60]!r}. Run render_episode.py first.')
        r = check(said, f.read_bytes(), key)
        tries = 0
        while r['spans'] and tries < args.retake:
            tries += 1
            take = speak(said, row['voice_id'], key, row.get('expressivity', 0))
            tr = check(said, take, key)
            print(f"  retake {tries} {row['chapter']} @ {row['start_seconds']:.1f}s: wer {r['wer']:.2f} -> {tr['wer']:.2f}")
            if tr['wer'] < r['wer']:
                f.write_bytes(take)
                r = tr
        for s in r['spans']:
            s['at'] = round(row['start_seconds'] + s['at'], 2)
        report.append({'chapter': row['chapter'], 'start': row['start_seconds'], **r})

    flagged = [r for r in report if r['spans']]
    for r in report:
        mark = 'ok ' if not r['spans'] else 'FLAG'
        print(f"{mark} {r['start']:7.1f}s  wer {r['wer']:.2f}  {r['chapter']}")
        for s in r['spans']:
            low = ' LOW-CONF' if s['min_confidence'] < LOW_CONFIDENCE else ''
            m, sec = divmod(int(s['at']), 60)
            print(f"        {m}:{sec:02d}  expected {s['expected']!r:32} heard {s['heard']!r}{low}")
    total_ref = sum(len(words(spoken_form(r['text']))) for r in rows)
    total_err = sum(round(r['wer'] * len(words(spoken_form(row['text'])))) for r, row in zip(report, rows))
    print(f'\n{len(flagged)} of {len(report)} paragraphs flagged, episode WER {total_err / total_ref:.3f}')
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
