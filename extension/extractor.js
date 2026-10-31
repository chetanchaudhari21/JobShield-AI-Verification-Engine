/**
 * JobShield AI - Chrome Extension Page Extractor & Privacy Filter
 * Feature F11 (Privacy-First Manifest V3 Extension)
 *
 * Enforces strict data-minimization:
 * - Extracts only visible job description text and page metadata.
 * - Filters out passwords, form inputs, credentials, tokens, OTPs, and scripts.
 * - Rejects non-HTTP/HTTPS URLs and internal browser pages.
 * - Enforces JobShield API input boundaries (20 - 50,000 characters).
 */

export const MIN_TEXT_LENGTH = 20;
export const MAX_TEXT_LENGTH = 50000;

/**
 * Validates that the active tab URL is a valid web address (HTTP/HTTPS)
 * and not a restricted browser-internal or local file URI.
 *
 * @param {string} url - Target URL string
 * @returns {{ valid: boolean, error?: string }}
 */
export function validatePageUrl(url) {
  if (!url || typeof url !== 'string') {
    return { valid: false, error: 'No active webpage URL detected.' };
  }

  const trimmed = url.trim();
  const restrictedProtocols = [
    'chrome:',
    'chrome-extension:',
    'edge:',
    'about:',
    'view-source:',
    'file:',
    'data:',
    'javascript:',
    'brave:',
    'opera:',
  ];

  for (const protocol of restrictedProtocols) {
    if (trimmed.startsWith(protocol)) {
      return {
        valid: false,
        error: `Cannot inspect browser system or internal pages (${protocol}). Please navigate to an online job listing or careers page.`,
      };
    }
  }

  if (!trimmed.startsWith('http://') && !trimmed.startsWith('https://')) {
    return {
      valid: false,
      error: 'Only standard HTTP and HTTPS webpages can be analyzed.',
    };
  }

  return { valid: true };
}

/**
 * Priority selectors for identifying main job description containers
 * across popular job portals (LinkedIn, Indeed, Glassdoor, careers sites)
 * and generic semantic HTML.
 */
export const JOB_CONTAINER_SELECTORS = [
  '[data-job-description]',
  '#job-description',
  '.job-description',
  '#job-details',
  '.job-details',
  '#jobDescriptionText',                      // Indeed
  '.jobs-description__content',               // LinkedIn
  '[data-testid="job-description"]',
  '[data-automation-id="jobPostingDescription"]',
  '[class*="job-desc-container"]',            // Naukri
  '[class*="dang-inner-html"]',               // Naukri
  '[class*="job-description"]',
  '[class*="jobDescription"]',
  '[class*="JobDescription"]',
  '[class*="job_description"]',
  '[class*="job-details"]',
  '[class*="JobDetails"]',
  '[class*="job_details"]',
  '[class*="description__text"]',
  '[id*="job-description"]',
  '[id*="jobDescription"]',
  'article[role="main"]',
  'article',
  '[role="main"]',
  'main',
];

/**
 * Selectors for sensitive, non-content, or noisy elements that MUST be stripped
 * prior to reading text.
 */
export const STRIP_SELECTORS = [
  // Scripts and styles
  'script',
  'style',
  'noscript',
  'svg',
  'canvas',
  'audio',
  'video',
  'iframe',
  'object',
  'embed',
  // Forms and user inputs (Strict privacy: never collect candidate inputs)
  'form',
  'input',
  'textarea',
  'select',
  'button',
  'datalist',
  'option',
  // Password and sensitive fields
  '[type="password"]',
  '[autocomplete*="password"]',
  '[name*="password"]',
  '[id*="password"]',
  '[name*="token"]',
  '[name*="otp"]',
  '[name*="card"]',
  '[name*="cvv"]',
  // Site chrome, navigation and footers
  'header',
  'footer',
  'nav',
  'aside',
  // Hidden or invisible elements
  '[hidden]',
  '[aria-hidden="true"]',
  '[style*="display: none"]',
  '[style*="display:none"]',
  '[style*="visibility: hidden"]',
  '[style*="visibility:hidden"]',
  // Noisy recommendation and sidebar elements
  '[class*="recommend"]',
  '[class*="similar-job"]',
  '[class*="similarJob"]',
  '[class*="sponsored"]',
  '[class*="sidebar"]',
  '[id*="sidebar"]',
];

