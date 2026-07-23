# ADR 0008: OpenAPI 3.1 raw SDP wire format

## Status

Accepted

## Decision

The contract uses raw `application/sdp`; the internal UUID is returned through
`X-Voice-Session-Id` and a relative `Location`. Errors use sanitized
`application/problem+json`. Generated DTOs remain isolated behind a stable Ktor
facade because the generator currently serializes the raw SDP operation as JSON.

## Consequences

HTTP details do not enter shared domain models. Contract tests protect headers,
content types, route parity and deterministic generation.
