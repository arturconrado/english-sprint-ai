# Phase 2 SPEAK loop

## Delivery status

The implementation on `feat/phase-2-speak-loop` is an integration candidate, not
production acceptance. Contract, state-machine, backend, shared and Android evidence
is automated. The OpenAI workflow and the physical-device matrix remain pending until
they are executed with protected credentials and real hardware.

No provider or physical result may be inferred from unit tests, fake providers, an
emulator, or this document.

## Runtime architecture

```text
Android foreground service ── WebRTC media ──> OpenAI Realtime
          │                                      │
          │ mission HTTP commands                │ sideband events
          v                                      v
    FastAPI mission controller <── Redis Streams evaluator worker
          │
          └── PostgreSQL evidence, skills, reviews and sanitized usage
```

The backend owns canonical mission state. The common KMP reducer is a deterministic
projection for UI and service behavior. A mission call uses `server_vad` with
`create_response=false`; only backend sideband commands may present the scenario,
correction, transfer question or summary.

Completed transcription events are encrypted in Redis for at most 60 minutes and
correlated to the current attempt. Redis Stream messages contain only internal attempt
IDs. The evaluator retries once, then moves the attempt to dead letter and advances
through the explicitly defined unevaluated path. It never invents a correction after a
provider failure.

## Deterministic sources

- HTTP: `contracts/openapi.yaml` (OpenAPI 3.1).
- Mission transitions: `contracts/pedagogy/mission-state-machine.json`.
- Evaluation wire format: `contracts/pedagogy/evaluation-1.0.schema.json`.
- Mission content: versioned JSON under `missions/`.
- Evaluation instructions: metadata and template under `prompts/evaluation/`.
- Operational model-price estimates: the versioned pricing catalog in the pedagogy
  package. It is an estimate, never an invoice.

`scripts/verify-contracts` regenerates Python, Kotlin, mission-state sources and prompt
manifests, then rejects drift. Generated files are not edited manually.

## Privacy and authorization

Mission creation returns a 256-bit token once. Only its SHA-256 hash is persisted. The
Android client encrypts the token with an AES-GCM key held by Android Keystore. A mission
token authorizes only its session and pseudonymous user; the Realtime call validates the
mission association before linking both internal records.

Audio, PCM, SDP, provider call ID, complete prompts, chain-of-thought, IP address and raw
installation ID are not persisted. Text retention is off by default. The current
summary explicitly reports that textual content is unavailable when consented retention
was not enabled.

## Automated evidence

The standard five CI jobs remain uniquely named `contract`, `backend`, `android`, `ios`
and `security`.

- Backend tests use real PostgreSQL and Redis in CI, apply all migrations and exercise
  deterministic fake HTTP/WebSocket/Responses providers.
- The offline evaluation harness contains 40 synthetic, authorized cases. It verifies
  schema validity, literal grounding, forbidden categories, ranking thresholds and the
  correction-count invariant without network access.
- Android CI covers common reducers, JVM tests, lint, debug assembly and emulator
  lifecycle tests with explicit KVM validation.
- `pedagogical-e2e.yml` is manual, owner-only and uses one real Realtime session. It
  starts PostgreSQL, Redis, the evaluator worker and FastAPI, exercises three attempts,
  enforces at most four textual calls and US$2 of estimated textual model cost, performs
  cleanup and publishes no audio, transcript, trace or artifact.

Provider output is variable. The provider harness executes the same 40 cases three
times and reports only aggregate validity, grounding, stability, tokens, estimated cost
and latency:

```bash
./scripts/pedagogy-eval provider 3
```

Do not run it without explicit cost authorization and a protected `OPENAI_API_KEY`.

## Reproduction

```bash
./scripts/verify-contracts
cd backend
uv run ruff format --check src tests migrations
uv run ruff check src tests migrations
uv run mypy src tests
uv run alembic upgrade head
uv run pytest
cd ..
./scripts/pedagogy-eval offline
./gradlew --no-daemon --max-workers=2 \
  :shared:testAndroidHostTest \
  :apps:androidApp:testDebugUnitTest \
  :apps:androidApp:lintDebug \
  :apps:androidApp:assembleDebug
```

The real provider workflow and every physical row below remain release blockers until
their evidence URL, device identity and measurements are recorded.
