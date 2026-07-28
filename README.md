# English Sprint AI

Android-first, multiplatform foundation for a voice-based English tutor.

## Phase 1

This repository contains:

- a Kotlin Multiplatform shared module with Compose UI;
- native Android and SwiftUI application shells;
- a contract-first FastAPI backend;
- deterministic Python and Kotlin contract generation;
- PostgreSQL, Redis, OpenTelemetry Collector, and optional Jaeger;
- CI validation for contracts, backend, Android, iOS, and security.
- an Android foreground voice service using direct OpenAI Realtime WebRTC media;
- Bluetooth-only communication routing and local bilingual Vosk controls;
- server-side sideband control, sanitized session persistence and bounded recovery.

## Prerequisites

- JDK 17
- Android SDK 36 and Build Tools 36.0.0
- Xcode 26.4.1
- Python 3.13 managed by `uv`
- Node.js 20 or newer
- Docker with Compose

The current machine may omit the full Android and Xcode toolchains. GitHub Actions
is the canonical cross-platform validation environment.

## Bootstrap

```bash
npm ci
uv sync --project backend --group dev --locked
./scripts/generate-contracts
```

## Validation

```bash
./scripts/verify-contracts
uv run --project backend ruff check backend
uv run --project backend mypy --config-file backend/pyproject.toml backend/src backend/tests
uv run --project backend pytest backend/tests
./gradlew :shared:testAndroidHostTest :apps:androidApp:assembleDebug
```

Set an untracked Android backend URL when using a physical device:

```properties
# local.properties
ENGLISH_SPRINT_API_BASE_URL=http://192.168.1.10:8000
```

Realtime is disabled by default. Copy `.env.example`, set a strong
`INSTALLATION_HASH_SECRET`, keep `OPENAI_API_KEY` server-side, run migrations,
and set `REALTIME_ENABLED=true`.

## Local services

```bash
docker compose -f infrastructure/docker/compose.yaml up -d
```

Start the optional tracing UI:

```bash
docker compose -f infrastructure/docker/compose.yaml --profile observability-ui up -d
```

Jaeger is then available at <http://localhost:16686>.

## Realtime validation

The normal CI suite uses provider fakes and does not consume OpenAI traffic.
The manual `Realtime E2E` workflow requires the repository secret
`OPENAI_API_KEY` and performs a real WebRTC call without uploading artifacts.
See [`docs/validation/phase1-physical-device.md`](docs/validation/phase1-physical-device.md)
for the separate hardware acceptance matrix.

## Repository policy

This is a private, proprietary repository. GitHub Free does not enforce protected
branches in private repositories, so the target branch policy is documented in
[`docs/github-main-protection.md`](docs/github-main-protection.md) for activation
after a GitHub plan upgrade.
