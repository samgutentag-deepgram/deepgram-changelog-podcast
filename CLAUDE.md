# The Deepgram Changelog: notes for Claude Code

This repo turns an RSS or Atom feed into a multi-voice podcast: Claude writes each episode's script
from the feed's entries, Deepgram Flux TTS voices it, Deepgram speech-to-text checks it, and a small
Python server publishes the site and podcast feed. It ships as the Deepgram developer changelog's
show, and anyone can point it at their own feed.

## When someone is new here

If the person asks what this is, how to use it, or how to get started, offer the two commands:

- `/start [feed URL]` walks them from a fresh clone to their own show running locally: setup check,
  keys, planning, the first episode, the site, and more episodes. This is the default suggestion.
- `/plan-show <feed URL>` only plans a show from a feed and fills in `show.json`, without rendering.

The README's "Steps" section is the same flow done by hand.

## Things to know before acting

- **Rendering costs money.** An episode is about 20 cents to a dollar (Flux TTS plus Claude). Say
  so and ask before rendering anything, and before rendering more than one.
- **Never ask for API keys in chat.** Keys live in `.env` (gitignored, copied from `.env.sample`).
  Tell the person to edit it themselves. Never print its contents.
- **`show.json` is the show's identity:** name, art wordmark, description, author, owner email,
  links, feed, cadence, release day, and the credit line. Prefer editing it over editing strings in
  code.
- **The quickstart asks questions on a terminal.** To drive it from here, use its unattended flags:
  `--check`, `--cadence keep|recommended|weekly|biweekly|monthly`, `--first-only`, and
  `--render N`. Long renders belong in the background.
- **Use the virtual environment** at `.venv` (`.venv/bin/python`), created with
  `python3 -m venv .venv && .venv/bin/pip install anthropic pillow`.
- **Don't deploy, push, or delete episodes** unless the person asks.
- **A fork still inherits Deepgram's segments, outro, and cast.** The README's "What Else To
  Change" section lists where each one lives.
