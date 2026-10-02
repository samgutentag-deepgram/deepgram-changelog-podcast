"""The show's segments: their names, short labels, spoken names, and the keyword rules that sort a
changelog entry into one. Read from show.json's "segments"; Deepgram's own are the default.

Usage: from segments import SEGMENTS, SHORT, SPOKEN, segment_for, rollup_segments

Every show has the same three segments first, in this order: "Breaking changes and action
required", "Launches", and "Quick hits". After them come the product segments, one per area of the
product, each with a keyword pattern (a Python regex, case-insensitive). An entry lands in exactly
one segment, the way the show airs it:

1. Breaking changes, if any sentence matches the breaking-change pattern (and not the "no breaking
   changes" one). Corrections never count.
2. Launches, if the heading matches `launch_keywords` and not `launch_exclude`.
3. Quick hits, if the heading matches `quick_hits_keywords` and not `quick_hits_exclude`.
4. The first product segment whose keywords match the heading, then the first whose keywords match
   the body.
5. Otherwise, Quick hits.

Roll-up entries (heading matches `rollup_keywords`, like an SDK release covering several products)
also tick every product segment marked "rollup" whose keywords appear twice or more in the body.
"""

from __future__ import annotations

import re

from show import SHOW

FIXED = [('Breaking changes and action required', 'Breaking', 'breaking changes'),
         ('Launches', 'Launches', 'launches'),
         ('Quick hits', 'Quick hits', 'quick hits')]

# The Deepgram changelog's own rules, as tuned on its 141 episodes. A fork replaces them in show.json.
DEEPGRAM = {
    'launch_keywords': r'\bintroducing\b|generally available|general availability|\blaunch',
    'launch_exclude': r'self-hosted|endpoint',
    'quick_hits_keywords': (r'self-hosted|nova-\d (?:model )?(?:update|improve|adds)|improved models|new models|'
                            r'language|numerals|profanity|endpoint now generally available|concurrency|pricing|'
                            r'now available$|\bmodels? support\b|llm models?|model updates'),
    'quick_hits_exclude': r'\bsdk\b|\bcli\b',
    'rollup_keywords': r'sdk releases|sdk support|\bcli\b|@deepgram/react',
    'products': [
        {'name': 'Voice Agent', 'short': 'Voice Agent', 'spoken': 'Voice Agent', 'rollup': True,
         'keywords': (r'voice agent|\bagent\b|\bllm\b|think|updatelisten|update ?listen|injectagent|'
                      r'function call|claude|gemini|openai|nvidia|cartesia')},
        {'name': 'Speech-to-Text', 'short': 'STT', 'spoken': 'speech-to-text', 'rollup': True,
         'keywords': (r'\bnova\b|nova-\d|\bflux\b(?! tts)|diariz|redact|entit|transcri|speech-to-text|keyterm|'
                      r'language detection|topic|summar|sentiment|intelligence|smart format|\bstt\b')},
        {'name': 'Text-to-Speech', 'short': 'TTS', 'spoken': 'text-to-speech', 'rollup': True,
         'keywords': r'\baura\b|aura-\d|\btts\b|text-to-speech|\bspeak\b|voice controls|expressivity'},
        {'name': 'Developer experience', 'short': 'DX', 'spoken': 'developer experience', 'rollup': False,
         'keywords': (r'\bsdk\b|\bcli\b|react|docs?\b|documentation|correction|saga|\bmcp\b|playground|console|'
                      r'api key|token|developer')},
    ],
}

BREAKING = re.compile(
    r'breaking change|action required|not backwards?[- ]compatible|deprecat|will be removed|'
    r'has been removed|have been removed|\bremoves\b|\bremoved from\b|return(?:s)? (?:an? )?(?:HTTP )?4\d\d|'
    r'sessions? (?:now )?close automatically|must be updated', re.I)
NOT_BREAKING = re.compile(r'no breaking changes?|additive change|backward[- ]compatible\b(?! with previous)|'
                          r'no existing fields are removed|remain as deprecated aliases', re.I)


def _rx(pattern: str | None) -> re.Pattern | None:
    if not pattern:
        return None
    try:
        return re.compile(pattern, re.I)
    except re.error as e:
        raise SystemExit(f'show.json segments: bad keyword pattern {pattern!r}: {e}')


def load(show: dict = SHOW) -> dict:
    cfg = {**DEEPGRAM, **{k: v for k, v in (show.get('segments') or {}).items() if not k.startswith('_')}}
    names = [f[0] for f in FIXED]
    for p in cfg['products']:
        if not p.get('name') or not p.get('keywords'):
            raise SystemExit('show.json segments: every product segment needs a "name" and "keywords"')
        if p['name'] in names:
            raise SystemExit(f'show.json segments: {p["name"]!r} is listed twice')
        names.append(p['name'])
    return cfg


CONFIG = load()
PRODUCTS = [{**p, 'rx': _rx(p['keywords'])} for p in CONFIG['products']]
SEGMENTS = [f[0] for f in FIXED] + [p['name'] for p in PRODUCTS]
SHORT = {**{f[0]: f[1] for f in FIXED}, **{p['name']: p.get('short') or p['name'] for p in PRODUCTS}}
SPOKEN = {**{f[0]: f[2] for f in FIXED}, **{p['name']: p.get('spoken') or p['name'].lower() for p in PRODUCTS}}
LAUNCH, LAUNCH_EXCLUDE = _rx(CONFIG['launch_keywords']), _rx(CONFIG.get('launch_exclude'))
QUICK, QUICK_EXCLUDE = _rx(CONFIG['quick_hits_keywords']), _rx(CONFIG.get('quick_hits_exclude'))
ROLLUP = _rx(CONFIG.get('rollup_keywords'))


def segment_for(item: dict, launches_by_week: set[str] = frozenset()) -> str:
    head, body = item['title'], item['body']
    text = head + '\n' + body
    is_correction = head.lower().startswith('correction')
    if not is_correction:
        hits = [s for s in re.split(r'(?<=[.!?\n])\s+', text) if BREAKING.search(s) and not NOT_BREAKING.search(s)]
        if hits:
            return SEGMENTS[0]
    if not is_correction and not (LAUNCH_EXCLUDE and LAUNCH_EXCLUDE.search(head)):
        if (LAUNCH and LAUNCH.search(head)) or head in launches_by_week:
            return SEGMENTS[1]
    if QUICK and QUICK.search(head) and not (QUICK_EXCLUDE and QUICK_EXCLUDE.search(head)):
        return SEGMENTS[2]
    for where in (head, body):
        for p in PRODUCTS:
            if p['rx'].search(where):
                return p['name']
    return SEGMENTS[2]


def rollup_segments(item: dict, landed: str) -> list[str]:
    """The extra product segments a roll-up entry ticks, beyond the one it landed in."""
    if not (ROLLUP and ROLLUP.search(item['title'])):
        return []
    return [p['name'] for p in PRODUCTS
            if p.get('rollup') and p['name'] != landed and len(p['rx'].findall(item['body'])) >= 2]
