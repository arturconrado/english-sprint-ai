# Backup and restore drill

Run quarterly and before the first paid cohort.

1. Record the source Cloud SQL instance, backup/PITR point, Alembic revision,
   and expected row counts without personal content.
2. Restore to an isolated non-production project and network.
3. Point an isolated API revision at the restored database and a fresh Redis.
4. Run `/readyz`, contract tests, authentication isolation, entitlement and
   ledger reconciliation, sprint resumption, export, and deletion.
5. Confirm no restored service can contact production OpenAI, RevenueCat
   webhooks, analytics, notifications, or users.
6. Record RPO, RTO, checks, discrepancies, operator, and approval.
7. Destroy the isolated restore after evidence is retained without user
   content.

A backup is not accepted as operational evidence until this restore drill has
completed successfully.
