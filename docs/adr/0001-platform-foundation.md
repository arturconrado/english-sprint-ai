# ADR 0001: Android-first Kotlin Multiplatform foundation

## Status

Accepted.

## Decision

Use Kotlin Multiplatform for shared domain, state, networking, persistence
boundaries, and reusable Compose UI. Keep Android and iOS application entry
points separate and keep audio, Bluetooth, background execution, billing, and
secure storage behind native implementations.

Android is the first functional target. The iOS shell must continue compiling
from the first repository revision so shared code cannot silently acquire
Android-only dependencies.
