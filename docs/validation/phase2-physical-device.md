# Phase 2 physical-device acceptance

This matrix must contain measured results from real Android devices and bidirectional
Bluetooth routes. Blank evidence means pending and blocks removal of draft status.
Emulator evidence may validate lifecycle behavior but may not close a physical row.

| Area | Required coverage | Result | Evidence | Owner/date |
|---|---|---|---|---|
| Legacy Bluetooth | API 26–30, HFP/SCO microphone | Pending |  |  |
| Modern Bluetooth | API 31–32 communication device API | Pending |  |  |
| Current Android | API 33–36 communication device API | Pending |  |  |
| BLE Audio | Bidirectional microphone, when hardware is available | Pending |  |  |
| Background | Screen off for 30 minutes; notification controls remain usable | Pending |  |  |
| Barge-in | 30 samples; p95 below 300 ms | Pending |  |  |
| Offline commands | Stop/pause/resume/finish/repeat/time/help in EN and PT | Pending |  |  |
| Route recovery | Bluetooth loss and return; no speaker fallback | Pending |  |  |
| Network recovery | ICE restart, bounded recreation and stale-event rejection | Pending |  |  |
| Process lifecycle | Recreation, process death, uninstall and orphan cleanup | Pending |  |  |
| Pedagogy | Scenario, first attempt, correction, retry, transfer and summary | Pending |  |  |
| Review | Completion creates one review at `completed_at + 24h` | Pending |  |  |
| Privacy | No audio, SDP, provider ID or transcript in app/backend logs | Pending |  |  |
| Resources | Memory, CPU, battery and thermal state for a 30-minute session | Pending |  |  |

For every completed row, record device model, Android version, headset model/firmware,
build SHA, environment, exact procedure, raw measurement location and pass/fail
decision. Evidence must not contain audio, transcripts, credentials or provider call
IDs.

## Acceptance rule

Phase 2 remains a draft while the manual provider workflow or any applicable physical
row is pending. A failed row requires an issue and a new measured run; editing the result
to “pass” without execution is prohibited.
