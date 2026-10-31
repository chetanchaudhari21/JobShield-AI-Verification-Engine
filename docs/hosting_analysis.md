# JobShield AI — Production Hosting & Infrastructure Analysis

> **Specification Reference:** `PROJECT_SPECIFICATION.md` Section 15 (Deployment Plan) & Section 16 (Testing and Acceptance Criteria).  
> **Last Updated:** October 2026

---

## 1. Executive Summary

JobShield AI is a multi-tier recruitment fraud protection system combining:
1. **FastAPI Backend:** Asynchronous REST API, ML inference engine, SSRF filtering, and business logic.
2. **Scikit-Learn ML Inference:** Calibrated Logistic Regression model with Platt scaling (`v1.1.0`) and SHAP/linear feature explanations.
3. **OCR & PDF Extraction Worker:** Heavy PDF parsing and image OCR using `PyMuPDF` (MuPDF C-bindings) and `Tesseract OCR` (system binary).
4. **PostgreSQL Database:** Relational store for scans, evidence, verification records, community reports, user reviews, RBAC audit logs, and async jobs.
5. **React SPA Frontend:** Client dashboard, analysis interfaces, results preview with feature weight charts, and admin panels.
6. **Chrome Manifest V3 Extension:** Client-side privacy-first browser extension communicating with the FastAPI backend.

This document evaluates hosting providers against the system's technical constraints: **Tesseract system binary dependencies**, **memory consumption (minimum 2 GB RAM)**, **ephemeral disk limitations**, **database retention**, and **cold-start timeouts**.

---

## 2. Infrastructure Requirements & Technical Constraints

| Dimension | System Requirement | Technical Rationale & Failure Modes |
|---|---|---|
| **System Binaries** | `tesseract-ocr`, `tesseract-ocr-eng`, `poppler-utils` | Pure Python packages cannot perform optical character recognition on scanned PDFs. The hosting runtime must support Linux system package installation or custom Docker containers. Serverless platforms without Docker support fail immediately. |
| **Minimum RAM** | **2.0 GB - 4.0 GB** | - Python runtime + FastAPI: ~150 MB<br>- Scikit-learn + TF-IDF model artifacts: ~250 MB<br>- PyMuPDF rendering + Tesseract OCR page rasterization: ~600 MB - 1.2 GB per active worker thread<br>- PostgreSQL buffer pool: ~256 MB - 512 MB |
| **CPU Allocation** | **1 - 2 vCPUs** | Tesseract OCR and linear matrix dot products are CPU-bound. Single-core throttling causes PDF extraction timeouts (> 30s) under concurrent load. |
| **Disk Persistence** | **Named persistent volume or Object Storage** | Ephemeral file systems wipe local files on deployment or dyno sleep. SQLite databases, temporary uploads, or generated PDF reports stored on ephemeral disks are lost. Permanent database storage requires managed PostgreSQL; generated PDF reports require persistent object storage or on-the-fly rendering. |
| **Background Execution** | **Dedicated worker or non-blocking async task** | Heavy OCR parsing takes 3–15 seconds per scanned document. Synchronous execution in standard request threads causes gateway timeouts (504 Gateway Timeout) and starves API requests. |
| **Network & CORS** | **Configurable Origin Allowlist** | Strict CORS must permit only trusted origins (e.g. production domain, staging domain, `chrome-extension://*`). SSRF protections require egress IP validation. |

---

## 3. Hosting Provider Comparison Matrix

