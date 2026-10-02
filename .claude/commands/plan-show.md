---
description: Plan a podcast from an RSS or Atom feed, then fill in show.json
argument-hint: <feed URL>
---

I want to turn an RSS or Atom feed into a podcast with this repo. The feed is: $ARGUMENTS

If no feed URL was given above, ask me for one and stop until I answer.

Work through these in order and show me the results as you go:

1. Fetch the feed and tell me the product or publication it belongs to (the channel or feed
   title) and its public page (the channel or feed link). Use those as the product name and
   changelog page from here on.
2. Run `CHANGELOG_FEED_URL=<the feed> python3 scripts/backfill_plan.py --refresh`. Tell me how
   many episodes and entries it found, and whether the items carry full posts or only teasers. If
   they're teasers, say so plainly: the writer only sees what the feed carries, so this feed will
   make thin episodes.
3. Run `CHANGELOG_FEED_URL=<the feed> python3 scripts/cadence.py` and tell me the recommended
   cadence and its reason in one or two sentences.
4. Read the entry titles in research/backfill-plan.json and tell me what this feed is mostly
   about.
5. Suggest 5 show names, each with a one-line pitch. Nothing that sounds like the product's
   official podcast.
6. Propose 3 to 6 segments in running order. Keep "Breaking changes and action required",
   "Launches", and "Quick hits" first, and name the rest after this product's areas. For each
   one, list three real entries from the last year that would have landed in it.
7. Propose a cast from the Flux TTS voices in docs/cast.json and
   https://developers.deepgram.com/docs/flux-tts/overview: one anchor and a voice per segment.
8. Draft a canned intro line and outro for this show, in the style of the ones in
   scripts/write_episode.py, with the product's own support links in place of Deepgram's.
9. List the exact edits that would make all of it real, starting with show.json, then file by
   file.

Don't edit any files or make any paid API calls yet. Steps 2 and 3 are free; they only read the
feed.

When I pick a name, update show.json only: `name`, `wordmark` (two strings, a small line and a
big line, drawn on the art), `description` (one or two sentences: what the show reads, and that
it's voiced by Deepgram Flux TTS), `author`, `owner_email` (ask me for these two if you don't know
them), `changelog_url`, and `feed_url`. Leave `site_url`, `cadence`, `release_day`, and
`attribution` as they are. The quickstart offers the cadence change itself.

Then tell me the next step: exit Claude Code and run `python3 scripts/quickstart.py` with the
virtual environment active (`source .venv/bin/activate`).
