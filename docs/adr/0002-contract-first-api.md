# ADR 0002: Contract-first HTTP API

## Status

Accepted.

## Decision

`contracts/openapi.yaml` is the only HTTP contract source. Python and Kotlin
transport models are generated deterministically. FastAPI's automatic OpenAPI
document is disabled, and runtime conformance tests validate routes and
responses against the versioned contract.

Generated DTOs remain transport details. Stable facades map them to independent
domain models before exposing data to application logic.
