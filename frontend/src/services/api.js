/**
 * API client for JobShield AI backend service.
 * Configured using VITE_API_BASE_URL.
 */

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/+$/, '');

let inMemoryAuthToken = null;

export const setAuthToken = (token) => {
  inMemoryAuthToken = token || null;
};

export const getAuthToken = () => inMemoryAuthToken;

export const clearAuthToken = () => {
  inMemoryAuthToken = null;
};

/**
 * Standard fetch wrapper with timeout, in-memory auth token, HttpOnly credentials,
 * automatic 401 session refresh retry, and JSON error handling.
 */
async function request(endpoint, options = {}, isRetry = false) {
  const url = `${API_BASE_URL}${endpoint}`;
  const timeoutMs = options.timeout || 15000;

  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeoutMs);

  const headers = {
    'Accept': 'application/json',
    ...(options.headers || {}),
  };
  if (inMemoryAuthToken && !headers['Authorization']) {
    headers['Authorization'] = `Bearer ${inMemoryAuthToken}`;
  }
  if (!(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }

  try {
    const response = await fetch(url, {
      credentials: 'include',
      ...options,
      signal: controller.signal,
      headers,
    });

    clearTimeout(id);

    // If 401 Unauthorized occurs on a non-auth endpoint, attempt token refresh using HttpOnly cookie once
    if (response.status === 401 && !isRetry && !endpoint.startsWith('/api/v1/auth/')) {
      try {
        const refreshData = await request('/api/v1/auth/refresh', { method: 'POST' }, true);
        if (refreshData && refreshData.access_token) {
          setAuthToken(refreshData.access_token);
        }
        return await request(endpoint, options, true);
      } catch {
        clearAuthToken();
      }
    }

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      let errorMessage = data.message || data.detail || `Request failed with status ${response.status}`;
      if (Array.isArray(data.detail)) {
        // FastAPI / Pydantic validation error list
        errorMessage = data.detail.map((item) => item.msg || JSON.stringify(item)).join(' ');
      } else if (typeof data.detail === 'string') {
        errorMessage = data.detail;
      }

      const error = new Error(errorMessage);
      error.status = response.status;
      error.data = data;
      throw error;
    }

    return data;
  } catch (err) {
    clearTimeout(id);
    if (err.name === 'AbortError') {
      const timeoutErr = new Error(`Request timed out after ${Math.round(timeoutMs / 1000)}s. The remote server or network may be slow. Please try again.`);
      timeoutErr.isTimeout = true;
      throw timeoutErr;
    }
    throw err;
  }
}

