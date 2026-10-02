"""Zero to a podcast site on your own machine: check the setup, render one episode, open the
site, then offer to render the rest of the back catalog with a cost estimate first.

Usage:
  python3 scripts/quickstart.py            first run: plan, render the newest week, serve, offer more
  python3 scripts/quickstart.py --more     skip to the offer, for a site that already has episodes
  python3 scripts/quickstart.py --port 8020 --no-open

Reads keys from .env (or the environment), the show's name and feed from show.json. Nothing is
spent until the first episode renders, and nothing after that until you say how many more.
Leave it running to keep the site up; Ctrl-C stops the server.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import shutil
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / 'scripts'
EPISODES = ROOT / 'episodes'
PLAN = ROOT / 'research' / 'backfill-plan.json'
PY = sys.executable
JOBS = 3  # renders at once when catching up; Flux and Claude both handle this without throttling
# Used for the estimate until this machine has rendered an episode of its own. The Deepgram
# show's measured average over 141 episodes: Flux TTS plus Claude, and wall-clock per episode.
DEFAULT_USD, DEFAULT_SECONDS = 0.20, 300


def say(msg: str = '') -> None:
    print(msg, flush=True)


def load_env() -> None:
    """Read .env into the environment without overriding anything already set, so a fresh shell
    doesn't need the `set -a` step."""
    env = ROOT / '.env'
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def check_setup() -> None:
    problems = []
    if sys.version_info < (3, 9):
        problems.append(f'Python 3.9 or newer is needed; this is {sys.version.split()[0]}.')
    if not shutil.which('ffmpeg'):
        problems.append('ffmpeg is not on your PATH. On a Mac: brew install ffmpeg')
    for module, package in (('anthropic', 'anthropic'), ('PIL', 'pillow')):
        if importlib.util.find_spec(module) is None:
            problems.append(f'The {package} package is missing. With your venv active: pip install {package}')
    for key, where in (('DEEPGRAM_API_KEY', 'https://console.deepgram.com/signup'),
                       ('ANTHROPIC_API_KEY', 'https://console.anthropic.com')):
        if not os.environ.get(key):
            problems.append(f'{key} is not set. Copy .env.sample to .env and add it ({where}).')
    if problems:
        say('Setup needs a few things first:')
        for p in problems:
            say(f'  - {p}')
        raise SystemExit(1)


def set_aside_example(show_name: str) -> None:
    """The repo ships the Deepgram show's 2026-09-22 episode as a worked example. In a fork with its
    own name, that directory would collide with your own 2026-09-22 week and get re-voiced instead
    of rewritten, so move it out of the way. A leading dot keeps the site and catalog from listing it."""
    ep = EPISODES / '2026-09-22'
    script = ep / 'script.md'
    if not script.exists() or show_name in script.read_text().splitlines()[0]:
        return
    target = EPISODES / '.example-deepgram-2026-09-22'
    if target.exists():
        return
    ep.rename(target)
    say(f'Moved the Deepgram example episode to {target.relative_to(ROOT)} so it can\'t collide with yours.')


def offer_cadence(show: dict) -> bool:
    """Before the first render, say what cadence the feed's history suggests and offer to switch
    show.json to it. Returns True if show.json changed, so the plan gets rebuilt."""
    try:
        rec = json.loads((ROOT / 'research' / 'cadence.json').read_text())
    except (OSError, ValueError):
        return False
    current = show.get('cadence', 'weekly')
    say(f"Cadence: {rec['reason']}")
    if rec['cadence'] == current:
        say(f'{current.capitalize()} fits, and that is what show.json has.')
        return False
    answer = input(f"Recommended: {rec['cadence']}. show.json says {current}. Switch to {rec['cadence']}? [y/N] ")
    if answer.strip().lower() not in ('y', 'yes'):
        return False
    path = ROOT / 'show.json'
    data = json.loads(path.read_text())
    data['cadence'] = rec['cadence']
    path.write_text(json.dumps(data, indent=2) + '\n')
    say(f"show.json now says {rec['cadence']}. Re-planning.")
    return True


def run(*args: str) -> None:
    # stdin closed so nothing a step runs can swallow the answer to the "how many more" prompt.
    r = subprocess.run([PY, *args], cwd=ROOT, stdin=subprocess.DEVNULL)
    if r.returncode != 0:
        raise SystemExit(f'{Path(args[0]).name} failed (exit {r.returncode}). The output above says why.')


def published(ep_id: str) -> bool:
    d = EPISODES / ep_id
    return (d / 'episode.mp3').exists() and ((d / 'produce.json').exists() or (d / 'art.jpg').exists())


def plan() -> list[dict]:
    try:
        return json.loads(PLAN.read_text())
    except (OSError, ValueError):
        return []


def measured() -> tuple[float, float, int]:
    """Mean all-in cost and wall-clock seconds per episode rendered on this machine, and how many
    episodes that mean is over. Falls back to the Deepgram show's figures with a count of 0."""
    costs, seconds = [], []
    for f in EPISODES.glob('*/produce.json'):
        try:
            ep = json.loads((f.parent / 'episode.json').read_text())
            run_seconds = json.loads(f.read_text()).get('seconds')
        except (OSError, ValueError):
            continue
        cost = ep.get('cost') or {}
        if isinstance(cost.get('usd'), (int, float)):
            costs.append(cost['usd'] + (cost.get('writer_usd') or 0))
        if isinstance(run_seconds, (int, float)):
            seconds.append(run_seconds)
    if not costs:
        return DEFAULT_USD, DEFAULT_SECONDS, 0
    return sum(costs) / len(costs), (sum(seconds) / len(seconds) if seconds else DEFAULT_SECONDS), len(costs)


