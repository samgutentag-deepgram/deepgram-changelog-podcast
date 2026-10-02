"""The cron entry point: on a release date, run produce.py --weekly and keep a capture bundle.

Usage (crontab): python scripts/weekly_run.py [--force]

Cron calls this every morning. On any day that isn't a release date for show.json's cadence and
release_day, it exits at once without a bundle or an alert. --force runs it anyway.

Every run gets its own directory, /data/runs/<UTC timestamp>/, holding:
  run.log               every line produce.py printed, each stamped with UTC time
  catalog-before.json   the public catalog as it was before the run
  catalog-after.json    and after
  feed-after.xml        the feed after the run
  produce.json          the new episode's own result line, if one was made
  summary.json          start, end, seconds, exit code, and which episode it made

A failed attempt is retried, up to ATTEMPTS in all, RETRY_WAIT_S apart. produce.py --weekly skips
what already published, so a retry only redoes the episodes that failed, and it reuses their
written script.md. alerts.py pushes a 🔁 for each retry, then one final ✅ (published, on
whichever attempt) or ❌ (every attempt failed).

The bundle lives on the Fly volume, so capturing a run never depends on a laptop being awake.
Pull one down with:
  fly ssh sftp get -a dg-devrel-deepgram-changelog /data/runs/<stamp>/run.log .
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

from alerts import notify

from show import SHOW
from cadence import CADENCE

ROOT = Path(__file__).resolve().parent.parent
EPISODES = Path(os.environ.get('EPISODES_DIR', ROOT / 'episodes'))
RUNS = Path(os.environ.get('RUNS_DIR', EPISODES.parent / 'runs'))
SITE_URL = SHOW['site_url']
KEEP_RUNS = 104  # two years of Tuesdays; each bundle is a few hundred KB
ATTEMPTS = 3
RETRY_WAIT_S = 300  # the 2026-09-29 Flux failure passed on a rerun about four hours later


def stamp() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def copy_if(src: Path, dst: Path) -> None:
    if src.exists():
        shutil.copy2(src, dst)


def attempt(n: int, log) -> tuple[int, list[str]]:
    """One produce.py --weekly run, streamed into the run log. Returns (exit code, FAILED lines)."""
    # No --clean-cache: a retry reuses the paragraphs the failed attempt already paid for. main()
    # clears the cache once, after the last attempt.
    cmd = [sys.executable, '-u', str(ROOT / 'scripts' / 'produce.py'), '--weekly']
    log.write(f'{stamp()} attempt {n} of {ATTEMPTS} $ {" ".join(cmd)}\n')
    log.flush()
    failed = []
    proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in proc.stdout:
        if ': FAILED ' in line:
            failed.append(line.strip())
        out = f'{stamp()} {line.rstrip()}'
        log.write(out + '\n')
        log.flush()
        print(out, flush=True)  # also into /data/logs/weekly.log via the crontab redirect
    return proc.wait(), failed


def main() -> int:
    if '--force' not in sys.argv and CADENCE.window_for_release(date.today()) is None:
        print(f'{date.today()}: not a release date ({CADENCE.adjective}, {CADENCE.day_name}s), nothing to do')
        return 0
    run_dir = RUNS / datetime.now(timezone.utc).strftime('%Y-%m-%dT%H%M%SZ')
    run_dir.mkdir(parents=True, exist_ok=True)
    before = {p.name for p in EPISODES.iterdir() if (p / 'episode.mp3').exists()} if EPISODES.exists() else set()
    copy_if(EPISODES / 'catalog.json', run_dir / 'catalog-before.json')

    started, t0 = stamp(), time.time()
    attempts = []
    try:
        with open(run_dir / 'run.log', 'w') as log:
            for n in range(1, ATTEMPTS + 1):
                code, failed = attempt(n, log)
                attempts.append({'attempt': n, 'exit_code': code, 'failed': failed})
                if code == 0 and not failed:
                    break
                if n < ATTEMPTS:
                    notify('retry', f'Attempt {n} of {ATTEMPTS} failed, retrying in '
                           f'{RETRY_WAIT_S // 60} min\n{reasons(code, failed)}', url=SITE_URL)
                    time.sleep(RETRY_WAIT_S)
    except Exception as e:
        notify('fail', f'Weekly run crashed before it finished: {e!r}'[:500], url=SITE_URL)
        raise
    finally:
        shutil.rmtree(ROOT / '.cache' / 'tts', ignore_errors=True)

    made = sorted({p.name for p in EPISODES.iterdir() if (p / 'episode.mp3').exists()} - before)
    copy_if(EPISODES / 'catalog.json', run_dir / 'catalog-after.json')
    copy_if(EPISODES / 'feed.xml', run_dir / 'feed-after.xml')
    for ep in made:
        copy_if(EPISODES / ep / 'produce.json', run_dir / f'{ep}-produce.json')
    (run_dir / 'summary.json').write_text(json.dumps({
        'started': started, 'finished': stamp(), 'seconds': round(time.time() - t0),
        'exit_code': code, 'episodes_made': made, 'attempts': attempts,
    }, indent=2) + '\n')

    for old in sorted(p for p in RUNS.iterdir() if p.is_dir())[:-KEEP_RUNS]:
        shutil.rmtree(old, ignore_errors=True)
    alert(code, made, failed, len(attempts), round(time.time() - t0), run_dir)
    return code


def reasons(code: int, failed: list[str]) -> str:
    # One line per failed episode, already of the form "<id>: FAILED <step> failed: <exception>".
    return '\n'.join(l.replace(': FAILED ', ': ', 1)[:300] for l in failed) or f'produce.py exited {code}'


def alert(code: int, made: list[str], failed: list[str], tries: int, seconds: int, run_dir: Path) -> None:
    took = f'{seconds // 60}m{seconds % 60:02d}s'
    on_try = f' on attempt {tries} of {ATTEMPTS}' if tries > 1 else ''
    if code == 0 and not failed:
        if not made:
            notify('ok', f'Weekly run OK{on_try}, nothing new to publish ({took})', url=SITE_URL)
            return
        parts = []
        for ep in made:
            try:
                render = json.loads((EPISODES / ep / 'produce.json').read_text()).get('render', '')
            except (OSError, ValueError):
                render = ''
            cost = next((w.rstrip(',') for w in render.split() if w.startswith('$')), '')
            parts.append(f'{ep} published' + ('' if parts else on_try) + (f', {cost}' if cost else ''))
        notify('ok', f"{'; '.join(parts)} ({took})", url=f'{SITE_URL}/e/{made[-1]}')
        return
    ok_part = f"\nPublished anyway: {', '.join(made)}" if made else ''
    notify('fail', f'Weekly run failed all {tries} attempts ({took})\n{reasons(code, failed)}'
           f'{ok_part}\nLog: {run_dir}/run.log', url=SITE_URL)


if __name__ == '__main__':
    sys.exit(main())