/**
 * Safely triggers visible 'Read more' or 'Show more' collapse toggles
 * without navigating to external links or bypassing user authorization.
 *
 * @param {Document|HTMLElement} rootDoc
 */
export function triggerReadMoreIfCollapsed(rootDoc) {
  if (!rootDoc || typeof rootDoc.querySelectorAll !== 'function') return;
  try {
    const candidateButtons = Array.from(rootDoc.querySelectorAll('button, span, a'));
    for (const btn of candidateButtons) {
      const text = (btn.textContent || '').trim().toLowerCase();
      if (/^(?:read\s+more|show\s+more|view\s+more|see\s+more)\b/i.test(text)) {
        if (btn.tagName === 'A') {
          const href = btn.getAttribute('href') || '';
          if (href && !href.startsWith('#') && !href.startsWith('javascript:')) {
            continue;
          }
        }
        if (typeof btn.click === 'function') {
          btn.click();
        }
      }
    }
  } catch {
    // Graceful no-op in restricted or non-DOM test environments
  }
}

/**
 * Safely extracts job description text and metadata from a Document or Element.
 *
 * @param {Document|HTMLElement} rootDoc - The DOM document or container
 * @param {string} [pageUrl=''] - Optional current page URL
 * @returns {{
 *   success: boolean,
 *   url: string,
 *   title: string,
 *   claimedCompany: string,
 *   experience: string,
 *   location: string,
 *   text: string,
 *   charCount: number,
 *   truncated: boolean,
 *   isPartial: boolean,
 *   warning?: string|null,
 *   error?: string
 * }}
 */
