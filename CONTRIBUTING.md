# Contributing

## Workflow

1. Branch from `main`.
2. Keep generated sources unchanged by hand.
3. Run the relevant validation commands from the root README.
4. Open a pull request and wait for every CI job to pass.
5. Squash merge the pull request.

## Generated contracts

`contracts/openapi.yaml` is the only HTTP contract source. After changing it, run:

```bash
./scripts/generate-contracts
```

The generator owns `backend/src/generated/models.py` and all source files below
the generated Kotlin packages. CI rejects generator drift.

## Commits

Use short, imperative Conventional Commit messages.
