"""The Tuesday cron entry point: run produce.py --weekly and keep a capture bundle of the run.

Usage (crontab): python scripts/weekly_run.py

Every run gets its own directory, /data/runs/<UTC timestamp>/, holding:
  run.log               every line produce.py printed, each stamped with UTC time
  catalog-before.json   the public catalog as it was before the run
  catalog-after.json    and after
  feed-after.xml        the feed after the run
  produce.json          the new episode's own result line, if one was made
  summary.json          start, end, seconds, exit code, and which episode it made

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
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EPISODES = Path(os.environ.get('EPISODES_DIR', ROOT / 'episodes'))
RUNS = Path(os.environ.get('RUNS_DIR', EPISODES.parent / 'runs'))
KEEP_RUNS = 104  # two years of Tuesdays; each bundle is a few hundred KB


def stamp() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def copy_if(src: Path, dst: Path) -> None:
    if src.exists():
        shutil.copy2(src, dst)


def main() -> int:
    run_dir = RUNS / datetime.now(timezone.utc).strftime('%Y-%m-%dT%H%M%SZ')
    run_dir.mkdir(parents=True, exist_ok=True)
    before = {p.name for p in EPISODES.iterdir() if (p / 'episode.mp3').exists()} if EPISODES.exists() else set()
    copy_if(EPISODES / 'catalog.json', run_dir / 'catalog-before.json')

    started, t0 = stamp(), time.time()
    cmd = [sys.executable, '-u', str(ROOT / 'scripts' / 'produce.py'), '--weekly', '--clean-cache']
    with open(run_dir / 'run.log', 'w') as log:
        log.write(f'{started} $ {" ".join(cmd)}\n')
        proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in proc.stdout:
            out = f'{stamp()} {line.rstrip()}'
            log.write(out + '\n')
            log.flush()
            print(out, flush=True)  # also into /data/logs/weekly.log via the crontab redirect
        code = proc.wait()

    made = sorted({p.name for p in EPISODES.iterdir() if (p / 'episode.mp3').exists()} - before)
    copy_if(EPISODES / 'catalog.json', run_dir / 'catalog-after.json')
    copy_if(EPISODES / 'feed.xml', run_dir / 'feed-after.xml')
    for ep in made:
        copy_if(EPISODES / ep / 'produce.json', run_dir / f'{ep}-produce.json')
    (run_dir / 'summary.json').write_text(json.dumps({
        'started': started, 'finished': stamp(), 'seconds': round(time.time() - t0),
        'exit_code': code, 'episodes_made': made,
    }, indent=2) + '\n')

    for old in sorted(p for p in RUNS.iterdir() if p.is_dir())[:-KEEP_RUNS]:
        shutil.rmtree(old, ignore_errors=True)
    return code


if __name__ == '__main__':
    sys.exit(main())
