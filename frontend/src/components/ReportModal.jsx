import React, { useState } from 'react';
import { AlertOctagon, X, AlertTriangle, CheckCircle2, Loader2, ShieldAlert } from 'lucide-react';
import { api } from '../services/api';

const REPORT_TYPES = [
  { value: 'fake_offer', label: 'Fake or Unsolicited Job Offer' },
  { value: 'fee_demand', label: 'Upfront Fee / Security Deposit Demand' },
  { value: 'impersonation', label: 'Recruiter / Company Brand Impersonation' },
  { value: 'phishing', label: 'Phishing / Suspicious Links' },
  { value: 'suspicious_domain', label: 'Lookalike or Spoofed Domain' },
  { value: 'other', label: 'Other Suspicious Activity' },
];

export default function ReportModal({
  isOpen,
  onClose,
  companyId,
  companyName,
  recruiterEmail,
  scanId,
  onSuccess,
}) {
  const [reportType, setReportType] = useState('fake_offer');
  const [details, setDetails] = useState('');
  const [evidenceSummary, setEvidenceSummary] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(false);

  if (!isOpen) return null;

  async function handleSubmit(e) {
    e.preventDefault();
    if (details.trim().length < 10) {
      setError('Please provide at least 10 characters describing the incident.');
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      await api.submitReport({
        company_id: companyId || undefined,
        company_name: companyName || undefined,
        recruiter_email: recruiterEmail || undefined,
        scan_id: scanId || undefined,
        report_type: reportType,
        details: details.trim(),
        evidence_summary: evidenceSummary.trim() || undefined,
      });

      setSuccess(true);
      if (onSuccess) {
        onSuccess();
      }
      setTimeout(() => {
        setSuccess(false);
        onClose();
      }, 1500);
    } catch (err) {
      setError(err.message || 'Failed to submit report. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs">
      <div className="w-full max-w-lg bg-white rounded-2xl shadow-2xl border border-slate-200 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 bg-rose-50/50 border-b border-rose-100">
          <div className="flex items-center gap-2.5">
            <div className="p-1.5 rounded-lg bg-rose-100 text-rose-700">
              <AlertOctagon className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-semibold text-slate-900">
                Report Suspicious Recruiter Activity
              </h3>
              <p className="text-xs text-slate-500">
                {companyName ? `Reporting allegation regarding ${companyName}` : 'Report suspected fraud or impersonation'}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-200/50 transition-colors"
            aria-label="Close modal"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Mandatory Pre-Submission Privacy Notice */}
        <div className="px-6 pt-4 pb-1">
          <div className="p-3 rounded-lg bg-amber-50 border border-amber-200 text-amber-800 flex items-start gap-2.5 text-xs">
            <ShieldAlert className="w-4 h-4 shrink-0 text-amber-600 mt-0.5" />
            <div className="space-y-0.5">
              <span className="font-semibold block">Privacy & Security Notice</span>
              <p className="text-amber-700 leading-relaxed">
                Do not include passwords, one-time passwords (OTPs), bank details, payment credentials, or other sensitive personal information in reviews or reports.
              </p>
            </div>
          </div>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {error && (
            <div className="p-3 rounded-lg bg-rose-50 border border-rose-200 text-rose-700 text-xs flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 shrink-0 text-rose-600" />
              <span>{error}</span>
            </div>
          )}

          {success && (
            <div className="p-3 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-600" />
              <span>Report registered. Thank you for protecting the job seeker community.</span>
            </div>
          )}

          {/* Allegation Type */}
          <div>
            <label htmlFor="report-type" className="block text-xs font-semibold text-slate-700 mb-1.5">
              Type of Suspicious Activity
            </label>
            <select
              id="report-type"
              value={reportType}
              onChange={(e) => setReportType(e.target.value)}
              className="w-full text-xs rounded-lg border border-slate-300 px-3 py-2 bg-white text-slate-800 focus:outline-hidden focus:ring-2 focus:ring-rose-500"
            >
              {REPORT_TYPES.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
          </div>

          {/* Details */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label htmlFor="report-details" className="text-xs font-semibold text-slate-700">
                Incident Details (Minimum 10 characters)
              </label>
              <span className="text-[10px] text-slate-400">{details.length}/3000</span>
            </div>
            <textarea
              id="report-details"
              rows={4}
              maxLength={3000}
              required
              value={details}
              onChange={(e) => setDetails(e.target.value)}
              placeholder="Describe what occurred, what was requested (e.g. upfront fee, security deposit), or why the recruiter seems fraudulent..."
              className="w-full text-xs rounded-lg border border-slate-300 p-3 text-slate-800 focus:outline-hidden focus:ring-2 focus:ring-rose-500 placeholder:text-slate-400"
            />
          </div>

          {/* Evidence Summary */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label htmlFor="report-evidence" className="text-xs font-semibold text-slate-700">
                Evidence References (Optional)
              </label>
              <span className="text-[10px] text-slate-400">{evidenceSummary.length}/2000</span>
            </div>
            <textarea
              id="report-evidence"
              rows={2}
              maxLength={2000}
              value={evidenceSummary}
              onChange={(e) => setEvidenceSummary(e.target.value)}
              placeholder="Payment links, UPI handles, sender domain headers, or offer letter filenames..."
              className="w-full text-xs rounded-lg border border-slate-300 p-3 text-slate-800 focus:outline-hidden focus:ring-2 focus:ring-rose-500 placeholder:text-slate-400"
            />
          </div>

          {/* Disclaimer */}
          <p className="text-[11px] text-slate-500 italic">
            Allegations are reviewed independently by moderators and kept strictly separate from service quality star ratings.
          </p>

          {/* Actions */}
          <div className="flex items-center justify-end gap-2.5 pt-2 border-t border-slate-100">
            <button
              type="button"
              onClick={onClose}
              disabled={isSubmitting}
              className="px-4 py-2 text-xs font-medium text-slate-600 hover:text-slate-800 hover:bg-slate-100 rounded-lg transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting || success || details.trim().length < 10}
              className="px-5 py-2 text-xs font-semibold text-white bg-rose-600 hover:bg-rose-700 rounded-lg shadow-xs flex items-center gap-1.5 transition-colors disabled:opacity-50"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  <span>Submitting...</span>
                </>
              ) : (
                'Submit Fraud Report'
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
