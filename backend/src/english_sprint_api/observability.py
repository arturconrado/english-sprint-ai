from fastapi import FastAPI
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from english_sprint_api.config import Settings

_libraries_instrumented = False


def configure_observability(app: FastAPI, settings: Settings) -> None:
    global _libraries_instrumented

    if not settings.otel_enabled:
        return

    resource = Resource.create(
        {
            "service.name": "english-sprint-api",
            "deployment.environment": settings.app_env,
        }
    )
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    metric_exporter = OTLPMetricExporter(
        endpoint=settings.otel_exporter_otlp_endpoint,
        insecure=True,
    )
    metrics.set_meter_provider(
        MeterProvider(
            resource=resource,
            metric_readers=[PeriodicExportingMetricReader(metric_exporter)],
        )
    )

    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)
    if not _libraries_instrumented:
        HTTPXClientInstrumentor().instrument(tracer_provider=provider)
        AsyncPGInstrumentor().instrument(tracer_provider=provider)  # type: ignore[no-untyped-call]
        RedisInstrumentor().instrument(tracer_provider=provider)
        _libraries_instrumented = True
