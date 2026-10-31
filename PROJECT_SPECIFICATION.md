# JobShield AI — Master Project Specification
**Document type:** Product requirements, technical architecture, implementation plan, and AI-agent handoff brief  
**Project name:** JobShield AI  
**Full name:** Explainable AI-Powered Job & Internship Verification Platform  
**Project status:** Planned / in development. The development environment has been prepared, but a feature must not be described as implemented until code has been built and tested.

---

## 1. Instructions for Any AI Coding Agent

You are helping build **JobShield AI**, a full-stack platform that helps people assess potentially fraudulent job postings, internships, recruiter communications, and offer letters.

Treat this document as the authoritative project specification. Before editing or generating code:

1. Inspect the existing repository and preserve any working implementation.
2. Do not overwrite files blindly. Explain the intended structure and create a phased implementation plan.
3. Build a runnable, testable MVP first, then add advanced modules incrementally.
4. Use the technology choices in this document unless a genuine compatibility issue requires a change. If a change is necessary, explain it and update the documentation.
5. Do not invent datasets, company records, verification results, performance metrics, or successful tests.
6. Never claim a feature is complete unless its code, tests, and user-facing behavior exist.
7. Use environment variables for secrets. Never commit passwords, API keys, private data, uploaded offer letters, database dumps, or `.env` files.
8. Add tests, clear error handling, logging that avoids sensitive data, and a README as implementation progresses.
9. Use migrations for database schema changes. Do not silently drop or recreate user data.
10. Follow privacy, security, source licensing, website terms, and safe browsing rules described below.

The first implementation target is a **local development MVP** that runs on the user's Windows machine. Deployment comes later.

---

## 2. Product Goal and Scope

### 2.1 Problem
Job seekers can encounter fake job postings, internship scams, company impersonation, fraudulent recruiters, requests for upfront fees, suspicious links, misleading offer letters, and duplicate or copied job listings. A single machine-learning prediction or a company-registration lookup is not enough to determine whether an individual offer is genuine.

### 2.2 Goal
Build a platform that combines:
- Machine-learning analysis of job-posting text.
- Evidence-based company and domain verification.
- Recruiter email and communication checks.
- Job impersonation and duplicate-posting detection.
- Offer-letter text extraction and analysis.
- Explainable risk assessment.
- Community feedback and recruiter experience ratings.
- Safe next-step recommendations.
- Downloadable verification reports.
- Monitoring and controlled model improvement.

### 2.3 Product principles
- **Evidence first:** Show why a result was produced and identify the source and timestamp of each check.
- **No unsupported accusations:** A model score, low rating, unverified domain, or unmoderated report is not proof of fraud.
- **Unknown is not fraudulent:** A missing registry match or unavailable website must be shown as unknown/unverified, not automatically as fraud.
- **Separate facts from predictions:** Official registry facts, technical checks, ML outputs, and user allegations must be visibly distinct.
- **Explain uncertainty:** A low risk score does not prove a job is legitimate. A high score is a warning for further verification, not a legal conclusion.
- **Privacy by design:** Collect the minimum data required, restrict access, and define retention/deletion rules.
- **No automatic label contamination:** Community feedback does not become ground-truth training data without review and validation.

---

## 3. User Types

1. **Job seeker / visitor:** Analyzes a job URL or pasted job description, recruiter email, message, or offer letter; sees evidence and safety steps.
2. **Registered user:** Can save scans, submit feedback, rate recruitment experiences, and request corrections.
3. **Moderator / reviewer:** Reviews reports, evidence, duplicate submissions, appeals, and potential abuse.
4. **Administrator / ML maintainer:** Manages data imports, source freshness, model versions, evaluation, monitoring, and controlled releases.

For an MVP, authentication can be limited or postponed, but any feature that stores user-specific history or allows moderation must have a clear access-control design.

---

## 4. Required Result Workflow

Every completed analysis should return a consistent result with the following:

1. **Overall risk score:** 0–100, with documented, configurable risk categories.
2. **Potential fraud warning:** Show when evidence and calibrated thresholds warrant it.
3. **Evidence breakdown:** Explain each signal, its source, observation time, and confidence/limitations.
4. **Company verification:** Registered-company match, startup-recognition status when available, domain match, or unknown/unverified status.
5. **Recruiter checks:** Email/domain checks and identity consistency, where possible.
6. **ML analysis:** Model prediction and calibrated probability, shown separately from the overall risk score.
7. **Community summary:** Eligible review count, rating/confidence, moderated reports, conflicting evidence, and caveats.
8. **Recommended safe actions:** Practical steps tailored to the evidence.
9. **Limitations:** Missing sources, stale data, unsupported formats, and checks that could not be completed.
10. **Timestamp and report ID:** Include a stable scan identifier and time of analysis.

