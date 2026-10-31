/**
 * JobShield AI - Extension Popup Controller
 * Feature F11 (Privacy-First Manifest V3 Extension)
 *
 * Implements:
 * - User-initiated extraction on explicit button click.
 * - Pre-flight preview allowing review or cancellation prior to transmission.
 * - Secure API communication with timeout handling and allowlisted payloads.
 * - Safe DOM manipulation (zero innerHTML injection of untrusted strings).
 * - Full report navigation and authoritative PDF report download.
 */

import {
  validatePageUrl,
  extractPageContent,
  buildAnalysisPayload,
  validateAnalysisResponse,
} from './extractor.js';

export const DEFAULT_API_BASE_URL = 'http://localhost:8000';
export const DEFAULT_WEB_BASE_URL = 'http://localhost:5173';
export const API_TIMEOUT_MS = 15000;

// Application State
export const state = {
  currentView: 'view-ready',
  activeTab: null,
  extractedData: null,
  latestAnalysis: null,
  apiBaseUrl: DEFAULT_API_BASE_URL,
  webBaseUrl: DEFAULT_WEB_BASE_URL,
  privacyDismissed: false,
};

/**
 * Safely accesses extension storage with fallback for test or mock environments.
 */
export async function getStoredSettings() {
  if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
    return new Promise((resolve) => {
      chrome.storage.local.get(['apiBaseUrl', 'webBaseUrl', 'privacyDismissed'], (result) => {
        resolve(result || {});
      });
    });
  }
  return {};
}

export async function saveStoredSettings(newSettings) {
  if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
    return new Promise((resolve) => {
      chrome.storage.local.set(newSettings, () => {
        resolve();
      });
    });
  }
}

/**
 * Switches the active UI view safely.
 *
 * @param {string} viewId - ID of view element ('view-ready', 'view-preview', etc.)
 */
export function switchView(viewId) {
  const views = document.querySelectorAll('.view');
  views.forEach((v) => v.classList.remove('active'));

  const target = document.getElementById(viewId);
  if (target) {
    target.classList.add('active');
    state.currentView = viewId;
  }
}

/**
 * Retrieves the user's currently focused browser tab.
 */
export async function getActiveTab() {
  if (typeof chrome !== 'undefined' && chrome.tabs && chrome.tabs.query) {
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    return tabs && tabs.length > 0 ? tabs[0] : null;
  }
  return { id: 1, url: 'https://example.com/careers/sample-job', title: 'Senior Software Engineer' };
}

/**
 * Initializes the popup on DOM load.
 */
export async function initializePopup() {
  // 1. Load preferences from local extension storage
  const settings = await getStoredSettings();
  state.apiBaseUrl = settings.apiBaseUrl || DEFAULT_API_BASE_URL;
  state.webBaseUrl = settings.webBaseUrl || DEFAULT_WEB_BASE_URL;
  state.privacyDismissed = Boolean(settings.privacyDismissed);

  // Configure settings inputs
  const apiInput = document.getElementById('settings-api-url');
  const webInput = document.getElementById('settings-web-url');
  if (apiInput) apiInput.value = state.apiBaseUrl;
  if (webInput) webInput.value = state.webBaseUrl;

  // Toggle privacy banner visibility
  const banner = document.getElementById('privacy-banner');
  if (banner && state.privacyDismissed) {
    banner.classList.add('hidden');
  }

  // 2. Query active tab information (metadata only, no content extraction)
  try {
    const tab = await getActiveTab();
    state.activeTab = tab;

    const titleEl = document.getElementById('ready-page-title');
    const urlEl = document.getElementById('ready-page-url');

    if (tab) {
      if (titleEl) titleEl.textContent = tab.title || 'Untitled Page';
      if (urlEl) urlEl.textContent = tab.url || 'No URL available';
    } else {
      if (titleEl) titleEl.textContent = 'No Active Webpage';
      if (urlEl) urlEl.textContent = 'Unable to detect active tab.';
    }
  } catch (err) {
    showError('Tab Access Error', err.message || 'Unable to retrieve current tab information.');
  }

  // 3. Register Event Listeners
  attachEventListeners();
}

/**
 * Attaches UI event listeners without inline HTML attributes.
 */
