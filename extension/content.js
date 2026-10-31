/**
 * JobShield AI - Content Script (Feature F11)
 *
 * Privacy Guarantees:
 * - NO automatic execution on page load.
 * - NO continuous background inspection or DOM listeners.
 * - Executes extraction ONLY upon receiving an explicit user-initiated request from the popup.
 * - Ignores passwords, session tokens, form inputs, scripts, and navigation chrome.
 */

import { extractPageContent } from './extractor.js';

if (typeof chrome !== 'undefined' && chrome.runtime && chrome.runtime.onMessage) {
  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request && request.action === 'EXTRACT_JOB_CONTENT') {
      try {
        const result = extractPageContent(document, window.location.href);
        sendResponse(result);
      } catch (err) {
        sendResponse({
          success: false,
          error: err.message || 'Content extraction failed',
        });
      }
    }
    return true; // Keep message channel open for async response
  });
}
