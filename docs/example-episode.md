# The Deepgram Changelog, week of 2026-09-13 to 2026-09-19

**Summary:** Java SDK 0.10 ships a breaking change, Nova-3 Pharma launches, the India endpoint goes GA, app-controlled turn endings reach the Python, JavaScript, and Java SDKs, and two Browser Agent docs pages are corrected.

**Multi-voice.** Rendered with `--cast docs/cast.json`. Replaced the single-voice Brooke version as the main episode on 2026-09-25.

Experimental script, hand-written to test the format in `docs/show-format.md`. Releases Tuesday
2026-09-22. Everything under a segment heading is spoken. Show notes are at the bottom.

Segments in play: Breaking, Launches, Quick hits, Voice Agent, Text-to-Speech, Developer
experience. **Speech-to-Text is omitted** because its only item (Nova-3 Pharma) aired under
Launches.

Spoken length is 3,721 characters, about 4.3 minutes. At $0.045 per 1k characters that is $0.17,
and $200 covers 1,194 episodes (said as "more than eleven hundred seventy five").

---

## Intro

Hello, this is Brooke with The Deepgram Changelog. Changelogs from the week of September
thirteenth to September nineteenth. Links to every docs page mentioned are in the show notes.

## Breaking changes and action required

First up, breaking changes and action required. There's one this week. The Java SDK, version zero
point ten, changes how you set speech speed, and that's a breaking change. Check the migration
guide before you upgrade.

Drew has this week's launches.

## Launches

Thanks, Brooke. Nova-3 Pharma is out. It's a new speech-to-text model tuned for pharmaceutical
vocabulary, especially drug names, and it's aimed at pharmacy and healthcare voice agents. It's
English only, it works for both batch and streaming, and it's live on the hosted API now. The
Models and Languages Overview has the details.

That's the launch news. Back to you, Brooke.

## Quick hits

Thanks, Drew. Now some quick hits. The India endpoint is now generally available, for anyone who needs their
data processed inside India. It supports speech-to-text, text-to-speech, the Voice Agent API, and
Text Intelligence, and your existing API keys work with it. The Regional Endpoints page has the
URLs.

That's it for quick hits. Kit has the Voice Agent updates next.

## Voice Agent

Thanks, Brooke. Last month, Flux added a way for your app to end a user's turn itself, for
the moments you know they're done before the model does, like when someone lets go of a
push-to-talk button. That control is now built into the Python, JavaScript, and Java SDKs. The
Flux turn-taking docs cover how it works.

Cole has the text-to-speech updates next.

## Text-to-Speech

Thanks, Kit. On the text-to-speech side, two Flux TTS controls are now in the SDKs. Expressivity sets how calm or
animated a voice sounds inside a Voice Agent. And the wider speed range from August, from half
speed up to one and a half times, is now available in the Python, JavaScript, and Java SDKs. The
Expressivity page has the details.

Elise has the developer experience updates next.

## Developer experience

Thanks, Cole. To close things out, developer experience. New SDK versions are out: Python seven point nine, JavaScript
five point eleven, and Java zero point ten. They carry the Voice Agent and text-to-speech updates
you just heard about. Release notes for each one are in the show notes.

Two docs corrections, too. The example for creating short-lived tokens in the Browser Agent SDK
docs used the wrong field name for the token lifetime. The right field is TTL underscore seconds,
and the Token-Based Authentication guide has the corrected version. The Browser Agent SDK docs also
described client-side voice activity detection, which never shipped. Barge-in works, and it's
handled on the server. The Browser Agent pages now match what actually shipped.

That's developer experience. Back to you, Brooke.

## Outro

Thanks, Elise. That's the week. This episode was voiced start to finish by Deepgram Flux TTS, and rendering it
cost eighteen cents, at the pay as you go rate. Looking to start building with Deepgram? New Console accounts start with a two hundred dollar
credit, which covers more than eleven hundred twenty five episodes like this one.

