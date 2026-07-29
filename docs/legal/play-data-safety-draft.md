# Google Play Data Safety mapping — approval draft

Complete the Play Console form from the final SDK inventory and production
configuration. Recheck after every analytics, crash, authentication, billing,
or voice dependency change.

| Data category | Purpose | Product handling |
|---|---|---|
| User ID | Account, security, entitlement | Firebase ID mapped to internal UUID |
| Purchases | Subscription and quota | RevenueCat/Play event metadata |
| App activity | Sprint progress and product analytics | Analytics only after consent; allowlisted events |
| Audio | Realtime learning session | Transmitted for processing; never persisted by this product |
| Text/voice-derived learning content | Evaluation | Transient up to 60 minutes; optional encrypted 30-day retention |
| Diagnostics | Reliability | Content-free Crashlytics/telemetry after consent where required |
| Support content | User support | Encrypted and operator-access controlled |

The final declaration must reflect provider retention, encryption in transit,
account deletion, the public deletion URL, data sharing definitions, and the
legal reviewer’s decision. Do not publish this draft as the declaration.