| Provider / Architecture | OCR & Docker Compatibility | RAM & CPU Feasibility | Database Persistence | Estimated Monthly Cost | Cold-Start & Timeout Limits | Recommendation Status |
|---|---|---|---|---|---|---|
| **Option A: Render Ecosystem**<br>*(Web Service + Background Worker + Managed Postgres + Static Site)* | **Excellent**<br>Full Dockerfile support for Web and Worker services. Native apt/Docker installation of Tesseract. | **Good**<br>Starter (512MB) is insufficient; **Standard (2GB, 1 vCPU)** is required for API/worker to avoid OOM during OCR. | **Managed PostgreSQL**<br>Persistent managed database with automated daily backups. Ephemeral disk on web services requires S3/Supabase for report persistence. | - Web (Standard): \$25/mo<br>- Worker (Standard): \$25/mo<br>- Postgres (Basic 1GB): \$7/mo<br>- Static Site: \$0/mo<br>**Total: ~\$57/mo** | - Web services do not sleep on paid tiers.<br>- Request timeout is 100 seconds (sufficient for OCR queue polling).<br>- Free tier sleeps after 15 min and lacks RAM (512MB OOMs on Tesseract). | **Recommended Managed Cloud Option** |
| **Option B: Hybrid Vercel + Render / Supabase**<br>*(Vercel Frontend + Render API/Worker + Supabase DB)* | **Good**<br>Vercel serves React SPA with global CDN. Render handles Docker backend + worker. | **Good**<br>Frontend offloaded to edge network. Render handles compute-heavy ML and OCR workloads. | **Supabase Postgres**<br>Free/Pro tier managed Postgres with PgBouncer connection pooling and persistent object storage included. | - Vercel: \$0 (Hobby)<br>- Render API+Worker: \$50/mo<br>- Supabase DB: \$0 - \$25/mo<br>**Total: ~\$50 - \$75/mo** | - Vercel edge: 0 cold start.<br>- Backend on Render paid tier: zero sleep.<br>- Separation of concerns simplifies frontend deploys. | **Strong Alternative for Global CDN** |
| **Option C: Self-Hosted VPS with Docker Compose**<br>*(Hetzner, DigitalOcean, or Linode)* | **Full Native Control**<br>Single `docker-compose.yml` runs all 4 containers (`db`, `backend`, `worker`, `frontend`) with Nginx reverse proxy. | **Superior**<br>Hetzner 4 vCPU, 8 GB RAM VPS: \$7.50/mo (€6.90). DigitalOcean 2 vCPU, 4 GB RAM: \$24/mo. Easily handles ML, OCR, and DB. | **Persistent Volume**<br>Docker named volume `pgdata` mapped to VPS SSD. Local automated snapshot backups via cron. | - Hetzner CPX21: ~\$8/mo<br>- DigitalOcean Droplet: \$24/mo<br>**Total: ~\$8 - \$24/mo** | - Zero cold starts.<br>- Zero ephemeral disk wipes.<br>- No request timeout restrictions.<br>- Full control over resource limits and logs. | **Recommended Budget & Production Choice** |
| **Option D: Serverless (AWS Lambda / Vercel Serverless Functions)** | **Poor / High Complexity**<br>Requires custom Lambda layers for `tesseract-ocr` and MuPDF C libraries. | **Marginal**<br>Configurable memory up to 10GB, but cold starts with 300MB ML+OCR bundles take 8–15 seconds. | Requires external RDS/Aurora PostgreSQL and S3 buckets. | Unpredictable per-invocation billing; easily exceeds VPS cost with heavy OCR usage. | 15-minute Lambda max timeout; 10-second API Gateway HTTP timeout risks aborting OCR. | **Not Recommended for Initial Launch** |

---

## 4. Key Failure Modes & Mitigation Strategies

### 4.1 Ephemeral Disk Data Loss
* **Risk:** Cloud platforms (Render, Heroku, Fly.io without mounted disks) wipe the container filesystem on restart or code deployment. Storing SQLite databases, user uploads, or generated PDF reports in `./tmp` causes silent permanent data loss.
* **Mitigation:** 
  1. Relational schema must strictly reside on managed PostgreSQL or persistent named Docker volume `pgdata`.
  2. PDF verification reports (Feature F10) are generated **on-the-fly directly from persisted database evidence**, eliminating the need to store raw PDF binaries on disk.
  3. Uploaded offer letters are processed in-memory, validated for SHA-256 deduplication, and discarded from RAM immediately after extraction.

