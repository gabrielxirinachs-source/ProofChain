"""
app/core/telemetry.py

OpenTelemetry (OTel) setup for ProofChain.

What is OpenTelemetry?
  It's an open standard for collecting observability data:
  - Traces: the journey of a single request through your system
  - Metrics: counters, gauges, histograms (req/sec, latency, error rate)
  - Logs: structured log events tied to traces

Why does this matter?
  When a /verify call takes 45 seconds instead of 10, you need to know:
    - Was it the Wikidata query? (span: wikidata_node)
    - The web fetch? (span: web_search_node)
    - The LLM call? (span: plan_node)
    - Or was it a cache miss on a hot claim?

  Without tracing, you're guessing. With OTel, you see a flame graph
  showing exactly where time was spent.

We use the console exporter in development (prints traces to stdout)
and can swap to Jaeger/Honeycomb/Datadog in production by changing
one environment variable.
"""
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

from app.core.config import get_settings

settings = get_settings()

# Module-level tracer — used across the codebase
# Usage: tracer.start_as_current_span("my_operation")
tracer: trace.Tracer | None = None


def setup_telemetry(app) -> None:
    """
    Initialize OpenTelemetry tracing for the FastAPI app.

    Call this once at startup in the lifespan function.

    Args:
        app: The FastAPI application instance
    """
    global tracer

    # Resource identifies this service in trace backends
    resource = Resource.create({
        "service.name": "proofchain-api",
        "service.version": settings.APP_VERSION,
        "deployment.environment": settings.ENV,
    })

    # TracerProvider is the factory for creating tracers
    provider = TracerProvider(resource=resource)

    # Exporter determines WHERE traces go
    # ConsoleSpanExporter prints to stdout — great for development
    # In production, swap for OTLPSpanExporter to send to Jaeger/Honeycomb
    exporter = ConsoleSpanExporter()
    processor = BatchSpanProcessor(exporter)
    provider.add_span_processor(processor)

    # Register as the global provider
    trace.set_tracer_provider(provider)

    # Create our module-level tracer
    tracer = trace.get_tracer("proofchain")


    # Auto-instrument httpx — adds spans for every outbound HTTP call
    # This traces our Wikidata + web retrieval calls automatically
    HTTPXClientInstrumentor().instrument()

    print(f"[telemetry] OpenTelemetry initialized for {settings.ENV}")


def get_tracer() -> trace.Tracer:
    """
    Get the module-level tracer for manual instrumentation.

    Usage in agent nodes:
        from app.core.telemetry import get_tracer
        tracer = get_tracer()

        with tracer.start_as_current_span("wikidata_query") as span:
            span.set_attribute("entity_id", "Q243")
            facts = await get_entity_facts("Q243")
            span.set_attribute("facts_count", len(facts))
    """
    global tracer
    if tracer is None:
        # Fallback: return a no-op tracer if setup_telemetry wasn't called
        tracer = trace.get_tracer("proofchain")
    return tracer