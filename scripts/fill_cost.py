"""Rewrite the outro's spoken cost and credit figures so they match the script's own length.

Usage: python3 scripts/fill_cost.py episodes/2026-09-22

The cost sentence is part of the spoken text, so changing it changes the cost. This iterates
until the figures are stable. The episode count is rounded DOWN to a multiple of 25 and said as
"more than N", so the claim is always true.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_episode import RATE_USD_PER_1K, parse_segments, spoken_form  # noqa: E402

ONES = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten',
        'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen', 'sixteen', 'seventeen', 'eighteen',
        'nineteen']
TENS = ['', '', 'twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy', 'eighty', 'ninety']
COST_RE = re.compile(r'(rendering it\s+cost\s+)(.+?)(,\s+at the pay as you go rate)', re.S)
COUNT_RE = re.compile(r'(covers more than\s+)(.+?)(\s+episodes like this one)', re.S)


def under_100(n: int) -> str:
    return ONES[n] if n < 20 else TENS[n // 10] + ('' if n % 10 == 0 else ' ' + ONES[n % 10])


def spoken_count(n: int) -> str:
    # Said the way a person would: 1,175 is "eleven hundred seventy five", 2,000 is "two thousand".
    if n % 1000 == 0 and n >= 1000:
        return under_100(n // 1000) + ' thousand'
    hundreds, rest = divmod(n, 100)
    words = under_100(hundreds) + ' hundred' if hundreds else ''
    return (words + (' ' + under_100(rest) if rest else '')).strip()


def spoken_cost(usd: float) -> str:
    cents = round(usd * 100)
    if cents >= 100:
        dollars, c = divmod(cents, 100)
        return f"{under_100(dollars)} dollar{'s' if dollars > 1 else ''}" + (f' and {under_100(c)} cents' if c else '')
    return f'{under_100(cents)} cents'


def main() -> None:
    path = Path(sys.argv[1]) / 'script.md'
    text = path.read_text()
    if not COST_RE.search(text) or not COUNT_RE.search(text):
        sys.exit('outro cost or credit sentence not found')
    for _ in range(8):
        chars = sum(len(spoken_form(p)) for _, ps in parse_segments(text) for p in ps)
        usd = chars / 1000 * RATE_USD_PER_1K
        count = int((200 / usd) // 25 * 25)
        new = COST_RE.sub(lambda m: m.group(1) + spoken_cost(usd) + m.group(3), text)
        new = COUNT_RE.sub(lambda m: m.group(1) + spoken_count(count) + m.group(3), new)
        if new == text:
            break
        text = new
    path.write_text(text)
    print(f'{chars} chars, ${usd:.4f}, {int(200 / usd)} episodes per $200, said as "more than {spoken_count(count)}"')


if __name__ == '__main__':
    main()
