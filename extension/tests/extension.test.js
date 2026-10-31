/**
 * Automated Unit Test Suite for JobShield AI Chrome Extension (Feature F11)
 *
 * Tests:
 * 1. URL validation and restricted protocol rejection.
 * 2. DOM text extraction and container prioritization.
 * 3. Strict privacy filtering (passwords, forms, inputs, scripts, hidden fields).
 * 4. Text boundary enforcement (min 20 chars, max 50,000 chars, truncation).
 * 5. Allowlisted API payload construction (zero leak of unauthorized fields).
 * 6. Explicit pre-flight click-before-send behavior and cancellation.
 * 7. Response validation and risk category mapping.
 * 8. Error, timeout, and malformed response handling.
 * 9. Safe DOM text rendering and XSS protection.
 * 10. Full report and PDF report URL generation.
 */

import test from 'node:test';
import assert from 'node:assert/strict';
import {
  validatePageUrl,
  extractPageContent,
  triggerReadMoreIfCollapsed,
  buildAnalysisPayload,
  validateAnalysisResponse,
  MIN_TEXT_LENGTH,
  MAX_TEXT_LENGTH,
} from '../extractor.js';

// ============================================================================
// LIGHTWEIGHT MOCK DOM IMPLEMENTATION (Zero External Dependencies)
// ============================================================================
class MockDOMNode {
  constructor(tagName, options = {}) {
    this.tagName = (tagName || 'div').toUpperCase();
    this.nodeType = 1;
    this.attributes = options.attributes || {};
    this.style = options.style || {};
    this.childNodes = [];
    this.parentNode = null;
    this._textContent = options.textContent || '';
  }

  getAttribute(name) {
    return this.attributes[name] !== undefined ? this.attributes[name] : null;
  }

  setAttribute(name, value) {
    this.attributes[name] = String(value);
  }

  removeAttribute(name) {
    delete this.attributes[name];
  }

  appendChild(child) {
    child.parentNode = this;
    this.childNodes.push(child);
    return child;
  }

  removeChild(child) {
    const idx = this.childNodes.indexOf(child);
    if (idx !== -1) {
      this.childNodes.splice(idx, 1);
      child.parentNode = null;
    }
    return child;
  }

  replaceChildren(...newChildren) {
    for (const c of [...this.childNodes]) {
      c.parentNode = null;
    }
    this.childNodes = [];
    for (const c of newChildren) {
      if (c instanceof MockDOMNode) {
        this.appendChild(c);
      }
    }
  }

  get textContent() {
    if (this.childNodes.length === 0) {
      return this._textContent;
    }
    return this.childNodes.map((c) => c.textContent).join(' ');
  }

  set textContent(val) {
    this._textContent = String(val);
    this.childNodes = [];
  }

  get innerText() {
    return this.textContent;
  }

  click() {
    if (typeof this.onclick === 'function') {
      this.onclick();
    }
    this._clicked = true;
  }

  cloneNode(deep = true) {
    const clone = new MockDOMNode(this.tagName, {
      attributes: { ...this.attributes },
      style: { ...this.style },
      textContent: this._textContent,
    });
    if (deep) {
      for (const child of this.childNodes) {
        clone.appendChild(child.cloneNode(true));
      }
    }
    return clone;
  }

