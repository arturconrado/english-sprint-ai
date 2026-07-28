# ADR 0010: Backend-authoritative deterministic pedagogy

Status: accepted

## Decision

The FastAPI orchestration domain is the authority for mission state and pedagogical
progress. Android and shared KMP use generated contracts and a pure reducer as a local
projection. OpenAI Realtime supplies media, transcription and tutor audio but cannot
advance a mission autonomously.

The canonical transition manifest generates equivalent Python and Kotlin definitions.
PostgreSQL records optimistic state versions and append-only evidence. Redis Streams
carry internal IDs to a bounded evaluator worker. Domain services do not depend on SQL,
WebRTC or OpenAI event classes.

## Consequences

Reconnection always reloads canonical state. Stale events are rejected by session,
attempt and state version. Evaluation variability is contained behind a strict schema;
ranking, correction count, retry, transfer, skill promotion and review scheduling are
deterministic policies.

This adds orchestration and worker complexity, but prevents a provider response or a
recreated Android process from silently advancing learning state.
