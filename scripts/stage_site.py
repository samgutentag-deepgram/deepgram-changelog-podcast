"""Copy exactly what the Fly image needs into dist/, which is the only Docker build context.

Usage: python3 scripts/stage_site.py

An allowlist on purpose. The image carries the pipeline (scripts, the format spec, the cast, the
planning data it needs to write episodes) but serve.py only ever serves web/ and the public
files in each episode directory, so none of that is reachable from the site. Locally rendered
episodes go in as seed/episodes with their public files only: no script.md with writer's notes,
no render or readback reports. Staging to a directory makes the shipped set something you can
`ls` before deploying.
"""

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / 'dist'
SCRIPTS = ('serve.py', 'produce.py', 'write_episode.py', 'render_episode.py', 'readback_check.py',
           'fill_cost.py', 'build_feed.py', 'build_catalog.py', 'backfill_plan.py', 'make_art.py',
           'seed_volume.py', 'weekly_run.py')
DOCS = ('show-format.md', 'cast.json', 'example-episode.md', 'key-terms.json')
RESEARCH = ('backfill-plan.json',)
EPISODE_FILES = ('episode.mp3', 'episode.json', 'chapters.json', 'script.json', 'transcript.vtt',
                 'art.jpg')


def main() -> None:
    if DIST.exists():
        shutil.rmtree(DIST)
    shutil.copytree(ROOT / 'web', DIST / 'web')
    for folder, names in (('scripts', SCRIPTS), ('docs', DOCS), ('research', RESEARCH)):
        (DIST / folder).mkdir(parents=True)
        for name in names:
            src = ROOT / folder / name
            if not src.exists():
                raise SystemExit(f'{folder}/{name} is missing')
            shutil.copy2(src, DIST / folder / name)
    for name in ('crontab', 'docker-entrypoint.sh'):
        shutil.copy2(ROOT / name, DIST / name)
    seed = DIST / 'seed' / 'episodes'
    seed.mkdir(parents=True)
    shutil.copy2(ROOT / 'episodes' / 'cover.png', seed / 'cover.png')
    count = 0
    for d in sorted((ROOT / 'episodes').iterdir()):
        if not (d / 'episode.mp3').exists():
            continue
        (seed / d.name).mkdir()
        for name in EPISODE_FILES:
            if (d / name).exists():
                shutil.copy2(d / name, seed / d.name / name)
        count += 1
    size = sum(p.stat().st_size for p in DIST.rglob('*') if p.is_file())
    print(f'staged dist/ with {count} seed episode(s), {size / 1e6:.1f} MB')


if __name__ == '__main__':
    main()
