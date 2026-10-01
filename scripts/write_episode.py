"""Write an episode's script.md from the changelog, with Claude.

Usage: python3 scripts/write_episode.py 2026-09-22 [--force]

The argument is the Tuesday release date. The episode covers the Sunday to Saturday before it
(release minus 9 days through release minus 3). Claude writes only the summary, the segments in
between, and their show notes. The intro, the outro, and the cost figures are canned and filled
here, so the parts that make claims about money and contact details never come from a model.

Needs ANTHROPIC_API_KEY. Reads changelog entries from .cache/changelog (see backfill_plan.py). The
changelog is the only source: launches are the entries that introduce a new model, product, or
API, or announce general availability of one.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urljoin

import anthropic

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backfill_plan import human_range, items, load_entries  # noqa: E402
from show import SHOW  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
EPISODES = Path(os.environ.get('EPISODES_DIR', ROOT / 'episodes'))
MODEL = 'claude-opus-5'
SEGMENTS = ['Breaking changes and action required', 'Launches', 'Quick hits', 'Voice Agent',
            'Speech-to-Text', 'Text-to-Speech', 'Developer experience']
# Claude pricing per million tokens (input, output), for the writer cost column. Thinking tokens
# bill as output. A server-side fallback can answer on another model, so price by the model that ran.
PRICE_PER_MTOK = {'claude-opus-5': (5.0, 25.0), 'claude-opus-4-8': (5.0, 25.0),
                  'claude-sonnet-5': (2.0, 10.0)}
USAGE: list[dict] = []
SPOKEN_SEGMENT = {'Voice Agent': 'Voice Agent', 'Speech-to-Text': 'speech-to-text',
                  'Text-to-Speech': 'text-to-speech', 'Developer experience': 'developer experience'}
PROMO_START, PROMO_END = date(2026, 9, 15), date(2026, 12, 31)
ORDINAL = {1: 'first', 2: 'second', 3: 'third', 4: 'fourth', 5: 'fifth', 6: 'sixth', 7: 'seventh',
           8: 'eighth', 9: 'ninth', 10: 'tenth', 11: 'eleventh', 12: 'twelfth', 13: 'thirteenth',
           14: 'fourteenth', 15: 'fifteenth', 16: 'sixteenth', 17: 'seventeenth', 18: 'eighteenth',
           19: 'nineteenth', 20: 'twentieth', 21: 'twenty first', 22: 'twenty second',
           23: 'twenty third', 24: 'twenty fourth', 25: 'twenty fifth', 26: 'twenty sixth',
           27: 'twenty seventh', 28: 'twenty eighth', 29: 'twenty ninth', 30: 'thirtieth',
           31: 'thirty first'}

OUTRO_COST = ("That's the week. This episode was voiced start to finish by Deepgram Flux TTS, and "
              "rendering it cost thirty cents, at the pay as you go rate. Looking to start building "
              "with Deepgram? New Console accounts start with a two hundred dollar credit, which "
              "covers more than one thousand episodes like this one.")
OUTRO_PROMO = ("As a bonus through December thirty first of this year, every dollar you spend on Flux "
               "TTS is matched with a dollar in bonus credits, up to five hundred dollars per project. "
               "What you earn never expires, and it works on any Deepgram API in that project. It's "
               "open to Pay As You Go and Growth projects, and the full terms are in the show notes.")
OUTRO_HELP = ("Need more help, or have questions about anything in today's episode? Email support at "
              "deepgram dot com and include the dg request ID header from the failing response, it's "
              "the fastest way to get a fix. For questions and a second pair of eyes, find us on "
              "Discord at D P G R dot A M slash discord, or in GitHub Discussions under the Deepgram "
              "org. If you think something's down, check status dot deepgram dot com first. The full "
              "changelog can be found at developers dot deepgram dot com slash changelog. See you "
              "next Tuesday!")
CANNED_NOTES = {
    'Credits and pricing': [('Deepgram pricing', 'https://deepgram.com/pricing'),
                            ('Sign up for Console', 'https://console.deepgram.com')],
    'Get in touch': [('Discord', 'https://dpgr.am/discord'),
                     ('GitHub Discussions', 'https://github.com/orgs/deepgram/discussions'),
                     ('status.deepgram.com', 'https://status.deepgram.com'),
                     ('support@deepgram.com', 'mailto:support@deepgram.com')],
}
PROMO_NOTE = ('Flux TTS credit match terms',
              'https://deepgram.com/promotions/2026-09/flux-tts-promo-terms-and-conditions')

SYSTEM = """You write scripts for {show}, a weekly podcast that reads the Deepgram developer changelog back to developers. Text-to-speech voices perform every word, so you write for the ear.

