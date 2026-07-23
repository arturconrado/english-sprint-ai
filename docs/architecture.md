# English Sprint AI architecture

## Direction

English Sprint AI is an Android-first Kotlin Multiplatform product. Roughly
75–85% of domain, state, networking, persistence boundaries, analytics, feature
flags, and reusable UI should live in shared code. Audio, Bluetooth, background
execution, billing, notifications, and secure storage remain native.

The backend uses Python and FastAPI with PostgreSQL, pgvector, Redis, WebRTC, and
cost-aware AI providers. Realtime media should flow directly between the client
and the voice provider; the backend keeps a sideband control channel for
pedagogy, memory, permissions, usage, and audit.

## AI efficiency

The system separates local deterministic behavior, backend rules, economical
realtime inference, selective advanced inference, and asynchronous evaluation.
Local commands, timers, audio-route handling, cached review, and business rules
must not require an LLM.

The long-term router should keep at least 85% of turns on the economical path,
record every model decision, compact context, and avoid unconditional
transcription or retrieval.

## Delivery phases

1. Multiplatform foundation with Android, iOS, shared contracts, backend, CI,
   observability, environments, feature flags, and provider interfaces.
2. Android audio spike covering microphone, playback, Bluetooth, foreground
   service, screen-off operation, WebRTC, barge-in, and route loss.
3. Product vertical slice from login through a completed and persisted session.
4. AI efficiency, pedagogy, career mode, full iOS native integrations, and
   commercial operations.

The first technical product gate is a ten-to-fifteen-minute Android conversation
over Bluetooth with the screen off, interruption, correction and retry,
headset disconnect/reconnect, verbal completion, and persisted progress.
