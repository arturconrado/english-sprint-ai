# Production risk register

Probability and impact are qualitative because the project does not yet have
production or cohort data. A risk closes only with the evidence named below.

| ID | Risk | Probability | Impact | Owner | Early signal | Mitigation | Contingency | Closure evidence |
|---|---|---|---|---|---|---|---|---|
| R01 | Phase 1 remains outside `main` | Medium | Critical | `@arturconrado` | PR #16 stays draft or diverges | Preserve green HEAD and require human squash merge | Continue documentation/accounts only; block dependent code | Integrated `main` SHA and clean-clone run |
| R02 | Phase 2 scope delays the usable product | High | Critical | `@arturconrado` | No vertical mission completes end to end | Deliver deterministic SPEAK core before breadth | Reduce catalog, never remove correction/retry/transfer | End-to-end mission test and accepted PR |
| R03 | Physical Bluetooth/background behavior fails | High | Critical | Founder/device tester | Route, wake lock, or audio fails in early device checks | Test representative APIs and profiles before product expansion | Keep beta closed; narrow supported devices only with explicit evidence | Completed physical matrix |
| R04 | OpenAI provider behavior differs from fakes | Medium | Critical | `@arturconrado` | E2E schema, sideband, or cleanup failure | Add protected real-provider workflow and bounded cleanup | Disable Realtime and block beta | Successful provider workflow with sanitized metrics |
| R05 | Realtime unit cost breaks margin | Medium | High | Founder | Cost per active minute exceeds budget | Meter usage, cap output, enforce server quota, monitor model pricing | Reduce quota or response duration before adding users | Cohort unit economics reviewed |
| R06 | Play, merchant, or tester setup is late | High | Critical | Founder/account owner | Accounts remain unverified or tester roster is short | Start external setup before feature completion | Run private beta outside paid launch; do not charge | Verified Play/merchant status and eligible closed track |
| R07 | Legal/LGPD review blocks charging | High | Critical | Legal reviewer | No reviewer or unresolved data-flow questions | Prepare inventory, vendor register, terms, and deletion evidence early | Keep beta free until written review | Legal approval with tracked changes closed |
| R08 | Cross-track OpenAPI or migration conflicts | Medium | High | `@arturconrado` | Competing contract/migration branches | Track A owns product contract and serial migration order | Pause platform integration and rebase on integrated contract | Drift-free generation and one migration head |
| R09 | Identity, entitlement, or quota crosses users | Medium | Critical | `@arturconrado` | Auth-isolation or concurrency test fails | Server-side Firebase verification, internal UUIDs, idempotent ledger | Disable billing and voice creation | Cross-user and concurrent-quota tests pass |
| R10 | Production cannot recover from data loss or bad deploy | Medium | Critical | Founder/platform owner | Restore or rollback has never run | Automated backup, PITR, immutable artifacts, staged migrations | Halt release and restore last verified version | Timestamped restore and rollback drills |
| R11 | Logs or analytics expose sensitive content | Medium | Critical | `@arturconrado` | Transcript, token, SDP, or raw ID appears in telemetry | Allowlist structured fields and test redaction | Disable affected exporter and rotate exposed secrets | Redaction tests plus sanitized production sample |
| R12 | Solo ownership overloads three tracks | High | High | Founder | Review queues grow or multiple P0 tasks are in progress | Limit WIP and follow dependency gates | Pause noncritical work and finish the earliest blocker | Current milestone has one accepted exit decision |
| R13 | Unprotected `main` permits unsafe merge | Medium | High | `@arturconrado` | Direct push or unchecked merge | Draft PR, five checks, manual checklist, squash only | Revert through a new PR and audit branch history | Merge record satisfies manual policy |
| R14 | Vendor outage or lock-in blocks sessions | Medium | High | Founder/platform owner | Repeated provider or regional errors | Provider boundaries, timeouts, feature flags, exportable data | Pause new sessions and communicate incident; no fake fallback | Tested disable path and incident drill |

## Escalation rules

- Any Critical risk with a triggered early signal blocks the next launch gate.
- A failed provider or physical test blocks payments, even when automated CI is green.
- A failed identity, entitlement, deletion, restore, or redaction test blocks all
  external users until fixed and revalidated.
- An unresolved legal review blocks charging, not engineering-only private tests.
- Cost above the approved per-user budget triggers an offer/quota decision before
  recruiting more users.
- More than one conflicting OpenAPI or migration owner triggers immediate
  serialization of the affected work.

## Review cadence

Review this register at every milestone entry, every go/no-go decision, and after
any provider, privacy, billing, or availability incident. Update probability only
from observed evidence.
