# ADR 0009: Realtime metadata and retention

## Status

Accepted

## Decision

PostgreSQL stores only the internal session UUID, HMAC installation hash,
provider/model, state, timestamps, duration and termination reason. Redis keeps
provider correlation, locks, rate counters and short-lived idempotency data.

Audio, transcript, SDP, prompt, provider call ID, IP and credentials are not
persisted in PostgreSQL or observability.

## Consequences

Operational lifecycle and cost can be analyzed without retaining conversation
content. Redis loss may reduce cleanup certainty, so provider duration limits
remain a required backstop.
