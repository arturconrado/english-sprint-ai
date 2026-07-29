# Incident response

## Severity

- **SEV-1:** credential or personal-data exposure, uncontrolled billing/cost,
  cross-user access, or broad production outage.
- **SEV-2:** mission, voice, payment, quota, deletion, or support is materially
  unavailable to multiple users.
- **SEV-3:** degraded experience with a safe workaround.

## First response

1. Assign incident commander and timestamp the incident.
2. Preserve sanitized logs and metrics; never copy audio, SDP, transcript,
   Firebase tokens, OpenAI call IDs, or secrets into the incident record.
3. Contain: disable Realtime or billing, revoke secrets, stop a revision, or
   reduce traffic as appropriate.
4. Verify quota reservations are settled or released and reconcile orphan
   calls.
5. Communicate status through the configured support address.
6. Restore service through rollback or a forward fix.

For a suspected personal-data incident, notify the responsible privacy/legal
reviewer immediately and follow the legally approved notification timeline.
Rotate affected keys by version, retain the old decryption key only for the
approved retention window, and record every access.
