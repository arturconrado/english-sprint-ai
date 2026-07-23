# ADR 0003: WebRTC through the unified Realtime interface

## Status

Accepted

## Decision

Android sends an SDP offer to FastAPI. FastAPI creates the OpenAI call and
returns the SDP answer; media then flows directly between Android and OpenAI.
FastAPI keeps a server-side sideband WebSocket and terminates calls through the
provider hangup endpoint.

## Consequences

The permanent API key never enters the app. The backend remains responsible for
cost control and cleanup without proxying latency-sensitive audio.
