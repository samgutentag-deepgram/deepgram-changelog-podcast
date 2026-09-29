"""Copy episodes baked into the image (seed/episodes) onto the volume at boot.

Usage: python scripts/seed_volume.py

Episodes rendered locally ship inside the image; episodes the weekly cron renders exist only on
the volume. A seed episode is copied when the volume lacks it or holds a different render (its
episode.json or MP3 differs), so a local re-render replaces the old one on the next deploy. Episodes that
exist only on the volume are never touched.
"""

import os
import shutil
from pathlib import Path

SEED = Path(__file__).resolve().parent.parent / 'seed' / 'episodes'
EPISODES = Path(os.environ.get('EPISODES_DIR', '/data/episodes'))


def main() -> None:
    EPISODES.mkdir(parents=True, exist_ok=True)
    if not SEED.exists():
        print('[seed] nothing to seed')
        return
    copied = 0
    for src in sorted(SEED.iterdir()):
        if not src.is_dir():
            continue
        dst = EPISODES / src.name
        # A retake re-renders the MP3 without changing episode.json, so compare both.
        same = all((dst / n).exists() and (dst / n).read_bytes() == (src / n).read_bytes()
                   for n in ('episode.json', 'episode.mp3'))
        if same:
            continue
        dst.mkdir(exist_ok=True)
        for f in src.iterdir():
            shutil.copy2(f, dst / f.name)
        copied += 1
    cover = SEED / 'cover.png'
    if cover.exists():
        shutil.copy2(cover, EPISODES / 'cover.png')
    print(f'[seed] copied {copied} episode(s) into {EPISODES}')


if __name__ == '__main__':
    main()
