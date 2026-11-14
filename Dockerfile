# syntax=docker/dockerfile:1
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first so Docker caches this layer
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Run as a non-root user
RUN useradd --create-home --uid 1000 appuser

COPY app.py templates_store.py ./

USER appuser

EXPOSE 8000

# 2 workers, 4 threads each, served by gunicorn (not Flask's dev server)
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4", "--access-logfile", "-", "app:app"]
