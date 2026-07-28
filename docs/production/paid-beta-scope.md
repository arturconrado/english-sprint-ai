# Paid closed beta scope

## Audience and outcome

The launch serves Brazilian technology professionals preparing to communicate
in English at work. The product outcome is a focused seven-day practice sprint,
not a language certification or general-purpose English course.

The initial cohort is invite-only, Android-only, and limited to 30 paying
subscribers.

## Minimum user journey

1. Sign in with Google through Firebase Authentication.
2. Review processing, privacy, analytics, and notification choices.
3. Complete an approximately ten-minute voice diagnosis.
4. Select a professional goal and receive a seven-day plan.
5. Complete daily voice missions using a bidirectional Bluetooth headset.
6. Receive grounded correction, one retry, and a transfer attempt.
7. Complete reviews at approximately 24 hours, 3 days, and 7 days.
8. View minutes, completed missions, retries, practiced skills, retained skills,
   and the next review without a pseudo-scientific global score.
9. Manage subscription, export data, and delete the account.
10. Contact support from the app.

## Launch content

The seven-day plan may reuse and vary a small, versioned catalog, but it must
cover at least:

- professional introduction;
- career history;
- explanation of a technical project;
- explanation of an architecture decision;
- behavioral interview question;
- international meeting scenario;
- final simulation.

The acceptance set must explicitly exercise professional introduction,
technical project, and behavioral question missions.

## Commercial offer

| Item | Beta decision |
|---|---|
| Product | One monthly Google Play subscription |
| Price hypothesis | R$49.90 per month |
| Entitlement | One RevenueCat entitlement for paid beta access |
| Included voice usage | 120 active voice minutes per billing cycle |
| Promotional diagnosis | One ten-minute diagnosis per verified account before paywall |
| Overage | None |
| Quota behavior | Server-authoritative hard stop with a clear recovery message |
| Cohort cap | 30 paid subscribers |
| Trials and annual plans | Deferred |
| Refunds and cancellation | Google Play lifecycle with documented support path |

The offer is a testable commercial hypothesis. It may change only after measured
provider cost, store fees, tax, support load, and conversion are recorded. Usage
must never be unlocked solely from client state.

## Technical platform decisions

- Android remains the only voice platform in the beta.
- GCP region is `southamerica-east1`.
- Firebase Authentication provides Google Sign-In; the backend maps the managed
  identity to an internal user UUID.
- Firebase Crashlytics and consent-aware Firebase Analytics provide the initial
  mobile operational and funnel signals.
- RevenueCat manages Play subscription lifecycle and exposes one entitlement;
  the backend remains authoritative for user access and minute consumption.
- FastAPI, workers, PostgreSQL, Redis, secrets, artifacts, telemetry, backups,
  and rollback run in isolated development, staging, and production contexts.

## Privacy and safety boundary

- Do not persist audio, PCM, SDP, provider call IDs, full prompts, reasoning, IP
  addresses, or raw installation identifiers.
- Content retention remains off by default. Any opted-in content retention is
  encrypted, purpose-limited, and expires according to the reviewed policy.
- Analytics and crash reporting exclude audio, transcripts, tutor instructions,
  authentication tokens, and raw personal identifiers.
- Account deletion is available in-app and through a public web resource.
- Payment state, safety audit records, and fraud-prevention records may be
  retained only when the reviewed policy establishes a lawful need.

## Required operational experience

- Bidirectional Bluetooth only; no speaker, earpiece, or output-only A2DP
  fallback.
- Session remains functional with the screen off.
- Foreground notification supports pause/resume and end.
- Route loss silences input and output immediately and performs bounded recovery.
- Network and provider retries are bounded and observable.
- Support can locate account state, entitlement, consumption, deletion state,
  session metadata, and sanitized errors without seeing conversation content.

## Explicitly deferred

- iOS voice.
- Companion Mode, Siri, and long-running passive audio.
- Advanced phonetic or accent scoring.
- Hundreds of missions, sophisticated RAG, and multiple agents.
- Enterprise plans, annual subscriptions, add-on minute packs, and web billing.
- Advanced gamification and an advanced administrative console.

## Scope-change rule

A proposed addition must demonstrate that it blocks the minimum learning
journey, safety, LGPD, Play policy, payment correctness, reliability, or support.
Otherwise it is deferred until paid-beta evidence exists.

## Current policy and pricing references

- [Google Play Data Safety](https://support.google.com/googleplay/android-developer/answer/10787469)
- [Google Play account deletion requirements](https://support.google.com/googleplay/android-developer/answer/13327111)
- [Testing requirements for new personal accounts](https://support.google.com/googleplay/android-developer/answer/14151465)
- [GPT-Realtime-2.1 mini model and pricing](https://developers.openai.com/api/docs/models/gpt-realtime-2.1-mini)
- [RevenueCat pricing](https://www.revenuecat.com/pricing)

These external rules and prices must be rechecked at implementation and launch;
the links are evidence sources, not immutable product assumptions.