### Risk score requirements
- The 0–100 score must be designed and validated; do not make up a score from arbitrary weights and describe it as statistically calibrated.
- Keep the ML probability distinct from the composite risk score.
- Start with explicit, configurable thresholds and label them as provisional until validated against representative data.
- Calibrate probabilities when appropriate and measure calibration.
- A score below a threshold must not be called proof of legitimacy.
- Show “Insufficient evidence” or “Unable to verify” when data is inadequate.
- The explanation should show which checks contributed and how; never present fabricated explanations.

### Safe-action examples
Depending on evidence, advise users to:
- Verify the vacancy on the company's official careers page using a URL found independently.
- Contact the company through an independently sourced contact channel.
- Never pay an application, interview, training, equipment, security-deposit, or offer-release fee to obtain a job.
- Avoid opening suspicious attachments/links or sharing OTPs, passwords, bank credentials, or unnecessary identity documents.
- Preserve relevant messages and offer documents if they suspect fraud.
- Report a suspected scam through appropriate platform or official channels. Do not imply JobShield itself makes a legal determination.

---

## 5. Feature Requirements

### F1. Job-posting fraud detection
- Accept pasted job text and, where safe and permitted, a public job URL.
- Extract relevant fields such as title, company, location, description, salary, experience, requirements, contact details, and application instructions.
- Use a baseline text classifier such as TF-IDF + Logistic Regression; compare suitable alternatives (for example, Naive Bayes, Random Forest, or gradient boosting) using proper validation.
- Detect patterns such as upfront fees, unrealistic compensation claims, urgency, suspicious contact instructions, requests for sensitive information, and inconsistent job details.
- Return a model prediction, calibrated probability if supported, evidence, limitations, and safe actions.
- Rule-based signals must be disclosed as rules, not represented as ML discoveries.
- Do not rely on one keyword or one feature to label a job fraudulent.

### F2. Multi-source company and startup verification
Use independent sources and preserve provenance:
- **MCA Company Master Data:** https://data.gov.in/catalog/company-master-data
- **MCA Corporate Data Management portal:** https://mcacdm.nic.in/company-master-details
- **Startup India:** https://www.startupindia.gov.in/
- **DPIIT-recognized startup data/catalog where available:** https://data.gov.in/catalog/startup-recognized-dpiit
- Official company website and careers/contact pages.
- Public DNS/domain information and permitted technical checks.
- User-submitted job/offer evidence with appropriate consent.

Rules:
- MCA registration validates an entity's registry presence/status; it does **not** validate a specific recruiter or vacancy.
- DPIIT recognition is a separate status. A genuine startup may not be DPIIT-recognized.
- Do not assume all Indian business types appear in a single dataset. Companies, LLPs, proprietorships, and other forms may have different records.
- Handle name matching carefully (legal name, trade name, punctuation, abbreviations, CIN where available).
- Record source URL/name, retrieval/check timestamp, dataset version or last-updated date, match method, and confidence.
- Distinguish `MATCHED`, `NO_MATCH`, `UNKNOWN`, `STALE`, and `SOURCE_UNAVAILABLE`. `NO_MATCH` is not proof of fraud.
- Prefer linked, normalized tables rather than blindly merging all datasets into one raw table.

### F3. Recruiter email and domain verification
Maintain a permission-aware directory focused primarily on **company domains and evidence-backed verification records**, not an unverified public blacklist of individual people.

Potential permitted collection sources:
- Official company careers/contact pages.
- Public job postings accessed in compliance with their terms.
- Official company registries and startup sources.
- DNS records and public domain/email-security information.
- User-submitted offers and emails where the user has appropriate rights and consents to analysis.
- Moderated community reports and reviewed verification evidence.

Do not:
- Harvest private personal email addresses indiscriminately.
- Scrape websites/platforms in violation of their terms or access controls.
- Test whether an email exists by sending unsolicited messages.
- Collect passwords, OTPs, or entire inboxes.
- Publish an individual's address as fraudulent solely based on a report or model output.

Suggested checks:
- Email syntax.
- DNS and MX availability.
- SPF, DKIM, and DMARC records when publicly available and technically feasible.
- Compare the sender's domain to independently verified company domains.
- Check for lookalike domains, misspellings, suspicious redirects, or identity mismatches.
- Analyze user-pasted message text for fee requests, urgency, suspicious links, and requests for sensitive information.
- Record the check date and limitations.

Important limitations:
- A legitimate employer may use an agency, subdomain, or mainstream email provider.
- A valid domain or passing email-security record does not prove the sender is authorized.
- Spoofing, compromised accounts, and lookalike domains can exist.
- Show statuses such as `PUBLISHED_BY_COMPANY`, `DOMAIN_MATCH`, `IDENTITY_UNVERIFIED`, `MISMATCH_DETECTED`, and `UNDER_REVIEW`; explain each status.

### F4. Job impersonation detection
- Compare the claimed company identity, domain, logo/name if applicable, job title, vacancy, contact details, and wording against independently sourced official information.
- Detect lookalike domains and inconsistent recruiter identities.
- Flag copied branding or vacancy text as a signal requiring review, not conclusive proof.
- Preserve evidence and sources used for comparison.
- Provide a confidence level and clear limitations.