export function attachEventListeners() {
  // Dismiss Privacy Banner
  const btnDismissPrivacy = document.getElementById('btn-dismiss-privacy');
  if (btnDismissPrivacy) {
    btnDismissPrivacy.addEventListener('click', () => {
      const banner = document.getElementById('privacy-banner');
      if (banner) banner.classList.add('hidden');
      state.privacyDismissed = true;
      saveStoredSettings({ privacyDismissed: true });
    });
  }

  // Settings Toggle
  const btnToggleSettings = document.getElementById('btn-toggle-settings');
  if (btnToggleSettings) {
    btnToggleSettings.addEventListener('click', () => {
      if (state.currentView === 'view-settings') {
        switchView('view-ready');
      } else {
        switchView('view-settings');
      }
    });
  }

  const btnCloseSettings = document.getElementById('btn-close-settings');
  if (btnCloseSettings) {
    btnCloseSettings.addEventListener('click', () => switchView('view-ready'));
  }

  // Save Settings
  const btnSaveSettings = document.getElementById('btn-save-settings');
  if (btnSaveSettings) {
    btnSaveSettings.addEventListener('click', handleSaveSettings);
  }

  // Reset Settings
  const btnResetSettings = document.getElementById('btn-reset-settings');
  if (btnResetSettings) {
    btnResetSettings.addEventListener('click', handleResetSettings);
  }

  // Extract Page Action (Analyze This Job)
  const btnExtract = document.getElementById('btn-extract');
  if (btnExtract) {
    btnExtract.addEventListener('click', handleExtractJob);
  }

  // Pre-flight Actions
  const btnCancelPreview = document.getElementById('btn-cancel-preview');
  if (btnCancelPreview) {
    btnCancelPreview.addEventListener('click', () => {
      state.extractedData = null;
      switchView('view-ready');
    });
  }

  const btnConfirmAnalyze = document.getElementById('btn-confirm-analyze');
  if (btnConfirmAnalyze) {
    btnConfirmAnalyze.addEventListener('click', handleConfirmAnalyze);
  }

  // Result Actions
  const btnViewReport = document.getElementById('btn-view-report');
  if (btnViewReport) {
    btnViewReport.addEventListener('click', handleViewFullReport);
  }

  const btnDownloadPdf = document.getElementById('btn-download-pdf');
  if (btnDownloadPdf) {
    btnDownloadPdf.addEventListener('click', handleDownloadPdf);
  }

  const btnNewScan = document.getElementById('btn-new-scan');
  if (btnNewScan) {
    btnNewScan.addEventListener('click', () => {
      state.extractedData = null;
      state.latestAnalysis = null;
      switchView('view-ready');
    });
  }

  // Error Actions
  const btnErrorBack = document.getElementById('btn-error-back');
  if (btnErrorBack) {
    btnErrorBack.addEventListener('click', () => switchView('view-ready'));
  }

  const btnErrorRetry = document.getElementById('btn-error-retry');
  if (btnErrorRetry) {
    btnErrorRetry.addEventListener('click', () => {
      if (state.extractedData) {
        handleConfirmAnalyze();
      } else {
        handleExtractJob();
      }
    });
  }
}

/**
 * Handles explicit user request to extract job posting text from the current page.
 */
export async function handleExtractJob() {
  if (!state.activeTab || !state.activeTab.url) {
    showError('No Webpage Detected', 'Please open an active job posting page in your browser.');
    return;
  }

  // 1. Validate Target URL
  const urlCheck = validatePageUrl(state.activeTab.url);
  if (!urlCheck.valid) {
    showError('Unsupported Webpage', urlCheck.error);
    return;
  }

  // 2. Perform DOM extraction via chrome.scripting.executeScript
  try {
    let extractionResult = null;

    if (typeof chrome !== 'undefined' && chrome.scripting && chrome.scripting.executeScript) {
      const results = await chrome.scripting.executeScript({
        target: { tabId: state.activeTab.id },
        func: extractContentInTab,
      });

      if (!results || !results[0] || !results[0].result) {
        showError('Extraction Failed', 'Unable to extract content from this webpage.');
        return;
      }
      extractionResult = results[0].result;
    } else {
      // Mock / fallback for testing environment
      extractionResult = extractPageContent(document, state.activeTab.url);
    }

    if (!extractionResult.success) {
      showError('Content Ineligible for Analysis', extractionResult.error || 'Extracted content does not meet minimum requirements.');
      return;
    }

    // 3. Populate Pre-flight Preview
    state.extractedData = extractionResult;
    renderPreviewView(extractionResult);
    switchView('view-preview');
  } catch (err) {
    showError('Extraction Error', err.message || 'An error occurred while inspecting the webpage.');
  }
}

