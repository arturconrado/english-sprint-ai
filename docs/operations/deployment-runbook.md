# Deployment and rollback runbook

## Preconditions

- A reviewed Terraform plan for the target environment.
- An immutable backend image digest built from the intended source.
- All Secret Manager values created and enabled.
- Firebase Google Sign-In configured for the same environment.
- Free beta enabled with the approved cohort and allowance limits. RevenueCat
  and the Play product are required only when paid billing is explicitly enabled.
- Database backup current and no unresolved incident.

## Deploy

1. Apply the approved Terraform plan.
2. Execute the Cloud Run migration job and require a successful exit.
3. Confirm the Alembic revision is `0005_free_beta`.
4. Deploy a new Cloud Run revision with zero traffic.
5. Call `/healthz`, then `/readyz`, and require `200` from both.
6. Run the staging journey: login, free-beta enrollment, diagnostic, plan,
   mission, review, quota settlement, export, and a support request.
7. Shift 5% traffic, observe errors, latency, DB connections, Redis, OpenAI
   failures, and minute settlement for ten minutes.
8. Shift 100% traffic only if the observation window remains healthy.

Never run an old application revision against a schema it cannot read.
Migrations must be backward compatible for at least the current and previous
application revisions.

## Rollback

1. Stop traffic growth and disable `REALTIME_ENABLED` if provider cost or media
   cleanup is affected.
2. Route traffic to the previous healthy Cloud Run revision.
3. Do not downgrade the database during an incident. Use only a separately
   rehearsed forward repair migration.
4. Verify `/readyz`, authentication, quota reservation/settlement, and support.
5. Record the revision, image digest, timestamps, affected sessions, and cause.

## Production smoke test

The test must use designated beta accounts and sandbox billing until the formal
GO decision. It must not store or attach audio, SDP, transcripts, tokens, or
provider call identifiers.
