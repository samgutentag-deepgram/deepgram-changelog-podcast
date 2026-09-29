"""Key-term pronunciation test: render spelling candidates several times each and score them by
whether Deepgram STT hears the intended words.

Usage: python3 scripts/term_test.py [--takes 3] [--voice flux-brooke-en] [--only auth,vad]

Flux TTS is not deterministic, so one good render proves nothing. Each candidate is rendered
--takes times inside the same carrier sentence and scored as hits/takes. The winners go into
SPOKEN_FORMS in render_episode.py (or become a writing rule, like "acronyms in caps").

Flux TTS (/v2/speak) has no pronunciation-override control yet. The Aura-2 inline IPA syntax is
read aloud as literal text, verified 2026-09-25, so respelling is the only lever for now.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_episode import ROOT, load_key, speak  # noqa: E402
from readback_check import transcribe, words  # noqa: E402

TERMS_FILE = ROOT / 'docs' / 'key-terms.json'


def heard_in_order(expected: list[str], heard: list[str]) -> bool:
    # Each expected slot may list alternates with "|", because STT writes "v2" or "v two"
    # depending on context and either one means Flux said it right.
    it = iter(heard)
    return all(any(h in e.split('|') for h in it) for e in expected)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--takes', type=int, default=3)
    ap.add_argument('--voice', default='flux-brooke-en')
    ap.add_argument('--only', help='comma-separated term ids')
    args = ap.parse_args()
    terms = json.loads(TERMS_FILE.read_text())['terms']
    if args.only:
        keep = set(args.only.split(','))
        terms = [t for t in terms if t['id'] in keep]
    key = load_key()

    results = {}
    for t in terms:
        print(f"\n{t['id']}  (want: {' '.join(t['expect'])})")
        results[t['id']] = {}
        for cand in t['candidates']:
            sentence = t['carrier'].replace('{}', cand)
            hits, samples = 0, []
            for _ in range(args.takes):
                heard = [re.sub(r"[^a-z0-9']", '', w['word'].lower())
                         for w in transcribe(speak(sentence, args.voice, key), key)]
                ok = heard_in_order(t['expect'], heard)
                hits += ok
                samples.append(' '.join(heard))
            results[t['id']][cand] = hits
            print(f"  {hits}/{args.takes}  {cand!r:28}  e.g. {samples[0][:70]!r}")
    out = ROOT / '.cache' / 'term_test.json'
    out.write_text(json.dumps(results, indent=2) + '\n')
    print(f'\nwrote {out.relative_to(ROOT)}')


if __name__ == '__main__':
    main()