/**
 * Function serialized and injected into the active tab context.
 * Performs DOM extraction strictly within the current document without injecting external scripts.
 */
function extractContentInTab() {
  const MIN_LEN = 20;
  const MAX_LEN = 50000;

  const JOB_CONTAINER_SELECTORS = [
    '[data-job-description]',
    '#job-description',
    '.job-description',
    '#job-details',
    '.job-details',
    '#jobDescriptionText',
    '.jobs-description__content',
    '[data-testid="job-description"]',
    '[data-automation-id="jobPostingDescription"]',
    '[class*="job-desc-container"]',
    '[class*="dang-inner-html"]',
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

  const STRIP_SELECTORS = [
    'script', 'style', 'noscript', 'svg', 'canvas', 'audio', 'video', 'iframe', 'object', 'embed',
    'form', 'input', 'textarea', 'select', 'button', 'datalist', 'option',
    '[type="password"]', '[autocomplete*="password"]', '[name*="password"]', '[id*="password"]',
    '[name*="token"]', '[name*="otp"]', '[name*="card"]', '[name*="cvv"]',
    'header', 'footer', 'nav', 'aside',
    '[hidden]', '[aria-hidden="true"]',
    '[style*="display: none"]', '[style*="display:none"]',
    '[style*="visibility: hidden"]', '[style*="visibility:hidden"]',
    '[class*="recommend"]', '[class*="similar-job"]', '[class*="similarJob"]',
    '[class*="sponsored"]', '[class*="sidebar"]', '[id*="sidebar"]',
  ];

  try {
    const pageUrl = window.location.href;

    // Safely trigger visible 'Read more' toggles
    try {
      const candidateButtons = Array.from(document.querySelectorAll('button, span, a'));
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
      // Ignore click errors
    }

    // 1. Extract Page / Job Title
    let title = '';
    let hasExplicitTitleHeading = false;
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
      const el = document.querySelector(tSel);
      if (el && el.textContent && el.textContent.trim()) {
        title = el.textContent.trim();
        hasExplicitTitleHeading = true;
        break;
      }
    }
    if (!title && document.title) {
      title = document.title
        .replace(/\s*[-–|].*(?:naukri|linkedin|indeed|glassdoor|foundit|monster|shine).*$/i, '')
        .trim();
    }

    // 2. Extract Claimed Company
    let claimedCompany = '';
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
      const el = document.querySelector(cSel);
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

    // 3. Extract Experience & Location
    let experience = '';
    let location = '';
    const expSelectors = [
      '[class*="jhc__exp"]',
      '[class*="experience"]',
      '[class*="exp-wrap"]',
      '[class*="exp_wrap"]',
    ];
    for (const sel of expSelectors) {
      const el = document.querySelector(sel);
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
      const el = document.querySelector(sel);
      if (el && el.textContent && el.textContent.trim()) {
        location = el.textContent.trim();
        break;
      }
    }

    // 4. Identify candidate description container
    let container = null;
    for (const sel of JOB_CONTAINER_SELECTORS) {
      const match = document.querySelector(sel);
      if (match && match.textContent && match.textContent.trim().length >= MIN_LEN) {
        container = match;
        break;
      }
    }
    if (!container) {
      container = document.body || document.documentElement;
    }

    const clone = container.cloneNode(true);
    for (const sel of STRIP_SELECTORS) {
      const nodes = clone.querySelectorAll(sel);
      nodes.forEach((n) => {
        if (n.parentNode) n.parentNode.removeChild(n);
      });
    }

    let rawText = clone.innerText || clone.textContent || '';
    let cleanedText = rawText
      .replace(/[ \t]+/g, ' ')
      .replace(/\r\n/g, '\n')
      .replace(/\n\s*\n\s*\n+/g, '\n\n')
      .trim();

    // 5. Compose structured job text
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

    // 6. Detect partial or collapsed description
    const isPartial = Boolean(
      (cleanedText.length < 180 && (cleanedText.includes('...') || /read\s*more|show\s*more/i.test(cleanedText))) ||
      (Boolean(title || claimedCompany) && cleanedText.length < 80)
    );

    let warning = null;
    if (isPartial) {
      warning = "Extracted job description appears brief or collapsed. On dynamic pages like Naukri, click 'Read more' to expand full details before analyzing, or copy and paste the job description text into the JobShield web app.";
    }

    // 7. Enforce boundaries
    if (cleanedText.length < MIN_LEN) {
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
        error: `Extracted text is too short (${cleanedText.length} chars). JobShield AI requires at least ${MIN_LEN} characters of job description text. Please verify the job posting is fully loaded.`,
      };
    }

    const totalLen = fullJobText.length;
    let truncated = false;
    if (totalLen > MAX_LEN) {
      fullJobText = fullJobText.slice(0, MAX_LEN);
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
  } catch (err) {
    return {
      success: false,
      url: window.location.href,
      title: '',
      claimedCompany: '',
      text: '',
      charCount: 0,
      truncated: false,
      isPartial: false,
      error: err.message || 'Extraction failed',
    };
  }
}