As a bonus through December thirty first of this year, every dollar you spend on Flux TTS is
matched with a dollar in bonus credits, up to five hundred dollars per project. What you earn
never expires, and it works on any Deepgram API in that project. It's open to Pay As You Go and
Growth projects, and the full terms are in the show notes.

Need more help, or have questions about anything in today's episode? Email support at deepgram dot
com and include the dg request ID header from the failing response, it's the fastest way to get a
fix. For questions and a second pair of eyes, find us on Discord at D P G R dot A M slash discord,
or in GitHub Discussions under the Deepgram org. If you think something's down, check status dot
deepgram dot com first. The full changelog can be found at developers dot deepgram dot com slash
changelog. See you next Tuesday!

---

## Show notes

**Breaking changes and action required**

- [Java SDK v0.10.0 release](https://github.com/deepgram/deepgram-java-sdk/releases/tag/v0.10.0)
- [Java SDK v0.9 to v0.10 migration guide](https://github.com/deepgram/deepgram-java-sdk/blob/main/docs/Migrating-v0.9-to-v0.10.md)

**Launches**

- [Nova-3 Pharma changelog entry](https://developers.deepgram.com/changelog/2026/9/17)
- [Models & Languages Overview](https://developers.deepgram.com/docs/models-languages-overview#nova-3)

**Quick hits**

- [India endpoint GA](https://developers.deepgram.com/changelog/2026/9/15)
- [Regional Endpoints](https://developers.deepgram.com/reference/regional-endpoints)

**Voice Agent**

- [SDK releases, 2026-09-14](https://developers.deepgram.com/changelog/2026/9/14)
- [Force End Turn](https://developers.deepgram.com/docs/flux/force-end-turn)
- [Flexible turn-taking control for Flux, 2026-08-28](https://developers.deepgram.com/changelog/2026/8/28)
- [Bring Your Own Turn Detection](https://developers.deepgram.com/docs/flux/own-turn-detection)

**Text-to-Speech**

- [TTS Expressivity](https://developers.deepgram.com/docs/tts-expressivity)
- [Wider speed range for Flux TTS, 2026-08-31](https://developers.deepgram.com/changelog/2026/8/31)

**Developer experience**

- [Python SDK v7.9.0](https://github.com/deepgram/deepgram-python-sdk/releases/tag/v7.9.0)
- [JavaScript SDK v5.11.0](https://github.com/deepgram/deepgram-js-sdk/releases/tag/v5.11.0)
- [Java SDK v0.10.0](https://github.com/deepgram/deepgram-java-sdk/releases/tag/v0.10.0)
- [Correction: token lifetime uses `ttl_seconds`](https://developers.deepgram.com/changelog/2026/9/18)
- [Token-Based Authentication](https://developers.deepgram.com/guides/fundamentals/token-based-authentication)
- [Correction: Browser Agent SDK has no client-side VAD](https://developers.deepgram.com/changelog/2026/9/18)
- [Browser Agent JavaScript SDK](https://developers.deepgram.com/docs/browser-agent-javascript)

**Credits and pricing**

- [Deepgram pricing](https://deepgram.com/pricing)
- [Flux TTS credit match terms](https://deepgram.com/promotions/2026-09/flux-tts-promo-terms-and-conditions)
- [Sign up for Console](https://console.deepgram.com)

**Get in touch**

- [Discord](https://dpgr.am/discord)
- [GitHub Discussions](https://github.com/orgs/deepgram/discussions)
- [status.deepgram.com](https://status.deepgram.com)
- [support@deepgram.com](mailto:support@deepgram.com)

---

## Writer's notes (not spoken)

- **India endpoint went to Quick hits, not Launches.** A regional endpoint going GA is a quick hit
  under the launch rule in `docs/show-format.md`. If regional GAs should count as launches, the rule
  needs a second path.
- Rewritten 2026-09-25 to stay high level: what changed, why it matters, where to read more. No
  method names, and no commentary on how the changes were shipped.
- Pronunciation choices come from `scripts/term_test.py` (see `docs/key-terms.json`): "TTL" in caps,
  "D P G R dot A M". "Minting" and "force end turn" are phrased around, not respelled.
