# JobShield AI — Privacy-First Chrome Extension (Manifest V3)

> **Feature F11**: Browser extension for on-demand job posting verification, recruitment fraud detection, and explainable AI risk scoring.

The JobShield AI Chrome Extension brings automated fraud analysis directly to job seekers' browsers while enforcing strict privacy-first data minimization.

---

## 1. Core Architecture & Philosophy

The extension is designed around three fundamental guarantees:

1. **Zero Passive Monitoring / Zero Background Tracking**: The extension never tracks tabs, never monitors navigation events in the background, and never collects browsing history.
2. **Explicit User-Initiated Inspection**: Page content is extracted **only** when the user opens the extension popup and explicitly clicks **"Analyze This Job"**.
3. **Pre-Flight Review Before Transmission**: Extracted text, detected company name, and character counts are displayed in a pre-flight preview screen. No network requests are sent to the backend API until the user reviews and clicks **"Confirm & Analyze"**.

---

## 2. Directory Structure

```
extension/
├── manifest.json         # Manifest V3 configuration, strict CSP & minimal permissions
├── popup.html            # Extension popup user interface (multi-view lifecycle)
├── popup.css             # Tailwind-inspired Slate/Blue design tokens and responsive layout
├── popup.js              # Popup controller, pre-flight review, API client, safe DOM renderer
├── extractor.js          # Pure DOM extraction, container prioritization & privacy filter
├── content.js            # On-demand runtime message listener
├── icons/
│   ├── icon16.png        # 16x16 toolbar and tab icon
│   ├── icon48.png        # 48x48 extension management icon
│   └── icon128.png       # 128x128 Chrome Web Store and installer icon
├── tests/
│   └── extension.test.js # Automated unit test suite (Node test runner)
└── README.md             # Architecture, security, privacy & installation documentation
```

---

## 3. Permissions Justification

Manifest V3 permissions are kept strictly minimal in `extension/manifest.json`:

| Permission | Scope & Purpose | Privacy Justification |
| :--- | :--- | :--- |
| `activeTab` | Temporary access to the currently active tab when popup is opened. | Restricts extension access exclusively to the single focused tab. Never grants access to other open tabs or background windows. |
| `scripting` | Executes the content extraction function in the active tab context upon user action. | Injects the extractor strictly on-demand when the user clicks "Analyze This Job". Never runs automatically on page load. |
| `storage` | Isolated key-value storage (`chrome.storage.local`). | Stores user's configured API base URL (development vs. production) and the privacy disclosure dismissal flag. Never stores submitted job text, tokens, or browsing history. |

### Prohibited Permissions & Host Bounds

- **NO `tabs` permission**: Broad tab enumeration and tab URL monitoring are prohibited.
- **NO `history` permission**: Browsing history is never accessed.
- **NO `cookies` permission**: Session cookies, auth tokens, and local credentials are never collected.
- **NO `<all_urls>` permission**: Network requests are strictly bounded via `host_permissions` to:
  - `http://localhost:8000/*` (local development API)
  - `http://127.0.0.1:8000/*` (local loopback development API)
  - `https://*.jobshield.ai/*` (production JobShield AI API)

---

## 4. Privacy & Data Flow Lifecycle

```
[ Active Webpage ]
       │
       ▼ (User clicks "Analyze This Job")
[ extractPageContent() ]
  ├── 1. Priority container lookup (e.g. #job-description, .job-details, article, main)
  ├── 2. Strict privacy strip:
  │      - <form>, <input>, <textarea>, <select>, <button>
  │      - [type="password"], [autocomplete*="password"], [name*="password"]
  │      - [name*="token"], [name*="otp"], [name*="card"], [name*="cvv"]
  │      - <script>, <style>, <noscript>, <svg>, <iframe>
  │      - [hidden], [aria-hidden="true"], display:none, visibility:hidden
  ├── 3. Enforce boundaries: min 20 chars; max 50,000 chars (truncate with indicator)
  └── 4. Plaintext normalization
       │
       ▼
[ Pre-Flight Review Screen ]
  ├── Displays extracted URL & page title
  ├── Displays character count and truncation badge
  ├── Displays editable claimed employer name & CIN
  ├── Displays scrollable extracted text preview
  │
  ├── [ Cancel Button ] ────► Discards state; 0 network requests dispatched.
  │
  └── [ Confirm & Analyze ]
       │
       ▼ (Explicit user confirmation)
[ buildAnalysisPayload() ] ──► Strict allowlist: { text, company_name, cin, explanation_method }
       │
       ▼ (POST /api/v1/analyze/job-text over HTTPS/HTTP)
[ JobShield AI Backend ]
  ├── Evaluates heuristic fraud patterns & ML risk inference
  ├── Verifies company against MCA-21 & DPIIT registry
  └── Never persists raw text (only non-reversible SHA-256 hash & derived scores)
       │
       ▼ (JSON Response)
[ Results Screen ]
  ├── Composite Risk Score (0 - 100)
  ├── Risk Category Badge (LOW / MODERATE / HIGH / CRITICAL / INSUFFICIENT)
  ├── Candidate Warning Alert Banner (if high-risk pattern detected)
  ├── Rule-based heuristic evidence signals & linear feature contributions
  ├── Informational legal disclaimer
  ├── [ View Full Interactive Report ] ──► Opens http://localhost:5173/results?scan_id={id}
  └── [ Download Official PDF ]        ──► Opens http://localhost:8000/api/v1/scans/{id}/report.pdf
```

