# Changelog survey, 2026-09-25

Research phase for a single-voice podcast generated from the Deepgram developer changelog, output
modeled on [HN Radio](https://github.com/samgutentag-deepgram/hn-radio). Everything below was measured from the live changelog on 2026-09-25.

## Sources

| Source | What it gives you | Quirks |
| --- | --- | --- |
| `https://developers.deepgram.com/changelog.rss` | 223 items, full HTML body per item | Items are **not sorted by date**. `pubDate` is midnight GMT. No categories or tags. Channel `<description>` is literally `undefined`. Days with several topics are split into separate items (11 such days). Each HTML block carries its MDX source base64-encoded in an `fve-mdx-b64` attribute. |
| `https://developers.deepgram.com/changelog/llms.txt` | 211 dated entries, newest first, some with a one-line summary | Index only, no bodies. |
| `https://developers.deepgram.com/changelog/YYYY/M/D.md` | Clean markdown for one day | Best body text. Strip the three leading `>` lines. |
| `https://developers.deepgram.com/support.md` | Every contact channel | Source for the outro. |

Recommended pipeline: poll the RSS for new GUIDs (change detection), then fetch the `.md` for each
new date as the body the writer reads. The RSS HTML is usable but noisier.

The HTML changelog index is client-rendered and fetches as an empty shell. So a scrape of the page can't
measure cadence; the RSS and `llms.txt` both sidestep it.

## Cadence

History goes back to 2020-07-30, but the volume is recent and accelerating:

| Year | Dated entries |
| --- | --- |
| 2024 | 26 |
| 2025 | 51 |
| 2026 through 09-24 | 77 |

Since May 2026 it runs 9 to 12 dated entries a month.

Last 53 weeks (from 2025-09-22), entries per week: median 2, max 5. **7 empty weeks, and only one
of them (week of 2026-06-01) in the last 30 weeks.** Bi-weekly buckets: one empty in the whole year.

Weekday spread: Thu 26, Wed 24, Tue 18, Fri 16, Mon 13. Nothing on weekends.

Conclusion: weekly holds. Publish Monday covering the previous Monday through Sunday, because
Friday entries are common enough that a Friday publish would routinely miss one.

## What the changelog is made of (last 12 months, 104 headlines)

| Theme | Headlines | Notes |
| --- | --- | --- |
| Languages and model accuracy | 33 | Nova-3 language adds and "improved models" roundups, numerals, profanity. High volume, low narrative. Almost always "no code change needed." |
| Self-hosted releases | 21 | Release IDs `YYMMDD`, roughly twice a month, like clockwork. Where most infra-level breaking changes live. |
| Voice Agent and LLMs | 21 | New control messages (`UpdateThink`, `UpdateListen`, `InjectAgentMessage`), LLM model adds, upstream deprecations. Most story-rich theme. |
| Flux (STT and TTS) | 8 | Flagship. Turn-taking, timestamps, numerals, speed range, containers. |
| SDKs and tooling | 7 | SDK multi-releases, CLI, `@deepgram/react`, Browser Agent SDK. |
| Regions and platform | 7 | EU, Australia, India endpoints; concurrency limits; pricing; deprecations. |
| STT features | 4 | Redaction, entity detection, diarization v2, Pharma, Medical. |
| Corrections | 2 | 2026-09-18 corrected two earlier entries. New entry type. |

## Breaking changes are real, frequent, and inconsistently labeled

Found in the last 12 months:

- **2025-11-05** Legacy Intelligence parameters now return HTTP 400. Labeled "Action Required."
- **2026-01** Self-hosted TTS release not backwards-compatible between API and Engine containers.
- **2026-05** Rust SDK `FluxResponse::TurnInfo` made `#[non_exhaustive]`; Java SDK 0.4, 0.7, 0.10
  all breaking (pre-1.0).
- **2026-06-11** Self-hosted Engine requires two new NVIDIA env vars. "Action Required."
- **2026-06-30** Self-hosted `GET /v1/models` response shape changed. "Breaking Change."
- **2026-07-31** Voice Agent sessions now hard-close at 2 hours. **Not labeled breaking at all**,
  third heading in a four-topic entry.
- **2026-08-19** CLI exit codes now nonzero on failure. Breaking for scripts.
- Upstream LLM retirements, repeatedly: Gemini 2.0 Flash, Gemini 3.1 Flash Lite preview, Gemini 2.5
  Flash family (October), Claude Sonnet 4, Llama Nemotron Super 49B removed.

Implication for the writer: breaking-change detection has to read entry bodies, not titles or labels.
Upstream model deprecations are a recurring breaking-change source Deepgram does not control, and
they are exactly the kind of thing a developer misses.

## Coverage gap

The hosted **Flux TTS GA on 2026-08-12 has no changelog entry of its own.** It appears only in
passing inside the CLI 0.3.0 entry on 2026-08-19 ("which reached general availability on 12 August").
The changelog is not a complete record of launches, so a changelog-only show would have missed the
biggest launch of the quarter.

The show went changelog-only anyway, and says so: see Launches in `docs/show-format.md`.

## Contact channels for the outro (from support.md)

- Discord: `dpgr.am/discord`
- GitHub Discussions: `github.com/orgs/deepgram/discussions`
- Status: `status.deepgram.com`
- Technical issues: `support@deepgram.com`, include the `dg-request-id` response header
- Account and billing: `success@deepgram.com`

## Catch-up count (added 2026-09-25)

Sunday-to-Saturday weeks with at least one entry, through Saturday 2026-09-19:

| Backfill from | Episodes | Calendar weeks |
| --- | --- | --- |
| First entry (2020-07-30) | 140 | 321 |
| 2025-01-01 | 65 | 90 |
| Trailing year (2025-09-21) | 45 | 52 |
| 2026-01-01 | 35 | 38 |

The week of 2026-09-20 to 09-26 already has entries (09-22, 09-24) and is the first live episode,
due Tuesday 2026-09-29.
