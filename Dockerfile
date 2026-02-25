FROM python:3.12-slim AS builder
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
COPY backend/requirements.txt .
RUN apt-get update && apt-get install -y build-essential gcc libpq-dev --no-install-recommends \
  && pip install --upgrade pip \
  && pip wheel -r requirements.txt -w /wheels \
  && apt-get remove -y build-essential gcc libpq-dev \
  && apt-get autoremove -y \
  && rm -rf /var/lib/apt/lists/*

FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
COPY --from=builder /wheels /wheels
RUN pip install --no-index --find-links=/wheels -r /app/requirements.txt || true
COPY backend/ /app
RUN adduser --disabled-password --gecos "" appuser || true
USER appuser
EXPOSE 8000
ENTRYPOINT ["/app/scripts/start.sh"]

