"""Produce episodes end to end: write, cost, render, readback retakes, art, catalog, feed.

Usage:
  python3 scripts/produce.py 2026-09-15                 one episode, by Tuesday release date
  python3 scripts/produce.py 2026-09-15 2026-09-08 --jobs 3   several, three at a time
  python3 scripts/produce.py --weekly                   the latest release, plus a sweep of the ones before (the cron job)
  python3 scripts/produce.py --weekly --dry-run         what the cron job would produce today, without producing it
  python3 scripts/produce.py --backfill 2026 --jobs 3   every planned week in a year not yet rendered

Each step is the standalone script it names, run as a subprocess, so any step can be rerun by
hand. A result line per episode lands in <episodes>/<id>/produce.json. Rendered paragraph audio
lives in .cache/tts; pass --clean-cache to delete it after the whole batch finishes, which is what
the server does so its disk only ever keeps MP3s.

Needs DEEPGRAM_API_KEY and ANTHROPIC_API_KEY. SITE_URL sets the feed's public origin.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

from show import SHOW
from cadence import CADENCE

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / 'scripts'
EPISODES = Path(os.environ.get('EPISODES_DIR', ROOT / 'episodes'))
SITE_URL = SHOW['site_url']
PY = sys.executable
SWEEP = CADENCE.sweep  # past releases each scheduled run re-checks for entries that arrived late
# The art step needs Pillow, which the rest of the pipeline does not. The container installs it
# into the one interpreter; locally it can point at any Python that has it.
ART_PY = os.environ.get('ART_PYTHON', PY)


def run(*args: str, capture: bool = True, py: str = PY) -> str:
    r = subprocess.run([py, *args], cwd=ROOT, capture_output=capture, text=True)
    if r.returncode != 0:
        # The exception line goes first: the FAILED log line and the Pushover alert keep only the
        # head of this message, and a head of stdout progress lines once hid the actual error.
        tail = (r.stderr or '').strip() or (r.stdout or '').strip()
        cause = tail.splitlines()[-1].strip() if tail else f'exit {r.returncode}'
        raise RuntimeError(f"{Path(args[0]).name} failed: {cause}\n"
                           f"{(r.stdout or '')[-1500:]}\n{(r.stderr or '')[-1500:]}")
    return (r.stdout or '').strip()


def complete(ep: Path) -> bool:
    # Done means the whole pipeline finished, not just that an MP3 exists: the first render writes
    # episode.mp3 before the readback check, so a run that fails there leaves audio but no art
    # and no produce.json. produce.json is written last; art.jpg covers the hand-made episode one.
    return (ep / 'episode.mp3').exists() and ((ep / 'produce.json').exists() or (ep / 'art.jpg').exists())


def produce(release: str, rewrite: bool = False) -> dict:
    t0 = time.time()
    ep = EPISODES / release
    result = {'id': release, 'started': time.strftime('%Y-%m-%dT%H:%M:%S')}
    # Wall-clock seconds per step, so a post can say how long each part takes.
    timings: dict[str, float] = {}

    def timed(step: str, *args: str, **kw) -> str:
        t = time.time()
        try:
            return run(*args, **kw)
        finally:
            timings[step] = round(timings.get(step, 0) + time.time() - t, 1)

    if rewrite or not (ep / 'script.md').exists():
        result['write'] = timed('write', str(SCRIPTS / 'write_episode.py'), release, *(['--force'] if rewrite else []))
    result['cost'] = run(str(SCRIPTS / 'fill_cost.py'), str(ep))
    timed('voice', str(SCRIPTS / 'render_episode.py'), str(ep))
    check = timed('check', str(SCRIPTS / 'readback_check.py'), str(ep), '--retake', '3', '--json', str(ep / 'readback.json'))
    result['readback'] = check.splitlines()[-1] if check else ''
    result['render'] = timed('assemble', str(SCRIPTS / 'render_episode.py'), str(ep)).splitlines()[-1]
    if (SCRIPTS / 'make_art.py').exists():
        try:
            timed('art', str(SCRIPTS / 'make_art.py'), str(ep), py=ART_PY)
        except RuntimeError as e:
            result['art_error'] = str(e)[-300:]
    result['seconds'] = round(time.time() - t0)
    result['timings'] = timings
    (ep / 'produce.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def refresh_site() -> None:
    if (SCRIPTS / 'build_catalog.py').exists():
        run(str(SCRIPTS / 'build_catalog.py'))
    run(str(SCRIPTS / 'build_feed.py'), '--base', SITE_URL)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('release', nargs='*', help='one or more Tuesday release dates')
    ap.add_argument('--weekly', action='store_true')
    ap.add_argument('--backfill', help='year, e.g. 2026')
    ap.add_argument('--jobs', type=int, default=1)
    ap.add_argument('--rewrite', action='store_true')
    ap.add_argument('--clean-cache', action='store_true')
    ap.add_argument('--dry-run', action='store_true', help='list what would be produced, then stop')
    args = ap.parse_args()

    # One clock read for the whole run, so a run that straddles midnight plans and picks the
    # same week.
    today = date.today()
    if args.weekly or args.backfill:
        run(str(SCRIPTS / 'backfill_plan.py'), '--refresh', '--through', CADENCE.latest_end(today).isoformat())
    if args.release:
        targets = list(args.release)
    elif args.weekly:
        # The latest release, plus a sweep of the SWEEP before it (about four weeks). The sweep catches
        # changelog entries that were posted or backdated into a past week after that week's own
        # Tuesday run, which would otherwise never get an episode.
        window = [r.isoformat() for r in CADENCE.releases_through(today, SWEEP + 1)]
        planned = {p['id'] for p in json.loads((ROOT / 'research' / 'backfill-plan.json').read_text())}
        targets = []
        for rel in window:
            if rel not in planned:
                print(f'{rel}: no changelog entries that week, no episode')
            elif complete(EPISODES / rel):
                print(f'{rel}: already published')
            else:
                targets.append(rel)
                print(f'{rel}: has entries and no episode, producing' + ('' if rel == window[0] else ' (sweep)'))
        if not targets:
            if not args.dry_run:
                refresh_site()
            return
    elif args.backfill:
        plan = json.loads((ROOT / 'research' / 'backfill-plan.json').read_text())
        targets = sorted((p['id'] for p in plan if p['id'].startswith(args.backfill)
                          and not complete(EPISODES / p['id'])), reverse=True)
    else:
        ap.error('give a release date, --weekly, or --backfill YEAR')

    if args.dry_run:
        print(f'dry run: would produce {len(targets)} episode(s): {", ".join(targets) or "none"}')
        return
    print(f'producing {len(targets)} episode(s) with {args.jobs} job(s)', flush=True)
    failures = []
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        futures = {pool.submit(produce, t, args.rewrite): t for t in targets}
        for f in as_completed(futures):
            t = futures[f]
            try:
                r = f.result()
                print(f"{t}: {r['render']} | {r['readback']} | {r['seconds']}s", flush=True)
            except Exception as e:
                failures.append(t)
                print(f'{t}: FAILED {str(e)[:600]}', flush=True)
            try:
                refresh_site()
            except RuntimeError as e:
                print(f'site refresh failed: {e}', flush=True)
    # Cleaned once, after every job is done. Per-episode cleanup raced: the outro's closing
    # paragraph is identical in every episode, so one job deleted the clip another job's
    # readback check was still reading, and 22 of the 75-episode history backfill failed that way.
    if args.clean_cache:
        shutil.rmtree(ROOT / '.cache' / 'tts', ignore_errors=True)
        print('removed .cache/tts', flush=True)
    print(f'done, {len(targets) - len(failures)} ok, {len(failures)} failed {failures}')
    if failures:
        sys.exit(1)


if __name__ == '__main__':
    main()