### F5. Duplicate posting detection
- Detect exact and near-duplicate postings using normalized text, hashes, TF-IDF/cosine similarity, and/or sentence embeddings.
- Compare relevant fields such as title, company, location, contact address, description, and posting date.
- Identify likely reposts separately from suspicious copies.
- Do not automatically classify duplicate postings as fraudulent; legitimate employers often repost jobs.
- Avoid data leakage when training/evaluating models by grouping related postings appropriately.

### F6. Explainable AI
- Use suitable model-specific explanations and optionally SHAP where computationally appropriate.
- Include rule-based evidence as a separate evidence type.
- Show human-readable reasons, affected text/fields where safe, source, and caveats.
- Ensure explanations reflect the actual model and input. Never fabricate feature importance.
- Explain that feature contribution does not prove criminal intent.

### F7. Offer-letter analyzer (PDF + OCR)
- Accept PDF files; optionally support image files if designed and tested.
- Extract text using PyMuPDF. Use Tesseract OCR for scanned/image-based documents.
- Detect fields such as company name, candidate name if needed, role, salary, dates, sender/contact details, links, fees/deposits, and unusual clauses.
- Compare extracted claims with company/domain verification and suspicious-pattern rules.
- Preserve original documents only when necessary and with a clear retention policy; delete temporary files safely.
- Enforce file size, page count, MIME/type, processing-time, and OCR resource limits.
- Treat the result as an assessment, not legal or definitive authentication.
- Warn users not to upload documents containing unnecessary sensitive data.

### F8. Community-powered feedback
Allow users to submit one of:
- `I believe this offer is fraudulent`
- `I had a legitimate experience`
- `I am unsure / could not verify`

Suggested reasons:
- Upfront fee requested.
- Suspected impersonation.
- Suspicious communication.
- Independently verified.
- Other.

Allow optional details and supporting evidence, but tell users not to submit passwords, OTPs, full bank details, or unnecessary personal information.

Requirements:
- Store community feedback separately from confirmed ground-truth labels.
- Support moderation, duplicate-report detection, coordinated-voting/low-quality-report detection, conflicting reports, appeals/corrections, and audit history.
- Do not expose unsupported allegations as facts.
- Use community feedback as a risk signal only after appropriate validation/moderation.
- Only reviewed and appropriately supported labels may enter controlled periodic retraining.
- Evaluate any updated model on an independent test set before deployment.

### F9. Recruiter reputation and 1–5 star rating
- Users can rate their recruitment experience from 1 to 5 stars and optionally write a review.
- Capture an experience category (for example, communication, interview process, role clarity, or offer process) and optional supporting evidence.
- Separate **service-quality rating** from **fraud-related reports**.
- Display average rating, number of eligible reviews, and a confidence/coverage indicator separately from the fraud risk score.
- Use a Bayesian-adjusted average to reduce instability from very few reviews:

  `R = (n / (n + m)) * r_bar + (m / (n + m)) * C`

  where `n` is the number of eligible reviews, `r_bar` is their mean rating, `C` is the platform-wide prior average, and `m` is a configurable prior strength. Define these values transparently and validate the method.
- Detect duplicate, fake, or coordinated voting; allow moderation and appeals.
- Link reviews to a company, domain, specific job/offer, or recruiter only when there is a defensible evidence-based link.
- A low star rating alone must not classify a person/company as fraudulent. Good service ratings do not prove a job offer is genuine.
- Community reviews do not automatically become training labels.

### F10. Verification report (PDF)
Generate a downloadable PDF containing:
- Scan/report ID and timestamp.
- Submitted job/offer summary, minimizing personal information.
- Overall risk score/category and provisional-threshold notice where relevant.
- Model prediction/probability separately from the composite score.
- Company registry/startup verification status.
- Domain/recruiter checks.
- Impersonation and duplicate-posting signals.
- Key explainable evidence and source provenance.
- Community rating, review count, moderation/uncertainty notes.
- Recommended safe actions.
- Missing checks, stale data, and limitations.
- A disclaimer that the result is informational and not a definitive legal finding.

Use ReportLab. Do not invent evidence or verification results in generated reports.

### F11. Chrome extension
- Provide a browser extension for supported job pages.
- Extract only necessary, permitted page information after the user invokes the extension.
- Send data to the JobShield API over HTTPS in production.
- Respect each website's terms and browser policies; do not bypass authentication or access controls.
- Request minimal extension permissions and clearly explain what is sent to the server.
- Avoid collecting credentials, unrelated page content, or browsing history.
- Show risk/evidence/next actions and link to the full report.
- The extension itself runs in the user's browser; its backend API is hosted separately.

### F12. Model monitoring and controlled improvement
Track:
- Precision, recall, F1-score, confusion matrix.
- False-positive and false-negative rates.
- PR-AUC/ROC-AUC where appropriate.
- Probability calibration.
- Performance by relevant data segments when data size and privacy permit.
- Input drift and prediction distribution drift.
- Model version, dataset version, training configuration, evaluation date, and deployment history.

