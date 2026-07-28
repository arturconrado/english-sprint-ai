# Production current-state audit

Snapshot date: 2026-07-23

Repository: `arturconrado/english-sprint-ai`

Default branch: [`main@142da2d`](https://github.com/arturconrado/english-sprint-ai/commit/142da2deea87ce7bc5ce96a7cde96e65c2561f17)

## Purpose and evidence policy

This audit records what can be demonstrated from code, tests, CI, repository
settings, and explicit evidence. Documentation alone is not treated as proof of
implementation. Automated tests do not substitute for an OpenAI provider run or
physical-device acceptance.

Status vocabulary:

- **Implemented**: production-intended code exists.
- **Automatically validated**: the relevant deterministic test or build passed.
- **Provider validated**: a real OpenAI workflow passed with protected credentials.
- **Physically validated**: the documented device and headset scenario was run.
- **Pending**: required work or evidence does not exist.
- **Blocked**: progress requires an external account, credential, person, or device.

## Repository and delivery state

| Item | Evidence | State |
|---|---|---|
| Private repository | GitHub repository metadata | Complete |
| Default branch | `main@142da2d` | Complete |
| Phase 0 validation | [CI run 30033197629](https://github.com/arturconrado/english-sprint-ai/actions/runs/30033197629) | Five checks passed |
| Phase 1 implementation | [Draft PR #16](https://github.com/arturconrado/english-sprint-ai/pull/16), HEAD `17f3d8c` | Implemented, not integrated |
| Phase 1 validation | [CI run 30041753611](https://github.com/arturconrado/english-sprint-ai/actions/runs/30041753611) | Contract, backend, Android, iOS, and security passed |
| Phase 2 | No branch, PR, contract, migration, or implementation | Pending |
| GitHub Issues | [Paid beta backlog #17–#36](https://github.com/arturconrado/english-sprint-ai/issues/36) | Complete for coordination; no product issues existed at audit start |
| GitHub environments | No environments configured | Pending |
| Repository secrets | No Actions secrets configured | Blocked |
| Releases and deployments | No release or deployment records | Pending |
| `main` protection | Unavailable for this private repository on the current GitHub plan | Accepted operational risk |

The Phase 1 workflow proves compilation and automated behavior on its draft
branch. It does not prove that the work is present on `main`.

## Capability matrix

| Capability | Source | Implemented | Automated | Real provider | Physical device | Classification | Gap or evidence |
|---|---|---:|---:|---:|---:|---|---|
| KMP monorepo and Android/iOS shells | `main@142da2d` | Yes | Yes | N/A | No | Already complete | Phase 0 CI is green |
| Contract-first OpenAPI generation | `main@142da2d` | Yes | Yes | N/A | N/A | Already complete | Generation drift is checked in CI |
| FastAPI health and readiness | `main@142da2d` | Yes | Yes | N/A | N/A | Already complete | PostgreSQL, Redis, and migration head are exercised in CI |
| PostgreSQL and Redis development stack | `main@142da2d` | Yes | Yes | N/A | N/A | Already complete | Compose is development-only |
| Local OpenTelemetry collector | `main@142da2d` | Yes | Config checked | N/A | N/A | Already complete | No managed backend, dashboard, or alerting |
| Secret and dependency scanning | `main@142da2d` | Yes | Yes | N/A | N/A | Already complete | No branch protection enforcement |
| Realtime call contract and backend control plane | PR #16 | Yes | Yes | No | No | Needs validation | Merge, provider workflow, and production configuration remain |
| Sanitized voice-session metadata | PR #16 | Yes | Yes | No | No | Needs validation | No production retention or deletion exercise |
| Android WebRTC foreground service | PR #16 | Yes | Yes | No | No | Needs validation | Emulator tests do not prove media or background behavior |
| Bluetooth-only route policy | PR #16 | Yes | Unit/instrumented | No | No | Needs validation | HFP, BLE Audio, SCO legacy, and route recovery are untested physically |
| Screen-off 30-minute session | PR #16 | Intended | No | No | No | Needs validation | Evidence matrix is blank |
| Offline EN/PT voice controls | PR #16 | Yes | Unit-level | No | No | Needs validation | Accuracy, CPU, memory, battery, and false positives need devices |
| Barge-in below 300 ms p95 | PR #16 | Intended | Partial | No | No | Needs validation | Thirty physical samples are required |
| Real OpenAI Realtime E2E | PR #16 workflow | Harness exists | Not run | No | N/A | Blocked | `OPENAI_API_KEY` is absent and workflow is not on `main` |
| SPEAK mission loop | None | No | No | No | No | Required before private beta | Phase 2 has not started |
| Structured evaluation, retry, and transfer | None | No | No | No | No | Required before private beta | Phase 2 has not started |
| Skill Graph and spaced reviews | None | No | No | No | No | Required before private beta | Reviews at 24h/3d/7d are absent |
| Authentication and account lifecycle | None | No | No | N/A | No | Required before private beta | Installation ID is explicitly not authentication |
| Onboarding, diagnosis, and seven-day plan | None | No | No | No | No | Required before private beta | Product flow is absent |
| Professional launch mission catalog | None | No | No | No | No | Required before private beta | Introduction, technical project, and behavioral missions are absent |
| User progress and resume | None | No | No | N/A | No | Required before private beta | No user-scoped persistence exists |
| Consent, privacy export, and account deletion | None | No | No | N/A | No | Required before private beta | No user identity or data-rights workflow exists |
| Staging environment | Placeholder only | No | No | N/A | N/A | Required before private beta | GCP project and credentials are external blockers |
| Production environment and recovery | Placeholder only | No | No | N/A | N/A | Required before paid beta | Terraform, backups, restore, and rollback are absent |
| Subscription and entitlement | None | No | No | N/A | No | Required before paid beta | Play Console and RevenueCat are external blockers |
| Monthly voice-minute quota | None | No | No | N/A | No | Required before paid beta | Server-authoritative ledger is absent |
| Play listing and closed track | None | No | No | N/A | No | Required before paid beta | Account, merchant profile, signing, and testers are blocked |
| Production observability and Android crash reporting | Interfaces/local collector only | No | No | N/A | No | Required before private beta | No managed telemetry, dashboard, alert, or Crashlytics project |
| Support and minimal operations | None | No | No | N/A | N/A | Required before private beta | Domain, support channel, and operator process are blocked |
| Privacy-safe acquisition analytics | Interface only | No | No | N/A | No | Required before private beta | Consent-aware event implementation is absent |

## Validation constraints

The current workstation has JDK 17 and Swift, but no complete Xcode toolchain,
Android SDK/ADB, or Docker daemon. GitHub Actions is therefore the canonical
cross-platform evidence source. The audit uses the successful immutable CI runs
above instead of pretending that unavailable local tools ran successfully.

The manual Realtime workflow must not be run until a protected
`OPENAI_API_KEY` exists. Physical evidence must identify the device, Android
version, headset/profile, build SHA, procedure, measurement, and result.

## Required report categories

### Already complete

- Phase 0 foundation on `main`, including deterministic contracts and five-part CI.
- Phase 1 implementation and automated validation on its draft branch.

### Needs validation

- Human integration of PR #16 and clean-clone validation from updated `main`.
- OpenAI Realtime E2E with protected credentials.
- Physical Bluetooth, screen-off, duration, barge-in, recovery, battery, and thermal evidence.

### Required before private beta

- Phase 2 learning loop, authentication, onboarding, diagnosis, adaptive plan,
  launch missions, reviews, progress, staging, data rights, observability,
  support, and consented analytics.

### Required before paid beta

- Production recovery, RevenueCat/Play subscription, minute quota, legal review,
  Data Safety, signed closed-track release, and paid cohort operations.

### Can be deferred

- iOS voice, advanced phonetics, sophisticated RAG, multiple agents, enterprise
  plans, advanced gamification, and an advanced admin console.

### Blocked

- Provider and platform credentials, Play merchant setup, domain and support
  address, legal reviewer, beta testers, and representative physical devices.