The show's full format spec follows, then the cast, then a finished example episode. The spec is authoritative. Follow its editorial rule, segment rules, segment announcements, handoff rules, and pronunciation guidance exactly.

<format_spec>
{spec}
</format_spec>

<cast>
{cast}
</cast>

<example_episode>
{example}
</example_episode>

What you write, and what you do not:
- You write the summary line, the segments between the intro and the outro, and the show notes for those segments. The intro, the outro, the cost figures, the credit and contact lines, and their show notes are added by code. Never write an Intro or Outro segment.
- Use only these segment headings, in this order, and omit any segment with nothing in it: {segments}.
- Every item must come from the changelog entries you are given. Never add products, features, dates, numbers, or claims that are not in them. If an entry is ambiguous, say less rather than guess.
- Stay high level: what changed, why it matters to someone building on Deepgram, and which docs page to read. Two to four sentences per item. No method names, parameter lists, or code. No commentary on how Deepgram shipped or documented something.
- A docs correction is never a breaking change. It goes under Developer experience.
- Many weeks are mostly Nova-3 language updates. Collapse them into one or two quick-hit sentences that name the languages briefly and say whether a code change is needed.
- Handoffs follow the spec: the outgoing voice ends its segment with "{{Voice}} has the {{segment}} updates next." (for Launches: "Drew has this week's launches."), the incoming desk voice opens with "Thanks, {{previous voice}}.", and a desk voice handing back to the anchor ends with "Back to you, Brooke." The voices are fixed by the cast, so a handoff always names the voice that owns the next segment you actually include. The last segment before the outro must end with a handoff to Brooke if a desk voice speaks it. If Brooke speaks the last segment, it needs no handoff.
- The first segment you include opens with "First up," per the spec. The anchor's own segments use the spec's openers.
- Write numbers, versions, and identifiers the way they should be spoken ("version zero point ten", "TTL" in caps, "V2" for version two). Avoid spelling out hard identifiers at all.
- Refer to time relative to the episode's own week ("this week", "last month"), as of the release date. Never mention anything after the week you are covering.
- Plain text only in spoken paragraphs: no markdown, no bullet lists, no em dashes, no URLs. Paragraphs are separated by a blank line; each paragraph becomes one audio clip, so keep paragraphs to one item or one handoff.
- Show notes: under each segment's bold heading, list the public links for the items in that segment as markdown links. Use only URLs that appear in the entries (relative paths like /docs/x become absolute URLs on the changelog's own site) or the entry's own changelog URL.

Return exactly this shape and nothing else:

SUMMARY: <one sentence naming the week's main items, in plain text>

## <Segment heading>

<spoken paragraphs>

## <next segment heading>

<spoken paragraphs>

NOTES:

**<Segment heading>**