Rules:
- No automatic retraining on every user submission.
- Separate unreviewed community reports from ground-truth labels.
- Prevent train/test leakage; split by company, duplicate cluster, or time where appropriate.
- Keep an independent evaluation set.
- Require review and evaluation gates before model deployment.
- Retain rollback capability and model/version metadata.
- Do not claim performance numbers until measured on documented data.

### F13. Scan history and administration
Recommended for the complete product:
- Store scan metadata and results subject to privacy/retention rules.
- Allow users to delete their own stored data where applicable.
- Provide source freshness/status, review moderation, model version, and import history for administrators.
- Keep audit records for sensitive administrative changes.
- Apply role-based access control before exposing moderation/admin endpoints.

---

## 6. Technology Stack

Use one primary backend framework. The planned default is **FastAPI** because this is an API-centric application. Do not also build a parallel Flask backend unless a specific requirement justifies it.

### Frontend
- React
- Vite
- Tailwind CSS
- React Router
- Recharts for charts/dashboard visuals

### Backend
- Python 3.12
- FastAPI
- Uvicorn
- Pydantic / pydantic-settings
- SQLAlchemy
- Alembic database migrations
- `psycopg` for PostgreSQL
- `python-multipart` for file upload handling

### Machine learning and data processing
- NumPy
- Pandas
- SciPy
- Scikit-learn
- Matplotlib
- Joblib
- SHAP
- TF-IDF and cosine similarity; embeddings can be added for semantic similarity

### Website, domain, and email analysis
- Requests
- BeautifulSoup
- Standard-library parsing and controlled DNS/network checks as appropriate
- No unauthorized scraping or access-control bypass

### Documents and reports
- PyMuPDF (`import pymupdf` preferred over deprecated `import fitz`)
- Tesseract OCR external application
- `pytesseract`
- Pillow
- ReportLab

### Database
- PostgreSQL 18 is the intended local server based on the user's current machine state.
- PostgreSQL 17 is also installed, but its Windows service is stopped.
- Use one version consistently for the project. The `psql` command currently resolves to PostgreSQL 17.11, so explicitly use PostgreSQL 18's tools or adjust PATH if PostgreSQL 18 is selected.
- pgAdmin 4 is available for database administration.
- Database name planned: `jobshield_db`.
- Never put the database password in source code.

### Testing and quality
- pytest
- HTTPX / FastAPI test client
- Automated unit, integration, API, ML pipeline, upload-security, and authorization tests
- Add linting/formatting tools if needed and document them.

### Containers and deployment
- Docker Desktop
- Docker Compose
- Vercel is a possible frontend host.
- Render is a possible host for the backend, managed PostgreSQL, and background worker.
- The user asked about single-provider hosting; Render is the current recommended one-provider ecosystem option, though components can still be separate services and costs/resources depend on plan.
- Do not assume free-tier persistence or capacity. Verify current provider limits when deployment begins.
- For local development, PostgreSQL can run natively or in Docker. Do not run duplicate databases without clearly identifying which one the app uses.

---

## 7. Tools Already Installed / Environment State

The user is working on Windows, with the project folder on the D: drive.

### Confirmed by user command output
- Python 3.12.1 is the primary `python` command.
- Node.js `v24.11.0`.
- npm `11.6.1`.
- Git `2.54.0.windows.1`.
- Docker `29.8.2`.
- Docker Compose `v5.5.1`.
- Docker test container `hello-world` ran successfully.
- PostgreSQL 17 and 18 installations exist.
- Windows service `postgresql-x64-18` was reported running; `postgresql-x64-17` was stopped.
- `psql --version` returned PostgreSQL 17.11 because this is the version currently earlier in PATH.
- pgAdmin 4 was opened and a Query Tool session was shown, but the intended project database and connection credentials still need explicit verification.

### Project path and virtual environment
- Project folder: `D:\JobShield-AI`
- Python virtual environment: `D:\JobShield-AI\.venv`
- The virtual environment was activated successfully in PowerShell.
- `pip` upgraded successfully to `26.2.1`.
- The prompt shows `(.venv) PS D:\JobShield-AI>` when active.

### Python packages confirmed installed
The user's terminal log confirms successful installation of:
- FastAPI
- Uvicorn with standard extras
- SQLAlchemy
- `psycopg[binary]`
- Alembic
- pydantic-settings
- python-multipart
- Requests
- BeautifulSoup
- PyMuPDF
- pytesseract
- Pillow
- ReportLab
- pytest
- HTTPX

A verification command successfully imported:
`fastapi, sqlalchemy, sklearn, pandas, numpy, shap, fitz, reportlab`

The import emitted a PyMuPDF deprecation warning for `fitz`; new code should use `import pymupdf`.

The log shown so far does **not** prove whether all of the following are installed: NumPy, Pandas, SciPy, Scikit-learn, Matplotlib, Joblib, SHAP. Some imports worked, but run a direct verification before assuming all are present.

