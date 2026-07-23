# ADR 0005: Foreground service owns Android voice

## Status

Accepted

## Decision

An explicit, non-sticky foreground service owns WebRTC, routing, audio focus,
MediaSession, notification, wake lock, local recognition and cleanup. The UI
does not own a call and no boot receiver restarts it.

## Consequences

Screen-off operation can continue while Activity recreation is harmless.
Every start must originate while the app is visible and permissions are valid.
