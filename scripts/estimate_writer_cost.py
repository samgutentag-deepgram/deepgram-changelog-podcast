"""Estimate the Claude writing cost of episodes written before writer.json existed.

Usage: python3 scripts/estimate_writer_cost.py [--dry-run]

The 2026 episodes were written on 2026-09-25, before usage was recorded. Two of the three parts of
the bill can be recovered exactly, and the third is calibrated against the 30 episodes that do
have a real bill:

- Input tokens: the writer's prompt is deterministic from the episode's changelog entries, so it
  is rebuilt with write_episode.build_prompts and counted with the token-counting endpoint.
- Visible output tokens: the model's own text is still in script.md (summary, segments, show
  notes), so it is cut back out and counted.
- Thinking tokens bill as output but leave no trace. Their share is taken from the measured
  episodes: the ratio of billed output tokens to visible output tokens, median for the estimate,
  and the 10th to 90th percentile for the range.

Each estimate lands in writer.json with "estimated": true and its method, and in episode.json as
cost.writer_usd plus cost.writer_estimated, so the site can mark it. Measured episodes are never
touched. The hand-written episode one (2026-09-22) had no writer, so it is skipped.

Needs ANTHROPIC_API_KEY. Token counting is free.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from datetime import date
from pathlib import Path

import anthropic

sys.path.insert(0, str(Path(__file__).resolve().parent))
from write_episode import EPISODES, MODEL, PRICE_PER_MTOK, ROOT, build_prompts, gather  # noqa: E402

HAND_WRITTEN = {'2026-09-22'}


def visible_output(script_md: str) -> str:
    """Rebuild what the model returned: SUMMARY, the segments between the canned intro and outro,
    and NOTES minus the canned credit and contact blocks."""
    summary = re.search(r'^\*\*Summary:\*\*\s*(.+)$', script_md, re.M).group(1)
    body = script_md.split('## Intro', 1)[1].split('## Outro', 1)[0]
    segs = body[body.index('\n## ') + 1:] if '\n## ' in body else ''
    notes = script_md.split('## Show notes', 1)[1].split('\n---\n', 1)[0]
    notes = re.split(r'^\*\*(?:Credits and pricing|Get in touch)\*\*', notes, flags=re.M)[0]
    return f'SUMMARY: {summary}\n\n{segs.strip()}\n\nNOTES:\n\n{notes.strip()}'


def count(client: anthropic.Anthropic, system: str | None, text: str) -> int:
    kwargs = {'model': MODEL, 'messages': [{'role': 'user', 'content': text}]}
    if system:
        kwargs['system'] = system
    return client.messages.count_tokens(**kwargs).input_tokens


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()
    client = anthropic.Anthropic()
    overhead = count(client, None, '.')  # the message wrapper, subtracted from a bare-text count
    cast = json.loads((ROOT / 'docs' / 'cast.json').read_text())

    ratios, input_check = [], []
    for w in sorted(EPISODES.glob('*/writer.json')):
        rec = json.loads(w.read_text())
        if rec.get('estimated') or len(rec['calls']) != 1:
            continue  # calibrate on clean single-call bills only
        call = rec['calls'][0]
        vis = count(client, None, visible_output((w.parent / 'script.md').read_text())) - overhead
        ratios.append(call['output_tokens'] / max(1, vis))
        release = date.fromisoformat(w.parent.name)
        start, end, entries = gather(release)
        system, user = build_prompts(release, start, end, entries, cast)
        input_check.append(count(client, system, user) / max(1, call['input_tokens']))
    ratios.sort()
    mid = statistics.median(ratios)
    lo, hi = ratios[len(ratios) // 10], ratios[(len(ratios) * 9) // 10]
    drift = statistics.median(input_check)
    print(f'calibrated on {len(ratios)} measured episodes: billed/visible output ratio median {mid:.2f} '
          f'(p10 {lo:.2f}, p90 {hi:.2f}); rebuilt prompt vs recorded input {drift:.3f}')

    pin, pout = PRICE_PER_MTOK[MODEL]
    done = []
    for ep_dir in sorted(p for p in EPISODES.iterdir() if (p / 'script.md').exists()):
        if ep_dir.name in HAND_WRITTEN or (ep_dir / 'writer.json').exists():
            continue
        release = date.fromisoformat(ep_dir.name)
        start, end, entries = gather(release)
        system, user = build_prompts(release, start, end, entries, cast)
        inp = round(count(client, system, user) / drift)
        vis = count(client, None, visible_output((ep_dir / 'script.md').read_text())) - overhead

        def usd(ratio: float) -> float:
            return round((inp * pin + vis * ratio * pout) / 1e6, 5)

        rec = {
            'model': MODEL, 'estimated': True, 'usd': usd(mid), 'usd_low': usd(lo), 'usd_high': usd(hi),
            'input_tokens': inp, 'visible_output_tokens': vis,
            'method': ('Input rebuilt with write_episode.build_prompts and counted; visible output cut from '
                       'script.md and counted; thinking share from the billed/visible output ratio of '
                       f'{len(ratios)} measured episodes (median {mid:.2f}, p10 {lo:.2f}, p90 {hi:.2f}). '
                       'Assumes one writer call, since no retry was logged for these episodes.'),
            'estimated_on': date.today().isoformat(),
            'pricing_url': 'https://www.anthropic.com/pricing', 'pricing_as_of': '2026-09-25',
        }
        done.append((ep_dir.name, rec['usd'], rec['usd_low'], rec['usd_high']))
        if args.dry_run:
            continue
        (ep_dir / 'writer.json').write_text(json.dumps(rec, indent=2) + '\n')
        ep_json = ep_dir / 'episode.json'
        if ep_json.exists():
            ep = json.loads(ep_json.read_text())
            ep.setdefault('cost', {})['writer_usd'] = rec['usd']
            ep['cost']['writer_estimated'] = True
            ep_json.write_text(json.dumps(ep, indent=2) + '\n')
    for row in done:
        print(f'{row[0]}: ${row[1]:.4f} (range ${row[2]:.4f} to ${row[3]:.4f})')
    total = sum(r[1] for r in done)
    print(f'{len(done)} episodes estimated, ${total:.2f} total '
          f'(${sum(r[2] for r in done):.2f} to ${sum(r[3] for r in done):.2f})'
          + (' [dry run, nothing written]' if args.dry_run else ''))


if __name__ == '__main__':
    main()
