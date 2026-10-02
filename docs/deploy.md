# Deploy: Tuesday Mornings On Fly

How the live show runs on its own, and how to deploy yours. Back to the [README](../README.md).

The show runs on one Fly machine in the `deepgram` org, at
[dg-devrel-deepgram-changelog.fly.dev](https://dg-devrel-deepgram-changelog.fly.dev).

At 5am Pacific every morning, the machine's own cron (supercronic, reading `crontab`) runs
`scripts/weekly_run.py`. It exits at once unless today is a release date for the show's cadence,
which for this show means Tuesdays. On a release date it wraps `scripts/produce.py --weekly`, which
refreshes the changelog and writes, renders, checks, and illustrates the episode for the Sunday to
Saturday that just ended. It
then rebuilds the feed and the back catalog on the volume, so there's nothing to deploy. A failed
run retries up to three times, five minutes apart. Set `CHANGELOG_PUSHOVER_TOKEN` and
`CHANGELOG_PUSHOVER_USER` (see `.env.sample`) to get a push for each retry and for the result.

A week with no changelog entries gets no episode. Each run also re-checks about four weeks of
earlier releases (four weekly, two biweekly, or one monthly), so an entry that shows up late still
gets an episode.

Every run leaves a record on the volume at `/data/runs/<UTC stamp>/`: a timestamped `run.log`, the
catalog before and after, the feed after, the new episode's `produce.json`, and a `summary.json`
with the exit code. To list and pull them:

```bash
fly ssh console -a dg-devrel-deepgram-changelog -C "ls /data/runs"
fly ssh sftp get -a dg-devrel-deepgram-changelog /data/runs/<stamp>/run.log .
```

To deploy your own:

1. **Set the site.** Put your public URL in `show.json` `site_url` and in `[env]` in `fly.toml`,
   and rename `app` in `fly.toml`.
2. **Set the keys.** `fly secrets set DEEPGRAM_API_KEY=... ANTHROPIC_API_KEY=...`
3. **Pick your morning.** `crontab` runs at 5am Pacific. Change `CRON_TZ` if that isn't yours.
   The day comes from `release_day` in `show.json`, so the crontab doesn't change with it.
4. **Ship it.** `python3 scripts/backfill_plan.py --refresh`, then
   `python3 scripts/stage_site.py && fly deploy --remote-only --ha=false`.

Episodes you render locally ship inside the image as `seed/episodes`, and the machine copies them
onto the volume when it boots (`seed_volume.py`). A newer local render replaces the volume copy.
Episodes the cron made only exist on the volume. Locally, set `ART_PYTHON` if your default Python
doesn't have Pillow.

**Storage:** an episode takes about 1.5 MB on the volume (a 64 kbps MP3 plus art and JSON). All 141
use about 175 MB of the 1 GB volume, and new weeks add roughly 75 MB a year. The server deletes its
raw paragraph audio (`.cache/tts`) after each run. Locally it's kept, so editing a script only
re-renders the paragraphs you changed.

Each `script.md` carries writer's notes, so the deploy leaves it out. `serve.py` only serves an
allowlist of public file names from the episodes directory.

**Cost:** going by the 141 episodes on the live
[back catalog](https://dg-devrel-deepgram-changelog.fly.dev/back-catalog), an episode is about 10
cents of Flux TTS and 9 cents of Claude. That's roughly 20 cents a week, or about $10 for a year of
Tuesdays. A backfill costs the same per episode, so check the week count in
`research/backfill-review.html` first.
