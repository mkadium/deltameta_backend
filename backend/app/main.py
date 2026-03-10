from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
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

# CORS — allow any origin (set allow_origins=["*"] for open access)
# For production, use CORS_ORIGINS env (comma-separated) to restrict.
try:
    from app.settings import settings
    if settings.cors_origins:
        _origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
        _origins.extend(["http://localhost:3000", "http://127.0.0.1:3000"])
        _allow_creds = True
    else:
        _origins = ["*"]
        _allow_creds = False  # required when using "*"
except Exception:
    _origins = ["*"]
    _allow_creds = False
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_origin_regex=r"https://.*\.vercel\.app" if _origins != ["*"] else None,
    allow_credentials=_allow_creds,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
try:
    from app.auth.router import router as auth_router
    from app.teams.router import router as teams_router
    from app.roles.router import router as roles_router
    from app.policies.router import router as policies_router
    from app.org.router import router as org_router
    from app.subscriptions.router import router as subscriptions_router
    from app.setting_nodes.router import router as settings_router
    from app.resources.router import router as resources_router
    from app.nav_items.router import router as nav_router
    from app.subject_areas.router import router as subject_areas_router
    from app.lookup.router import router as lookup_router
    from app.catalog_domains.router import router as catalog_domains_router
    from app.data_products.router import router as data_products_router
    from app.glossary.router import router as glossary_router
    from app.classifications.router import router as classifications_router
    from app.govern_metrics.router import router as govern_metrics_router
    from app.change_requests.router import router as change_requests_router
    from app.activity_feed.router import router as activity_feed_router
    from app.storage_config.router import router as storage_config_router
    from app.service_endpoints.router import router as service_endpoints_router
    from app.monitor.router import router as monitor_router
    from app.admin.router import router as admin_router
    from app.datasets.router import router as datasets_router
    from app.data_assets.router import router as data_assets_router
    from app.bots.router import router as bots_router
    from app.scheduled_tasks.router import router as scheduled_tasks_router
    from app.profiling.router import router as profiling_router
    from app.lineage.router import router as lineage_router
    from app.quality.router import router as quality_router
    from app.search.router import router as search_router
    from app.ingest.router import router as ingest_router
except Exception:
    from .auth.router import router as auth_router
    from .teams.router import router as teams_router
    from .roles.router import router as roles_router
    from .policies.router import router as policies_router
    from .org.router import router as org_router
    from .subscriptions.router import router as subscriptions_router
    from .setting_nodes.router import router as settings_router
    from .resources.router import router as resources_router
    from .nav_items.router import router as nav_router
    from .subject_areas.router import router as subject_areas_router
    from .lookup.router import router as lookup_router
    from .catalog_domains.router import router as catalog_domains_router
    from .data_products.router import router as data_products_router
    from .glossary.router import router as glossary_router
    from .classifications.router import router as classifications_router
    from .govern_metrics.router import router as govern_metrics_router
    from .change_requests.router import router as change_requests_router
    from .activity_feed.router import router as activity_feed_router
    from .storage_config.router import router as storage_config_router
    from .service_endpoints.router import router as service_endpoints_router
    from .monitor.router import router as monitor_router
    from .admin.router import router as admin_router
    from .datasets.router import router as datasets_router
    from .data_assets.router import router as data_assets_router
    from .bots.router import router as bots_router
    from .scheduled_tasks.router import router as scheduled_tasks_router
    from .profiling.router import router as profiling_router
    from .lineage.router import router as lineage_router
    from .quality.router import router as quality_router
    from .search.router import router as search_router
    from .ingest.router import router as ingest_router

app.include_router(auth_router)
app.include_router(teams_router)
app.include_router(roles_router)
app.include_router(policies_router)
app.include_router(org_router)
app.include_router(subscriptions_router)
app.include_router(settings_router)
app.include_router(resources_router)
app.include_router(nav_router)
app.include_router(subject_areas_router)
app.include_router(lookup_router)
app.include_router(catalog_domains_router)
app.include_router(data_products_router)
app.include_router(glossary_router)
app.include_router(classifications_router)
app.include_router(govern_metrics_router)
app.include_router(change_requests_router)
app.include_router(activity_feed_router)
app.include_router(storage_config_router)
app.include_router(service_endpoints_router)
app.include_router(monitor_router)
app.include_router(admin_router)
app.include_router(datasets_router)
app.include_router(data_assets_router)
app.include_router(bots_router)
app.include_router(scheduled_tasks_router)
app.include_router(profiling_router)
app.include_router(lineage_router)
app.include_router(quality_router)
app.include_router(search_router)
app.include_router(ingest_router)

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

