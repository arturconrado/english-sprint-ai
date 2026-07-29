# Free beta access

The free beta allows authenticated Android users to complete the product journey
without Google Play or RevenueCat. Access is granted by the backend and never by
the client.

## Runtime policy

```dotenv
BILLING_ENABLED=false
FREE_BETA_ENABLED=true
FREE_BETA_ALLOWANCE_SECONDS=7200
FREE_BETA_MAX_ACCOUNTS=30
```

The first 30 authenticated accounts that request billing status are enrolled.
Each receives a lifetime 120-minute mission allowance. The separate ten-minute
diagnostic allowance is unchanged. Enrollment and minute reservations are
serialized in PostgreSQL, so concurrent devices cannot create an extra place or
spend more than the account balance.

An active paid subscription takes precedence if billing is enabled later.
Disabling `FREE_BETA_ENABLED` stops new enrollments but does not delete existing
records; re-enabling it restores their remaining allowance.

## Before inviting users

1. Apply migration `0005_free_beta`.
2. Configure Firebase Google Sign-In and the Android Firebase values.
3. Configure the backend URL with HTTPS.
4. Configure OpenAI and enable Realtime only after `/readyz` is healthy.
5. Verify login, enrollment, diagnostic, mission, review, quota settlement,
   export, deletion, and support in staging.

Never change balances directly during an incident. Use a reviewed operational
repair with an append-only `voice_usage_ledger` adjustment.

## Capacity checks

```sql
SELECT count(*) AS enrolled_accounts
FROM free_beta_enrollments;

SELECT allowance_seconds - consumed_seconds AS remaining_seconds,
       enrolled_at
FROM free_beta_enrollments
WHERE user_id = :user_id;
```

The Android app displays `Free beta` and the effective remaining minutes. When
the cohort is full, it does not show a purchase action and directs the user to
support.
