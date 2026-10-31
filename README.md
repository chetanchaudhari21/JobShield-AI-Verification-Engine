# JobShield AI

> **Explainable AI-Powered Recruitment Fraud Defense, Entity Verification & Governance Platform**  
> **Status:** ✅ **Production Ready (Phases 1–7 & Features F1–F12 Fully Implemented & Verified)**

---

## 1. Overview

**JobShield AI** is an enterprise-grade recruitment fraud defense platform that protects students, job seekers, and career institutions from employment scams, fake recruitment drives, entity impersonation, and fraudulent offer letters.

The platform combines:
- **Calibrated Machine Learning Analysis:** Leakage-free NLP classification (`v1.1.0`) with Platt scaling (Sigmoid) evaluated against held-out benchmark splits.
- **Entity Corroboration:** Automated cross-referencing against 2.7M+ corporate records from the **Ministry of Corporate Affairs (MCA-21)** and **DPIIT Recognized Startups**.
- **Domain Security & Recruiter Authentication:** DNS/MX records, SPF/DMARC corroboration, and typo-squatting lookalike detection.
- **SSRF-Protected URL Ingestion:** Safe web scraping with strict IP blacklisting against cloud metadata services (`169.254.169.254`) and internal networks.
- **Duplicate & Impersonation Detection:** Real-time MinHash/LSH cosine posting clustering and high-risk employer identity verification.
- **Explainable AI (XAI):** Linear feature weight attribution and decision boundary reconciliation distinguishing statistical contributions from deterministic rule overrides.
- **Offer Letter PDF Extraction & Selective OCR:** Async document processing with PyMuPDF and Tesseract OCR, enforcing 10-page limits, 10 MB caps, and 30-second timeouts.
- **Community Feedback & Bayesian Reputation:** Moderated user reviews, Bayesian-adjusted 1–5 star employer ratings, and fraud reports strictly quarantined from training weights.
- **Evidence-Based PDF Verification Reports:** Downloadable audit reports generated on-the-fly strictly from stored database evidence.
- **Job-Relevance Validation & Invalid Input Guard:** Pre-flight qualification preventing non-job submissions (recipes, code, essays, invoices, personal chat, gibberish) from generating false risk assessments.
- **Privacy-First Chrome Extension:** Manifest V3 extension with selective DOM extraction, zero PII storage, and full-report navigation.
- **Production Governance & Model Registry:** Zero-downtime atomic model hot-swapping, instant rollback, privacy-preserving drift monitoring (PSI), and Docker Compose containerization.

---

## 2. System Architecture

```
                               +-------------------------------------+
                               |   Client Browser / Chrome Ext (V3)  |
                               +------------------+------------------+
                                                  | HTTPS (:443)
                                                  v
                               +-------------------------------------+
                               |      Nginx Frontend Container       |
                               |    (React 19 SPA + API Proxy)       |
                               +------------------+------------------+
                                                  | HTTP /api/v1/ (:8000)
                                                  v
                               +-------------------------------------+
                               |       FastAPI Backend Container     |
                               |  - REST API & RBAC Dependencies     |
                               |  - ML Inference Engine (v1.1.0)     |
                               |  - SSRF URL Sanitizer & Rules Engine|
                               +---------+------------------+--------+
                                         |                  |
                      Async Job Enqueue /|                  | SQLAlchemy Pool
                      Shared Queue       |                  | (Pool: 10 + 20 overflow)
                                         v                  v
                   +-----------------------+     +-----------------------+
                   |  Async OCR Worker     |     |  PostgreSQL 16 Engine |
                   |  - PyMuPDF Extraction |     |  - Named Volume pgdata|
                   |  - Tesseract OCR (opt)|     |  - Reversible Alembic |
                   |  - Strict IDOR Checks |     |  - Read-Only Separation|
                   +-----------------------+     +-----------------------+
```

---

## 3. Feature Matrix (F1 – F12)

