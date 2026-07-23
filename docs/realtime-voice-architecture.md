# Realtime voice architecture

## Media and control paths

The Android app creates an audio-only WebRTC offer and sends only that SDP to
`POST /v1/realtime/calls`. FastAPI combines the offer with the server-owned
session configuration and authenticates to OpenAI. The SDP answer returns to
Android, after which encrypted media flows directly between Android and OpenAI.

FastAPI retains the provider call ID from the upstream `Location` header in
Redis. It opens a sideband WebSocket before returning success, observes usage
and lifecycle events, and can hang up the provider call. The provider call ID,
API key, SDP, audio and conversation content are never returned by operational
endpoints or written to application logs.

## Android ownership

`VoiceSessionService` is the single owner of the active call. It is an explicit,
non-sticky foreground service with microphone and media-playback types. The
Activity and notification send commands into the same service. The shared
reducer owns platform-independent session transitions; Android owns WebRTC,
audio focus, Bluetooth routing, MediaSession, notification, wake lock and Vosk.

Only bidirectional Bluetooth communication devices are accepted. API 31 and
newer use `setCommunicationDevice`; API 26–30 use the isolated SCO adapter.
Loss of the route pauses both directions and never falls back to speaker.

The WebRTC audio-device callback copies PCM into a bounded, drop-oldest channel.
Two grammar-restricted Vosk recognizers consume resampled 16 kHz mono audio for
English and Portuguese commands without provider transcription.

## Recovery and cleanup

- ICE receives one direct restart, followed by one complete session rebuild.
- Bluetooth receives three recovery attempts over fifteen seconds.
- Every local object has an explicit close path.
- Client cleanup is best-effort; Redis TTL, the 30-minute limit and startup
  reconciliation cover process death and orphaned provider calls.
- The backend currently runs one application worker because an active sideband
  WebSocket is process-owned. Horizontal sideband ownership is deferred.

## Local development

Set `ENGLISH_SPRINT_API_BASE_URL` in untracked `local.properties` to a LAN URL
for a physical device. Debug builds permit cleartext local traffic; release
builds require HTTPS. Realtime remains disabled until backend environment
variables and a server-side `OPENAI_API_KEY` are supplied.