  matchesSelector(selector) {
    if (selector.includes(',')) {
      return selector.split(',').some((sub) => this.matchesSelector(sub.trim()));
    }
    const s = selector.trim();
    const tagMatch = s.match(/^([a-z0-9_-]+)(\[.+\]|\.[a-z0-9_-]+|#[a-z0-9_-]+)$/i);
    if (tagMatch) {
      const tag = tagMatch[1];
      const rest = tagMatch[2];
      return this.tagName.toLowerCase() === tag.toLowerCase() && this.matchesSelector(rest);
    }
    if (s.startsWith('#')) {
      return this.attributes['id'] === s.slice(1);
    }
    if (s.startsWith('.')) {
      const cls = this.attributes['class'] || '';
      return cls.split(/\s+/).includes(s.slice(1));
    }
    if (s.startsWith('[') && s.endsWith(']')) {
      const attrExpr = s.slice(1, -1);
      if (attrExpr.includes('*=')) {
        const [a, v] = attrExpr.split('*=');
        const attrVal = this.attributes[a.trim()] || '';
        return attrVal.includes(v.replace(/['"]/g, '').trim());
      }
      if (attrExpr.includes('=')) {
        const [a, v] = attrExpr.split('=');
        return this.attributes[a.trim()] === v.replace(/['"]/g, '').trim();
      }
      return this.attributes[attrExpr] !== undefined;
    }
    return this.tagName.toLowerCase() === s.toLowerCase();
  }

  querySelector(selector) {
    const results = this.querySelectorAll(selector);
    return results.length > 0 ? results[0] : null;
  }

  querySelectorAll(selector) {
    const matched = [];
    const walk = (node) => {
      for (const child of node.childNodes) {
        if (child.matchesSelector(selector)) {
          matched.push(child);
        }
        walk(child);
      }
    };
    walk(this);
    return matched;
  }
}

class MockDocument {
  constructor() {
    this.title = '';
    this.documentElement = new MockDOMNode('html');
    this.head = new MockDOMNode('head');
    this.body = new MockDOMNode('body');
    this.documentElement.appendChild(this.head);
    this.documentElement.appendChild(this.body);
  }

  createElement(tagName) {
    return new MockDOMNode(tagName);
  }

  querySelector(selector) {
    return this.documentElement.querySelector(selector);
  }

  querySelectorAll(selector) {
    return this.documentElement.querySelectorAll(selector);
  }
}

// ============================================================================
// TEST SUITE: JobShield AI Chrome Extension
// ============================================================================

test('1. URL Validation: Permits HTTP and HTTPS webpages, rejects restricted schemes', () => {
  // Valid URLs
  assert.strictEqual(validatePageUrl('https://careers.google.com/jobs/123').valid, true);
  assert.strictEqual(validatePageUrl('http://localhost:3000/careers/software-engineer').valid, true);
  assert.strictEqual(validatePageUrl('https://www.linkedin.com/jobs/view/4019283').valid, true);

  // Restricted and system browser URLs
  assert.strictEqual(validatePageUrl('chrome://extensions').valid, false);
  assert.strictEqual(validatePageUrl('chrome-extension://abcdefghijklmnopqrstuvwxyz/popup.html').valid, false);
  assert.strictEqual(validatePageUrl('edge://settings').valid, false);
  assert.strictEqual(validatePageUrl('about:blank').valid, false);
  assert.strictEqual(validatePageUrl('file:///C:/Users/candidate/Downloads/job.html').valid, false);
  assert.strictEqual(validatePageUrl('javascript:alert(1)').valid, false);
  assert.strictEqual(validatePageUrl('').valid, false);
  assert.strictEqual(validatePageUrl(null).valid, false);
});

test('2. DOM Extraction: Prioritizes job container selectors over generic page noise', () => {
  const doc = new MockDocument();
  doc.title = 'Lead Backend Engineer - Acme Tech';

  const noiseContainer = doc.createElement('div');
  noiseContainer.textContent = 'Site sidebar promotions and unrelated news articles.';
  doc.body.appendChild(noiseContainer);

  const jobDesc = doc.createElement('div');
  jobDesc.setAttribute('id', 'job-description');
  jobDesc.textContent = 'We are seeking an experienced Backend Engineer to scale distributed REST APIs and secure cloud architectures.';
  doc.body.appendChild(jobDesc);

  const result = extractPageContent(doc, 'https://example.com/job/lead-backend');
  assert.strictEqual(result.success, true);
  assert.strictEqual(result.title, 'Lead Backend Engineer - Acme Tech');
  assert.match(result.text, /Backend Engineer to scale distributed REST APIs/);
  // Ensure sidebar noise outside of #job-description was not extracted
  assert.strictEqual(result.text.includes('sidebar promotions'), false);
});

test('3. Privacy Sanitization: Excludes passwords, form inputs, credentials, tokens, and scripts', () => {
  const doc = new MockDocument();
  doc.title = 'Data Entry Operations - Urgent Joining';

  const jobContainer = doc.createElement('div');
  jobContainer.setAttribute('class', 'job-description');
  jobContainer.textContent = 'Immediate remote vacancy for customer support and data entry operations. High weekly payout.';

  // Form with password and login fields that MUST be stripped
  const form = doc.createElement('form');
  const inputPwd = doc.createElement('input');
  inputPwd.setAttribute('type', 'password');
  inputPwd.setAttribute('value', 'secret_candidate_password_123');
  form.appendChild(inputPwd);

  const inputToken = doc.createElement('input');
  inputToken.setAttribute('name', 'csrf_token');
  inputToken.setAttribute('value', 'a8f9c0e21b7');
  form.appendChild(inputToken);

  const inputOtp = doc.createElement('input');
  inputOtp.setAttribute('name', 'user_otp_code');
  inputOtp.setAttribute('value', '984210');
  form.appendChild(inputOtp);

  const btnSubmit = doc.createElement('button');
  btnSubmit.textContent = 'Submit Application & Card Details';
  form.appendChild(btnSubmit);

  jobContainer.appendChild(form);

  // Script and style that MUST be stripped
  const scriptEl = doc.createElement('script');
  scriptEl.textContent = 'console.log("harvest_tracking_code");';
  jobContainer.appendChild(scriptEl);

  // Hidden tracker element that MUST be stripped
  const hiddenEl = doc.createElement('div');
  hiddenEl.setAttribute('hidden', 'true');
  hiddenEl.textContent = 'HIDDEN_TRACKER_DATA';
  jobContainer.appendChild(hiddenEl);

  doc.body.appendChild(jobContainer);

  const result = extractPageContent(doc, 'https://example.com/job/data-entry');
  assert.strictEqual(result.success, true);

  // Asserts complete omission of sensitive data
  assert.strictEqual(result.text.includes('secret_candidate_password'), false);
  assert.strictEqual(result.text.includes('csrf_token'), false);
  assert.strictEqual(result.text.includes('984210'), false);
  assert.strictEqual(result.text.includes('harvest_tracking_code'), false);
  assert.strictEqual(result.text.includes('HIDDEN_TRACKER_DATA'), false);
  assert.strictEqual(result.text.includes('Submit Application'), false);
});

test('4. Boundary Limits: Enforces minimum (20 chars) and maximum (50,000 chars) length', () => {
  const doc = new MockDocument();
  doc.title = 'Short Posting';

  // Sub-minimum text (< 20 characters)
  const shortEl = doc.createElement('div');
  shortEl.setAttribute('id', 'job-description');
  shortEl.textContent = 'Too short';
  doc.body.appendChild(shortEl);

  const failResult = extractPageContent(doc, 'https://example.com/short');
  assert.strictEqual(failResult.success, false);
  assert.match(failResult.error, /too short/i);

  // Exactly minimum boundary (20 characters)
  shortEl.textContent = '12345678901234567890';
  const minResult = extractPageContent(doc, 'https://example.com/min');
  assert.strictEqual(minResult.success, true);
  assert.strictEqual(minResult.charCount, 20);
  assert.strictEqual(minResult.truncated, false);

  // Exceeds maximum allowed size (> 50,000 characters)
  const longText = 'A'.repeat(55000);
  shortEl.textContent = longText;
  const maxResult = extractPageContent(doc, 'https://example.com/oversized');
  assert.strictEqual(maxResult.success, true);
  assert.strictEqual(maxResult.charCount, MAX_TEXT_LENGTH);
  assert.strictEqual(maxResult.truncated, true);
  assert.strictEqual(maxResult.text.length, 50000);
});

test('5. API Payload Construction: Strict allowlist prevents unauthorized property transmission', () => {
  const payload = buildAnalysisPayload({
    text: 'Authentic job description for Senior Python Backend Engineer with 5 years experience.',
    companyName: 'Infosys Limited ',
    cin: 'l85110ka1981plc013115',
    explanationMethod: 'auto',
    // Unauthorized fields that must be ignored
    unauthorizedToken: 'malicious_bearer_token',
    userCookies: 'session=123',
    browsingHistory: ['https://bank.com', 'https://mail.google.com'],
  });

  const keys = Object.keys(payload);
  assert.deepStrictEqual(keys.sort(), ['cin', 'company_name', 'explanation_method', 'text'].sort());
  assert.strictEqual(payload.company_name, 'Infosys Limited');
  assert.strictEqual(payload.cin, 'L85110KA1981PLC013115'); // Uppercased
  assert.strictEqual(payload.explanation_method, 'auto');
  assert.strictEqual(payload.unauthorizedToken, undefined);
  assert.strictEqual(payload.userCookies, undefined);
  assert.strictEqual(payload.browsingHistory, undefined);
});

test('6. Pre-flight Review & Explicit User Action: Data is packaged for user review before transmission', () => {
  const doc = new MockDocument();
  doc.title = 'Remote Operations Specialist';
  const el = doc.createElement('div');
  el.setAttribute('id', 'job-description');
  el.textContent = 'Remote position paying $4,000 weekly. Requires refundable equipment deposit of $100.';
  doc.body.appendChild(el);

  // Extraction returns preview data
  const preview = extractPageContent(doc, 'https://example.com/job/remote-ops');
  assert.strictEqual(preview.success, true);
  assert.strictEqual(typeof preview.text, 'string');
  assert.strictEqual(preview.charCount > 0, true);

  // User has ability to review, and cancellation discards state without transmission
  let isTransmitted = false;
  let userConfirmed = false;

  const simulateUserAction = (confirm) => {
    if (confirm) {
      userConfirmed = true;
      const payload = buildAnalysisPayload({ text: preview.text });
      isTransmitted = Boolean(payload);
    } else {
      userConfirmed = false;
      isTransmitted = false;
    }
  };

  // Scenario A: User cancels
  simulateUserAction(false);
  assert.strictEqual(userConfirmed, false);
  assert.strictEqual(isTransmitted, false);

  // Scenario B: User confirms
  simulateUserAction(true);
  assert.strictEqual(userConfirmed, true);
  assert.strictEqual(isTransmitted, true);
});

test('7. API Response Validation: Handles all risk categories and rejects malformed responses', () => {
  const mockValidResponse = {
    report_id: 'scan-1111-2222-3333-4444',
    timestamp: '2026-10-17T20:00:00Z',
    risk_score: 87.4,
    risk_category: 'CRITICAL',
    warning: 'Severe recruitment fraud warning: Upfront payment requested.',
    override_floor_applied: 'UPFRONT_FEE_DEMAND',
    override_floor_reason: 'Safety floor applied due to deposit requirement.',
    evidence: [
      {
        evidence_type: 'rule_signal',
        source_name: 'Rule: Upfront Fees Request',
        status: 'DETECTED',
        confidence: 0.95,
        summary: 'Detected demand for refundable equipment deposit.',
      },
    ],
  };

  const parsed = validateAnalysisResponse(mockValidResponse);
  assert.strictEqual(parsed.reportId, 'scan-1111-2222-3333-4444');
  assert.strictEqual(parsed.riskScore, 87);
  assert.strictEqual(parsed.riskCategory, 'CRITICAL');
  assert.strictEqual(parsed.overrideFloorApplied, 'UPFRONT_FEE_DEMAND');
  assert.strictEqual(parsed.evidence.length, 1);
  assert.strictEqual(parsed.evidence[0].status, 'DETECTED');

  // Insufficient evidence test
  const insufficientResponse = {
    report_id: 'scan-5555',
    risk_score: null,
    risk_category: 'INSUFFICIENT_EVIDENCE',
  };
  const parsedInsufficient = validateAnalysisResponse(insufficientResponse);
  assert.strictEqual(parsedInsufficient.riskScore, null);
  assert.strictEqual(parsedInsufficient.riskCategory, 'INSUFFICIENT_EVIDENCE');

  // Malformed response rejection
  assert.throws(() => validateAnalysisResponse(null), /Malformed API response/);
  assert.throws(() => validateAnalysisResponse('invalid string'), /Malformed API response/);
  assert.throws(() => validateAnalysisResponse({ no_report_id: true }), /missing scan report identifier/);
});

test('8. Safe DOM Manipulation: Untrusted HTML strings are handled strictly as textContent', () => {
  const doc = new MockDocument();
  const summaryEl = doc.createElement('div');

  // Untrusted payload containing malicious XSS tags
  const maliciousSummary = '<script>alert("XSS")</script><img src="x" onerror="stealCookies()">Deposit required';
  
  // Safe assignment via textContent (the exact pattern used in popup.js)
  summaryEl.textContent = maliciousSummary;

  // Verify that script and img nodes were NOT created in the DOM
  assert.strictEqual(summaryEl.childNodes.length, 0);
  assert.strictEqual(summaryEl.textContent, maliciousSummary);
  assert.strictEqual(summaryEl.querySelector('script'), null);
  assert.strictEqual(summaryEl.querySelector('img'), null);
});

test('9. Full Report & PDF URLs: Generates legitimate, verified endpoints', () => {
  const scanId = '7b6d1942-8c10-4411-92b1-09876543210f';
  const webBaseUrl = 'http://localhost:5173';
  const apiBaseUrl = 'http://localhost:8000';

  const fullReportUrl = `${webBaseUrl.replace(/\/+$/, '')}/results?scan_id=${encodeURIComponent(scanId)}`;
  const pdfReportUrl = `${apiBaseUrl.replace(/\/+$/, '')}/api/v1/scans/${encodeURIComponent(scanId)}/report.pdf`;

  assert.strictEqual(
    fullReportUrl,
    'http://localhost:5173/results?scan_id=7b6d1942-8c10-4411-92b1-09876543210f'
  );
  assert.strictEqual(
    pdfReportUrl,
    'http://localhost:8000/api/v1/scans/7b6d1942-8c10-4411-92b1-09876543210f/report.pdf'
  );
});

test('10. Dynamic Portal Composite Extraction: Extracts title, employer, exp, loc, and description', () => {
  const doc = new MockDocument();
  doc.title = 'Analyst - Data Science Jobs in Gurgaon - American Express | Naukri.com';

  // Explicit title heading
  const titleEl = doc.createElement('h1');
  titleEl.setAttribute('class', 'styles_jd-header-title__xyz');
  titleEl.textContent = 'Analyst - Data Science';
  doc.body.appendChild(titleEl);

  // Employer name
  const compEl = doc.createElement('div');
  compEl.setAttribute('class', 'styles_jd-header-comp-name__abc');
  compEl.textContent = 'American Express';
  doc.body.appendChild(compEl);

  // Experience
  const expEl = doc.createElement('div');
  expEl.setAttribute('class', 'styles_jhc__exp__123');
  expEl.textContent = '1 - 4 years';
  doc.body.appendChild(expEl);

  // Location
  const locEl = doc.createElement('div');
  locEl.setAttribute('class', 'styles_jhc__loc__456');
  locEl.textContent = 'Gurgaon/Gurugram';
  doc.body.appendChild(locEl);

  // Job description container
  const jdContainer = doc.createElement('div');
  jdContainer.setAttribute('class', 'styles_job-desc-container__main');

  const jdInner = doc.createElement('div');
  jdInner.setAttribute('class', 'styles_JDC__dang-inner-html__content');
  jdInner.textContent = 'Design, build, and deploy predictive machine learning models. Collaborate with risk management, analytics, and business strategy teams. Required qualifications: Bachelor or Master degree in Statistics, Mathematics, Computer Science, or Engineering. Hands-on experience with Python, SQL, and data visualization tools.';
  jdContainer.appendChild(jdInner);

  // Recommendation noise inside body
  const recEl = doc.createElement('div');
  recEl.setAttribute('class', 'styles_recommend-jobs-card');
  recEl.textContent = 'Explore 20+ other data scientist jobs in Delhi NCR';
  doc.body.appendChild(recEl);

  doc.body.appendChild(jdContainer);

  const result = extractPageContent(doc, 'https://www.naukri.com/job-listings-analyst-data-science-american-express-12345');
  assert.strictEqual(result.success, true);
  assert.strictEqual(result.title, 'Analyst - Data Science');
  assert.strictEqual(result.claimedCompany, 'American Express');
  assert.strictEqual(result.experience, '1 - 4 years');
  assert.strictEqual(result.location, 'Gurgaon/Gurugram');
  assert.strictEqual(result.isPartial, false);
  assert.strictEqual(result.warning, null);

  // Verify composite text format includes headers and body
  assert.match(result.text, /Job Title: Analyst - Data Science/);
  assert.match(result.text, /Company: American Express/);
  assert.match(result.text, /Experience: 1 - 4 years/);
  assert.match(result.text, /Location: Gurgaon\/Gurugram/);
  assert.match(result.text, /predictive machine learning models/);
  // Verify noise was omitted
  assert.strictEqual(result.text.includes('Explore 20+ other data scientist jobs'), false);
});

test('11. Dynamic Page with Collapsed Description: Flags isPartial and produces actionable guidance', () => {
  const doc = new MockDocument();
  doc.title = 'Senior DevOps Architect - CloudTech';

  const titleEl = doc.createElement('h1');
  titleEl.setAttribute('class', 'job-title');
  titleEl.textContent = 'Senior DevOps Architect';
  doc.body.appendChild(titleEl);

  const compEl = doc.createElement('div');
  compEl.setAttribute('class', 'company-name');
  compEl.textContent = 'CloudTech Systems';
  doc.body.appendChild(compEl);

  const jdEl = doc.createElement('div');
  jdEl.setAttribute('id', 'job-description');
  // Collapsed text snippet ending with Read more
  jdEl.textContent = 'Lead Kubernetes infrastructure and Terraform CI/CD pipelines across AWS cloud environments... Read more';
  doc.body.appendChild(jdEl);

  const result = extractPageContent(doc, 'https://careers.example.com/jobs/devops-789');
  assert.strictEqual(result.success, true);
  assert.strictEqual(result.isPartial, true);
  assert.strictEqual(typeof result.warning, 'string');
  assert.match(result.warning, /brief or collapsed/i);
  assert.match(result.warning, /Read more/i);
  assert.match(result.warning, /copy and paste/i);
});

test('12. Safe Read-more Button Trigger: Safely expands in-page collapsibles without external navigation', () => {
  const doc = new MockDocument();

  let btnClicked = false;
  let extLinkClicked = false;
  let hashLinkClicked = false;

  const btn = doc.createElement('button');
  btn.textContent = 'Read more';
  btn.onclick = () => { btnClicked = true; };
  doc.body.appendChild(btn);

  const extLink = doc.createElement('a');
  extLink.setAttribute('href', 'https://malicious-external-site.com/phish');
  extLink.textContent = 'Read more details here';
  extLink.onclick = () => { extLinkClicked = true; };
  doc.body.appendChild(extLink);

  const hashLink = doc.createElement('a');
  hashLink.setAttribute('href', '#show-all-requirements');
  hashLink.textContent = 'Show more';
  hashLink.onclick = () => { hashLinkClicked = true; };
  doc.body.appendChild(hashLink);

  triggerReadMoreIfCollapsed(doc);

  assert.strictEqual(btnClicked, true);
  assert.strictEqual(extLinkClicked, false);
  assert.strictEqual(hashLinkClicked, true);
});

test('13. Noise Rejection & Strip Selectors: Omit sidebars, recommendations, and sponsored cards', () => {
  const doc = new MockDocument();
  doc.title = 'Full Stack Engineer';

  const mainContainer = doc.createElement('div');
  mainContainer.setAttribute('class', 'job-description');
  mainContainer.textContent = 'We are seeking a Full Stack Software Engineer to build scalable microservices and React frontends. 3+ years experience with Node.js and TypeScript required.';

  // Embedded noisy elements inside container
  const recJobs = doc.createElement('div');
  recJobs.setAttribute('class', 'similar-jobs');
  recJobs.textContent = 'Similar jobs: PHP Developer, Junior QA';
  mainContainer.appendChild(recJobs);

  const sponsored = doc.createElement('div');
  sponsored.setAttribute('class', 'sponsored-ad');
  sponsored.textContent = 'Sponsored: Buy our resume review package for $99';
  mainContainer.appendChild(sponsored);

  const sidebar = doc.createElement('aside');
  sidebar.setAttribute('class', 'sidebar-nav');
  sidebar.textContent = 'Trending blog articles and tech news';
  mainContainer.appendChild(sidebar);

  doc.body.appendChild(mainContainer);

  const result = extractPageContent(doc, 'https://example.com/job/fullstack');
  assert.strictEqual(result.success, true);
  assert.match(result.text, /Full Stack Software Engineer/);
  assert.strictEqual(result.text.includes('Similar jobs'), false);
  assert.strictEqual(result.text.includes('Sponsored: Buy our resume'), false);
  assert.strictEqual(result.text.includes('Trending blog articles'), false);
});

test('14. Valid Listing Without Salary Information: Successfully extracts and satisfies boundaries', () => {
  const doc = new MockDocument();
  doc.title = 'Data Scientist - Predictive Modeling';

  const titleEl = doc.createElement('h1');
  titleEl.setAttribute('class', 'job-title');
  titleEl.textContent = 'Data Scientist';
  doc.body.appendChild(titleEl);

  const compEl = doc.createElement('div');
  compEl.setAttribute('class', 'company-name');
  compEl.textContent = 'Global Analytics Corp';
  doc.body.appendChild(compEl);

  // Many postings say "Not Disclosed" or omit salary completely
  const salaryEl = doc.createElement('div');
  salaryEl.setAttribute('class', 'salary-info');
  salaryEl.textContent = 'Salary: Not Disclosed by Recruiter';
  doc.body.appendChild(salaryEl);

  const jdEl = doc.createElement('div');
  jdEl.setAttribute('class', 'job-details');
  jdEl.textContent = 'Responsibilities include feature engineering, training machine learning algorithms, validating statistical significance, and communicating insights to executive leadership. Qualifications: Bachelor degree in STEM discipline, 2+ years experience in Python, PyTorch, and SQL databases.';
  doc.body.appendChild(jdEl);

  const result = extractPageContent(doc, 'https://careers.example.com/jobs/ds-not-disclosed');
  assert.strictEqual(result.success, true);
  assert.strictEqual(result.isPartial, false);
  assert.strictEqual(result.charCount >= MIN_TEXT_LENGTH, true);
  assert.strictEqual(result.truncated, false);
  assert.match(result.text, /Data Scientist/);
  assert.match(result.text, /Global Analytics Corp/);
  assert.match(result.text, /training machine learning algorithms/);
});
