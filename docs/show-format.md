# Show format

Canonical spec for the weekly changelog podcast (decided 2026-09-25). Show name for now: **The Deepgram Changelog** (renamed 2026-09-25 from "The Deepgram
Changelog Readback"). A fork swaps in its own company name. It is served from
`dg-devrel-deepgram-changelog.fly.dev`; the first deploy briefly lived at
`dg-devrel-changelog-readback.fly.dev`.

## Schedule

| Thing | Rule |
| --- | --- |
| Coverage window | Sunday through Saturday |
| Buffer | Monday. Nothing is scheduled there, it absorbs late entries and fixes. |
| Release | Tuesday |
| Empty week | No episode. Last 30 weeks had one. |

Example: the week of 2026-09-13 to 2026-09-19 releases Tuesday 2026-09-22.

## Running order

1. Intro (canned)
2. Breaking changes and action required
3. Launches
4. Quick hits
5. Voice Agent
6. Speech-to-Text
7. Text-to-Speech
8. Developer experience
9. Outro (canned)

**General rule: a segment with nothing in it is omitted.** The show never says "nothing in this
segment this week." It just moves on.

**Each item airs once**, in the first segment it qualifies for. A later segment can point back to
it in one clause, never re-explain it.

## Editorial rule

High level. Each item is what changed, why it matters to someone building on it, and which docs
page to read. That is usually two to four sentences. No method names, parameter lists, or code
walkthroughs: the docs link does that job. No commentary on how Deepgram shipped or documented
something. If an identifier has to be spoken (a field name in a breaking change), check it with
`scripts/term_test.py` first.

## Segment announcements

Every segment opens by naming itself, then goes straight into its lead item:

| Segment | Opener |
| --- | --- |
| First segment after the intro | "First up, {segment name}." |
| Breaking changes | "breaking changes and action required. There are {n} this week." |
| Launches | "On to launches." |
| Quick hits | "Now some quick hits." |
| Voice Agent | "Over to Voice Agent." |
| Speech-to-Text | "Next, speech-to-text." |
| Text-to-Speech | "On the text-to-speech side," |
| Developer experience | "And to close, developer experience." |

Whichever segment comes first uses "First up," so an episode with no breaking changes still opens
cleanly.

When a segment belongs to a desk voice (see Voice), the handoff replaces the opener. The outgoing
voice closes its segment by naming the next voice and segment in one pattern: "{Voice} has the
{segment} updates next." (for example "Cole has the text-to-speech updates next."). Launches use
"Drew has this week's launches.", and a desk voice handing back says "Back to you, Brooke." The incoming voice opens with "Thanks,
{previous voice}." and goes straight into the item. The last desk segment ends with "Back to you,
Brooke.", and the anchor opens the outro with "Thanks, {last voice}." Handoffs always name the
voice that actually speaks next, so they are written after the week's segments are known.

## Segment rules

**Breaking changes and action required.** Classified from the entry body, never the title, because
the changelog does not label these consistently (the 2-hour Voice Agent session limit on
2026-07-31 was never called breaking). Qualifies if a developer has to do something or something
they rely on stops working:

- a removed or renamed parameter, field, model, constant, or endpoint
- a response shape change
- a new hard limit or required config
- an SDK release marked breaking
- a deprecation with a date, including upstream LLM retirements

Each item states what breaks, who it hits, and the one thing to do.

**A docs change is never a breaking change.** Documentation cannot break anyone's code. A docs
correction goes under Developer experience, even when the old docs were wrong in a way that
mattered. It only belongs here if the thing the docs describe changed in a breaking way, and then
the item is that product change, not the docs edit.

**Launches.** Sourced from the changelog alone (decided 2026-09-25). An entry is a launch when it
introduces a new model, product, or API, or announces general availability of one. Regional
endpoints and self-hosted releases are quick hits. A launch with no changelog entry (Flux TTS GA
on 2026-08-12 was one) does not air; the fix for that belongs in the changelog, not the show.

**Quick hits.** Short, one to three sentences each. Nova-3 language and accuracy updates, regional
endpoints, self-hosted releases, anything GA-shaped that is not a new model, product, or API. Language roundups
collapse into one line per entry ("nine languages improved, no code change").

**Voice Agent, Speech-to-Text, Text-to-Speech.** What changed, what it means for someone building
on it, and the docs page to read. Flux STT goes under Speech-to-Text, Flux TTS under
Text-to-Speech.

**Developer experience.** The closer. SDK releases, CLI, `@deepgram/react`, docs restructures,
and every docs correction.

## Links

The voice names the docs page ("the Regional Endpoints page"), never reads a URL beyond the bare
domain. Every link goes in the show notes, in segment order.

## Canned intro

Only the dates change.

> Hello, this is {host} with The Deepgram Changelog. Changelogs from the week of {start}
> to {end}, {year}. Links to every docs page mentioned are in the show notes.

The year is always said ("September nineteenth, twenty twenty six"), and a monthly show says the
month and year ("July twenty twenty six"), so an episode heard years later still says when it was.

## Canned outro

> That's the week. This episode was voiced start to finish by Deepgram Flux TTS, and rendering it
> cost {cost}, at the pay as you go rate. Looking to start building with Deepgram? New Console
> accounts start with a two hundred dollar credit, which covers more than {episodes} episodes like this one.
>
> {promo}
>
> Need more help, or have questions about anything in today's episode? Email support at deepgram
> dot com and include the dg request ID header from the failing response, it's the fastest way to
> get a fix. For questions and a second pair of eyes, find us on Discord at D P G R dot A M slash
> discord, or in GitHub Discussions under the Deepgram org. If you think something's down, check
> status dot deepgram dot com first. The full changelog can be found at developers dot deepgram dot com
> slash changelog. See you next Tuesday!

### Outro variables

- `{cost}`: Flux TTS list price for the spoken characters of this episode, at the Pay As You Go rate
  (`$0.045` per 1k characters as of 2026-09-25). Computed after the script is final, because the
  cost line is itself part of the spoken text. HN Radio's `pricing.episode_cost` already does this.
- `{episodes}`: `$200 / cost`, **rounded down** to a multiple of 25 and said as "more than N," so
  the claim is always true. Say 1,175 as "eleven hundred seventy five", the way a person would.
- `{promo}`: the Flux TTS credit match, aired only through 2026-12-31, then dropped:

  > As a bonus through December thirty first of this year, every dollar you spend on Flux TTS is
  > matched with a dollar in bonus credits, up to five hundred dollars per project. What you earn
  > never expires, and it works on any Deepgram API in that project. It's open to Pay As You Go and
  > Growth projects, and the full terms are in the show notes.

  Source: `deepgram.com/promotions/2026-09/flux-tts-promo-terms-and-conditions`, read 2026-09-25.
  It's use a dollar, get a dollar, **not** deposit a dollar. Facts the line rests on: paid Flux TTS
  usage only (1.2), no match on usage paid with the signup credit or with bonus credits (3.2), $500
  cap per project, not per account (2.3), never expires (3.4), spendable on any later Deepgram API
  usage in the same project (3.3, 3.6), Pay As You Go and Growth only, Enterprise excluded (2.1,
  2.4). Runs 2026-09-15 to 2026-12-31. The terms say grants land "typically within 1 week" (3.1),
  and the show doesn't promise a day either.

## Pronunciation

Scripts keep real spellings. Words Flux misreads are respelled only in the text sent to
`/v2/speak`, via `SPOKEN_FORMS` in `scripts/render_episode.py`, and the episode page says so.
Current list: "changelog" becomes "change log" (misread as "changegog" in 2 of 4 test renders on
2026-09-25, correct in 4 of 4 as two words). An entry needs that kind of evidence, not a hunch.

## Voice

One anchor plus one fixed voice per product segment. The cast is the same every episode, so a
listener learns who covers what. Status: **confirmed by Sam 2026-09-25.** Machine-readable copy:
`docs/cast.json`, passed to the renderer with `--cast`.

| Role | Segments | Voice |
| --- | --- | --- |
| Anchor | Intro, Breaking, Quick hits, Outro | Brooke, `flux-brooke-en` |
| Launches desk | Launches | Drew, `flux-drew-en` |
| Voice Agent desk | Voice Agent | Kit, `flux-kit-en` |
| Speech-to-Text desk | Speech-to-Text | Miles, `flux-miles-en` |
| Text-to-Speech desk | Text-to-Speech | Cole, `flux-cole-en` |
| Developer experience desk | Developer experience | Elise, `flux-elise-en` |

Handoffs are one short line each way, so the show stays a show and not a relay:

- The outgoing voice hands off by name: "Kit has the Voice Agent updates next."
- The desk voice opens with "Thanks, Brooke." and goes straight into the item.
- Whoever has the last product segment ends with "Back to you, Brooke." before the outro.
- An omitted segment's voice simply does not appear that week.

Every voice renders at **expressivity 1** ("a little more" animated than the tuned default), picked by
ear from a five-way comparison of -2 through 2. It is a beta parameter, so
re-check it when Flux ships a model update.

Every voice gets its own `scripts/term_test.py` run, because pronunciation varies by voice.

## Sources

| Source | Used for |
| --- | --- |
| `developers.deepgram.com/changelog.rss` | Change detection, new GUIDs |
| `developers.deepgram.com/changelog/YYYY/M/D.md` | Entry bodies the writer reads |
| `developers.deepgram.com/support.md` | Outro contact channels |
