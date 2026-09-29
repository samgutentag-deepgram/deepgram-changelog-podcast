"""Copy episodes baked into the image (seed/episodes) onto the volume at boot.

Usage: python scripts/seed_volume.py

Episodes rendered locally ship inside the image; episodes the weekly cron renders exist only on
the volume. A seed episode is copied when the volume lacks it or when the seed's MP3 is newer than
the volume's, so a local re-render replaces the old one on the next deploy while a re-render done on
the box is never rolled back by an older seed. Episodes that exist only on the volume are never
touched.
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
        # copy2 keeps each file's mtime, so a seeded MP3 carries the time it was rendered locally.
        # Newer wins: an older seed must not overwrite a re-render done on the box (it did once,
        # rolling back ten episodes re-rendered from the RSS feed).
        src_mp3, dst_mp3 = src / 'episode.mp3', dst / 'episode.mp3'
        if dst_mp3.exists() and (not src_mp3.exists() or src_mp3.stat().st_mtime <= dst_mp3.stat().st_mtime):
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