/**
 * Renders data into the Pre-Flight Review view safely.
 */
export function renderPreviewView(data) {
  const charCountEl = document.getElementById('preview-char-count');
  const compInput = document.getElementById('preview-claimed-company');
  const cinInput = document.getElementById('preview-claimed-cin');
  const textEl = document.getElementById('preview-text-content');
  const truncBadge = document.getElementById('preview-truncated-badge');
  const warningAlert = document.getElementById('preview-warning-alert');
  const warningText = document.getElementById('preview-warning-text');

  if (charCountEl) {
    charCountEl.textContent = `${data.charCount.toLocaleString()} chars`;
  }
  if (compInput) {
    compInput.value = data.claimedCompany || '';
  }
  if (cinInput) {
    cinInput.value = '';
  }
  if (textEl) {
    // SAFE DOM: strictly textContent to eliminate XSS risks from arbitrary page text
    textEl.textContent = data.text;
  }
  if (truncBadge) {
    if (data.truncated) {
      truncBadge.classList.remove('hidden');
    } else {
      truncBadge.classList.add('hidden');
    }
  }
  if (warningAlert && warningText) {
    if (data.warning) {
      warningText.textContent = data.warning;
      warningAlert.classList.remove('hidden');
    } else {
      warningAlert.classList.add('hidden');
    }
  }
}

/**
 * Handles confirmation and transmission of the pre-flight payload to the API.
 */
export async function handleConfirmAnalyze() {
  if (!state.extractedData || !state.extractedData.text) {
    showError('No Content', 'Please extract job posting text before analyzing.');
    return;
  }

  // Read any optional user overrides from preview inputs
  const compInput = document.getElementById('preview-claimed-company');
  const cinInput = document.getElementById('preview-claimed-cin');

  const companyName = compInput ? compInput.value.trim() : state.extractedData.claimedCompany;
  const cin = cinInput ? cinInput.value.trim() : null;

  // Construct strict allowlisted request payload
  let payload = null;
  try {
    payload = buildAnalysisPayload({
      text: state.extractedData.text,
      companyName,
      cin,
      explanationMethod: 'auto',
    });
  } catch (err) {
    showError('Invalid Payload', err.message);
    return;
  }

  // Switch to Loading View
  switchView('view-loading');

  const endpoint = `${state.apiBaseUrl.replace(/\/+$/, '')}/api/v1/analyze/job-text`;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), API_TIMEOUT_MS);

  try {
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    clearTimeout(timeoutId);

    if (!response.ok) {
      let errDetail = `API request failed (HTTP ${response.status})`;
      try {
        const errJson = await response.json();
        if (errJson.detail) {
          errDetail = Array.isArray(errJson.detail)
            ? errJson.detail.map((d) => d.msg || JSON.stringify(d)).join(' ')
            : String(errJson.detail);
        }
      } catch {
        // Fallback for non-JSON error
      }
      showError('Analysis Failed', errDetail);
      return;
    }

    const rawData = await response.json();
    const validatedData = validateAnalysisResponse(rawData);
    state.latestAnalysis = validatedData;

    renderResultsView(validatedData);
    switchView('view-results');
  } catch (err) {
    clearTimeout(timeoutId);
    if (err.name === 'AbortError') {
      showError(
        'Request Timed Out',
        `The JobShield API at ${state.apiBaseUrl} did not respond within ${Math.round(API_TIMEOUT_MS / 1000)}s. Please confirm the server is running and reachable.`
      );
    } else {
      showError(
        'Connection Error',
        `Unable to reach JobShield API at ${state.apiBaseUrl}. Please ensure the backend is running and CORS allows extension origins.`
      );
    }
  }
}