---

## 5. Security Protections (CSP & Safe DOM)

1. **Content Security Policy**:
   `"content_security_policy": { "extension_pages": "script-src 'self'; object-src 'none';" }`
   - Disallows remote scripts, dynamic `eval()`, inline scripts, and untrusted execution contexts.
2. **Safe DOM Manipulation**:
   - Extracted job descriptions, warning banners, company names, and evidence summaries are rendered exclusively via safe DOM APIs (`document.createElement`, `element.textContent`, `element.className`, `element.setAttribute`).
   - Zero `innerHTML` injection of untrusted page or API strings.
3. **No Credential Harvesting**:
   - Form inputs, passwords, authentication tokens, and user cookies are never read, stored, or transmitted.
   - The extension operates in visitor/candidate mode and does not store user passwords or refresh tokens in extension storage.

---

## 6. Installation (Manual / Developer Mode)

To install and test the extension in Google Chrome, Brave, or Edge:

1. Open Chrome and navigate to `chrome://extensions/`.
2. Enable **Developer mode** using the toggle in the upper-right corner.
3. Click **Load unpacked** in the top-left toolbar.
4. Select the `extension/` directory located inside your JobShield AI repository:
   ```
   D:\JobShield-AI\extension
   ```
5. The extension icon will appear in your browser extensions menu. Pin the JobShield AI shield icon to your toolbar for quick access.

---

## 7. How to Verify Click-Before-Send & Privacy Guarantees

You can verify that no network requests occur without explicit confirmation:

1. In Chrome, open `chrome://extensions/` and click **Inspect views: popup** on JobShield AI, or right-click the extension icon and select **Inspect Popup**.
2. Switch to the **Network** tab in Developer Tools.
3. Open the extension popup on any webpage (e.g. `https://news.ycombinator.com/jobs`).
   - **Verification 1**: Notice that **zero** network requests are sent to the backend when the popup opens.
4. Click **Analyze This Job**.
   - The extension extracts the visible text into the Pre-Flight Review view.
   - **Verification 2**: Notice that **zero** requests have been sent to the backend. The data is only in the local popup UI.
5. Click **Cancel**.
   - The state is cleared and the UI returns to the initial screen with **zero** network requests sent.
6. Click **Analyze This Job** again, review the excerpt, and click **Confirm & Analyze**.
   - **Verification 3**: A single `POST /api/v1/analyze/job-text` request is sent with the exact allowlisted JSON payload.

---

## 8. API Configuration (Development vs Production)

Click the **Settings** gear icon in the extension header to configure destination endpoints:

- **Local Development Default**:
  - API Base URL: `http://localhost:8000`
  - Web App URL: `http://localhost:5173`
- **Production Setting**:
  - API Base URL: `https://api.jobshield.ai`
  - Web App URL: `https://jobshield.ai`

Settings are persisted locally using `chrome.storage.local`. Clicking **Reset Defaults** immediately restores the localhost developer defaults.

---

## 9. Running Automated Tests

### Extension Unit Tests (Node Test Runner)

Run the fast automated test suite covering URL filtering, privacy sanitization, boundary checks, and payload construction:

```powershell
node --test extension/tests/extension.test.js
```

### Backend & Manifest Integration Tests (Pytest)

Run the Pytest suite validating manifest schema, permissions, CSP, CORS headers, and backend endpoints:

```powershell
.venv\Scripts\pytest tests/test_extension.py -v
```

### Full Frontend Test Suite (Vitest)

Run the frontend test suite verifying the interactive Results page query parameter navigation:

```powershell
npm --prefix frontend test -- --run
```

---

## 10. Known Limitations & Next Steps

1. **Client-Rendered SPAs with Delayed Content**: Some job boards render job descriptions inside closed Shadow DOMs or load text several seconds after initial hydration. If a page has not finished loading, the extension will report that text is too short. Simply wait for the listing to render and click "Try Again".
2. **Third-Party Iframe Listings**: Cross-origin iframes embedded in certain career portals cannot be inspected directly due to browser same-origin policy. In such cases, navigate directly to the job listing page or use the JobShield AI web interface at `/analyze`.