export function extractPageContent(rootDoc, pageUrl = '') {
  if (!rootDoc) {
    return {
      success: false,
      url: pageUrl,
      title: '',
      claimedCompany: '',
      experience: '',
      location: '',
      text: '',
      charCount: 0,
      truncated: false,
      isPartial: false,
      error: 'Invalid document context.',
    };
  }

  // 0. Trigger 'Read more' expansion if present and safe
  triggerReadMoreIfCollapsed(rootDoc);

  // 1. Extract Page / Job Title
  let title = '';
  let hasExplicitTitleHeading = false;
  if (typeof rootDoc.querySelector === 'function') {
    const titleSelectors = [
      'h1[class*="title"]',
      'h1[class*="jd"]',
      '[class*="jd-header-title"]',
      '[class*="job-title"]',
      '[class*="jobTitle"]',
      '[data-testid="job-title"]',
      '.topcard__title',
      '.jobsearch-JobInfoHeader-title',
      'h1',
    ];
    for (const tSel of titleSelectors) {
      const el = rootDoc.querySelector(tSel);
      if (el && el.textContent && el.textContent.trim()) {
        title = el.textContent.trim();
        hasExplicitTitleHeading = true;
        break;
      }
    }
  }
  if (!title && rootDoc.title) {
    title = rootDoc.title
      .replace(/\s*[-–|].*(?:naukri|linkedin|indeed|glassdoor|foundit|monster|shine).*$/i, '')
      .trim();
  }

  // 2. Identify candidate container
  let targetElement = null;
  if (typeof rootDoc.querySelector === 'function') {
    for (const selector of JOB_CONTAINER_SELECTORS) {
      const match = rootDoc.querySelector(selector);
      if (match && match.textContent && match.textContent.trim().length >= MIN_TEXT_LENGTH) {
        targetElement = match;
        break;
      }
    }
  }

  // Fallback to body or document element if no specific job container was found
  if (!targetElement) {
    targetElement = rootDoc.body || rootDoc.documentElement || rootDoc;
  }

  // 3. Clone node to perform safe stripping without affecting the host page
  if (!targetElement || typeof targetElement.cloneNode !== 'function') {
    return {
      success: false,
      url: pageUrl,
      title,
      claimedCompany: '',
      text: '',
      charCount: 0,
      truncated: false,
      error: 'Unable to read webpage content.',
    };
  }

  const clone = targetElement.cloneNode(true);

  // 4. Strip sensitive, form, and layout elements
  for (const selector of STRIP_SELECTORS) {
    if (typeof clone.querySelectorAll === 'function') {
      const elements = clone.querySelectorAll(selector);
      elements.forEach((el) => {
        if (el.parentNode) {
          el.parentNode.removeChild(el);
        }
      });
    }
  }

  // 5. Extract raw text from sanitized clone
  let rawText = clone.innerText || clone.textContent || '';

  // Normalize excessive whitespaces and multiple consecutive blank lines
  let cleanedText = rawText
    .replace(/[ \t]+/g, ' ')
    .replace(/\r\n/g, '\n')
    .replace(/\n\s*\n\s*\n+/g, '\n\n')
    .trim();

  // 6. Attempt employer name heuristic extraction
  let claimedCompany = '';
  if (typeof rootDoc.querySelector === 'function') {
    const companySelectors = [
      '[data-company-name]',
      '[class*="jd-header-comp-name"]',
      '[class*="company-name"]',
      '[class*="companyName"]',
      '[class*="comp-name"]',
      '[class*="employer-name"]',
      '.jobs-unified-top-card__company-name',
      '.jobsearch-CompanyInfoContainer',
      '.topcard__flavor--black-link',
      'meta[property="og:site_name"]',
    ];
    for (const cSel of companySelectors) {
      const el = rootDoc.querySelector(cSel);
      if (el) {
        if (cSel.startsWith('meta') && el.getAttribute('content')) {
          claimedCompany = el.getAttribute('content').trim();
          break;
        } else if (el.textContent && el.textContent.trim()) {
          claimedCompany = el.textContent.trim();
          break;
        }
      }
    }
  }

  // 7. Extract Experience & Location
  let experience = '';
  let location = '';
  if (typeof rootDoc.querySelector === 'function') {
    const expSelectors = [
      '[class*="jhc__exp"]',
      '[class*="experience"]',
      '[class*="exp-wrap"]',
      '[class*="exp_wrap"]',
    ];
    for (const sel of expSelectors) {
      const el = rootDoc.querySelector(sel);
      if (el && el.textContent && el.textContent.trim()) {
        experience = el.textContent.trim();
        break;
      }
    }

    const locSelectors = [
      '[class*="jhc__loc"]',
      '[class*="location"]',
      '[class*="loc-wrap"]',
      '[class*="loc_wrap"]',
    ];
    for (const sel of locSelectors) {
      const el = rootDoc.querySelector(sel);
      if (el && el.textContent && el.textContent.trim()) {
        location = el.textContent.trim();
        break;
      }
    }
  }

  // 8. Compose structured job posting text if header fields exist
  const hasExplicitHeader = Boolean(hasExplicitTitleHeading || claimedCompany || experience || location);
  let headerPrefix = '';
  if (hasExplicitHeader) {
    if (title && hasExplicitTitleHeading) headerPrefix += `Job Title: ${title}\n`;
    if (claimedCompany) headerPrefix += `Company: ${claimedCompany}\n`;
    if (experience) headerPrefix += `Experience: ${experience}\n`;
    if (location) headerPrefix += `Location: ${location}\n`;
  }

  let fullJobText = cleanedText;
  if (headerPrefix && !cleanedText.toLowerCase().includes(title.toLowerCase())) {
    fullJobText = `${headerPrefix}\nJob Description:\n${cleanedText}`;
  } else if (headerPrefix) {
    fullJobText = `${headerPrefix}\n${cleanedText}`;
  }
  fullJobText = fullJobText.trim();

  // 9. Detect partial or collapsed description
  const isPartial = Boolean(
    (cleanedText.length < 180 && (cleanedText.includes('...') || /read\s*more|show\s*more/i.test(cleanedText))) ||
    (Boolean(title || claimedCompany) && cleanedText.length < 80)
  );

  let warning = null;
  if (isPartial) {
    warning = "Extracted job description appears brief or collapsed. On dynamic pages like Naukri, click 'Read more' to expand full details before analyzing, or copy and paste the job description text into the JobShield web app.";
  }

  // 10. Enforce JobShield backend character boundaries
  if (cleanedText.length < MIN_TEXT_LENGTH) {
    return {
      success: false,
      url: pageUrl,
      title,
      claimedCompany,
      experience,
      location,
      text: fullJobText,
      charCount: cleanedText.length,
      truncated: false,
      isPartial: true,
      error: `Extracted text is too short (${cleanedText.length} chars). JobShield AI requires at least ${MIN_TEXT_LENGTH} characters of job description text. Please verify the job posting is fully loaded.`,
    };
  }

  const totalLength = fullJobText.length;

  let truncated = false;
  if (totalLength > MAX_TEXT_LENGTH) {
    fullJobText = fullJobText.slice(0, MAX_TEXT_LENGTH);
    truncated = true;
  }

  return {
    success: true,
    url: pageUrl,
    title,
    claimedCompany,
    experience,
    location,
    text: fullJobText,
    charCount: fullJobText.length,
    truncated,
    isPartial,
    warning,
  };
}