### Still to verify / install
- Tesseract OCR executable: `pytesseract` Python package is installed, but the separate OCR program still needs to be installed and its executable path verified.
- React frontend packages/project scaffold: not yet created.
- Tailwind CSS: not yet configured.
- `jobshield_db` creation and successful FastAPI-to-PostgreSQL connection: not yet verified.
- Antigravity is the planned coding tool; user will open `D:\JobShield-AI` in it.
- `requirements.txt` should be generated after confirming all dependencies, e.g. `python -m pip freeze > requirements.txt`.

Do not state that the whole application is implemented. So far, this is environment preparation.

---

## 8. Database Design (Recommended Initial Schema)

Use normalized relational tables and foreign keys. Avoid one giant table.

Suggested core tables:

1. `companies`
   - `id`, `legal_name`, `normalized_name`, `cin` nullable, `entity_type`, `registry_status`, `created_at`, `updated_at`

2. `company_source_records`
   - `id`, `company_id`, `source_name`, `source_url`, `source_record_id`, `source_status`, `retrieved_at`, `source_updated_at`, `match_method`, `match_confidence`, `raw_metadata` JSONB where appropriate

3. `startup_recognition`
   - `id`, `company_id`, `recognition_status`, `recognition_id` nullable, `source_url`, `checked_at`, `status_details`

4. `company_domains`
   - `id`, `company_id`, `domain`, `source_url`, `verification_status`, `evidence_summary`, `checked_at`, `is_primary`

5. `job_listings`
   - `id`, `company_id` nullable, `source_url` nullable, `title`, `location`, `description`, `normalized_text`, `content_hash`, `posted_at` nullable, `first_seen_at`, `last_seen_at`, `source_name`, `ingestion_method`

6. `job_similarity_matches`
   - `id`, `job_id`, `matched_job_id`, `similarity_method`, `similarity_score`, `created_at`, `review_status`

7. `recruiter_email_scans`
   - `id`, `job_id` nullable, `claimed_company_id` nullable, `email_or_redacted_identifier`, `domain`, `status`, `created_at`, `retention_expires_at` nullable

8. `domain_checks`
   - `id`, `domain`, `dns_status`, `mx_status`, `spf_status`, `dkim_status`, `dmarc_status`, `lookalike_flags` JSONB, `source_details` JSONB, `checked_at`

9. `verification_evidence`
   - `id`, `scan_id`, `evidence_type`, `source_name`, `source_url`, `observed_at`, `status`, `confidence` nullable, `summary`, `limitations`, `metadata` JSONB

10. `prediction_history`
    - `id`, `scan_id`, `model_version`, `predicted_class`, `model_probability` nullable, `risk_score`, `risk_category`, `threshold_version`, `explanation` JSONB, `created_at`

11. `user_reviews`
    - `id`, `user_id` nullable for anonymous MVP, `company_id` nullable, `job_id` nullable, `domain_id` nullable, `experience_rating` 1–5, `experience_category`, `review_text` nullable, `moderation_status`, `created_at`, `updated_at`

12. `recruiter_reports`
    - `id`, `user_id` nullable, `company_id` nullable, `job_id` nullable, `domain` nullable, `report_type`, `reason`, `details` nullable, `evidence_reference` nullable, `moderation_status`, `created_at`

13. `review_moderation`
    - `id`, `review_id` or `report_id`, `moderator_id`, `action`, `reason`, `created_at`

14. `training_labels`
    - `id`, `job_id`, `label`, `label_source`, `reviewed_by`, `evidence_reference`, `label_status`, `created_at`, `approved_for_training_at` nullable

15. `dataset_imports`
    - `id`, `dataset_name`, `version_or_snapshot`, `license`, `source_url`, `imported_at`, `row_count`, `validation_summary`

16. `model_versions`
    - `id`, `version`, `artifact_path`, `dataset_snapshot`, `metrics` JSONB, `calibration_summary` JSONB, `evaluation_status`, `created_at`, `deployed_at` nullable

17. `scan_requests`
    - `id`, `user_id` nullable, `input_type`, `input_reference` nullable, `status`, `created_at`, `completed_at` nullable, `retention_expires_at` nullable

Schema can be simplified for MVP, but retain source provenance, model versioning, moderation status, and separation between reviews/reports and confirmed training labels.

---

## 9. API Design (Initial Proposal)

Use `/api/v1` versioning. Validate all inputs with Pydantic and use explicit response models.

Potential endpoints:
- `GET /health` — liveness check.
- `GET /api/v1/health/ready` — dependency readiness, without exposing secrets.
- `POST /api/v1/analyze/job-text` — analyze pasted job text.
- `POST /api/v1/analyze/job-url` — analyze a permitted public job URL.
- `POST /api/v1/analyze/recruiter-email` — analyze an email address/domain and optionally user-pasted message text.
- `POST /api/v1/analyze/offer-letter` — upload and analyze an offer letter.
- `GET /api/v1/scans/{scan_id}` — retrieve a scan result with authorization checks.
- `GET /api/v1/scans/{scan_id}/report.pdf` — generate/download the verification report.
- `POST /api/v1/jobs/{job_id}/feedback` — submit community feedback.
- `POST /api/v1/reviews` — submit an experience rating/review.
- `GET /api/v1/companies/{company_id}` — retrieve sourced company verification summary.
- `GET /api/v1/companies/{company_id}/reputation` — return rating and review counts separately from fraud risk.
- `POST /api/v1/reports/{report_id}/appeal` — submit correction/appeal where user identity and workflow permit.
- Admin-only endpoints for moderation, data imports, and model/version management.

