---
description: Go from a fresh clone to your own podcast site, guided step by step
argument-hint: [feed URL]
---

Walk me from a fresh clone of this repo to my own podcast running on this machine. I may know
nothing about the repo yet. Feed URL, if I gave one: $ARGUMENTS

Ground rules for the whole walkthrough:
- Ask one question at a time and wait for my answer.
- Before anything that costs money (rendering an episode), say roughly what it will cost and how
  long it takes, and ask first.
- Never ask me to paste an API key into this chat. If I paste one anyway, don't repeat it back, and
  suggest I rotate it.
- When I need to run a setup command (installing ffmpeg, creating the venv, copying `.env.sample`),
  give it to me as one line starting with `!`, for example `! python3 -m venv .venv`, and tell me
  to type it at this prompt. `!` runs it in this session, so we both see the output and you can
  carry on from it. Offer to run it for me instead if I'd rather.
- Run Python through the virtual environment directly (`.venv/bin/python ...`), so nothing depends
  on an activated shell.
- Render only through `scripts/quickstart.py` (`--first-only`, then `--render N`). It already
  renders several episodes at once, prints the time and token report, and rebuilds the site once.
  Don't call `produce.py` yourself and don't split renders across subagents.
- Keep each message short: what just happened, then the one thing you need from me.

1. **Say what's going to happen**, in three or four sentences: this turns an RSS or Atom feed into
   a multi-voice podcast written by Claude and voiced by Deepgram Flux TTS. We'll check the setup,
   plan the show from the feed, render one episode, open the site, and then decide on more. The
   first episode takes 5 to 25 minutes and costs about 20 cents to a dollar.

2. **Check the tools.** Run `python3 --version` (needs 3.9 or newer), `git --version`, and
   `which ffmpeg`. If ffmpeg is missing, tell me how to install it (on a Mac,
   `! brew install ffmpeg`, after installing Homebrew from https://brew.sh) and wait. If `.venv`
   doesn't exist, give me the line to create it and install the packages, about 30 seconds:
   `! python3 -m venv .venv && .venv/bin/pip install anthropic pillow`.

3. **Keys.** If `.env` doesn't exist, give me `! cp .env.sample .env` to run. Then tell me to open `.env` in my
   editor and fill in `DEEPGRAM_API_KEY` (https://console.deepgram.com/signup, new accounts get
   $200 in credit) and `ANTHROPIC_API_KEY` (https://console.anthropic.com), and to tell you when
   that's done. Then run `.venv/bin/python scripts/quickstart.py --check` and fix whatever it
   lists before going on.

4. **Plan the show.** If I didn't give a feed URL, ask for one, and offer a few that work well if I
   just want to try it: Tailscale (`https://tailscale.com/changelog/index.xml`), Resend
   (`https://resend.com/changelog/rss.xml`), or Linear (`https://linear.app/rss/changelog.xml`).
   Then read `.claude/commands/plan-show.md` and do everything it says for that feed, including
   filling in show.json one field at a time, but skip its final "next step" paragraph.

5. **Cadence.** From the plan, tell me the recommended cadence and why in one sentence, and ask
   whether to use it or keep weekly. Remember the answer as `recommended` or `keep`.

6. **First episode.** Say what it will cost and take, and ask to go ahead. Then run
   `.venv/bin/python scripts/quickstart.py --cadence <my answer> --first-only --no-open` in the
   background. While it runs, tell me in two or three sentences what it's doing (writing the
   script with Claude, voicing each paragraph with Flux TTS, listening back with Deepgram
   speech-to-text, then drawing the art). When it finishes, show me its "How long it took, and
   what it used" block exactly as printed.

7. **Open the site.** Start `.venv/bin/python scripts/serve.py --port <a free port, 8010 or up>` in
   the background, open the new episode's page in my browser (`open <url>` on a Mac), and tell me
   what to look at: the player and chapters, the transcript following along, the art, the cost
   card, and Back catalog in the header.

8. **More episodes.** Tell me how many more episodes the feed has and roughly what they'd cost all
   in (the quickstart's last lines say both), and ask how many to render: a number, all, or none.
   For a number, run `.venv/bin/python scripts/quickstart.py --render <N>` in the background,
   tell me to watch the back catalog fill in, and show the report when it's done.

9. **Wrap up.** Tell me, briefly: the site keeps running until I stop it; `python3
   scripts/quickstart.py --more` renders more later; the show's name, segments, cast, cadence,
   writer brief, and outro are all set, but the pronunciation list (`docs/key-terms.json`) and the
   writer's format spec (`docs/show-format.md`) are still Deepgram's, and the README's "What Else To
   Change" section covers them; and `docs/deploy.md` covers deploying it so it publishes on its own.