export const api = {
  getBaseUrl() {
    return API_BASE_URL;
  },

  /**
   * Check backend liveness (GET /health)
   */
  async checkHealth() {
    return request('/health');
  },

  /**
   * Check backend & dependency readiness (GET /api/v1/health/ready)
   */
  async checkReadiness() {
    return request('/api/v1/health/ready');
  },

  /**
   * Submit job description text for recruitment fraud risk analysis.
   * Calls POST /api/v1/analyze/job-text.
   *
   * @param {string|Object} input - Raw text string or { text, company_name, cin } object.
   * @returns {Promise<Object>} JobTextAnalysisResponse
   */
  async analyzeJobText(input) {
    const payload = typeof input === 'string' ? { text: input } : input;
    return request('/api/v1/analyze/job-text', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  /**
   * Backward-compatible alias for analyzeJobText.
   */
  async submitJobText(payload) {
    if (typeof payload === 'string') {
      return this.analyzeJobText({ text: payload });
    }
    const text = payload.text || payload.description || '';
    return this.analyzeJobText({
      text,
      company_name: payload.company_name,
      cin: payload.cin,
    });
  },

  /**
   * Submit public job URL for recruitment fraud and domain security analysis.
   * Calls POST /api/v1/analyze/job-url.
   *
   * @param {string|Object} input - URL string or { url, company_name, cin } object.
   * @returns {Promise<Object>} JobUrlAnalysisResponse
   */
  async analyzeJobUrl(input) {
    const payload = typeof input === 'string' ? { url: input } : input;
    return request('/api/v1/analyze/job-url', {
      method: 'POST',
      body: JSON.stringify(payload),
      timeout: 65000,
    });
  },

  /**
   * Submit recruiter email and optional message text for fraud risk analysis.
   * Calls POST /api/v1/analyze/recruiter-email.
   *
   * @param {Object} payload - { email, company_name, cin, message_text }
   * @returns {Promise<Object>} RecruiterEmailAnalysisResponse
   */
  async analyzeRecruiterEmail(payload) {
    return request('/api/v1/analyze/recruiter-email', {
      method: 'POST',
      body: JSON.stringify(payload),
      timeout: 35000,
    });
  },

  /**
   * Fetch verified company details by ID.
   * Calls GET /api/v1/companies/{id}.
   *
   * @param {string} companyId - Company UUID
   * @returns {Promise<Object>} CompanyDetailResponse
   */
  async getCompany(companyId) {
    return request(`/api/v1/companies/${encodeURIComponent(companyId)}`);
  },

  /**
   * Register a job listing and evaluate duplicate similarity & impersonation signals.
   * Calls POST /api/v1/listings/register-or-analyze.
   *
   * @param {Object} payload - { job_title, job_description, claimed_company_name, cin, source_url, job_location, employment_type }
   * @returns {Promise<Object>} JobListingResponse
   */
  async registerOrAnalyzeListing(payload) {
    return request('/api/v1/listings/register-or-analyze', {
      method: 'POST',
      body: JSON.stringify(payload),
      timeout: 35000,
    });
  },

  /**
   * Retrieve a registered job listing by ID.
   * Calls GET /api/v1/listings/{listingId}.
   *
   * @param {string} listingId - Listing UUID
   * @returns {Promise<Object>} JobListingResponse
   */
  async getJobListing(listingId) {
    return request(`/api/v1/listings/${encodeURIComponent(listingId)}`);
  },

  /**
   * Retrieve similarity matches and impersonation evidence for a listing.
   * Calls GET /api/v1/listings/{listingId}/similar.
   *
   * @param {string} listingId - Listing UUID
   * @returns {Promise<Object>} DuplicateAnalysisSummary
   */
  async getSimilarListings(listingId) {
    return request(`/api/v1/listings/${encodeURIComponent(listingId)}/similar`);
  },

  /**
   * Check job description text for duplicates and impersonation signals without persisting.
   * Calls POST /api/v1/listings/check-duplicate.
   *
   * @param {Object} payload - { text, title, company_name, cin, source_url, location }
   * @returns {Promise<Object>} DuplicateAnalysisSummary
   */
  async checkDuplicate(payload) {
    return request('/api/v1/listings/check-duplicate', {
      method: 'POST',
      body: JSON.stringify(payload),
      timeout: 35000,
    });
  },

  /**
   * Upload and analyze an offer letter PDF using PyMuPDF and Tesseract OCR.
   * Calls POST /api/v1/analyze/offer-letter.
   *
   * @param {File} file - PDF document File object
   * @param {string} [companyName] - Optional claimed company name
   * @param {string} [cin] - Optional Corporate Identification Number
   * @returns {Promise<Object>} OfferLetterAnalysisResponse
   */
  async analyzeOfferLetter(file, companyName = '', cin = '') {
    const formData = new FormData();
    formData.append('file', file);
    if (companyName) formData.append('company_name', companyName);
    if (cin) formData.append('cin', cin);

    return request('/api/v1/analyze/offer-letter', {
      method: 'POST',
      body: formData,
      timeout: 45000, // OCR processing may require slightly longer timeout
    });
  },

  /**
   * Retrieves stored scan details and complete persisted evidence.
   * Calls GET /api/v1/scans/{scanId}.
   *
   * @param {string} scanId - UUID of the scan record
   * @returns {Promise<Object>} Scan details object
   */
  async getScan(scanId) {
    if (!scanId) {
      throw new Error('A valid Scan ID is required to fetch scan details.');
    }
    return request(`/api/v1/scans/${encodeURIComponent(scanId)}`);
  },

  /**
   * Constructs the absolute URL for downloading the verification report PDF.
   *
   * @param {string} scanId - UUID of the scan record
   * @returns {string} URL to GET /api/v1/scans/{scanId}/report.pdf
   */
  getReportPdfUrl(scanId) {
    if (!scanId) return '';
    return `${API_BASE_URL}/api/v1/scans/${encodeURIComponent(scanId)}/report.pdf`;
  },

  /**
   * Downloads the official Evidence-Based PDF Verification Report from the server.
   * Calls GET /api/v1/scans/{scanId}/report.pdf.
   *
   * @param {string} scanId - UUID of the scan record
   * @returns {Promise<Blob>} PDF binary Blob
   */
  async downloadReportPdf(scanId) {
    if (!scanId) {
      throw new Error('A valid Scan ID is required to download the verification report.');
    }
    const url = this.getReportPdfUrl(scanId);
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 30000);

    try {
      const headers = {
        'Accept': 'application/pdf',
      };
      if (inMemoryAuthToken) {
        headers['Authorization'] = `Bearer ${inMemoryAuthToken}`;
      }
      const response = await fetch(url, {
        method: 'GET',
        credentials: 'include',
        signal: controller.signal,
        headers,
      });
      clearTimeout(timeoutId);

      if (!response.ok) {
        let errorMessage = `Failed to generate report (HTTP ${response.status})`;
        try {
          const errData = await response.json();
          errorMessage = errData.detail || errData.message || errorMessage;
        } catch {
          // Non-JSON response
        }
        const error = new Error(errorMessage);
        error.status = response.status;
        throw error;
      }

      return await response.blob();
    } catch (err) {
      clearTimeout(timeoutId);
      if (err.name === 'AbortError') {
        const timeoutErr = new Error('PDF report generation timed out. Please try again.');
        timeoutErr.isTimeout = true;
        throw timeoutErr;
      }
      throw err;
    }
  },

  /**
   * Retrieves Bayesian company reputation metrics (GET /api/v1/companies/{companyId}/reputation).
   *
   * @param {number} companyId
   * @returns {Promise<Object>} CompanyReputationResponse
   */
  async getCompanyReputation(companyId) {
    if (!companyId) throw new Error('Company ID is required to fetch reputation.');
    return request(`/api/v1/companies/${companyId}/reputation`);
  },

  /**
   * Submits a 1-5 star recruitment experience review (POST /api/v1/reviews).
   *
   * @param {Object} reviewData
   * @returns {Promise<Object>} UserReviewResponse
   */
  async submitReview(reviewData) {
    return request('/api/v1/reviews', {
      method: 'POST',
      body: JSON.stringify(reviewData),
    });
  },

  /**
   * Queries community reviews (GET /api/v1/reviews).
   *
   * @param {Object} params - { company_id, status, limit, offset }
   * @returns {Promise<Array>} List of UserReviewResponse
   */
  async getReviews(params = {}) {
    const query = new URLSearchParams();
    if (params.company_id) query.append('company_id', params.company_id);
    if (params.status) query.append('status', params.status);
    if (params.limit) query.append('limit', params.limit);
    if (params.offset) query.append('offset', params.offset);
    const qs = query.toString() ? `?${query.toString()}` : '';
    return request(`/api/v1/reviews${qs}`);
  },

  /**
   * Submits a recruiter fraud report (POST /api/v1/reports).
   *
   * @param {Object} reportData
   * @returns {Promise<Object>} RecruiterReportResponse
   */
  async submitReport(reportData) {
    return request('/api/v1/reports', {
      method: 'POST',
      body: JSON.stringify(reportData),
    });
  },

  /**
   * Queries fraud reports (GET /api/v1/reports).
   *
   * @param {Object} params - { company_id, status, limit, offset }
   * @returns {Promise<Array>} List of RecruiterReportResponse
   */
  async getReports(params = {}) {
    const query = new URLSearchParams();
    if (params.company_id) query.append('company_id', params.company_id);
    if (params.status) query.append('status', params.status);
    if (params.limit) query.append('limit', params.limit);
    if (params.offset) query.append('offset', params.offset);
    const qs = query.toString() ? `?${query.toString()}` : '';
    return request(`/api/v1/reports${qs}`);
  },

  /**
   * Appeals a recruiter fraud report decision (POST /api/v1/reports/{reportId}/appeal).
   *
   * @param {string} reportId
   * @param {Object} appealData - { moderation_id, appeal_reason }
   * @returns {Promise<Object>} ModerationAppealResponse
   */
  async appealReport(reportId, appealData) {
    return request(`/api/v1/reports/${reportId}/appeal`, {
      method: 'POST',
      body: JSON.stringify(appealData),
    });
  },

  // ============================================================================
  // Authentication & Session Management
  // ============================================================================

  /**
   * Register a new user account (POST /api/v1/auth/register).
   */
  async register(userData) {
    return request('/api/v1/auth/register', {
      method: 'POST',
      body: JSON.stringify(userData),
    });
  },

  /**
   * Log in and retrieve access token & session cookies (POST /api/v1/auth/login).
   */
  async login(credentials) {
    const res = await request('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify(credentials),
    });
    if (res && res.access_token) {
      setAuthToken(res.access_token);
    }
    return res;
  },

  /**
   * Refresh access token (POST /api/v1/auth/refresh).
   */
  async refreshToken(refreshTokenVal = null) {
    const payload = refreshTokenVal ? { refresh_token: refreshTokenVal } : {};
    const res = await request('/api/v1/auth/refresh', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    if (res && res.access_token) {
      setAuthToken(res.access_token);
    }
    return res;
  },

  /**
   * Log out and revoke active refresh token (POST /api/v1/auth/logout).
   */
  async logout(refreshTokenVal = null) {
    try {
      const payload = refreshTokenVal ? { refresh_token: refreshTokenVal } : {};
      await request('/api/v1/auth/logout', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
    } finally {
      setAuthToken(null);
    }
  },

  /**
   * Get current authenticated user profile (GET /api/v1/auth/me).
   */
  async getMe() {
    return request('/api/v1/auth/me');
  },

  /**
   * Update password (POST /api/v1/auth/change-password).
   */
  async changePassword(data) {
    return request('/api/v1/auth/change-password', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  // ============================================================================
  // Scan History & IDOR-Protected Scans
  // ============================================================================

  /**
   * Retrieve current user's scan history (GET /api/v1/scans/my-scans).
   */
  async getMyScans(params = {}) {
    const query = new URLSearchParams();
    if (params.limit) query.append('limit', params.limit);
    if (params.offset) query.append('offset', params.offset);
    const qs = query.toString() ? `?${query.toString()}` : '';
    return request(`/api/v1/scans/my-scans${qs}`);
  },

  /**
   * Delete a scan from user's history (DELETE /api/v1/scans/{scanId}).
   */
  async deleteScan(scanId) {
    return request(`/api/v1/scans/${encodeURIComponent(scanId)}`, {
      method: 'DELETE',
    });
  },

  // ============================================================================
  // Moderation Appeals
  // ============================================================================

  /**
   * Submit an appeal against moderation decision (POST /api/v1/appeals).
   */
  async submitAppeal(appealData) {
    return request('/api/v1/appeals', {
      method: 'POST',
      body: JSON.stringify(appealData),
    });
  },

  /**
   * Retrieve current user's submitted appeals (GET /api/v1/appeals/my-appeals).
   */
  async getMyAppeals(params = {}) {
    const query = new URLSearchParams();
    if (params.limit) query.append('limit', params.limit);
    if (params.offset) query.append('offset', params.offset);
    const qs = query.toString() ? `?${query.toString()}` : '';
    return request(`/api/v1/appeals/my-appeals${qs}`);
  },

  // ============================================================================
  // Moderator & Admin Operations
  // ============================================================================

  /**
   * Retrieve items pending moderation review (GET /api/v1/moderation/queue).
   */
  async getModerationQueue(params = {}) {
    const query = new URLSearchParams();
    if (params.item_type) query.append('item_type', params.item_type);
    if (params.limit) query.append('limit', params.limit);
    if (params.offset) query.append('offset', params.offset);
    const qs = query.toString() ? `?${query.toString()}` : '';
    return request(`/api/v1/moderation/queue${qs}`);
  },

  /**
   * Commit a moderation decision atomically with audit log (POST /api/v1/moderation/decisions).
   */
  async submitModerationDecision(decisionData) {
    return request('/api/v1/moderation/decisions', {
      method: 'POST',
      body: JSON.stringify(decisionData),
    });
  },

  /**
   * Resolve an appeal (POST /api/v1/moderation/appeals/{appealId}/resolve).
   */
  async resolveAppeal(appealId, resolutionData) {
    return request(`/api/v1/moderation/appeals/${encodeURIComponent(appealId)}/resolve`, {
      method: 'POST',
      body: JSON.stringify(resolutionData),
    });
  },

  /**
   * Retrieve append-only moderation audit trail (GET /api/v1/moderation/audit-trail).
   */
  async getModerationAuditTrail(params = {}) {
    const query = new URLSearchParams();
    if (params.item_type) query.append('item_type', params.item_type);
    if (params.limit) query.append('limit', params.limit);
    if (params.offset) query.append('offset', params.offset);
    const qs = query.toString() ? `?${query.toString()}` : '';
    return request(`/api/v1/moderation/audit-trail${qs}`);
  },

  // ============================================================================
  // Admin User & System Controls
  // ============================================================================

  /**
   * List users with pagination and search (GET /api/v1/admin/users).
   */
  async getAdminUsers(params = {}) {
    const query = new URLSearchParams();
    if (params.search) query.append('search', params.search);
    if (params.limit) query.append('limit', params.limit);
    if (params.offset) query.append('offset', params.offset);
    const qs = query.toString() ? `?${query.toString()}` : '';
    return request(`/api/v1/admin/users${qs}`);
  },

  /**
   * Update user role (PUT /api/v1/admin/users/{userId}/role).
   */
  async updateUserRole(userId, role) {
    return request(`/api/v1/admin/users/${encodeURIComponent(userId)}/role`, {
      method: 'PUT',
      body: JSON.stringify({ role }),
    });
  },

  /**
   * Update user active status (PUT /api/v1/admin/users/{userId}/status).
   */
  async updateUserStatus(userId, isActive) {
    return request(`/api/v1/admin/users/${encodeURIComponent(userId)}/status`, {
      method: 'PUT',
      body: JSON.stringify({ is_active: isActive }),
    });
  },

  /**
   * Query append-only security audit logs (GET /api/v1/admin/audit-logs).
   */
  async getSecurityAuditLogs(params = {}) {
    const query = new URLSearchParams();
    if (params.action) query.append('action', params.action);
    if (params.target_type) query.append('target_type', params.target_type);
    if (params.limit) query.append('limit', params.limit);
    if (params.offset) query.append('offset', params.offset);
    const qs = query.toString() ? `?${query.toString()}` : '';
    return request(`/api/v1/admin/audit-logs${qs}`);
  },
};

export default api;