Do not expose moderator/admin endpoints without authentication and authorization. Add request limits, file limits, rate limiting where feasible, and clear error responses.

---

## 10. Data Sources and ML Pipeline

### 10.1 Candidate training data
- Use a suitable, appropriately licensed public job-fraud dataset, such as a Kaggle dataset or the academic EMSCAD dataset, only after checking its license, terms, provenance, schema, label meaning, and limitations.
- Do not assume a dataset is available or license-compatible until verified.
- Do not mix registry records with job-level fraud labels without a defined relationship.
- Keep data-source records, data versions, cleaning rules, and reproducible preprocessing.

### 10.2 ML pipeline
1. Acquire permitted dataset and document provenance/license.
2. Inspect class balance, missing values, duplicate records, label quality, and sensitive fields.
3. Deduplicate and normalize text carefully.
4. Split data into training/validation/test. Group duplicate postings and, where feasible, companies/time periods to reduce leakage.
5. Build a simple baseline: TF-IDF + Logistic Regression.
6. Compare alternatives only when justified.
7. Tune thresholds based on the cost of false positives and false negatives.
8. Evaluate precision, recall, F1, confusion matrix, PR-AUC/ROC-AUC where appropriate, and calibration.
9. Generate explanations consistent with the selected model.
10. Save model, vectorizer/preprocessing pipeline, version, dataset snapshot, metrics, and model card.
11. Evaluate on an independent holdout before deployment.
12. Monitor performance and drift; roll back if necessary.

### 10.3 Data leakage and feedback policy
- Near-duplicate listings should not leak across training and test sets.
- User feedback and star ratings are not ground truth.
- Only reviewed, supported labels may be considered for training, with independent evaluation.
- Do not retrain directly from the public rating average or a stream of unmoderated reports.

---

## 11. Security, Privacy, and Abuse Prevention

### Website URL safety / SSRF prevention
When the server fetches a user-provided URL:
- Allow only supported `http`/`https` schemes.
- Reject localhost, private, loopback, link-local, multicast, and cloud metadata destinations.
- Resolve and validate IP addresses; revalidate after redirects and DNS changes where feasible.
- Limit redirects, timeouts, downloaded bytes, content types, and parsing time.
- Do not fetch arbitrary internal services or bypass logins/CAPTCHAs/access controls.
- Do not execute downloaded JavaScript or documents.

### Upload security
- Enforce maximum size, file count, page count, allowed file types, and processing time.
- Do not trust filename or MIME type alone.
- Store temporary uploads outside public web roots and delete them according to retention policy.
- Protect against malicious PDFs, decompression/resource abuse, and OCR exhaustion.
- Do not log full document contents, email addresses, or sensitive personal details by default.

### Secrets and access control
- Use `.env` locally and hosting environment variables in production.
- Commit `.env.example` only with placeholders.
- Add `.env`, `.venv`, model artifacts/data uploads when appropriate, caches, logs, and secrets to `.gitignore`.
- Use least-privilege database credentials for the application; do not use the `postgres` superuser in production.
- Use authentication and role-based access for reviews, scan history, moderation, and admin functions.
- Use HTTPS in production and appropriate CORS origins.
- Minimize stored email data; mask/redact where possible.
- Define retention and deletion policies.
- Maintain a correction/appeal mechanism for disputed records.

### Community integrity
- Rate-limit feedback and reviews.
- Detect duplicates and suspicious bursts/coordinated voting.
- Preserve moderation audit trails.
- Distinguish user allegations from verified facts.
- Avoid public doxxing or unsupported allegations against individuals.

---

## 12. Local Development Setup

### Known local folder
`D:\JobShield-AI`

### Python environment
The user successfully created and activated:
`D:\JobShield-AI\.venv`

Activation in PowerShell:
```powershell
cd D:\JobShield-AI
.venv\Scripts\Activate.ps1
```

### Verify Python
```powershell
python --version
python -m pip --version
```

### Verify important imports
```powershell
python -c "import fastapi, sqlalchemy, sklearn, pandas, numpy, shap, pymupdf, reportlab; print('Core dependencies OK')"
```

Use `import pymupdf`, not `import fitz`, in new code.

### Verify Node/Git/Docker
```powershell
node -v
npm -v
git --version
docker --version
docker compose version
docker run hello-world
```

These tools have previously been verified by the user, including a successful Docker `hello-world` run.

### PostgreSQL
- PostgreSQL 18 service was reported running.
- PostgreSQL 17 service was stopped.
- `psql` in PATH reports version 17.11.
- PostgreSQL 18 executable is expected at `C:\Program Files\PostgreSQL\18\bin\psql.exe`.
- Use explicit PostgreSQL 18 path while verifying:
```powershell
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" --version
Get-Service *postgres*
```
- Verify connection and create `jobshield_db` only after confirming the correct server, port, username, and password.
- Never put a real password in code or documentation.

