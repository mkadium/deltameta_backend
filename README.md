# Deltameta Backend

Production-grade FastAPI backend with PostgreSQL, file-based telemetry, and Kubernetes-ready deployment.

## Features

### ✅ Core Framework
- **FastAPI**: Modern, high-performance Python web framework
- **Python 3.12+**: Latest Python with type hints
- **Pydantic v2**: Data validation and settings management
- **SQLAlchemy 2.0**: Modern async ORM with type safety

### ✅ Database
- **PostgreSQL**: Production-grade relational database
- **Alembic**: Database migrations with rollback support
- **Connection pooling**: Efficient database connections
- **Multiple database support**: Primary + secondary DB connections

### ✅ Telemetry
- **OpenTelemetry**: Automatic instrumentation for all requests
- **File-based logging**: Daily log files in `telemetry_logs/`
- **Traces**: Every HTTP request and database query
- **Metrics**: Performance and system metrics
- **No external tools needed**: Perfect for development

### ✅ Production Ready
- **Docker**: Multi-stage containerization
- **Kubernetes**: Complete manifests (deployment, service, ingress)
- **Health checks**: `/health` and `/ready` endpoints
- **Structured logging**: JSON logs for easy parsing
- **Security**: Environment-based configuration, no secrets in code

### ✅ Developer Experience
- **Hot reload**: Development server with auto-reload
- **API docs**: Auto-generated OpenAPI/Swagger docs
- **Type safety**: Full type hints and Pydantic models
- **Git hooks**: Pre-commit hooks for code quality
- **Comprehensive docs**: Detailed guides and onboarding

## Quick Start

### 1. Start FastAPI Application
```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

API will be available at: http://localhost:8000

- **API Docs**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health
- **Metrics**: http://localhost:8000/metrics

### 2. View Telemetry Logs

```bash
# Real-time telemetry logs
tail -f backend/telemetry_logs/telemetry_$(date +%Y-%m-%d).log | jq '.'

# Filter traces only
tail -f backend/telemetry_logs/telemetry_$(date +%Y-%m-%d).log | jq 'select(.type == "TRACE")'

# Application logs
tail -f backend/uvicorn.log | jq '.'
```

## Project Structure

```
deltameta/
├── backend/
│   ├── app/                    # FastAPI application
│   │   ├── main.py            # Application entry point
│   │   ├── settings.py        # Configuration management
│   │   ├── tracing.py         # OpenTelemetry file logging
│   │   ├── logging_config.py  # Structured JSON logging
│   │   ├── metrics.py         # Prometheus metrics
│   │   ├── db.py              # Database connection
│   │   └── models.py          # SQLAlchemy models
│   ├── telemetry_logs/        # Daily telemetry files (auto-created)
│   │   └── telemetry_2026-02-25.log
│   ├── scripts/               # Utility scripts
│   │   ├── start.sh           # Production start script
│   │   └── run_migrations.sh  # Database migration helper
│   ├── k8s/                   # Kubernetes manifests
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   └── ingress.yaml
│   ├── Dockerfile             # Multi-stage Docker build
│   ├── requirements.txt       # Python dependencies
│   └── .env                   # Environment variables
├── docs/                       # Documentation
│   ├── GETTING_STARTED.md     # Quick start guide
│   ├── TELEMETRY.md           # Telemetry logging guide
│   ├── DEVELOPMENT_ONBOARDING.md
│   ├── PRODUCTION_HARDENING.md
│   └── DEPLOYMENT.md
├── .github/workflows/          # CI/CD pipelines
└── README.md
```

## Telemetry

All traces, metrics, and logs are automatically captured and written to dated files:

```
backend/telemetry_logs/telemetry_2026-02-25.log
```

### What Gets Logged

- ✅ **HTTP Requests**: Every API call with duration, status, attributes
- ✅ **Database Queries**: SQL queries with execution time
- ✅ **Trace Context**: Correlate logs with traces using trace_id
- ✅ **Metrics**: Request counts, durations, system metrics
- ✅ **JSON Format**: One entry per line, easy to parse

### Generate Test Traffic

```bash
# Make requests
for i in {1..50}; do 
  curl -s http://localhost:8000/ > /dev/null
done

# View traces
tail -20 backend/telemetry_logs/telemetry_$(date +%Y-%m-%d).log | jq '.'
```

Full guide: [docs/TELEMETRY.md](docs/TELEMETRY.md)

## Configuration

Edit `backend/.env`:

```bash
# Application
APP_ENV=development
APP_DEBUG=true

# Database
PRIMARY_DB_HOST=localhost
PRIMARY_DB_PORT=5432
PRIMARY_DB_NAME=deltameta
PRIMARY_DB_USER=postgres
PRIMARY_DB_PASSWORD=your_password
PRIMARY_DB_SCHEMA=deltameta

# Telemetry
OTEL_ENABLED=true
OTEL_SERVICE_NAME=deltameta-backend
OTEL_ENVIRONMENT=development

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
```

## Development

### Install Dependencies

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Run Migrations

```bash
cd backend
bash scripts/run_migrations.sh
```

### Run Tests

```bash
cd backend
pytest
```

### Build Docker Image

```bash
docker build -t deltameta-backend:latest backend/
```

## Deployment

### Kubernetes

```bash
cd backend/k8s
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml
kubectl apply -f ingress.yaml
```

### Environment Variables

Create Kubernetes secrets:

```bash
kubectl create secret generic deltameta-secrets \
  --from-literal=PRIMARY_DB_PASSWORD=your_password \
  --from-literal=SECONDARY_DB_PASSWORD=your_password
```

## Documentation

- **Quick Start**: [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md)
- **Telemetry**: [docs/TELEMETRY.md](docs/TELEMETRY.md)
- **Development**: [docs/DEVELOPMENT_ONBOARDING.md](docs/DEVELOPMENT_ONBOARDING.md)
- **Production**: [docs/PRODUCTION_HARDENING.md](docs/PRODUCTION_HARDENING.md)
- **Deployment**: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)

## Git Workflow

```bash
# Create feature branch
git checkout -b feature/my-feature

# Make changes and commit
git add .
git commit -m "feat: add new feature"

# Push to remote
git push origin feature/my-feature

# Create pull request on GitHub
```

See: [docs/GIT_COMMANDS.md](docs/GIT_COMMANDS.md)

## Tech Stack

| Component | Technology |
|-----------|------------|
| **Framework** | FastAPI 0.115+ |
| **Language** | Python 3.12+ |
| **Database** | PostgreSQL 16+ |
| **ORM** | SQLAlchemy 2.0 |
| **Migrations** | Alembic |
| **Validation** | Pydantic v2 |
| **Server** | Uvicorn + Gunicorn |
| **Telemetry** | OpenTelemetry (file-based) |
| **Container** | Docker |
| **Orchestration** | Kubernetes |
| **CI/CD** | GitHub Actions |

## Troubleshooting

**No telemetry logs?**
- Check `OTEL_ENABLED=true` in `.env`
- Make some requests to generate data
- Check `backend/telemetry_logs/` directory exists

**Database connection errors?**
- Verify PostgreSQL is running
- Check credentials in `.env`
- Run migrations: `bash backend/scripts/run_migrations.sh`

**Import errors?**
- Activate venv: `source backend/venv/bin/activate`
- Install dependencies: `pip install -r backend/requirements.txt`

## License

Proprietary

## Support

For issues or questions, create a GitHub issue or contact the development team.
