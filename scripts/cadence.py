"""How often the show comes out and which day: the window each episode covers, and its release date.

Usage: from cadence import CADENCE; CADENCE.window_of(day), CADENCE.release_for(end)

show.json sets "cadence" (weekly, biweekly, or monthly) and "release_day" (a weekday name). An
episode's id is its release date, so everything that maps a date to an episode goes through here.

- weekly: Sunday to Saturday.
- biweekly: two Sundays to Saturdays, on a fixed two-week grid (counted from Sunday 2017-01-01),
  so a window never shifts when the plan is rebuilt.
- monthly: the calendar month.

The release is the first release_day at least BUFFER_DAYS after the window ends. With the defaults
(weekly, Tuesday) that is the Tuesday three days after the Saturday, which leaves Monday as a buffer
for late entries, and every id the show already has stays the same.

`recommend()` reads a feed's recent history and picks the shortest cadence with enough material in
a typical episode. `python3 scripts/cadence.py` prints that recommendation for the current feed.
"""

from __future__ import annotations

import calendar
import re
import statistics
from dataclasses import dataclass
from datetime import date, timedelta

from show import SHOW

DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
CADENCES = ('weekly', 'biweekly', 'monthly')
BUFFER_DAYS = 2
GRID = date(2017, 1, 1)  # a Sunday; biweekly windows start an even number of weeks after it
# What a typical episode needs to say something: about two minutes of material. Measured on
# 2026-10-01, Deepgram's changelog runs about 3,300 characters a week, Resend's 3,700, Linear's
# 1,500, and Tailscale's 1,000.
MIN_CHARS = 2500
MAX_EMPTY = 0.2      # a cadence where more than a fifth of episodes would be skipped is too fast
LOOKBACK_WEEKS = 26
MIN_HISTORY_WEEKS = 8


