"""Write an episode's script.md from the changelog, with Claude.

Usage: python3 scripts/write_episode.py 2026-09-22 [--force]

The argument is the release date. The episode covers the window that release publishes: by
default the Sunday to Saturday before a Tuesday, or whatever show.json's cadence says. Claude writes only the summary, the segments in
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
from cadence import CADENCE  # noqa: E402
from segments import SEGMENTS as SEGMENT_NAMES, SPOKEN  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
EPISODES = Path(os.environ.get('EPISODES_DIR', ROOT / 'episodes'))
MODEL = 'claude-opus-5'
SEGMENTS = list(SEGMENT_NAMES)
# Claude pricing per million tokens (input, output), for the writer cost column. Thinking tokens
# bill as output. A server-side fallback can answer on another model, so price by the model that ran.
PRICE_PER_MTOK = {'claude-opus-5': (5.0, 25.0), 'claude-opus-4-8': (5.0, 25.0),
                  'claude-sonnet-5': (2.0, 10.0)}
USAGE: list[dict] = []
SPOKEN_SEGMENT = SPOKEN
ORDINAL = {1: 'first', 2: 'second', 3: 'third', 4: 'fourth', 5: 'fifth', 6: 'sixth', 7: 'seventh',
           8: 'eighth', 9: 'ninth', 10: 'tenth', 11: 'eleventh', 12: 'twelfth', 13: 'thirteenth',
           14: 'fourteenth', 15: 'fifteenth', 16: 'sixteenth', 17: 'seventeenth', 18: 'eighteenth',
           19: 'nineteenth', 20: 'twentieth', 21: 'twenty first', 22: 'twenty second',
           23: 'twenty third', 24: 'twenty fourth', 25: 'twenty fifth', 26: 'twenty sixth',
           27: 'twenty seventh', 28: 'twenty eighth', 29: 'twenty ninth', 30: 'thirtieth',
           31: 'thirty first'}

# How the outro wraps up the window it covered, per cadence.
WRAP = {'weekly': "That's the week.", 'biweekly': "That's two weeks of changes.", 'monthly': "That's the month."}
LAUNCHES = {'weekly': "this week's launches", 'biweekly': 'the launches', 'monthly': "this month's launches"}
# The spoken outro and its show notes, from show.json "outro"; Deepgram's own show is the default.
# fill_cost.py rewrites "rendering it cost ..., at the pay as you go rate" and "covers more than ...
# episodes like this one" with the episode's real figures, so those phrases are placeholders.
DEEPGRAM_OUTRO = {
    'cost': ("This episode was voiced start to finish by Deepgram Flux TTS, and rendering it cost thirty "
             "cents, at the pay as you go rate."),
    'pitch': ("Looking to start building with Deepgram? New Console accounts start with a two hundred "
              "dollar credit, which covers more than one thousand episodes like this one."),
    'promo': {
        'start': '2026-09-15', 'end': '2026-12-31',
        'text': ("As a bonus through December thirty first of this year, every dollar you spend on Flux "
                 "TTS is matched with a dollar in bonus credits, up to five hundred dollars per project. "
                 "What you earn never expires, and it works on any Deepgram API in that project. It's "
                 "open to Pay As You Go and Growth projects, and the full terms are in the show notes."),
        'note': ['Flux TTS credit match terms',
                 'https://deepgram.com/promotions/2026-09/flux-tts-promo-terms-and-conditions'],
        'note_section': 'Credits and pricing',
    },
    'help': ("Need more help, or have questions about anything in today's episode? Email support at "
             "deepgram dot com and include the dg request ID header from the failing response, it's "
             "the fastest way to get a fix. For questions and a second pair of eyes, find us on "
             "Discord at D P G R dot A M slash discord, or in GitHub Discussions under the Deepgram "
             "org. If you think something's down, check status dot deepgram dot com first. The full "
             "changelog can be found at developers dot deepgram dot com slash changelog."),
    'notes': {
        'Credits and pricing': [['Deepgram pricing', 'https://deepgram.com/pricing'],
                                ['Sign up for Console', 'https://console.deepgram.com']],
        'Get in touch': [['Discord', 'https://dpgr.am/discord'],
                         ['GitHub Discussions', 'https://github.com/orgs/deepgram/discussions'],
                         ['status.deepgram.com', 'https://status.deepgram.com'],
                         ['support@deepgram.com', 'mailto:support@deepgram.com']],
    },
}
# What the writer is told about the show's source and listener, from show.json "writer".
DEEPGRAM_WRITER = {
    'source': 'the Deepgram developer changelog',
    'listeners': 'developers',
    'audience': 'someone building on Deepgram',
    'product': 'Deepgram',
    'rules': ['A docs correction is never a breaking change. It goes under Developer experience.',
              'Many weeks are mostly Nova-3 language updates. Collapse them into one or two quick-hit '
              'sentences that name the languages briefly and say whether a code change is needed.'],
    'launch_rule': ('Treat an entry as a launch only if it introduces a new model, product, or API, or announces '
                    'general availability of one. Regional endpoints and self-hosted releases are quick hits.'),
}


def _section(key: str, default: dict) -> dict:
    given = SHOW.get(key)
    return {**default, **{k: v for k, v in given.items() if not k.startswith('_')}} if isinstance(given, dict) else dict(default)


OUTRO = _section('outro', DEEPGRAM_OUTRO)
WRITER = _section('writer', DEEPGRAM_WRITER)
OUTRO_COST = ' '.join(x for x in (WRAP[CADENCE.name], OUTRO.get('cost'), OUTRO.get('pitch')) if x)
PROMO = OUTRO.get('promo') or None
OUTRO_PROMO = PROMO['text'] if PROMO else ''
PROMO_START = date.fromisoformat(PROMO['start']) if PROMO else date.max
PROMO_END = date.fromisoformat(PROMO['end']) if PROMO else date.min
OUTRO_HELP = ' '.join(x for x in (OUTRO.get('help'), f'See you {CADENCE.next_phrase()}!') if x)
CANNED_NOTES = {k: [tuple(link) for link in v] for k, v in (OUTRO.get('notes') or {}).items()}
PROMO_NOTE = tuple(PROMO['note']) if PROMO and PROMO.get('note') else None

SYSTEM = """You write scripts for {show}, a {cadence} podcast that reads {source} back to {listeners}. Text-to-speech voices perform every word, so you write for the ear.

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
- Stay high level: what changed, why it matters to {audience}, and which docs page to read. Two to four sentences per item. No method names, parameter lists, or code. No commentary on how {product} shipped or documented something.
{rules}- Handoffs follow the spec: the outgoing voice ends its segment with "{{Voice}} has the {{segment}} updates next." (for Launches: "{launches_voice} has {launches_phrase}."), the incoming desk voice opens with "Thanks, {{previous voice}}.", and a desk voice handing back to the anchor ends with "Back to you, {anchor}." The voices are fixed by the cast, so a handoff always names the voice that owns the next segment you actually include. The last segment before the outro must end with a handoff to {anchor} if a desk voice speaks it. If {anchor} speaks the last segment, it needs no handoff.
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