- [Label](https://url)
"""

USER = """Write the episode released Tuesday {release} ({release_spoken}).

It covers changelog entries dated {start} through {end}. Here they are, each with its own changelog URL:

{entries}

{launch_block}"""


def spoken_day(d: date) -> str:
    return f'{d:%B} {ORDINAL[d.day]}'


def gather(release: date) -> tuple[date, date, list[dict]]:
    start, end = release - timedelta(days=9), release - timedelta(days=3)
    entries = []
    for day, body, url in load_entries(refresh=False):
        if start <= day <= end:
            for it in items(day, body):
                it['url'] = url
                entries.append(it)
    entries.sort(key=lambda it: it['date'])
    return start, end, entries


def allowed_urls(entries: list[dict]) -> set[str]:
    urls = {it['url'] for it in entries}
    for it in entries:
        for m in re.finditer(r'\]\((\S+?)\)', it['body']):
            u = m.group(1)
            # Relative links resolve against the entry's own page, so any changelog site works.
            urls.add(urljoin(it['url'], u))
    return {u.split('#')[0].rstrip('/') for u in urls}


def validate(raw: str, entries: list[dict]) -> list[str]:
    problems = []
    if not re.search(r'^SUMMARY:\s*\S', raw, re.M):
        problems.append('missing SUMMARY line')
    if 'NOTES:' not in raw:
        problems.append('missing NOTES: section')
    body = raw.split('NOTES:', 1)[0]
    heads = re.findall(r'^## (.+)$', body, re.M)
    if not heads:
        problems.append('no segments')
    bad = [h for h in heads if h.strip() not in SEGMENTS]
    if bad:
        problems.append(f'unknown segment headings: {bad}')
    order = [SEGMENTS.index(h.strip()) for h in heads if h.strip() in SEGMENTS]
    if order != sorted(order) or len(set(order)) != len(order):
        problems.append(f'segments out of order or repeated: {heads}')
    if '—' in raw or ' -- ' in raw:
        problems.append('contains an em dash')
    if re.search(r'https?://', body.split('## ', 1)[-1]):
        problems.append('a URL appears in spoken text')
    ok = allowed_urls(entries)
    for u in re.findall(r'\]\((\S+?)\)', raw.split('NOTES:', 1)[-1]):
        if u.split('#')[0].rstrip('/') not in ok:
            problems.append(f'link not found in the entries: {u}')
    return problems


def ask(client: anthropic.Anthropic, system: str, user: str) -> str:
    for attempt in range(4):
        try:
            with client.beta.messages.stream(
                model=MODEL,
                max_tokens=32000,
                thinking={'type': 'adaptive'},
                output_config={'effort': 'high'},
                betas=['server-side-fallback-2026-07-01'],
                extra_body={'fallbacks': 'default'},
                system=system,
                messages=[{'role': 'user', 'content': user}],
            ) as stream:
                msg = stream.get_final_message()
            u = msg.usage
            inp, cw, cr = u.input_tokens or 0, getattr(u, 'cache_creation_input_tokens', 0) or 0, \
                getattr(u, 'cache_read_input_tokens', 0) or 0
            pin, pout = PRICE_PER_MTOK.get(msg.model, PRICE_PER_MTOK[MODEL])
            USAGE.append({'model': msg.model, 'input_tokens': inp, 'output_tokens': u.output_tokens or 0,
                          'cache_write_tokens': cw, 'cache_read_tokens': cr,
                          'usd': round((inp * pin + cw * pin * 1.25 + cr * pin * 0.1
                                        + (u.output_tokens or 0) * pout) / 1e6, 5)})
            if msg.stop_reason == 'refusal':
                raise RuntimeError(f'writer refused: {msg.stop_details}')
            if msg.stop_reason == 'max_tokens':
                raise RuntimeError('writer hit max_tokens')
            return ''.join(b.text for b in msg.content if b.type == 'text').strip()
        except (anthropic.RateLimitError, anthropic.APIConnectionError, anthropic.InternalServerError) as e:
            wait = 20 * (attempt + 1)
            print(f'  writer retry in {wait}s: {type(e).__name__}', flush=True)
            time.sleep(wait)
    raise RuntimeError('writer failed after retries')


def assemble(raw: str, release: date, start: date, end: date, entries: list[dict], cast: dict) -> str:
    summary = re.search(r'^SUMMARY:\s*(.+)$', raw, re.M).group(1).strip()
    body, notes = raw.split('NOTES:', 1)
    segs = body[body.index('## '):].strip()
    heads = [h.strip() for h in re.findall(r'^## (.+)$', segs, re.M)]
    last = heads[-1]
    first = cast['segments'].get(heads[0])
    # The intro is canned, so when a desk voice opens the show the anchor still hands off to it.
    intro_handoff = ''
    if first:
        what = "this week's launches" if heads[0] == 'Launches' else f'the {SPOKEN_SEGMENT[heads[0]]} updates'
        intro_handoff = f" {first['name']} kicks us off with {what}."
    last_voice = cast['segments'].get(last, cast['anchor'])['name']
    promo = PROMO_START <= release <= PROMO_END
    thanks = '' if last_voice == cast['anchor']['name'] else f'Thanks, {last_voice}. '
    outro = [thanks + OUTRO_COST] + ([OUTRO_PROMO] if promo else []) + [OUTRO_HELP]
    canned = dict(CANNED_NOTES)
    if promo:
        canned['Credits and pricing'] = canned['Credits and pricing'][:1] + [PROMO_NOTE] + canned['Credits and pricing'][1:]
    canned_md = '\n\n'.join(f'**{k}**\n\n' + '\n'.join(f'- [{a}]({b})' for a, b in v) for k, v in canned.items())
    source = '\n'.join(f"- {it['date']}: {it['title']} ({it['url']})" for it in entries)
    return f"""# {SHOW['name']}, week of {start.isoformat()} to {end.isoformat()}

**Summary:** {summary}

Written by `scripts/write_episode.py` ({MODEL}). Releases Tuesday {release.isoformat()}. Everything
under a segment heading is spoken. Show notes are at the bottom.

---

## Intro

Hello, this is {cast['anchor']['name']} with {SHOW['name']}. Changelogs from the week of {spoken_day(start)} to {spoken_day(end)}. Links to every docs page mentioned are in the show notes.{intro_handoff}

{segs}

## Outro

{chr(10).join(p + chr(10) for p in outro).strip()}

---

## Show notes

{notes.strip()}

{canned_md}

---

## Writer's notes (not spoken)

Source entries:

{source}
"""


def build_prompts(release: date, start: date, end: date, entries: list[dict], cast: dict) -> tuple[str, str]:
    """The exact system and user prompts for one episode. Shared with estimate_writer_cost.py."""
    system = SYSTEM.format(
        show=SHOW['name'],
        spec=(ROOT / 'docs' / 'show-format.md').read_text(),
        cast=json.dumps(cast, indent=2),
        example=(ROOT / 'docs' / 'example-episode.md').read_text().split("## Writer's notes")[0],
        segments=', '.join(SEGMENTS),
    )
    entry_text = '\n\n'.join(f"<entry date=\"{it['date']}\" url=\"{it['url']}\">\n## {it['title']}\n{it['body'].strip()}\n</entry>"
                             for it in entries)
    launch_block = ('Treat an entry as a launch only if it introduces a new model, product, or API, or announces '
                    'general availability of one. Regional endpoints and self-hosted releases are quick hits.')
    user = USER.format(release=release.isoformat(), release_spoken=spoken_day(release),
                       start=start.isoformat(), end=end.isoformat(), entries=entry_text,
                       launch_block=launch_block)
    return system, user


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('release', help='Tuesday release date, YYYY-MM-DD')
    ap.add_argument('--force', action='store_true', help='overwrite an existing script.md')
    args = ap.parse_args()
    release = date.fromisoformat(args.release)
    if release.weekday() != 1:
        sys.exit(f'{release} is not a Tuesday')
    out = EPISODES / release.isoformat() / 'script.md'
    if out.exists() and not args.force:
        sys.exit(f'{out} exists; pass --force to rewrite it')
    start, end, entries = gather(release)
    if not entries:
        sys.exit(f'no changelog entries between {start} and {end}')

    cast = json.loads((ROOT / 'docs' / 'cast.json').read_text())
    system, user = build_prompts(release, start, end, entries, cast)

    client = anthropic.Anthropic()
    raw = ask(client, system, user)
    problems = validate(raw, entries)
    if problems:
        print(f'  first draft had problems, retrying: {problems}', flush=True)
        raw = ask(client, system, user + '\n\nA previous draft was rejected for these problems, fix all of them: '
                  + '; '.join(problems))
        problems = validate(raw, entries)
        if problems:
            raise SystemExit(f'writer output still invalid: {problems}')
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(assemble(raw, release, start, end, entries, cast))
    # Every call counts, including a rejected first draft, because every call was billed.
    (out.parent / 'writer.json').write_text(json.dumps({
        'model': MODEL, 'calls': USAGE, 'usd': round(sum(c['usd'] for c in USAGE), 5),
        'pricing_url': 'https://www.anthropic.com/pricing', 'pricing_as_of': '2026-09-25',
    }, indent=2) + '\n')
    print(f"wrote {out} from {len(entries)} entries, writer ${sum(c['usd'] for c in USAGE):.4f}")


if __name__ == '__main__':
    main()
