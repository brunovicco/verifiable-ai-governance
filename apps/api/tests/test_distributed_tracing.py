"""P1.5 privacy and W3C propagation tests for the Governance telemetry bridge."""

from ai_governance_api import telemetry as telemetry_module
from ai_governance_api.telemetry import GovernanceTelemetry
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind


def test_safe_attributes_drop_sensitive_and_unknown_fields() -> None:
    safe = telemetry_module._safe_attributes(
        {
            "component": "policy-model-router",
            "operation": "route",
            "correlation_id": "decision-123",
            "authorization": "secret",
            "prompt": "customer content",
            "api_key": "secret",
        }
    )

    assert safe == {
        "component": "policy-model-router",
        "operation": "route",
        "correlation_id": "decision-123",
    }


def test_w3c_context_is_injected_into_outbound_headers() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    telemetry = GovernanceTelemetry(
        enabled=True,
        tracer=provider.get_tracer("test-governance"),
        provider=provider,
    )

    headers: dict[str, str] = {}
    with telemetry.start_span(
        "test",
        kind=SpanKind.CLIENT,
        attributes={"operation": "route"},
    ):
        telemetry.inject(headers)

    assert headers["traceparent"].startswith("00-")
    provider.shutdown()


def test_incoming_w3c_context_is_continued() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    telemetry = GovernanceTelemetry(
        enabled=True,
        tracer=provider.get_tracer("test-governance"),
        provider=provider,
    )
    parent_trace_id = "11111111111111111111111111111111"
    headers = {
        "traceparent": f"00-{parent_trace_id}-2222222222222222-01",
    }

    with (
        telemetry.continue_trace(headers),
        telemetry.start_span(
            "child",
            kind=SpanKind.SERVER,
            attributes={"operation": "http.request"},
        ),
    ):
        current = trace.get_current_span().get_span_context()
        assert f"{current.trace_id:032x}" == parent_trace_id

    provider.shutdown()
