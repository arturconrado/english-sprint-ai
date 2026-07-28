# Phase 1 physical-device validation

Automated tests cannot prove Bluetooth routing, microphone selection,
screen-off survival, acoustic barge-in, battery or thermal behavior. Record
device model, Android version, headset model, build SHA and raw measurements.

## Required matrix

- API 26–30 device with classic HFP/SCO headset.
- API 31–32 device using `setCommunicationDevice`.
- API 33–36 device covering notification permission and foreground rules.
- BLE Audio headset when hardware is available.

## Required scenarios

1. Start only from visible UI and verify headset microphone and output.
2. Hold a 30-minute conversation with the screen off.
3. Pause, resume and finish from notification and spoken EN/PT commands.
4. Run 30 barge-in samples and show p95 below 300 ms.
5. Disconnect and reconnect Bluetooth; verify no speaker fallback.
6. Toggle network and prove bounded recovery without duplicate sessions.
7. Swipe the app away and confirm local/provider cleanup.
8. Deny and revoke microphone, Bluetooth and notification permissions.
9. Capture RSS, CPU, battery delta, thermal status and command false positives.

Until this matrix and the secret-backed manual workflow pass, report:

`Implementation complete; physical-device acceptance pending.`