### Tesseract OCR
The Python wrapper `pytesseract` is installed. Install the separate Windows Tesseract OCR executable and verify:
```powershell
tesseract --version
```
If it is not in PATH, configure the executable path securely in local environment/configuration.

### React frontend (not yet scaffolded)
From `D:\JobShield-AI`, a possible first scaffold:
```powershell
npm create vite@latest frontend -- --template react
cd frontend
npm install
npm install react-router-dom recharts
```
Then configure Tailwind CSS using its current Vite instructions. Do not generate the frontend until inspecting whether a scaffold already exists.

### Dependency lock / requirements
After verifying packages:
```powershell
python -m pip freeze > requirements.txt
```
For reproducible environments, review and test the resulting dependency file rather than blindly accepting incompatible version combinations.

---

## 13. Suggested Repository Layout

Adapt to existing files; do not overwrite a pre-existing structure without inspection.

```text
JobShield-AI/
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── services/
│   │   ├── hooks/
│   │   └── assets/
│   ├── public/
│   └── package.json
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/
│   │   ├── core/
│   │   ├── db/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── services/
│   │   ├── ml/
│   │   ├── verification/
│   │   ├── documents/
│   │   ├── reports/
│   │   └── workers/
│   ├── migrations/
│   ├── tests/
│   └── requirements.txt
├── extension/
│   ├── manifest.json
│   ├── src/
│   └── README.md
├── ml/
│   ├── data/                 # excluded from Git unless license permits
│   ├── notebooks/
│   ├── training/
│   ├── evaluation/
│   ├── artifacts/            # usually excluded from Git or managed intentionally
│   └── model_card.md
├── docs/
│   ├── architecture.md
│   ├── data_sources.md
│   ├── privacy_security.md
│   └── model_card_template.md
├── tests/
├── docker-compose.yml
├── .env.example
├── .gitignore
├── README.md
└── PROJECT_SPECIFICATION.md
```

For a small MVP, a simpler layout is acceptable. Keep clear boundaries between API, database, ML, verification, document processing, and reporting.

---

## 14. UI / UX Requirements

Create a clean, responsive, trustworthy interface. Do not use visual design to imply certainty that the data does not support.

Suggested pages:
- Landing page with concise explanation and clear limitations.
- Analyze page with tabs/cards for job text, job URL, recruiter email/message, and offer-letter upload.
- Results page with risk score/category, evidence timeline, company/recruiter verification, model explanation, community summary, safe actions, and report download.
- Company profile/reputation page with source-attributed registry/domain details and separate service-quality ratings.
- Feedback/review form with privacy guidance.
- Scan history page if accounts are implemented.
- Moderator/admin interface protected by authorization.
- About / data sources / privacy / disclaimer pages.

Accessibility:
- Clear text labels and keyboard navigation.
- Do not rely only on color to express risk.
- Explain icons and technical statuses.
- Show loading, error, no-match, source-unavailable, and insufficient-evidence states.

---

## 15. Deployment Plan

Preferred initial deployment option: one hosting provider ecosystem such as Render, with separate services where appropriate:
- Web service for API and/or frontend.
- Managed PostgreSQL.
- Background worker for OCR, expensive PDF analysis, or scheduled monitoring if needed.
- Persistent object storage for retained files/reports if required and configured safely.

Alternative:
- Vercel for React frontend.
- Render for backend, database, and worker.

Deployment constraints:
- Do not run model training in a normal web request.
- Do not rely on ephemeral local disk for permanent uploads, SQLite data, or reports.
- Heavy OCR/PDF work should have resource limits and may be queued.
- Use environment variables for database URLs and secrets.
- Configure CORS for known frontend origins.
- Add health checks, structured logs, database migrations, and a rollback plan.
- Test with realistic resource usage before public launch.
- Verify current hosting prices, free-tier limits, timeouts, storage, and database retention when deploying; do not assume free services are persistent.

---

## 16. Testing and Acceptance Criteria

### Core functional tests
- Text analysis accepts valid text and rejects empty/oversized input.
- URL analysis rejects unsafe destinations and handles timeout/blocked/unsupported sites gracefully.
- Company match returns source provenance and differentiates no match from fraud.
- Email/domain checks return statuses and limitations.
- Duplicate detection identifies known duplicates without automatically calling them fraudulent.
- Offer-letter processing handles text PDFs, scanned PDFs, invalid files, oversized files, and OCR failures safely.
- PDF report matches the stored scan result and includes timestamps, sources, caveats, and version metadata.
- Reviews and reports are moderated and kept separate from training labels.
- Ratings display counts/confidence and do not automatically decide fraud status.
- Admin endpoints require authorization.
- Database migrations can be applied to a fresh database.
- No secrets are committed to Git.