def in_use(port: int) -> bool:
    # Check IPv6 too: a server bound to [::] answers on localhost in the browser but not on
    # 127.0.0.1, and sharing its port sends the browser to the wrong site.
    for family, host in ((socket.AF_INET, '127.0.0.1'), (socket.AF_INET6, '::1')):
        try:
            with socket.socket(family) as s:
                s.settimeout(0.3)
                if s.connect_ex((host, port)) == 0:
                    return True
        except OSError:
            continue
    return False


def free_port(start: int) -> int:
    for port in range(start, start + 20):
        if not in_use(port):
            return port
    raise SystemExit(f'No free port between {start} and {start + 19}; pass --port.')


def serve(port: int) -> subprocess.Popen:
    proc = subprocess.Popen([PY, str(SCRIPTS / 'serve.py'), '--port', str(port)], cwd=ROOT,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        with socket.socket() as s:
            if s.connect_ex(('127.0.0.1', port)) == 0:
                return proc
        time.sleep(0.1)
    proc.terminate()
    raise SystemExit('The site server did not start. Run python3 scripts/serve.py to see why.')


def ask_how_many(waiting: list[str]) -> list[str]:
    usd, seconds, basis = measured()
    n = len(waiting)
    total_min = math.ceil(n / JOBS) * seconds / 60
    where = (f'your {basis} episode{"s" if basis != 1 else ""} so far' if basis
             else 'the Deepgram show\'s average')
    say()
    say(f'{n} more episode{"s" if n != 1 else ""} worth of changelog {"have" if n != 1 else "has"} no audio yet.')
    say(f'At about ${usd:.2f} an episode ({where}, Flux TTS plus Claude), all of them is about '
        f'${usd * n:.2f} and {max(1, round(total_min))} minutes, {JOBS} at a time.')
    while True:
        answer = input('How many more? A number, "all", or Enter to stop: ').strip().lower()
        if not answer:
            return []
        if answer == 'all':
            return waiting
        if answer.isdigit() and int(answer) > 0:
            pick = waiting[:int(answer)]
            say(f'Rendering {len(pick)}, newest first: about ${usd * len(pick):.2f}.')
            return pick
        say('  Type a number like 5, or "all", or just press Enter.')


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--more', action='store_true', help='skip the first episode and go to the offer')
    ap.add_argument('--port', type=int, default=8010)
    ap.add_argument('--no-open', action='store_true', help="don't open a browser")
    args = ap.parse_args()

    load_env()
    sys.path.insert(0, str(SCRIPTS))
    from show import SHOW  # after load_env, so SITE_URL from .env counts

    check_setup()
    feed = os.environ.get('CHANGELOG_FEED_URL') or SHOW['feed_url']
    say(f"{SHOW['name']}, from {feed}")
    set_aside_example(SHOW['name'])

    say('Reading the changelog (free, no API calls)...')
    run(str(SCRIPTS / 'backfill_plan.py'), '--refresh')
    if not args.more and not any(published(w['id']) for w in plan()):
        if offer_cadence(SHOW):
            run(str(SCRIPTS / 'backfill_plan.py'))
    weeks = sorted((w['id'] for w in plan()), reverse=True)
    if not weeks:
        raise SystemExit('The feed has no dated entries in a finished window yet, so there is nothing to render.')
    waiting = [w for w in weeks if not published(w)]
    say(f'{len(weeks)} episode{"s" if len(weeks) != 1 else ""} worth of changelog, {len(weeks) - len(waiting)} already rendered.')

    first = None
    if not args.more and waiting and len(waiting) == len(weeks):
        first = waiting.pop(0)
        say(f'Rendering the newest one, {first}, as your first episode. A quiet stretch of changelog '
            f'takes about 5 minutes and 20 cents; a busy one can take 20 minutes and about a dollar.')
        run(str(SCRIPTS / 'produce.py'), first)
    # Always redraw the cover: the repo ships Deepgram's, and a renamed show needs its own.
    run(str(SCRIPTS / 'make_art.py'))
    run(str(SCRIPTS / 'build_catalog.py'))

    port = free_port(args.port)
    server = serve(port)
    base = f'http://localhost:{port}'
    landing = f'{base}/e/{first}' if first else f'{base}/back-catalog'
    say()
    say(f'Your site is up: {base}')
    say(f'  Back catalog, every episode and what it costs: {base}/back-catalog')
    if not args.no_open:
        webbrowser.open(landing)

    try:
        pick = ask_how_many(waiting) if waiting else []
        if pick:
            say(f'Open {base}/back-catalog to watch them land.')
            run(str(SCRIPTS / 'produce.py'), *pick, '--jobs', str(JOBS))
        say()
        say(f'The site is still up at {base}. Ctrl-C to stop it. Run this again with --more any time.')
        server.wait()
    except (KeyboardInterrupt, EOFError):
        say()
    finally:
        server.terminate()


if __name__ == '__main__':
    main()
