# JobShield AI — Production Deployment & Operations Guide

> **Specification Reference:** `PROJECT_SPECIFICATION.md` Section 15 (Deployment Plan) & Section 16 (Acceptance Criteria).  
> **Last Updated:** October 2026

---

## 1. Overview

JobShield AI is containerized for deterministic, reproducible production deployments. The architecture separates the stateless React frontend, the asynchronous FastAPI backend, the OCR background worker, and the persistent PostgreSQL database.

```
                      +-----------------------------+
                      |   Client Browser / Ext      |
                      +--------------+--------------+
                                     | HTTPS (:443)
                                     v
                      +-----------------------------+
                      |  Nginx Frontend Container   |
                      |  (Static SPA + API Proxy)   |
                      +--------------+--------------+
                                     | HTTP /api/v1/ (:8000)
                                     v
                      +-----------------------------+
                      |  FastAPI Backend Container  |
                      |  (REST API, ML Inference)   |
                      +-------+--------------+------+
                              |              |
           Background Tasks / |              | Database Connections
           Shared DB Queue    |              | (Pool: 10 + 20 overflow)
                              v              v
       +-------------------------+     +--------------------------+
       |   OCR Worker Container  |     |   PostgreSQL Database    |
       |  (Tesseract + MuPDF)    |     |   (Persistent 'pgdata')  |
       +-------------------------+     +--------------------------+
```

---

## 2. Docker Compose Single-Node Deployment

### 2.1 Prerequisites
- Linux Server (Ubuntu 22.04 LTS / Debian 12 recommended) or Windows Server with Docker Desktop.
- Hardware specifications: Minimum 2 vCPUs, 4 GB RAM, 20 GB SSD storage.
- Software dependencies: Docker Engine v24+ and Docker Compose v2.20+.

### 2.2 Environment Configuration
Create the production environment file from the template:
```bash
cp .env.example .env
chmod 600 .env
```

Generate cryptographically secure secrets for JWT and session tokens:
```bash
# Generate 256-bit hexadecimal secrets
openssl rand -hex 32  # Use for JWT_SECRET_KEY
openssl rand -hex 32  # Use for SECRET_KEY
openssl rand -hex 24  # Use for POSTGRES_PASSWORD
```

Configure required variables in `.env`:
```ini
# Environment & Server
ENVIRONMENT=production
DEBUG=false
SERVER_HOST=0.0.0.0
SERVER_PORT=8000

# Security Secrets (Must be 32+ characters)
JWT_SECRET_KEY=replace_with_openssl_generated_hex_64_characters
SECRET_KEY=replace_with_openssl_generated_hex_64_characters
POSTGRES_PASSWORD=replace_with_strong_database_password

# Database URL
DATABASE_URL=postgresql://jobshield:replace_with_strong_database_password@db:5432/jobshield

# Allowed CORS Origins (Frontend Domain and Extension)
CORS_ORIGINS=["https://jobshield.yourdomain.com","http://localhost:5173","chrome-extension://*"]

# OCR & File Limits
MAX_OFFER_LETTER_UPLOAD_BYTES=10485760   # 10 MB limit
MAX_PDF_PAGES=10                        # 10 page limit
OCR_TIMEOUT_SECONDS=30                  # 30 second timeout
```

### 2.3 Starting Services
Build and start all 4 containers in detached mode:
```bash
docker compose up -d --build
```

Verify service health and startup ordering:
```bash
docker compose ps
```
Expected output:
```
NAME                 IMAGE                      COMMAND                  SERVICE    STATUS
jobshield-db         postgres:16-alpine         "docker-entrypoint.s…"   db         Up (healthy)
jobshield-backend    jobshield-ai-backend       "/app/entrypoint.sh …"   backend    Up (healthy)
jobshield-worker     jobshield-ai-worker        "python -m app.worke…"   worker     Up
jobshield-frontend   jobshield-ai-frontend      "/docker-entrypoint.…"   frontend   Up (healthy)
```

### 2.4 Applying Database Migrations
Run Alembic migrations to initialize or upgrade the relational schema:
```bash
docker compose exec backend alembic upgrade head
```