USER = """Write the episode released {release_day} {release} ({release_spoken}).

It covers changelog entries dated {start} through {end}. Here they are, each with its own changelog URL:

{entries}

{launch_block}"""


def spoken_day(d: date) -> str:
    return f'{d:%B} {ORDINAL[d.day]}'


PERIOD_OF = {'weekly': 'week of', 'biweekly': 'weeks of', 'monthly': 'month of'}


NUMBER_WORDS = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten',
                'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen', 'sixteen', 'seventeen', 'eighteen',
                'nineteen']
TENS_WORDS = ['', '', 'twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy', 'eighty', 'ninety']


def spoken_year(year: int) -> str:
    """2026 is 'twenty twenty six', 2005 is 'two thousand five', the way a host says it."""
    def under_100(n: int) -> str:
        return NUMBER_WORDS[n] if n < 20 else TENS_WORDS[n // 10] + ('' if n % 10 == 0 else ' ' + NUMBER_WORDS[n % 10])
    century, rest = divmod(year, 100)
    if 2000 <= year < 2010:
        return 'two thousand' + (f' {NUMBER_WORDS[rest]}' if rest else '')
    return f'{under_100(century)} ' + (under_100(rest) if rest >= 10 else f'oh {NUMBER_WORDS[rest]}' if rest else 'hundred')


def spoken_window(start: date, end: date) -> str:
    """'the week of September thirteenth to September nineteenth, twenty twenty six', or
    'September twenty twenty six' for a month. Always with the year, so an episode heard out of
    order, or years later in the back catalog, still says when it was."""
    if CADENCE.name == 'monthly':
        return f'{start:%B} {spoken_year(start.year)}'
    lead = 'the week of' if CADENCE.name == 'weekly' else 'the two weeks of'
    if start.year != end.year:
        return (f'{lead} {spoken_day(start)}, {spoken_year(start.year)}, to '
                f'{spoken_day(end)}, {spoken_year(end.year)}')
    return f'{lead} {spoken_day(start)} to {spoken_day(end)}, {spoken_year(end.year)}'


def gather(release: date) -> tuple[date, date, list[dict]]:
    window = CADENCE.window_for_release(release)
    if window is None:
        sys.exit(f'{release} is not a release date for a {CADENCE.adjective} show released on {CADENCE.day_name}s')
    start, end = window
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
        what = LAUNCHES[CADENCE.name] if heads[0] == 'Launches' else f'the {SPOKEN_SEGMENT.get(heads[0], heads[0].lower())} updates'
        intro_handoff = f" {first['name']} kicks us off with {what}."
    last_voice = cast['segments'].get(last, cast['anchor'])['name']
    promo = bool(PROMO) and PROMO_START <= release <= PROMO_END
    thanks = '' if last_voice == cast['anchor']['name'] else f'Thanks, {last_voice}. '
    outro = [thanks + OUTRO_COST] + ([OUTRO_PROMO] if promo else []) + [OUTRO_HELP]
    canned = dict(CANNED_NOTES)
    if promo:
        if PROMO_NOTE:
            sec = PROMO.get('note_section') or 'Credits and pricing'
            links = canned.get(sec, [])
            canned[sec] = links[:1] + [PROMO_NOTE] + links[1:]
    canned_md = '\n\n'.join(f'**{k}**\n\n' + '\n'.join(f'- [{a}]({b})' for a, b in v) for k, v in canned.items())
    source = '\n'.join(f"- {it['date']}: {it['title']} ({it['url']})" for it in entries)
    return f"""# {SHOW['name']}, {PERIOD_OF[CADENCE.name]} {start.isoformat()} to {end.isoformat()}

**Summary:** {summary}

Written by `scripts/write_episode.py` ({MODEL}). Releases {CADENCE.day_name} {release.isoformat()}. Everything
under a segment heading is spoken. Show notes are at the bottom.

---

## Intro

Hello, this is {cast['anchor']['name']} with {SHOW['name']}. Changelogs from {spoken_window(start, end)}. Links to every docs page mentioned are in the show notes.{intro_handoff}

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
    """The exact system and user prompts for one episode."""
    system = SYSTEM.format(
        show=SHOW['name'],
        cadence=CADENCE.adjective,
        source=WRITER['source'], listeners=WRITER['listeners'], audience=WRITER['audience'], product=WRITER['product'],
        rules=''.join(f'- {r}\n' for r in WRITER.get('rules') or []),
        anchor=cast['anchor']['name'],
        launches_voice=cast['segments'].get('Launches', cast['anchor'])['name'],
        launches_phrase=LAUNCHES[CADENCE.name],
        spec=(ROOT / 'docs' / 'show-format.md').read_text(),
        cast=json.dumps(cast, indent=2),
        example=(ROOT / 'docs' / 'example-episode.md').read_text().split("## Writer's notes")[0],
        segments=', '.join(SEGMENTS),
    )
    entry_text = '\n\n'.join(f"<entry date=\"{it['date']}\" url=\"{it['url']}\">\n## {it['title']}\n{it['body'].strip()}\n</entry>"
                             for it in entries)
    launch_block = WRITER['launch_rule']
    user = USER.format(release=release.isoformat(), release_spoken=spoken_day(release), release_day=CADENCE.day_name,
                       start=start.isoformat(), end=end.isoformat(), entries=entry_text,
                       launch_block=launch_block)
    return system, user


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('release', help='release date, YYYY-MM-DD')
    ap.add_argument('--force', action='store_true', help='overwrite an existing script.md')
    args = ap.parse_args()
    release = date.fromisoformat(args.release)
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
