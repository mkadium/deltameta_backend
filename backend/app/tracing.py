"""
OpenTelemetry configuration for logging traces to local files.
All telemetry data is written to dated log files in the telemetry_logs directory.
"""
import logging
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult, SimpleSpanProcessor
    from opentelemetry.sdk.resources import Resource, SERVICE_NAME
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor
    from opentelemetry.instrumentation.logging import LoggingInstrumentor
    
    OTEL_AVAILABLE = True
except ImportError as e:
    OTEL_AVAILABLE = False
    import_error = str(e)

logger = logging.getLogger("deltameta.telemetry")


class FileTelemetryExporter(SpanExporter):
    """Custom span exporter that writes traces to daily log files."""
    
    def __init__(self, log_dir: Path):
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
    
    def export(self, spans) -> SpanExportResult:
        """Export spans to a dated log file."""
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            log_file = self.log_dir / f"telemetry_{today}.log"
            
            with open(log_file, 'a') as f:
                for span in spans:
                    # Calculate duration in milliseconds
                    duration_ms = None
                    if span.end_time and span.start_time:
                        duration_ns = span.end_time - span.start_time
                        duration_ms = round(duration_ns / 1_000_000, 2)
                    
                    trace_data = {
                        "timestamp": datetime.now().isoformat(),
                        "time": timestamp,
                        "type": "TRACE",
                        "trace_id": format(span.context.trace_id, '032x'),
                        "span_id": format(span.context.span_id, '016x'),
                        "parent_span_id": format(span.parent.span_id, '016x') if span.parent else None,
                        "name": span.name,
                        "duration_ms": duration_ms,
                        "status": span.status.status_code.name if span.status else "UNSET",
                        "attributes": dict(span.attributes) if span.attributes else {},
                    }
                    
                    # Add events if present
                    if span.events:
                        trace_data["events"] = [
                            {
                                "name": event.name,
                                "attributes": dict(event.attributes) if event.attributes else {}
                            }
                            for event in span.events
                        ]
                    
                    f.write(json.dumps(trace_data) + '\n')
            
            return SpanExportResult.SUCCESS
        except Exception as e:
            logger.error(f"Failed to export spans: {e}")
            return SpanExportResult.FAILURE
    
    def shutdown(self) -> None:
        """Shutdown the exporter."""
        pass


def setup_tracing(app, settings=None) -> None:
    """
    Set up OpenTelemetry to log traces to local files.
    Files are organized by date in the telemetry_logs directory.
    
    All telemetry data (traces, logs) are written to:
    backend/telemetry_logs/telemetry_YYYY-MM-DD.log
    
    Args:
        app: FastAPI application instance
        settings: Application settings (optional, will import if not provided)
    """
    if not OTEL_AVAILABLE:
        logger.warning(
            f"OpenTelemetry is not available: {import_error}. "
            "Telemetry will be disabled. Run `pip install -r requirements.txt` to enable."
        )
        return
    
    # Import settings if not provided
    if settings is None:
        try:
            from app.settings import settings as app_settings
            settings = app_settings
        except Exception:
            try:
                from .settings import settings as app_settings
                settings = app_settings
            except Exception as e:
                logger.error(f"Could not load settings: {e}")
                return
    
    # Check if telemetry is enabled
    if not getattr(settings, 'otel_enabled', False):
        logger.info("OpenTelemetry telemetry is disabled in settings")
        return
    
    try:
        # Set up telemetry logs directory
        backend_dir = Path(__file__).parent.parent
        telemetry_dir = backend_dir / "telemetry_logs"
        telemetry_dir.mkdir(parents=True, exist_ok=True)
        
        # Configure resource with service information
        resource = Resource(attributes={
            SERVICE_NAME: getattr(settings, 'otel_service_name', 'deltameta-backend'),
            "deployment.environment": getattr(settings, 'otel_environment', 'development'),
        })
        
        # === TRACING SETUP ===
        tracer_provider = TracerProvider(resource=resource)
        
        # Add file exporter for traces
        file_span_exporter = FileTelemetryExporter(telemetry_dir)
        tracer_provider.add_span_processor(SimpleSpanProcessor(file_span_exporter))
        
        # Set global tracer provider
        trace.set_tracer_provider(tracer_provider)
        
        # === AUTO-INSTRUMENTATION ===
        # Instrument FastAPI
        FastAPIInstrumentor.instrument_app(app)
        logger.info("FastAPI instrumentation enabled")
        
        # Instrument SQLAlchemy (if database is used)
        try:
            SQLAlchemyInstrumentor().instrument()
            logger.info("SQLAlchemy instrumentation enabled")
        except Exception as e:
            logger.debug(f"SQLAlchemy instrumentation skipped: {e}")
        
        # Instrument AsyncPG (if used)
        try:
            AsyncPGInstrumentor().instrument()
            logger.info("AsyncPG instrumentation enabled")
        except Exception as e:
            logger.debug(f"AsyncPG instrumentation skipped: {e}")
        
        # Instrument logging (adds trace context)
        try:
            LoggingInstrumentor().instrument(set_logging_format=False)
            logger.info("Logging instrumentation enabled")
        except Exception as e:
            logger.debug(f"Logging instrumentation skipped: {e}")
        
        # Create header in log file
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = telemetry_dir / f"telemetry_{today}.log"
        if not log_file.exists() or log_file.stat().st_size == 0:
            with open(log_file, 'w') as f:
                header = {
                    "timestamp": datetime.now().isoformat(),
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "type": "HEADER",
                    "service": resource.attributes.get(SERVICE_NAME),
                    "environment": resource.attributes.get('deployment.environment'),
                    "log_file": f"telemetry_{today}.log",
                    "message": "Telemetry logging initialized"
                }
                f.write(json.dumps(header) + '\n')
        
        logger.info(
            f"OpenTelemetry file logging initialized. "
            f"Service: {resource.attributes.get(SERVICE_NAME)}, "
            f"Environment: {resource.attributes.get('deployment.environment')}, "
            f"Log directory: {telemetry_dir}"
        )
    
    except Exception as e:
        logger.error(f"Failed to initialize OpenTelemetry file logging: {e}", exc_info=True)
        raise


def get_tracer(name: str = "deltameta"):
    """Get a tracer instance for manual instrumentation."""
    if OTEL_AVAILABLE:
        return trace.get_tracer(name)
    return None