/**
 * Safely renders analysis results into the DOM without innerHTML injection.
 */
export function renderResultsView(result) {
  // 1. Risk Score
  const scoreValEl = document.getElementById('result-score-val');
  if (scoreValEl) {
    scoreValEl.textContent = result.riskScore !== null ? String(result.riskScore) : 'N/A';
  }

  // 2. Risk Category Badge
  const categoryBadge = document.getElementById('result-category-badge');
  if (categoryBadge) {
    categoryBadge.textContent = result.riskCategory.replace('_', ' ');
    categoryBadge.className = 'badge badge-lg';

    switch (result.riskCategory) {
      case 'LOW':
        categoryBadge.classList.add('badge-success');
        break;
      case 'MODERATE':
        categoryBadge.classList.add('badge-warning');
        break;
      case 'HIGH':
        categoryBadge.classList.add('badge-high');
        break;
      case 'CRITICAL':
        categoryBadge.classList.add('badge-critical');
        break;
      default:
        categoryBadge.classList.add('badge-neutral');
        break;
    }
  }

  // 3. Safety Override Floor
  const overrideBox = document.getElementById('result-override-floor');
  const overrideReason = document.getElementById('result-override-reason');
  if (overrideBox && overrideReason) {
    if (result.overrideFloorApplied) {
      overrideReason.textContent = result.overrideFloorReason || 'High-severity safety rule triggered override floor.';
      overrideBox.classList.remove('hidden');
    } else {
      overrideBox.classList.add('hidden');
    }
  }

  // 4. Warning Banner
  const warningCard = document.getElementById('result-warning-card');
  const warningText = document.getElementById('result-warning-text');
  if (warningCard && warningText) {
    if (result.warning) {
      warningText.textContent = result.warning;
      warningCard.classList.remove('hidden');
    } else {
      warningCard.classList.add('hidden');
    }
  }

  // 5. Evidence List (Safe DOM creation)
  const evidenceContainer = document.getElementById('results-evidence-list');
  if (evidenceContainer) {
    evidenceContainer.replaceChildren();

    if (!result.evidence || result.evidence.length === 0) {
      const emptyItem = document.createElement('div');
      emptyItem.className = 'evidence-item';
      emptyItem.textContent = 'No high-risk recruitment fraud indicators detected in this text.';
      evidenceContainer.appendChild(emptyItem);
    } else {
      result.evidence.slice(0, 5).forEach((item) => {
        const itemEl = document.createElement('div');
        itemEl.className = 'evidence-item';

        const headerEl = document.createElement('div');
        headerEl.className = 'evidence-header';

        const sourceEl = document.createElement('span');
        sourceEl.className = 'evidence-source truncate';
        sourceEl.textContent = item.source_name || item.evidence_type || 'Finding';

        const statusEl = document.createElement('span');
        statusEl.className = 'evidence-status';
        const st = (item.status || '').toUpperCase();
        if (st === 'FLAGGED' || st === 'DETECTED') {
          statusEl.classList.add('flagged');
        } else if (st === 'VERIFIED' || st === 'PASS') {
          statusEl.classList.add('verified');
        } else {
          statusEl.classList.add('neutral');
        }
        statusEl.textContent = item.status || 'REPORTED';

        headerEl.appendChild(sourceEl);
        headerEl.appendChild(statusEl);

        const summaryEl = document.createElement('div');
        summaryEl.className = 'evidence-summary';
        summaryEl.textContent = item.summary || 'Evidence signal observed during analysis.';

        itemEl.appendChild(headerEl);
        itemEl.appendChild(summaryEl);
        evidenceContainer.appendChild(itemEl);
      });
    }
  }

  // 6. Manage Action Buttons based on analysis outcome
  const btnDownloadPdf = document.getElementById('btn-download-pdf');
  const btnViewReport = document.getElementById('btn-view-report');
  if (result.riskScore === null || result.riskCategory === 'INSUFFICIENT_EVIDENCE') {
    if (btnDownloadPdf) {
      btnDownloadPdf.classList.add('hidden');
    }
    if (btnViewReport) {
      const span = btnViewReport.querySelector('span');
      if (span) span.textContent = 'Paste Full Text in Web App';
    }
  } else {
    if (btnDownloadPdf) {
      btnDownloadPdf.classList.remove('hidden');
    }
    if (btnViewReport) {
      const span = btnViewReport.querySelector('span');
      if (span) span.textContent = 'View Full Interactive Report';
    }
  }
}

