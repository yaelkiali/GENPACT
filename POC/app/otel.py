# app/otel.py
import logging
import os

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME

from opentelemetry._logs import set_logger_provider
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.instrumentation.logging import LoggingInstrumentor

SERVICE_NAME_VALUE = os.getenv("OTEL_SERVICE_NAME", "ai-metrics-api")
OTLP_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")


def setup_telemetry() -> TracerProvider:
    resource = Resource(attributes={SERVICE_NAME: SERVICE_NAME_VALUE})

    # ── Traces ────────────────────────────────────────────────────
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(endpoint=OTLP_ENDPOINT, insecure=True)
        )
    )
    trace.set_tracer_provider(tracer_provider)

    # ── Logs ──────────────────────────────────────────────────────
    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(
            OTLPLogExporter(endpoint=OTLP_ENDPOINT, insecure=True)
        )
    )
    set_logger_provider(logger_provider)

    # Attach OTel handler to the root logger so all app logs are exported
    otel_handler = LoggingHandler(level=logging.INFO, logger_provider=logger_provider)
    logging.getLogger().addHandler(otel_handler)
    logging.getLogger().setLevel(logging.DEBUG)

    # Inject trace_id/span_id into every log record's message text so Loki
    # derivedFields can regex-extract trace_id and create Tempo links
    LoggingInstrumentor().instrument(set_logging_format=True)

    return tracer_provider
