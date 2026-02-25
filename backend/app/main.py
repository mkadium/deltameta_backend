from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

# Prefer absolute imports so the module works whether run as a package or script.
try:
    from app.logging_config import setup_logging
except Exception:
    from .logging_config import setup_logging

setup_logging()
import logging

try:
    from app.db import get_session
except Exception:
    from .db import get_session

try:
    from app.tracing import setup_tracing
except Exception:
    try:
        from .tracing import setup_tracing
    except Exception:
        setup_tracing = None

app = FastAPI(title="Deltameta Backend", version="1.0.0")
logger = logging.getLogger("deltameta")

# Initialize OpenTelemetry tracing (optional)
if setup_tracing:
    try:
        setup_tracing(app)
        logger.info("OpenTelemetry tracing initialized successfully")
    except Exception as e:
        logger.warning(f"OpenTelemetry tracing could not be initialized: {e}")
        logger.info("Application will continue without tracing")


@app.get("/")
async def root():
    return {"message": "Hello, Deltameta!"}


@app.get("/health", response_class=PlainTextResponse)
async def health():
    return PlainTextResponse("OK")


@app.get("/ready", response_class=PlainTextResponse)
async def ready():
    # Basic readiness check; expand to DB checks if configured
    return PlainTextResponse("READY")


@app.get("/metrics")
async def metrics():
    data = generate_latest()
    return PlainTextResponse(data, media_type=CONTENT_TYPE_LATEST)

