FROM python:3.12-slim

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Phase 3 agent/integration deps
RUN pip install --no-cache-dir \
    celery[redis]==5.4.0 \
    redis==5.2.1 \
    flower==2.0.1 \
    minio==7.2.15 \
    boto3==1.35.81 \
    trino==0.329.0 \
    pyiceberg==0.8.1 \
    rdflib==7.1.3 \
    weaviate-client==4.11.2 \
    openai==1.66.3 \
    anthropic==0.43.0 \
    pandas==2.2.3 \
    openpyxl==3.1.5 \
    pyarrow==18.1.0

COPY . .

# Default: run FastAPI
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
