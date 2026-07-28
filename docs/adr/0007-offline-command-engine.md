# ADR 0007: Vosk for bilingual offline commands

## Status

Accepted, pending physical performance evidence

## Decision

Use Vosk Android 0.3.75 with small Apache-2.0 English and Portuguese models,
restricted grammars, confidence threshold 0.82 and a 1.5-second cooldown.
Models are checksum-pinned and copied from generated APK assets.

Sherpa-onnx was considered, but its ready-made keyword models did not provide
the required Portuguese coverage. Custom KWS training is outside Phase 1.

## Consequences

Commands do not depend on provider transcription, but two acoustic models have
a significant native-memory cost. Physical RSS, CPU, battery and thermal
measurements are mandatory before acceptance.