| Feature | Description | Architecture / Implementation | Status |
| :--- | :--- | :--- | :---: |
| **F1: Job-Text Fraud Analysis** | NLP text classification, contextual heuristic rules, and composite risk scoring ($0$–$100$). | TF-IDF + Balanced Logistic Regression (`v1.1.0`) with Platt Sigmoid calibration ($1.21\%$ ECE). | ✅ Complete |
| **F2: Company Verification** | Authoritative employer identity corroboration against official government company master data. | MCA-21 (2.7M+ companies) and DPIIT Recognized Startup adapters with string normalization. | ✅ Complete |
| **F3: Domain & Recruiter Verification** | Email address validation, DNS MX existence, free webmail abuse detection, and lookalike domains. | Async DNS resolution, Levenshtein distance matching, and SPF/DMARC security checks. | ✅ Complete |
| **F4: SSRF-Protected URL Analysis** | Safely ingests job postings from public URLs with defense-in-depth network protections. | Scheme validation, DNS pre-resolution, private/loopback IP rejection, and size caps. | ✅ Complete |
| **F5: Duplicate & Impersonation** | Identifies syndicated postings, multi-company reposts, and high-risk employer brand hijacking. | Near-duplicate clustering, MinHash LSH similarity, and entity name-domain mismatch rules. | ✅ Complete |
| **F6: Explainable AI (XAI)** | Transparent model contributions reconciling mathematical feature weights with decision thresholds. | Normalized TF-IDF feature weights, decision intercept reconciliation, and rule evidence badges. | ✅ Complete |
| **F7: Offer Letter Analyzer** | PDF offer letter parsing, salary/fee extraction, and selective OCR for scanned image pages. | PyMuPDF + Tesseract OCR engine, 10-page limit, 30s timeout, PII masking, and async queue. | ✅ Complete |
| **F8: Fraud Reporting & Moderation** | Incident reporting for fees, phishing, and scam behavior with reviewer moderation workflows. | Dedicated `recruiter_reports` and `review_moderation` tables with moderator appeal workflows. | ✅ Complete |
| **F9: Community Reputation** | 1–5 star employer service experience ratings with Bayesian dampening and confidence indicators. | Bayesian prior calculation with minimum sample thresholds; strictly separated from ML labels. | ✅ Complete |
| **F10: PDF Verification Report** | Formal, downloadable PDF verification reports generated strictly from persisted database evidence. | ReportLab generation with cryptographic SHA-256 digests, timestamps, and statutory caveats. | ✅ Complete |
| **F11: Chrome Extension** | Minimal-permission Manifest V3 browser extension for one-click job posting analysis. | Vanilla JS DOM extraction, pre-flight user review modal, sanitized payloads, and full report links. | ✅ Complete |
| **F12: Model Governance & Ops** | Model registry, atomic hot-swap deployment, instant rollback, and privacy-preserving drift monitoring. | Cryptographic checksum tracking, held-out evaluation gates, PSI drift monitor, and Docker Compose. | ✅ Complete |
| **Input Guard: Job Relevance** | Semantic pre-flight validation preventing non-job submissions from triggering scoring or report generation. | Multi-dimensional positive cue evaluation (Roles, Duties, Qualifications, Terms, CTA) + 8 anti-pattern disqualifiers. | ✅ Complete |

---

## 4. Quickstart with Docker Compose

The complete system (Database, Backend, OCR Worker, and Frontend) runs out of the box using Docker Compose:

```bash
# 1. Clone the repository
git clone https://github.com/your-org/JobShield-AI.git
cd JobShield-AI

# 2. Configure environment variables
cp .env.example .env

# 3. Start all services in detached mode
docker compose up -d --build

# 4. Apply database migrations
docker compose exec backend alembic upgrade head

# 5. Seed the Model Registry
docker compose exec backend python -c "from app.db.session import SessionLocal; from app.services.model_registry import seed_model_registry; seed_model_registry(SessionLocal())"
```