Seed the initial Model Registry with verified production model artifacts (`v1.0.0`, `v1.1.0`):
```bash
docker compose exec backend python -c "from app.db.session import SessionLocal; from app.services.model_registry import seed_model_registry; seed_model_registry(SessionLocal())"
```

---

## 3. Least-Privilege Database Configuration

For production installations requiring enterprise security compliance, restrict the application database user to non-administrative permissions:

```sql
-- Connect as postgres superuser
CREATE USER jobshield_app WITH PASSWORD 'secure_production_password';
GRANT CONNECT ON DATABASE jobshield TO jobshield_app;

-- Grant schema privileges
\c jobshield
GRANT USAGE ON SCHEMA public TO jobshield_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO jobshield_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO jobshield_app;

-- Ensure future tables inherit privileges
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO jobshield_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO jobshield_app;

-- REVOKE dangerous administrative privileges
REVOKE CREATE ON SCHEMA public FROM jobshield_app;
REVOKE DROP ON DATABASE jobshield FROM jobshield_app;
```

---

## 4. Health Checks & Monitoring

The backend exposes two standard monitoring endpoints conforming to Section 16 criteria:

### 4.1 Liveness Probe (`GET /health/live`)
Confirms that the FastAPI event loop is responsive.
```bash
curl -i http://localhost:8000/health/live
```
```json
HTTP/1.1 200 OK
Content-Type: application/json

{"status": "live", "timestamp": "2026-10-18T00:50:00Z"}
```

### 4.2 Readiness Probe (`GET /health/ready`)
Verifies active PostgreSQL database connectivity, Alembic schema currency, and ML model artifact memory loading.
```bash
curl -i http://localhost:8000/health/ready
```
```json
HTTP/1.1 200 OK
Content-Type: application/json

{
  "status": "ready",
  "database": "connected",
  "model_loaded": true,
  "active_model_version": "v1.1.0",
  "tesseract_available": true
}
```
> **Security Note:** The readiness probe returns strictly boolean statuses and version identifiers. It never exposes database connection strings, passwords, or hostnames.

---

## 5. Rollback Procedures

### 5.1 Application Code Rollback
To roll back the backend or frontend containers to a prior release tag:
```bash
git checkout <previous_stable_tag>
docker compose up -d --build --no-deps backend frontend
```

### 5.2 Relational Database Schema Rollback
To roll back the most recent database migration using Alembic:
```bash
# Roll back one migration step
docker compose exec backend alembic downgrade -1

# Or roll back to a specific migration revision ID
docker compose exec backend alembic downgrade 0008_auth_rbac_audit
```

### 5.3 Zero-Downtime Atomic Model Rollback
If an newly activated ML model exhibits drift or unexpected behavior, an Administrator can atomically restore the previously active model without restarting containers or dropping connections:

```bash
# Via cURL with Administrator JWT Bearer Token:
curl -X POST https://api.yourdomain.com/api/v1/admin/models/rollback \
  -H "Authorization: Bearer <ADMIN_ACCESS_TOKEN>"
```
Response:
```json
{
  "status": "rolled_back",
  "active_version": "v1.0.0",
  "rolled_back_from": "v1.1.0",
  "deployed_at": "2026-10-18T00:52:10Z"
}
```
* **Atomic Guarantee:** Swaps the active inference bundle in memory and updates database deployment states in a single transaction. If loading fails, the transaction rolls back cleanly, retaining the existing operational model.

---

## 6. Backup and Recovery

### 6.1 Persistent Volume Backup
The PostgreSQL data is persisted on the Docker named volume `pgdata`. To take an atomic SQL dump backup:
```bash
docker compose exec db pg_dump -U jobshield -d jobshield -F c -b -v -f /tmp/jobshield_backup.dump
docker cp $(docker compose ps -q db):/tmp/jobshield_backup.dump ./backups/jobshield_$(date +%Y%m%d_%H%M%S).dump
```

### 6.2 Restoration from Backup
```bash
# Stop backend and worker containers to close connections
docker compose stop backend worker

# Restore database dump
docker cp ./backups/jobshield_20261018.dump $(docker compose ps -q db):/tmp/restore.dump
docker compose exec db pg_restore -U jobshield -d jobshield -c -v /tmp/restore.dump

# Restart services
docker compose start backend worker
```
