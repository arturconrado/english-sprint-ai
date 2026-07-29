# Beta support operations

The Android app creates encrypted requests in categories `access`, `billing`,
`voice`, `privacy`, `learning`, and `other`. Operators use only the private
`/internal/support/requests` API with `INTERNAL_API_TOKEN`; the credential must
come from Secret Manager and must never be placed in tickets or chat.

```bash
curl -H "Authorization: Bearer $INTERNAL_API_TOKEN" \
  "$API_URL/internal/support/requests?status=open"

curl -H "Authorization: Bearer $INTERNAL_API_TOKEN" \
  "$API_URL/internal/support/requests/$REQUEST_ID"

curl -X POST -H "Authorization: Bearer $INTERNAL_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"status":"resolved"}' \
  "$API_URL/internal/support/requests/$REQUEST_ID"
```

Only open the description when needed to resolve the request. No free-form
operator notes are stored by the product. Use a separate approved support
system for correspondence and avoid copying learning or voice content.

Targets for the closed beta: acknowledge access, billing, and privacy requests
within one business day; other requests within two. Escalate deletion/export
failures immediately and billing/quota discrepancies before changing data.
