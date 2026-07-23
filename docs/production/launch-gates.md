# Production launch gates

No gate passes through intention or documentation alone. Each checked item must
link an immutable commit, CI run, provider run, physical test record, cloud
record, store record, or written approval.

Status values: `not started`, `in progress`, `passed`, `failed`, `blocked`.

## Gate 0 — Integrated Voice Baseline

| Requirement | Initial status | Owner | Required evidence |
|---|---|---|---|
| PR #16 is squash-merged by a human | Blocked | `@arturconrado` | Merge commit on `main` |
| Contract, backend, Android, iOS, and security pass on integrated HEAD | Not started | `@arturconrado` | Successful workflow URL |
| Clean clone reproduces the validation | Not started | `@arturconrado` | Commands, environment, SHA, and results |
| Contract generation has no drift | Passed on draft only | `@arturconrado` | Integrated contract check |
| No credential or forbidden file is versioned | Passed on draft only | `@arturconrado` | Integrated security check |

Exit decision: all requirements are `passed`.

## Gate 1 — Instrumented Private Beta

### Product

| Requirement | Initial status | Owner | Required evidence |
|---|---|---|---|
| Firebase login, logout, persistence, revocation, and deletion | Not started | `@arturconrado` | Automated auth and isolation tests |
| Consent and onboarding complete before voice processing | Not started | `@arturconrado` | UI/domain tests and staging evidence |
| Ten-minute diagnosis produces a bounded profile | Not started | `@arturconrado` | Eval harness and end-to-end test |
| Seven-day plan covers the launch scenarios | Not started | `@arturconrado` | Versioned seeds and deterministic tests |
| Mission supports correction, retry, and transfer | Not started | `@arturconrado` | SPEAK state-machine and integration tests |
| Reviews schedule at 24h, 3d, and 7d | Not started | `@arturconrado` | Clock-controlled tests |
| Progress and resume use canonical backend state | Not started | `@arturconrado` | Recreation and cross-device/session tests |

### Voice acceptance

| Requirement | Initial status | Owner | Required evidence |
|---|---|---|---|
| Real OpenAI WebRTC and sideband pass | Blocked | Founder/account owner | Protected workflow URL |
| API 26–30 legacy SCO path passes | Blocked | Founder/device tester | Device/headset evidence |
| API 31–32 communication-device path passes | Blocked | Founder/device tester | Device/headset evidence |
| API 33–36 permissions and foreground behavior pass | Blocked | Founder/device tester | Device/headset evidence |
| Screen-off session runs for 30 minutes | Blocked | Founder/device tester | Timed run with build SHA |
| Bluetooth loss never falls back to speaker | Blocked | Founder/device tester | Route-loss recording and logs |
| Barge-in p95 is below 300 ms over 30 samples | Blocked | Founder/device tester | Raw sanitized measurements |
| Battery, memory, CPU, and thermal behavior are acceptable | Blocked | Founder/device tester | Device measurements and threshold decision |

### Platform, privacy, and operations

| Requirement | Initial status | Owner | Required evidence |
|---|---|---|---|
| Staging is isolated, TLS-enabled, and reproducible | Blocked | Founder/platform owner | Terraform and deployment record |
| PostgreSQL, Redis, migrations, and worker readiness pass | Not started | `@arturconrado` | Staging smoke test |
| Export and account deletion complete end to end | Not started | `@arturconrado` | Automated test and staging deletion record |
| Logs and analytics exclude prohibited content | Not started | `@arturconrado` | Redaction tests and sampled fields |
| Crash, API, provider, queue, and cost monitoring are visible | Not started | Founder/platform owner | Dashboards and test alerts |
| Support path and incident ownership are published | Blocked | Founder | Working contact and runbook |

Exit decision: every row is `passed`; billing remains disabled.

## Gate 2 — Paid Closed Beta

### Commerce and quota

| Requirement | Initial status | Owner | Required evidence |
|---|---|---|---|
| Play merchant and RevenueCat projects are verified | Blocked | Founder/account owner | Account status without secret values |
| Purchase and restore grant the correct entitlement | Not started | `@arturconrado` | Licensed tester transactions |
| Cancellation, expiry, grace period, and billing issue are handled | Not started | `@arturconrado` | Sandbox lifecycle evidence |
| Authenticated webhooks are idempotent and reconcile state | Not started | `@arturconrado` | Replay and out-of-order tests |
| Monthly minutes cannot be overspent concurrently | Not started | `@arturconrado` | Concurrency and recovery tests |
| Hard stop and renewal behavior are clear to the user | Not started | `@arturconrado` | UI/instrumented tests |
| Unit economics fit the approved offer | Not started | Founder | Provider, store, tax, and support cost review |

### Production and compliance

| Requirement | Initial status | Owner | Required evidence |
|---|---|---|---|
| Production is isolated from development and staging | Blocked | Founder/platform owner | GCP project and IAM review |
| Immutable deploy, migration, smoke test, and rollback pass | Not started | Founder/platform owner | Production rehearsal |
| Backup and point-in-time restore pass | Not started | Founder/platform owner | Timestamped restore drill |
| Privacy Policy, Terms, retention, vendors, and transfers are reviewed | Blocked | Legal reviewer | Written legal approval |
| In-app and public-web account deletion paths work | Not started | `@arturconrado` | Store URL and deletion exercise |
| Play Data Safety matches measured application behavior | Not started | Founder | Submitted form and verification checklist |
| Signed AAB and closed-track rollout pass | Blocked | Founder/account owner | Play release record |
| Applicable tester-duration requirement is satisfied | Blocked | Founder | Play Console eligibility evidence |
| Support, incident, refund, and deletion procedures are staffed | Blocked | Founder | Dry run and published contact |

### Cohort and go/no-go

| Requirement | Initial status | Owner | Required evidence |
|---|---|---|---|
| At most 30 invited Brazilian technology professionals are enrolled | Not started | Founder | Consent-aware cohort count |
| Acquisition source and funnel are measurable without sensitive content | Not started | Founder | Analytics schema and dashboard |
| Private-beta critical incidents are closed | Not started | `@arturconrado` | Linked incident resolutions |
| Founder records the paid launch decision | Not started | Founder | Go/no-go issue with all evidence |

Exit decision: unanimous `passed` status for all blocking rows. A `blocked`,
`failed`, or missing-evidence row is an automatic no-go.

Google Play requires a Data Safety declaration for apps on closed testing tracks
and requires both in-app and public-web account deletion paths when an app
supports accounts. For qualifying new personal developer accounts, production
eligibility additionally requires at least 12 continuously opted-in testers for
14 days. Recheck the current primary guidance before submission:

- [Data Safety](https://support.google.com/googleplay/android-developer/answer/10787469)
- [Account deletion](https://support.google.com/googleplay/android-developer/answer/13327111)
- [Personal-account testing](https://support.google.com/googleplay/android-developer/answer/14151465)

## Required final report

Every launch review must summarize:

### Already complete

Capabilities implemented, integrated, and supported by the required evidence.

### Needs validation

Implemented capabilities missing provider, physical, production, or operational evidence.

### Required before private beta

Open work that blocks any external test user.

### Required before paid beta

Open work that blocks accepting payment.

### Can be deferred

Work explicitly outside the closed-beta critical path.

### Blocked

Work awaiting an external account, credential, device, tester, or reviewer.