Once running:
- **Frontend Dashboard:** [http://localhost:5173](http://localhost:5173)
- **API Documentation (Swagger UI):** [http://localhost:8000/docs](http://localhost:8000/docs)
- **API Health Liveness:** [http://localhost:8000/health/live](http://localhost:8000/health/live)
- **API Health Readiness:** [http://localhost:8000/health/ready](http://localhost:8000/health/ready)

---

## 5. Local Development Setup

### Prerequisites
- **Python 3.12+**
- **Node.js 20+** & **npm**
- **PostgreSQL 16+**
- **Tesseract OCR** (for local PDF OCR processing)

### Backend Setup
```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --app-dir backend --port 8000
```

### Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

### Chrome Extension Setup
1. Open Google Chrome and navigate to `chrome://extensions/`.
2. Enable **Developer mode** (toggle in top-right).
3. Click **Load unpacked** and select the `extension/` directory.

---

## 6. Model Governance & Operational Endpoints

JobShield AI provides role-based administrative endpoints (`/api/v1/admin/*`) for model management and monitoring:

| Endpoint | Method | Role | Description |
|---|---|---|---|
| `/api/v1/admin/models` | `GET` | `ADMIN` | Lists all registered model versions, statuses, SHA-256 checksums, and test metrics. |
| `/api/v1/admin/models/active` | `GET` | `ADMIN` | Returns the currently deployed active model version and threshold configuration. |
| `/api/v1/admin/models/{version}/deploy` | `POST` | `ADMIN` | Atomically deploys an evaluated candidate model with zero downtime and instant rollback on failure. |
| `/api/v1/admin/models/rollback` | `POST` | `ADMIN` | Atomically reverts to the previously archived active model with security audit logging. |
| `/api/v1/admin/monitoring/drift` | `GET` | `ADMIN` | Computes Population Stability Index (PSI) and category divergence without accessing raw user text. |
| `/api/v1/admin/retraining/provenance` | `GET` | `ADMIN` | Confirms dataset provenance, approved label counts, and quarantine of unreviewed community data. |
| `/api/v1/admin/retraining/trigger` | `POST` | `ADMIN` | Manually triggers retraining against approved labels, staging candidate models without auto-deployment. |

---

## 7. Testing & Verification

Execute the comprehensive automated test suites covering backend services, frontend components, and the browser extension:

```bash
# Backend Test Suite (303 passing tests)
.\.venv\Scripts\pytest tests/ -q

# Frontend Test Suite (39 passing tests)
npm --prefix frontend test -- --run

# Frontend Production Build
npm --prefix frontend run build

# Chrome Extension Test Suite (9 passing tests)
node --test extension/tests/extension.test.js
```

---

## 8. Documentation Index

- [`docs/hosting_analysis.md`](docs/hosting_analysis.md): Hosting provider comparison (Render vs Vercel vs Self-Hosted VPS), Tesseract limits, and memory constraints.
- [`docs/deployment.md`](docs/deployment.md): Single-node Docker Compose setup, least-privilege PostgreSQL permissions, health checks, and rollback runbooks.
- [`docs/data_provenance.md`](docs/data_provenance.md): EMSCAD/MCA-21 licensing, cluster-isolated splitting, and training-label quarantine protocol.
- [`docs/model_registry.md`](docs/model_registry.md): Model versioning register, Platt scaling calibration, evaluation gates, and atomic deployment Hot-Swap.
- [`docs/privacy_security.md`](docs/privacy_security.md): Threat modeling, PII masking, SSRF defenses, IDOR authorization, and structured logging.
- [`docs/risk_scoring.md`](docs/risk_scoring.md): Comprehensive composite risk engine specification and override floor schedule.
- [`docs/architecture.md`](docs/architecture.md): Full end-to-end data flows, entity relationships, and component interactions.
- [`ml/model_card.md`](ml/model_card.md): Formal model card for `v1.1.0` detailing dataset clustering, calibration curves, and operational trade-offs.
