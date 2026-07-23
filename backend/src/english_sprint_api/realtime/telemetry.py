from uuid import UUID

from opentelemetry import metrics

from english_sprint_api.realtime.models import UsageObserver


class TelemetryUsageObserver(UsageObserver):
    def __init__(self) -> None:
        meter = metrics.get_meter("english_sprint_api.realtime")
        self.sessions_started = meter.create_counter("voice_session_started")
        self.sessions_ended = meter.create_counter("voice_session_ended")
        self.provider_errors = meter.create_counter("voice_provider_error")
        self.orphans = meter.create_counter("voice_orphan_reconciled")
        self.duration = meter.create_histogram("voice_session_duration_seconds")
        self.create_latency = meter.create_histogram("voice_session_create_latency_ms")
        self.provider_input_tokens = meter.create_counter("voice_provider_input_tokens")
        self.provider_output_tokens = meter.create_counter("voice_provider_output_tokens")

    def observe(self, session_id: UUID, event: dict[str, object]) -> None:
        del session_id
        response = event.get("response")
        if not isinstance(response, dict):
            return
        usage = response.get("usage")
        if not isinstance(usage, dict):
            return
        input_tokens = usage.get("input_tokens")
        output_tokens = usage.get("output_tokens")
        if isinstance(input_tokens, int):
            self.provider_input_tokens.add(input_tokens)
        if isinstance(output_tokens, int):
            self.provider_output_tokens.add(output_tokens)
