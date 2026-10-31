# JobShield AI - Backend Dockerfile
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app

# Install system dependencies:
# - tesseract-ocr, tesseract-ocr-eng for optical character recognition
# - poppler-utils for PDF processing
# - libpq-dev & gcc for PostgreSQL drivers
# - curl for health check probing
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    libtesseract-dev \
    poppler-utils \
    libpq-dev \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt /app/
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Copy backend application code and alembic migrations
COPY . /app/

# Create non-root system user for security
RUN useradd -m -u 1001 -s /bin/bash jobshield && \
    chown -R jobshield:jobshield /app

USER jobshield

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
