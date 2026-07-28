# ADR 0004: Realtime provider and model registry

## Status

Accepted

## Decision

Provider integration is behind `RealtimeProvider`, `ModelRegistry`,
`SessionConfig`, `SessionFactory` and `UsageObserver`. Phase 1 selects OpenAI,
`gpt-realtime-2.1-mini`, voice `marin` and configurable server VAD.

## Consequences

The deprecated `gpt-realtime-mini` is not used. Provider wire details remain
outside routes and domain models, while a future provider can implement the
same lifecycle contract.
