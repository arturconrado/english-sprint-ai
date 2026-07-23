# Realtime voice threat model

## Assets and trust boundaries

Assets are the OpenAI API key, provider call IDs, session cost, microphone
media, anonymous installation identifiers and operational metadata. Trust
boundaries exist between Android and FastAPI, FastAPI and OpenAI, and FastAPI
and PostgreSQL/Redis.

## Threats and controls

| Threat | Control |
|---|---|
| Mobile key extraction | Permanent provider credentials exist only in backend environment variables. |
| Identifier correlation | The opaque installation UUID is HMAC-SHA256 hashed before persistence. |
| Replay and duplicate cost | Required UUID idempotency key, Redis creation lock and five-minute replay cache. |
| Anonymous endpoint abuse | One active call per installation and ten creations per hour. Authentication remains future work. |
| Oversized signaling | Strict `application/sdp`, UTF-8, 64 KiB maximum and basic SDP validation. |
| Provider identifier leakage | Call IDs exist only in TTL-bound Redis and are excluded from API responses and logs. |
| Sensitive observability | No audio, transcript, SDP, prompt, raw installation ID, IP, API key or provider call ID in logs/spans. |
| Orphaned paid calls | Explicit DELETE, provider hangup, sideband monitor, maximum duration, TTL and startup reconciler. |
| Speaker privacy leak | Bluetooth communication route is mandatory; route loss pauses and terminates instead of falling back. |
| Stale response playback | Buffered output is cancelled and cleared on interruption or session rebuild. |

The installation ID is not authentication and can be replaced by a malicious
client. Phase 1 rate limiting reduces accidental cost but does not replace
authenticated quotas, device attestation or an upstream gateway.