@dataclass(frozen=True)
class Cadence:
    name: str = 'weekly'
    release_day: str = 'tuesday'

    @property
    def weekday(self) -> int:
        return DAYS.index(self.release_day)

    # ---- windows and releases ------------------------------------------------------------------

    def window_of(self, day: date) -> tuple[date, date]:
        """The window that contains this day."""
        if self.name == 'monthly':
            last = calendar.monthrange(day.year, day.month)[1]
            return day.replace(day=1), day.replace(day=last)
        sunday = day - timedelta(days=(day.weekday() + 1) % 7)
        if self.name == 'weekly':
            return sunday, sunday + timedelta(days=6)
        start = sunday - timedelta(weeks=((sunday - GRID).days // 7) % 2)
        return start, start + timedelta(days=13)

    def release_for(self, end: date) -> date:
        earliest = end + timedelta(days=BUFFER_DAYS)
        return earliest + timedelta(days=(self.weekday - earliest.weekday()) % 7)

    def window_for_release(self, release: date) -> tuple[date, date] | None:
        """The window this release date publishes, or None if it isn't a release date."""
        for back in range(1, 45):
            start, end = self.window_of(release - timedelta(days=back))
            if self.release_for(end) == release:
                return start, end
        return None

    def latest_end(self, today: date | None = None) -> date:
        """The end of the most recent window that is over (the window holding today isn't)."""
        today = today or date.today()
        start, _ = self.window_of(today)
        return start - timedelta(days=1)

    def releases_through(self, today: date, count: int) -> list[date]:
        """The `count` most recent release dates on or before today, newest first."""
        out, end = [], self.latest_end(today)
        while len(out) < count:
            release = self.release_for(end)
            if release <= today:
                out.append(release)
            end = self.window_of(end)[0] - timedelta(days=1)
        return out

    # ---- words ---------------------------------------------------------------------------------

    @property
    def per_year(self) -> int:
        return {'weekly': 52, 'biweekly': 26, 'monthly': 12}[self.name]

    @property
    def sweep(self) -> int:
        """Past releases each scheduled run re-checks for late entries: about four weeks' worth."""
        return {'weekly': 4, 'biweekly': 2, 'monthly': 1}[self.name]

    @property
    def period(self) -> str:
        return {'weekly': 'week', 'biweekly': 'two weeks', 'monthly': 'month'}[self.name]

    @property
    def adjective(self) -> str:
        return {'weekly': 'weekly', 'biweekly': 'biweekly', 'monthly': 'monthly'}[self.name]

    @property
    def day_name(self) -> str:
        return self.release_day.capitalize()

    def next_phrase(self) -> str:
        """How the outro says goodbye: 'next Tuesday', 'in two weeks', 'next month'."""
        return {'weekly': f'next {self.day_name}', 'biweekly': 'in two weeks',
                'monthly': 'next month'}[self.name]

    def title(self, start: date, end: date) -> str:
        if self.name == 'monthly':
            return f'{start:%B} {start.year}'
        lead = 'Week of' if self.name == 'weekly' else 'Weeks of'
        return f'{lead} {human_range(start, end)}'

    def describe(self) -> str:
        span = {'weekly': 'Sunday to Saturday week', 'biweekly': 'two-week stretch, Sunday to Saturday',
                'monthly': 'calendar month'}[self.name]
        return f'one episode for every {span} with changelog entries, released the {self.day_name} after'


def human_range(a: date, b: date) -> str:
    if a.year != b.year:
        return f'{a:%B} {a.day}, {a.year} to {b:%B} {b.day}, {b.year}'
    if a.month == b.month:
        return f'{a:%B} {a.day} to {b.day}, {b.year}'
    return f'{a:%B} {a.day} to {b:%B} {b.day}, {b.year}'


def load(show: dict = SHOW) -> Cadence:
    name = str(show.get('cadence', 'weekly')).lower()
    day = str(show.get('release_day', 'tuesday')).lower()
    if name not in CADENCES:
        raise SystemExit(f'show.json: "cadence" must be one of {", ".join(CADENCES)}, not {name!r}')
    if day not in DAYS:
        raise SystemExit(f'show.json: "release_day" must be a weekday name like "tuesday", not {day!r}')
    return Cadence(name, day)


CADENCE = load()


# ---- the recommendation --------------------------------------------------------------------------

def recommend(entries: list[tuple[date, str, str]], release_day: str = CADENCE.release_day,
              today: date | None = None) -> dict:
    """Pick the shortest cadence whose typical episode has at least MIN_CHARS of changelog and
    that skips no more than MAX_EMPTY of its episodes, over the last LOOKBACK_WEEKS."""
    today = today or date.today()
    days = sorted(d for d, _, _ in entries)
    if not days:
        return {'cadence': 'weekly', 'reason': 'The feed has no dated entries yet.', 'periods': {}}
    history_weeks = (today - days[0]).days // 7
    weekly = Cadence('weekly', release_day)
    horizon_end = weekly.latest_end(today)
    horizon_start = horizon_end - timedelta(weeks=LOOKBACK_WEEKS) + timedelta(days=1)
    stats = {}
    for name in CADENCES:
        c = Cadence(name, release_day)
        chars: dict[date, int] = {}
        items: dict[date, int] = {}
        last = c.latest_end(today)
        d = c.window_of(last)[0]
        while d >= horizon_start:  # every finished window in the lookback, empty ones included
            chars[d], items[d] = 0, 0
            d = c.window_of(d - timedelta(days=1))[0]
        for day, body, _ in entries:
            start = c.window_of(day)[0]
            if start in chars and day <= last:
                chars[start] += len(body)
                items[start] += len(re.findall(r'^## ', body, re.M)) or 1
        values = list(chars.values())
        stats[name] = {
            'episodes': len(values),
            'empty': sum(v == 0 for v in values),
            'median_chars': int(statistics.median(values)) if values else 0,
            'median_entries': statistics.median(items.values()) if items else 0,
        }
    if history_weeks < MIN_HISTORY_WEEKS:
        return {'cadence': 'weekly', 'periods': stats, 'history_weeks': history_weeks,
                'reason': f'The feed only goes back {history_weeks} weeks, too little to judge, so '
                          'weekly is the default. Run this again once it has a couple of months.'}
    for name in CADENCES:
        s = stats[name]
        if s['median_chars'] >= MIN_CHARS and s['empty'] <= MAX_EMPTY * s['episodes']:
            pick = name
            break
    else:
        pick = 'monthly'
    s, per = stats[pick], Cadence(pick, release_day).period
    reason = (f'Over the last {LOOKBACK_WEEKS} weeks, a typical {per} has about {s["median_chars"]:,} '
              f'characters of changelog ({s["median_entries"]:g} entries), and {s["empty"]} of '
              f'{s["episodes"]} would have been empty.')
    if pick != 'weekly':
        w = stats['weekly']
        reason += (f' Weekly would average {w["median_chars"]:,} characters, which is thin'
                   if w['median_chars'] < MIN_CHARS else
                   f' Weekly would skip {w["empty"]} of {w["episodes"]} weeks')
        reason += '.'
    if stats['weekly']['median_chars'] > 20000:
        reason += ' Even weekly, this is a busy changelog, so expect long episodes.'
    return {'cadence': pick, 'reason': reason, 'periods': stats, 'history_weeks': history_weeks}


def main() -> None:
    import json
    import changelog_source
    rec = recommend(changelog_source.load_entries())
    print(json.dumps(rec, indent=2))


if __name__ == '__main__':
    main()