### ML acceptance criteria
- Dataset provenance/license is documented.
- Train/validation/test separation is reproducible.
- Duplicate/company/time leakage is considered.
- Baseline metrics and confusion matrix are recorded.
- Thresholds and calibration limitations are documented.
- Model and preprocessing versions are stored together.
- Explanations are consistent with the selected model.
- No unverified model performance claims appear in the UI or README.

### Deployment acceptance criteria
- App starts from documented commands.
- Environment variables are documented in `.env.example`.
- Health endpoint works.
- Database connection uses least privilege.
- Upload limits and URL-fetch protections are tested.
- Frontend can reach the API using configured origins.
- Production logs avoid secrets and sensitive document content.

---

## 17. Phased Implementation Roadmap

### Phase 0 — Repository and environment
- Inspect the folder.
- Add README, `.gitignore`, `.env.example`, and dependency files.
- Confirm PostgreSQL 18 connection.
- Add a health endpoint and frontend scaffold.
- Establish test and lint conventions.

### Phase 1 — MVP
- React dashboard and analyze form.
- FastAPI backend.
- PostgreSQL schema and migrations.
- Baseline job-text classifier pipeline.
- Initial results UI with provisional score, evidence, limitations, and safe actions.
- Unit/integration tests.

### Phase 2 — Verification evidence
- Company data import adapters and source provenance.
- Company/domain matching.
- DNS/MX and email-security checks where available.
- Recruiter email/message analysis.
- SSRF protections and source freshness indicators.

### Phase 3 — Advanced detection and explanations
- Job impersonation checks.
- Duplicate-posting similarity.
- SHAP/model-specific explanation and evidence presentation.
- Risk-score design/calibration and threshold validation.

### Phase 4 — Offer letters and reports
- PDF extraction.
- OCR integration.
- Offer-letter signal analysis.
- PDF verification report generation.
- Upload safety and retention.

### Phase 5 — Community and reputation
- User feedback categories.
- 1–5 star service-experience reviews.
- Bayesian-adjusted rating with confidence/count display.
- Moderation, duplicate/coordinated voting detection, appeals/corrections.
- Explicit separation from ground-truth labels.

### Phase 6 — Browser extension
- Minimal-permission Chrome extension.
- Supported-site extraction on user action.
- API integration and result view.
- Privacy disclosure and tests.

### Phase 7 — Production readiness
- Model monitoring, drift checks, model registry/versioning.
- Background worker and scheduled jobs.
- Docker Compose setup.
- Security and load testing.
- Deployment and GitHub documentation.

Do not attempt to implement all phases in one enormous code-generation action. Implement one phase at a time, run it, test it, and update documentation before proceeding.

---

## 18. GitHub and Project Presentation

Repository should include:
- Accurate README with problem, features, architecture, setup, screenshots, API docs, data sources, license notes, limitations, and deployment instructions.
- Architecture diagram and database ER diagram.
- `requirements.txt` or a well-managed lock file.
- `.env.example`, never real credentials.
- Tests and CI where feasible.
- Model card documenting dataset, label definitions, metrics, calibration, limitations, and intended use.
- Data provenance/license notes.
- Sample synthetic data clearly marked as synthetic, never presented as real verified records.
- Screenshots of actual implemented behavior.
- Clear distinction between implemented, planned, and experimental features.

Potential project summary:
“JobShield AI is an explainable job and internship verification platform that combines job-text classification, company/domain evidence, impersonation and duplicate detection, offer-letter analysis, and moderated community feedback to help users make safer decisions. Its results are risk assessments, not definitive declarations of fraud.”

---

## 19. Important Constraints / Non-Goals

- Do not promise that all fraudulent offers can be detected.
- Do not assert that a company/recruiter is fraudulent solely because no official record was found.
- Do not treat MCA/DPIIT data as proof that a specific job is authentic.
- Do not treat star ratings as proof of fraud or legitimacy.
- Do not auto-train on raw reviews or reports.
- Do not scrape or collect data contrary to source terms or privacy requirements.
- Do not expose private recruiter/user data in a public blacklist.
- Do not claim the model is accurate without evaluation on a suitable independent dataset.
- Do not invent scan results, sources, company records, user reviews, or performance metrics.
- Do not deploy OCR/ML-heavy tasks without resource limits and timeouts.
- Do not place secrets in frontend bundles, source control, or logs.

---

## 20. First Task for the AI Agent

Start by inspecting `D:\JobShield-AI` and report:
1. Existing files and folders.
2. Which frontend/backend/database files already exist.
3. Python environment and dependency status.
4. PostgreSQL 18 connectivity status (do not assume it is configured just because the service runs).
5. Whether Tesseract OCR is installed.
6. Any problems found.

Then propose the smallest Phase 0 implementation plan. After approval or according to the user's instruction, create the project skeleton without overwriting existing work. Build and verify the health endpoint and database connection before proceeding to ML functionality.

**Project status reminder:** The development tools have been installed and some Python packages verified. The complete JobShield AI application, datasets, model, database schema, extension, monitoring, and deployment are still to be built and tested.