/**
 * Opens the full interactive verification report in the JobShield AI web dashboard.
 */
export function handleViewFullReport() {
  if (!state.latestAnalysis) {
    return;
  }
  const reportUrl = state.latestAnalysis.riskScore === null
    ? `${state.webBaseUrl.replace(/\/+$/, '')}/analyze`
    : `${state.webBaseUrl.replace(/\/+$/, '')}/results?scan_id=${encodeURIComponent(state.latestAnalysis.reportId)}`;
  if (typeof chrome !== 'undefined' && chrome.tabs && chrome.tabs.create) {
    chrome.tabs.create({ url: reportUrl });
  } else if (typeof window !== 'undefined') {
    window.open(reportUrl, '_blank');
  }
}

/**
 * Downloads the authoritative Evidence-Based Verification PDF Report.
 */
export function handleDownloadPdf() {
  if (!state.latestAnalysis || !state.latestAnalysis.reportId) {
    return;
  }
  const pdfUrl = `${state.apiBaseUrl.replace(/\/+$/, '')}/api/v1/scans/${encodeURIComponent(state.latestAnalysis.reportId)}/report.pdf`;
  if (typeof chrome !== 'undefined' && chrome.tabs && chrome.tabs.create) {
    chrome.tabs.create({ url: pdfUrl });
  } else if (typeof window !== 'undefined') {
    window.open(pdfUrl, '_blank');
  }
}

/**
 * Displays error view safely.
 */
export function showError(title, message) {
  const titleEl = document.getElementById('error-title');
  const msgEl = document.getElementById('error-message');
  if (titleEl) titleEl.textContent = title;
  if (msgEl) msgEl.textContent = message;
  switchView('view-error');
}

/**
 * Handles saving API configuration.
 */
export async function handleSaveSettings() {
  const apiInput = document.getElementById('settings-api-url');
  const webInput = document.getElementById('settings-web-url');
  const statusEl = document.getElementById('settings-status');

  const newApi = apiInput ? apiInput.value.trim() : '';
  const newWeb = webInput ? webInput.value.trim() : '';

  if (!newApi.startsWith('http://') && !newApi.startsWith('https://')) {
    if (statusEl) {
      statusEl.textContent = 'API Base URL must start with http:// or https://';
      statusEl.className = 'status-msg text-red-600 bg-red-50 border border-red-200';
      statusEl.classList.remove('hidden');
    }
    return;
  }

  state.apiBaseUrl = newApi;
  state.webBaseUrl = newWeb || DEFAULT_WEB_BASE_URL;

  await saveStoredSettings({
    apiBaseUrl: state.apiBaseUrl,
    webBaseUrl: state.webBaseUrl,
  });

  if (statusEl) {
    statusEl.textContent = 'Settings saved successfully.';
    statusEl.className = 'status-msg success';
    statusEl.classList.remove('hidden');
    setTimeout(() => {
      statusEl.classList.add('hidden');
      switchView('view-ready');
    }, 1200);
  }
}

/**
 * Resets API configuration to localhost development defaults.
 */
export async function handleResetSettings() {
  const apiInput = document.getElementById('settings-api-url');
  const webInput = document.getElementById('settings-web-url');
  const statusEl = document.getElementById('settings-status');

  state.apiBaseUrl = DEFAULT_API_BASE_URL;
  state.webBaseUrl = DEFAULT_WEB_BASE_URL;

  if (apiInput) apiInput.value = DEFAULT_API_BASE_URL;
  if (webInput) webInput.value = DEFAULT_WEB_BASE_URL;

  await saveStoredSettings({
    apiBaseUrl: DEFAULT_API_BASE_URL,
    webBaseUrl: DEFAULT_WEB_BASE_URL,
  });

  if (statusEl) {
    statusEl.textContent = 'Reset to default localhost settings.';
    statusEl.className = 'status-msg success';
    statusEl.classList.remove('hidden');
    setTimeout(() => statusEl.classList.add('hidden'), 2000);
  }
}

// Automatically initialize when running in browser context
if (typeof document !== 'undefined') {
  document.addEventListener('DOMContentLoaded', initializePopup);
}
