# ADR 0011: Ephemeral and consented pedagogical content

Status: accepted

## Decision

Processing consent is required before a mission. Text retention is disabled by default.
Completed transcripts needed for an active evaluation are encrypted with AES-256-GCM in
Redis and expire within 60 minutes. Redis messages and durable evidence contain internal
IDs and metrics, not transcript text.

If retention is enabled in a future environment, it requires an explicit consent,
versioned keyring, 30-day expiry, export and deletion behavior. The environment is not
ready while its configured content key is invalid.

Audio, PCM, SDP, provider call ID, full prompts, reasoning, IP address and raw
installation identifiers are prohibited from durable storage and logs.

## Consequences

A non-retained summary cannot quote the learner and must say that textual content is
unavailable. Reviews fall back to a generic fragile-skill prompt. Operational debugging
uses internal IDs, state transitions, sanitized error codes and aggregate usage.