/**
 * Constructs an allowlisted JobTextAnalysisRequest payload for the API.
 * Ensures strict schema compliance and prevents unwanted field leakage.
 *
 * @param {Object} params
 * @param {string} params.text - Sanitized job text
 * @param {string} [params.companyName] - Optional claimed company name
 * @param {string} [params.cin] - Optional claimed CIN
 * @param {string} [params.explanationMethod='auto'] - Explanation method
 * @returns {{ text: string, company_name: string|null, cin: string|null, explanation_method: string }}
 */
export function buildAnalysisPayload({
  text,
  companyName = null,
  cin = null,
  explanationMethod = 'auto',
}) {
  if (!text || typeof text !== 'string') {
    throw new Error('Analysis payload requires a non-empty text string.');
  }

  const trimmedText = text.trim();
  if (trimmedText.length < MIN_TEXT_LENGTH) {
    throw new Error(`Job text is too short (min ${MIN_TEXT_LENGTH} characters).`);
  }

  const cleanedCompany = typeof companyName === 'string' && companyName.trim()
    ? companyName.trim()
    : null;

  const cleanedCin = typeof cin === 'string' && cin.trim()
    ? cin.trim().toUpperCase()
    : null;

  // Strict allowlist: ONLY fields documented in JobTextAnalysisRequest schema
  return {
    text: trimmedText.slice(0, MAX_TEXT_LENGTH),
    company_name: cleanedCompany,
    cin: cleanedCin,
    explanation_method: explanationMethod || 'auto',
  };
}

/**
 * Validates and parses API response to ensure required fields exist
 * before DOM rendering.
 *
 * @param {any} data - Raw JSON response from API
 * @returns {Object} Validated response object
 */
export function validateAnalysisResponse(data) {
  if (!data || typeof data !== 'object') {
    throw new Error('Malformed API response: expected JSON object.');
  }

  if (!data.report_id && !data.id) {
    throw new Error('Malformed API response: missing scan report identifier.');
  }

  const validCategories = ['LOW', 'MODERATE', 'HIGH', 'CRITICAL', 'INSUFFICIENT_EVIDENCE'];
  const category = (data.risk_category || 'INSUFFICIENT_EVIDENCE').toUpperCase();

  return {
    reportId: data.report_id || data.id,
    timestamp: data.timestamp || new Date().toISOString(),
    riskScore: typeof data.risk_score === 'number' ? Math.round(data.risk_score) : null,
    riskCategory: validCategories.includes(category) ? category : 'INSUFFICIENT_EVIDENCE',
    warning: typeof data.warning === 'string' ? data.warning : null,
    overrideFloorApplied: data.override_floor_applied || null,
    overrideFloorReason: data.override_floor_reason || null,
    evidence: Array.isArray(data.evidence) ? data.evidence : [],
    disclaimer: data.disclaimer || 'Informational assessment only. Not a legal finding.',
    recommendedActions: Array.isArray(data.recommended_safe_actions) ? data.recommended_safe_actions : [],
  };
}
