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

app = FastAPI(
    title="Deltameta Backend",
    version="1.0.0",
    description="Deltameta — Metadata Platform API",
)
logger = logging.getLogger("deltameta")

# Register routers
try:
    from app.auth.router import router as auth_router
    from app.domains.router import router as domains_router
    from app.teams.router import router as teams_router
    from app.roles.router import router as roles_router
    from app.policies.router import router as policies_router
    from app.org.router import router as org_router
    from app.subscriptions.router import router as subscriptions_router
except Exception:
    from .auth.router import router as auth_router
    from .domains.router import router as domains_router
    from .teams.router import router as teams_router
    from .roles.router import router as roles_router
    from .policies.router import router as policies_router
    from .org.router import router as org_router
    from .subscriptions.router import router as subscriptions_router

app.include_router(auth_router)
app.include_router(domains_router)
app.include_router(teams_router)
app.include_router(roles_router)
app.include_router(policies_router)
app.include_router(org_router)
app.include_router(subscriptions_router)

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

