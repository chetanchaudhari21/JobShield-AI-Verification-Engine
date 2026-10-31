# JobShield AI — Production Privacy, Security & Compliance Audit

> **Specification Reference:** `PROJECT_SPECIFICATION.md` Section 15 (Security & Privacy), Section 16 (Acceptance Criteria).  
> **Last Updated:** October 2026

---

## 1. Overview & Threat Model

JobShield AI operates in an adversarial environment where job seekers upload sensitive career documents and bad actors attempt to evade detection, scrape databases, or abuse system infrastructure.

The security architecture mitigates six primary threat vectors:
1. **PII and Confidential Document Exposure:** Accidental leakage of resumes, offer letters, or contact details in system logs or databases.
2. **Server-Side Request Forgery (SSRF):** Malicious job URLs targeting cloud metadata services (`169.254.169.254`) or internal microservices.
3. **Insecure Direct Object Reference (IDOR):** Unauthorized users viewing private scan reports or downloading another candidate's offer letter.
4. **Denial of Service (DoS) via Heavy OCR:** Uploading 500-page corrupted PDFs or ZIP bombs to exhaust CPU and memory.
5. **Credential Stuffing & Session Hijacking:** Brute-forcing passwords or reusing compromised refresh tokens.
6. **Data Poisoning & Adversarial Retraining:** Submitting fabricated fraud reports to corrupt ML model weights.

---

## 2. Privacy Protections & Structured Logging

### 2.1 Zero Raw Document Retention
- **In-Memory Parsing:** Uploaded offer letter PDF files and text postings are processed in-memory. File buffers are discarded immediately after feature extraction.
- **Deduplication via One-Way Hash:** The backend stores solely the **SHA-256 digest** of uploaded files (`file_sha256`) to support deduplication. Raw PDF binaries and extracted text streams are **never persisted** to database tables or object storage unless explicitly configured by the user.

### 2.2 Strict PII Masking
Any personally identifiable information identified during text analysis is masked before reaching database records or API responses:
- **Candidate Names:** `Johnathan Doe` $\rightarrow$ `J******** D**`
- **Email Addresses:** `candidate.contact@gmail.com` $\rightarrow$ `c****************t@gmail.com`
- **Phone Numbers:** `+91 98765 43210` $\rightarrow$ `+91 98*** **210`

### 2.3 Sanitized Structured Logging
Standard application logs (`jobshield.*`) are configured to strip all payload contents. Loggers emit structured event metadata (e.g. `action`, `user_id`, `scan_id`, `input_type`, `latency_ms`), guaranteeing that raw job text, candidate names, or auth tokens never appear in application stdout or container logs.

---

## 3. Server-Side Request Forgery (SSRF) Prevention

The Job URL analysis endpoint (`POST /api/v1/analyze/job-url`) incorporates defense-in-depth network validation (`app/services/url_analyzer.py`):

1. **Scheme Validation:** Permits strictly `http://` and `https://` schemes. Rejects `file://`, `gopher://`, `ftp://`, `data:`, `javascript:`.
2. **DNS Resolution & Private IP Blacklisting:** Prior to issuing an HTTP request, the domain is resolved to an IP address. Requests are rejected if the destination resolves to:
   - Loopback: `127.0.0.0/8`, `::1`
   - Private networks: `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`
   - Link-local & Cloud Metadata: `169.254.0.0/16` (including `169.254.169.254`)
   - Broadcast / Multicast: `224.0.0.0/4`, `255.255.255.255`
3. **Redirect Protection:** Disables automatic cross-protocol redirects. Re-validates target IP on every hop.
4. **Timeouts & Content Length:** Enforces a 5-second socket timeout and max 5 MB response body limit to prevent slowloris and decompression bombs.

---

## 4. Insecure Direct Object Reference (IDOR) Protections

JobShield AI enforces strict ownership checks across all scan reports, PDF downloads, and background OCR jobs:

| Resource Endpoint | Access Rule for Owner | Access Rule for Other Users | Access Rule for ADMIN |
|---|---|---|---|
| `GET /api/v1/scans/{scan_id}` | Allowed (200 OK) | **403 Forbidden** | Allowed (200 OK) |
| `GET /api/v1/scans/{scan_id}/report.pdf` | Allowed (200 OK) | **403 Forbidden** | Allowed (200 OK) |
| `GET /api/v1/jobs/{job_id}` | Allowed (200 OK) | **403 Forbidden** | Allowed (200 OK) |
| `GET /api/v1/jobs/{job_id}/result` | Allowed (200 OK) | **403 Forbidden** | Allowed (200 OK) |

- **Anonymous Visitor Tracking:** Unauthenticated visitors receive a unique `X-Session-ID` header. The database binds anonymous scans to this session hash, preventing third parties from guessing scan UUIDs to view results.

---

## 5. Authentication, Passwords & Session Security

### 5.1 Argon2id Password Hashing
- Conforms to RFC 9106 recommended parameters: Memory cost = 64 MiB, Time iterations = 3, Parallelism = 4 threads.
- Immune to GPU-accelerated dictionary attacks and side-channel timing analysis.

### 5.2 Short-Lived Access Tokens
- JWT access tokens expire after **15 minutes** (`ACCESS_TOKEN_EXPIRE_MINUTES = 15`).
- Strictly validated on every request for signature, expiration (`exp`), issuer (`iss`), and audience (`aud`).

### 5.3 Refresh Token Rotation & Reuse Detection
- Refresh tokens are 256-bit cryptographic secrets generated via `secrets.token_urlsafe(32)`.
- Stored as SHA-256 hashes in `refresh_tokens`; raw token strings are never saved in the database.
- **Automatic Reuse Detection:** If an already-rotated or revoked refresh token is presented, the system treats it as an active session hijack attempt and **immediately revokes all active sessions** for that user.

---

## 6. Resource Limits & Denial-of-Service Defense

To prevent denial-of-service via resource exhaustion:
1. **Document Upload Limits:** Enforces a hard 10 MB upload ceiling (`MAX_OFFER_LETTER_UPLOAD_BYTES = 10485760`).
2. **Page Count Limit:** Rejects documents with more than 10 pages (`MAX_PDF_PAGES = 10`).
3. **Execution Timeout:** Hard 30-second cap on OCR and PDF parsing threads.
4. **Input Length Limits:** Job text analysis enforces min 50 characters, max 50,000 characters.
5. **Rate Limiting:** IP-based sliding window rate limits protect login (5 requests/minute) and analysis endpoints (30 requests/minute).

---

## 7. HTTP Security Headers & Error Sanitization

The production Nginx reverse proxy (`frontend/nginx.conf`) injects hardened HTTP response headers:
```nginx
add_header X-Frame-Options "DENY" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-XSS-Protection "1; mode=block" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Content-Security-Policy "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; font-src 'self' data:; connect-src 'self' http://localhost:8000;" always;
```

### 7.1 Production Error Sanitization
All unhandled exceptions in the FastAPI application are intercepted by a global exception handler. The API returns a generic RFC 7807 error response with an opaque correlation ID. **Internal stack traces, SQL syntax errors, database hostnames, and filesystem paths are never exposed to the client.**