### 4.2 Tesseract Memory Spikes and OCR Timeouts
* **Risk:** High-resolution 300+ DPI scanned PDFs consume 800MB–1.2GB per page during rasterization. Multiple concurrent uploads on a 512MB or 1GB instance trigger Linux kernel Out-Of-Memory (OOM) killer terminating the Python process.
* **Mitigation:**
  1. Enforced hard upload limits: maximum 10 MB file size, maximum 10 pages per document.
  2. Hard timeout: 30-second execution cap on OCR processing via thread timeout.
  3. Background worker decoupling: Asynchronous jobs (`AsyncDocumentJob`) queued via `POST /api/v1/jobs/offer-letter/async` ensure API request threads are never blocked.
  4. Deduplication: Computing file SHA-256 prior to OCR checks for existing completed jobs, eliminating redundant compute cycles.

### 4.3 Database Connection Starvation
* **Risk:** FastAPI async endpoints under concurrent load create numerous transient database connections, exceeding managed PostgreSQL connection limits (e.g., Render free/starter allows 20–50 connections).
* **Mitigation:**
  1. SQLAlchemy connection pool configured with `pool_size=10`, `max_overflow=20`, `pool_pre_ping=True`, and `pool_recycle=300`.
  2. For high-concurrency cloud deployments, integrate PgBouncer or Supabase transaction pooler on port 6543.

---

## 5. Deployment Recommendation

1. **For Production on Cloud Infrastructure:**  
   Deploy using **Option A (Render)** or **Option B (Vercel + Render)** with a minimum of **2 GB RAM** allocated to the FastAPI backend and worker services. Use Managed PostgreSQL with automated backups.

2. **For Self-Hosted / On-Premise / Dev Environments:**  
   Deploy using the unified **`docker-compose.yml`** on a Linux VPS with 4 GB RAM. The single Compose file manages service ordering, persistent volume `pgdata`, health checks, Nginx SPA routing, and API proxying out-of-the-box.

---

## 6. Official Provider Documentation & Verification Citations

1. **Render Web Services & Request Timeouts:**
   - *Documentation:* [Render Web Services Documentation](https://render.com/docs/web-services)
   - *Verification:* Render imposes a default 100-second HTTP request timeout. Heavy synchronous OCR jobs exceeding 100s trigger a 504 Gateway Timeout, proving the absolute requirement for background task queuing (`AsyncDocumentJob`).
   - *Ephemeral Disks:* [Render Disks & Filesystems](https://render.com/docs/disks) — Render web service filesystems are strictly ephemeral; container restarts wipe all non-mounted state.

2. **Render Background Workers:**
   - *Documentation:* [Render Background Workers](https://render.com/docs/background-workers)
   - *Verification:* Background workers run continuously without HTTP request timeouts or incoming web traffic exposure, providing the ideal runtime environment for `python -m app.workers.ocr_worker`.

3. **Render Managed PostgreSQL Limits:**
   - *Documentation:* [Render PostgreSQL Limits & Connection Pooling](https://render.com/docs/databases)
   - *Verification:* Render free/starter databases limit concurrent client connections (20 to 50 connections max) and require explicit pool configuration or PgBouncer.

4. **Vercel Serverless & SPA Limits:**
   - *Documentation:* [Vercel Limits & Functions Overview](https://vercel.com/docs/limits/overview)
   - *Verification:* Vercel Edge/Hobby functions have a 10-second hard execution timeout and 50MB uncompressed bundle limit, making them unsuitable for hosting Scikit-Learn + Tesseract OCR pipelines directly, but optimal for hosting the static React SPA client.

5. **Supabase Managed Postgres & Storage:**
   - *Documentation:* [Supabase Database Architecture](https://supabase.com/docs/guides/database) & [Supabase Storage](https://supabase.com/docs/guides/storage)
   - *Verification:* Provides PostgreSQL 15/16 with built-in Supavisor/PgBouncer connection pooling and S3-compatible persistent object storage for retained report assets.

