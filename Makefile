.PHONY: contracts contract-check backend-check services services-observability

contracts:
	./scripts/generate-contracts

contract-check:
	./scripts/verify-contracts

backend-check:
	uv run --project backend ruff check backend
	uv run --project backend mypy backend/src backend/tests
	uv run --project backend pytest backend/tests

services:
	docker compose -f infrastructure/docker/compose.yaml up -d

services-observability:
	docker compose -f infrastructure/docker/compose.yaml --profile observability-ui up -d
