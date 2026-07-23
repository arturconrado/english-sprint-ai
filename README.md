# English Sprint AI

Android-first, multiplatform foundation for a voice-based English tutor.

## Phase 0

This repository contains:

- a Kotlin Multiplatform shared module with Compose UI;
- native Android and SwiftUI application shells;
- a contract-first FastAPI backend;
- deterministic Python and Kotlin contract generation;
- PostgreSQL, Redis, OpenTelemetry Collector, and optional Jaeger;
- CI validation for contracts, backend, Android, iOS, and security.

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

## Local services

```bash
docker compose -f infrastructure/docker/compose.yaml up -d
```

Start the optional tracing UI:

```bash
docker compose -f infrastructure/docker/compose.yaml --profile observability-ui up -d
```

Jaeger is then available at <http://localhost:16686>.

## Repository policy

This is a private, proprietary repository. GitHub Free does not enforce protected
branches in private repositories, so the target branch policy is documented in
[`docs/github-main-protection.md`](docs/github-main-protection.md) for activation
after a GitHub plan upgrade.
