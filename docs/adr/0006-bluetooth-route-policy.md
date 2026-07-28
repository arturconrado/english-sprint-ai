# ADR 0006: Private Bluetooth communication route

## Status

Accepted

## Decision

Only a bidirectional Bluetooth communication device is valid. API 31+ uses
`setCommunicationDevice`; API 26–30 uses `startBluetoothSco` behind one adapter.
Speaker, earpiece and output-only A2DP are never automatic fallbacks.

## Consequences

Route loss pauses the session and begins a bounded recovery window. Failure
terminates the call rather than exposing conversation audio.
