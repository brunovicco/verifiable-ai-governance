"""Minimal OpenTelemetry bridge for Governance while it remains on Python 3.12."""

from collections.abc import Iterator, Mapping, MutableMapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from opentelemetry import context, trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Span, SpanKind
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_ALLOWED_ATTRIBUTES = frozenset(
    {
        "component",
        "operation",
        "outcome",
        "correlation_id",
        "http.method",
        "http.status_code",
        "error.type",
    }
)
_PROPAGATOR = TraceContextTextMapPropagator()


@dataclass(slots=True)
class GovernanceTelemetry:
    """Small facade with the same privacy posture used by a2a-otel-kit."""

    enabled: bool
    tracer: trace.Tracer
    provider: TracerProvider | None = None

    @contextmanager
    def continue_trace(self, carrier: Mapping[str, str]) -> Iterator[None]:
        """Attach an incoming W3C trace context for the duration of one request."""
        parent = _PROPAGATOR.extract(carrier=carrier)
        token = context.attach(parent)
        try:
            yield
        finally:
            context.detach(token)

    @contextmanager
    def start_span(
        self,
        name: str,
        *,
        kind: SpanKind,
        attributes: Mapping[str, Any] | None = None,
    ) -> Iterator[Span]:
        """Start a span using only explicitly allowlisted, content-free attributes."""
        safe = _safe_attributes(attributes or {})
        with self.tracer.start_as_current_span(
            name,
            kind=kind,
            attributes=safe,
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            yield span

    def inject(self, carrier: MutableMapping[str, str]) -> None:
        """Inject the current W3C trace context into an outbound carrier."""
        _PROPAGATOR.inject(carrier=carrier)

    def annotate_current(self, attributes: Mapping[str, Any]) -> None:
        """Attach allowlisted operational identifiers to the active span."""
        span = trace.get_current_span()
        for key, value in _safe_attributes(attributes).items():
            span.set_attribute(key, value)

    def shutdown(self) -> None:
        """Flush and shut down the owned provider when telemetry is enabled."""
        if self.provider is None:
            return
        self.provider.force_flush(timeout_millis=5_000)
        self.provider.shutdown()


_TELEMETRY = GovernanceTelemetry(
    enabled=False,
    tracer=trace.get_tracer("verifiable-ai-governance"),
)


def configure_telemetry(
    *,
    enabled: bool,
    service_name: str,
    service_version: str,
    environment: str,
    endpoint: str,
    timeout_seconds: float,
) -> GovernanceTelemetry:
    """Configure an OTLP/HTTP provider once at application startup."""
    global _TELEMETRY
    if not enabled:
        _TELEMETRY = GovernanceTelemetry(
            enabled=False,
            tracer=trace.get_tracer(service_name, service_version),
        )
        return _TELEMETRY

    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": service_name,
                "service.version": service_version,
                "deployment.environment": environment,
            }
        )
    )
    exporter = OTLPSpanExporter(
        endpoint=endpoint,
        timeout=timeout_seconds,
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    _TELEMETRY = GovernanceTelemetry(
        enabled=True,
        tracer=provider.get_tracer(service_name, service_version),
        provider=provider,
    )
    return _TELEMETRY


def current_telemetry() -> GovernanceTelemetry:
    """Return the process telemetry facade configured by the FastAPI lifespan."""
    return _TELEMETRY


def shutdown_telemetry() -> None:
    """Flush and dispose the current provider."""
    current_telemetry().shutdown()


class TraceContextMiddleware:
    """Continue W3C context and create a content-free Governance HTTP server span."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Trace inbound HTTP requests while passing non-HTTP scopes through."""
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        status_code = 500

        async def traced_send(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
            await send(message)

        telemetry = current_telemetry()
        with (
            telemetry.continue_trace(headers),
            telemetry.start_span(
                "governance.http.request",
                kind=SpanKind.SERVER,
                attributes={
                    "component": "fastapi",
                    "operation": "http.request",
                    "http.method": str(scope.get("method", "")),
                },
            ) as span,
        ):
            try:
                await self._app(scope, receive, traced_send)
            except Exception as exc:
                span.set_attribute("outcome", "error")
                span.set_attribute("error.type", type(exc).__name__)
                raise
            else:
                span.set_attribute("http.status_code", status_code)
                span.set_attribute(
                    "outcome",
                    (
                        "success"
                        if status_code < 400
                        else "rejected"
                        if status_code < 500
                        else "error"
                    ),
                )


def _safe_attributes(attributes: Mapping[str, Any]) -> dict[str, Any]:
    """Drop everything not explicitly approved for telemetry."""
    safe: dict[str, Any] = {}
    for key, value in attributes.items():
        if key not in _ALLOWED_ATTRIBUTES or value is None:
            continue
        if isinstance(value, (str, bool, int, float)):
            safe[key] = value
    return safe
