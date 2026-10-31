import React, { useState, useEffect } from 'react';
import { useLocation, Link } from 'react-router-dom';
import {
  Shield,
  ShieldAlert,
  ShieldCheck,
  AlertTriangle,
  HelpCircle,
  Copy,
  Check,
  ArrowLeft,
  Download,
  CheckCircle2,
  Info,
  Calendar,
  Sparkles,
  Scale,
  Building,
  Mail,
  Globe,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  Loader2,
  FileText,
  Calculator,
  TrendingUp,
  TrendingDown,
  Users,
} from 'lucide-react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Cell,
  ReferenceLine,
} from 'recharts';
import RiskIndicator from '../components/RiskIndicator';
import EmptyState from '../components/EmptyState';
import CompanyReputationCard from '../components/CompanyReputationCard';
import { api } from '../services/api';

function getDomainStatusDot(status) {
  const s = (status || '').toUpperCase();
  if (s === 'PASS') return 'bg-emerald-500';
  if (s === 'TIMEOUT') return 'bg-amber-400';
  if (s === 'SKIPPED' || s === 'NOT_APPLICABLE') return 'bg-slate-300';
  if (s === 'NOT_FOUND' || s === 'NO_RECORDS' || s === 'NO_MX') return 'bg-slate-400';
  return 'bg-rose-500';
}

export function Results() {
  const location = useLocation();
  const [analysis, setAnalysis] = useState(location.state?.analysisResult);
  const jobText = location.state?.jobText || '';
  const claimedCompany = location.state?.claimedCompany || '';
  const claimedCin = location.state?.claimedCin || '';
  const jobTitle = location.state?.jobTitle || analysis?.extracted_title || '';
  const jobUrl = location.state?.jobUrl || analysis?.job_url || '';

  const [copiedReportId, setCopiedReportId] = useState(false);
  const [companyDetails, setCompanyDetails] = useState(null);
  const [loadingCompany, setLoadingCompany] = useState(false);
  const [companyError, setCompanyError] = useState(null);
  const [isCompanyDetailsOpen, setIsCompanyDetailsOpen] = useState(false);

  const [reverifyInput, setReverifyInput] = useState(claimedCin || '');
  const [isReverifying, setIsReverifying] = useState(false);
  const [reverifyError, setReverifyError] = useState(null);
  const [reverifySuccess, setReverifySuccess] = useState(null);

  const [isDownloadingPdf, setIsDownloadingPdf] = useState(false);
  const [downloadPdfError, setDownloadPdfError] = useState(null);

  const searchParams = new URLSearchParams(location.search);
  const queryScanId = searchParams.get('scan_id');

  const [loadingScan, setLoadingScan] = useState(!location.state?.analysisResult && Boolean(queryScanId));
  const [scanLoadError, setScanLoadError] = useState(null);

  useEffect(() => {
    if (!analysis && queryScanId && !scanLoadError) {
      setLoadingScan(true);
      api.getScan(queryScanId)
        .then((data) => {
          setAnalysis(data);
        })
        .catch((err) => {
          setScanLoadError(err.message || 'Failed to load scan report.');
        })
        .finally(() => {
          setLoadingScan(false);
        });
    }
  }, [queryScanId, analysis, scanLoadError]);

  async function handleDownloadPdf() {
    const scanId = analysis?.report_id || analysis?.id;
    if (!scanId) {
      setDownloadPdfError('Scan report identifier is missing. Cannot download report.');
      return;
    }
    setIsDownloadingPdf(true);
    setDownloadPdfError(null);
    try {
      const blob = await api.downloadReportPdf(scanId);
      const downloadUrl = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = downloadUrl;
      link.download = `JobShield_Report_${scanId.slice(0, 8)}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(downloadUrl);
    } catch (err) {
      setDownloadPdfError(err.message || 'Unable to download verification report.');
    } finally {
      setIsDownloadingPdf(false);
    }
  }

  async function handleToggleCompanyDetails(companyId) {
    if (isCompanyDetailsOpen) {
      setIsCompanyDetailsOpen(false);
      return;
    }
    setIsCompanyDetailsOpen(true);
    if (!companyDetails && companyId) {
      setLoadingCompany(true);
      setCompanyError(null);
      try {
        const data = await api.getCompany(companyId);
        setCompanyDetails(data);
      } catch (err) {
        setCompanyError(err.message || 'Failed to retrieve company registry details.');
      } finally {
        setLoadingCompany(false);
      }
    }
  }

  async function handleReverify(customInput) {
    const query = (customInput !== undefined ? customInput : reverifyInput).trim();
    if (!query) return;

    setIsReverifying(true);
    setReverifyError(null);
    setReverifySuccess(null);

    try {
      // Determine if input is a 21-character CIN
      const isCin = /^[ULu][0-9]{5}[A-Za-z]{2}[0-9]{4}[A-Za-z]{3}[0-9]{6}$/.test(query);
      const textToUse =
        jobText ||
        `Job recruitment communication for position at ${query}. Verification corroboration request.`;

      const updated = await api.analyzeJobText({
        text: textToUse,
        company_name: isCin ? undefined : query,
        cin: isCin ? query : undefined,
      });

      setAnalysis(updated);
      setReverifySuccess(`Re-verified against official registry for: "${query}"`);
    } catch (err) {
      setReverifyError(err.message || 'Failed to re-verify company entity.');
    } finally {
      setIsReverifying(false);
    }
  }

  if (loadingScan) {
    return (
      <div className="max-w-4xl mx-auto py-16 px-4 sm:px-6 lg:px-8 text-center" role="status" aria-live="polite">
        <Loader2 className="h-8 w-8 animate-spin text-blue-600 mx-auto mb-3" />
        <p className="text-sm font-medium text-slate-700">Loading scan verification report...</p>
      </div>
    );
  }

  if (scanLoadError) {
    return (
      <div className="max-w-4xl mx-auto py-12 px-4 sm:px-6 lg:px-8">
        <EmptyState
          title="Scan Report Unavailable"
          description={scanLoadError}
          action={
            <Link
              to="/analyze"
              className="mt-2 inline-flex items-center gap-2 px-5 py-2.5 bg-blue-700 hover:bg-blue-800 text-white text-xs font-semibold rounded-xl shadow transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600"
            >
              <ArrowLeft className="h-4 w-4" aria-hidden="true" />
              <span>Back to JobShield Analyze</span>
            </Link>
          }
        />
      </div>
    );
  }

  // If user visits /results directly without submitting, show EmptyState
  if (!analysis) {
    return (
      <div className="max-w-4xl mx-auto py-12 px-4 sm:px-6 lg:px-8">
        <EmptyState
          title="No Analysis Record Found"
          description="No job posting has been analyzed in this session yet. Submit a job description or recruitment message to generate a risk assessment report."
          action={
            <Link
              to="/analyze"
              className="mt-2 inline-flex items-center gap-2 px-5 py-2.5 bg-blue-700 hover:bg-blue-800 text-white text-xs font-semibold rounded-xl shadow transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600"
            >
              <ArrowLeft className="h-4 w-4" aria-hidden="true" />
              <span>Go to Analyze Form</span>
            </Link>
          }
        />
      </div>
    );
  }

  // Job-Relevance Validation Guard: If input is unrelated to jobs, suppress fraud assessment and show clear prompt
  const isInvalidInput =
    analysis.is_job_related === false ||
    analysis.risk_category === 'INVALID_INPUT' ||
    analysis.risk_category === 'UNCERTAIN' ||
    analysis.relevance?.is_job_related === false ||
    analysis.relevance?.status === 'INVALID' ||
    (analysis.relevance?.status === 'UNCERTAIN' && !analysis.domain_check);

  if (isInvalidInput) {
    let returnTab = 'job-text';
    if (analysis.job_url || location.state?.jobUrl) {
      returnTab = 'job-url';
    } else if (analysis.file_name || analysis.extracted_fields || location.state?.offerFile) {
      returnTab = 'offer-letter';
    } else if (analysis.email_masked || analysis.domain || location.state?.recruiterEmail) {
      returnTab = 'recruiter-email';
    }

    const diagnosticMessage =
      analysis.relevance?.supporting_message ||
      analysis.warning ||
      'The submitted content was evaluated as unrelated to recruitment, vacancies, or employment offers.';

    return (
      <div className="max-w-3xl mx-auto py-12 px-4 sm:px-6 lg:px-8">
        <div className="rounded-2xl border border-amber-200 bg-amber-50/60 p-8 sm:p-10 shadow-xs text-center space-y-6">
          <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-amber-100 text-amber-700 shadow-inner">
            <AlertTriangle className="h-9 w-9" aria-hidden="true" />
          </div>

          <div className="space-y-2">
            <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">
              Please provide job-related input to continue.
            </h1>
            <p className="text-sm sm:text-base text-slate-600 max-w-xl mx-auto leading-relaxed">
              JobShield AI analyzes job descriptions, job posting URLs, offer letters, and recruiter emails. Please submit relevant content so we can assess potential recruitment risks.
            </p>
          </div>

          {diagnosticMessage && (
            <div className="rounded-xl border border-amber-200/80 bg-white/90 p-4 text-xs sm:text-sm text-slate-700 max-w-lg mx-auto shadow-xs text-left flex items-start gap-3">
              <Info className="h-5 w-5 text-amber-600 shrink-0 mt-0.5" aria-hidden="true" />
              <div>
                <p className="font-semibold text-slate-900 mb-0.5">Diagnostic Finding:</p>
                <p className="text-slate-600 leading-normal">{diagnosticMessage}</p>
              </div>
            </div>
          )}

          <div className="pt-2 flex flex-wrap items-center justify-center gap-3">
            <Link
              to="/analyze"
              state={{ activeTab: returnTab }}
              className="inline-flex items-center gap-2 px-6 py-3 bg-blue-700 hover:bg-blue-800 text-white text-sm font-semibold rounded-xl shadow transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600"
            >
              <ArrowLeft className="h-4 w-4" aria-hidden="true" />
              <span>Back to Analyze Form</span>
            </Link>
          </div>
        </div>
      </div>
    );
  }

  const isInsufficient =
    analysis.risk_category === 'INSUFFICIENT_EVIDENCE' || analysis.risk_score === null;

  const formattedDate = analysis.timestamp
    ? new Date(analysis.timestamp).toLocaleString(undefined, {
        dateStyle: 'medium',
        timeStyle: 'medium',
      })
    : 'Just now';

  function handleCopyReportId() {
    if (analysis.report_id) {
      navigator.clipboard.writeText(analysis.report_id);
      setCopiedReportId(true);
      setTimeout(() => setCopiedReportId(false), 2000);
    }
  }

  // Prepare chart data for top linguistic features
  const mlAnalysis = analysis.ml_analysis;
  const rawFeatures =
    mlAnalysis?.top_features && mlAnalysis.top_features.length > 0
      ? mlAnalysis.top_features
      : [
          ...(mlAnalysis?.top_positive_features || []),
          ...(mlAnalysis?.top_negative_features || []),
        ];
  const featureChartData =
    rawFeatures.map((f) => ({
      name: f.feature,
      weight: f.contribution !== undefined ? f.contribution : (f.weight || 0),
      feature_value: f.feature_value,
      coefficient: f.coefficient,
      direction:
        f.direction || ((f.contribution !== undefined ? f.contribution : f.weight) >= 0 ? 'fraud_indicative' : 'legitimate_indicative'),
      direction_label: f.direction_label,
    })) || [];

  // Ambiguous brand candidate entities (if applicable)
  const candidateEntities =
    analysis.company_verification?.candidate_entities ||
    analysis.evidence?.find((e) => e.details?.candidate_entities)?.details?.candidate_entities ||
    [];

  return (
    <div className="max-w-5xl mx-auto py-8 px-4 sm:px-6 lg:px-8 space-y-8">
      {/* Back navigation & Report Actions */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-200 pb-4">
        <div>
          <Link
            to="/analyze"
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-blue-700 hover:text-blue-800 mb-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 rounded"
          >
            <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
            <span>Submit Another Job Posting</span>
          </Link>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">
            Job Posting Risk Assessment Report
          </h1>
        </div>

        {/* Action: Download PDF Report (Feature F10) */}
        <div className="flex flex-col items-end gap-1">
          <button
            type="button"
            onClick={handleDownloadPdf}
            disabled={isDownloadingPdf || !analysis?.report_id}
            aria-label="Download Evidence-Based PDF Verification Report"
            className="inline-flex items-center gap-2 px-3.5 py-2 text-xs font-semibold rounded-lg bg-blue-600 hover:bg-blue-700 text-white shadow-xs transition-colors disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600"
            title="Download official evidence-based verification report in PDF format"
          >
            {isDownloadingPdf ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                <span>Generating PDF...</span>
              </>
            ) : (
              <>
                <Download className="h-4 w-4" aria-hidden="true" />
                <span>Download PDF Report</span>
              </>
            )}
          </button>
          {downloadPdfError && (
            <p className="text-[11px] text-rose-600 font-medium mt-1 max-w-xs text-right" role="alert">
              {downloadPdfError}
            </p>
          )}
        </div>
      </div>

      {/* Report Metadata Header Card */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-6 shadow-xs grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 text-xs">
        <div>
          <span className="text-slate-500 font-medium uppercase tracking-wider block">Report Identifier</span>
          <div className="flex items-center gap-1.5 mt-1">
            <span className="font-mono font-semibold text-slate-900 truncate" title={analysis.report_id}>
              {analysis.report_id}
            </span>
            <button
              type="button"
              onClick={handleCopyReportId}
              className="p-1 rounded text-slate-500 hover:text-slate-800 hover:bg-slate-100 transition-colors"
              title="Copy Report ID"
              aria-label="Copy Report ID to clipboard"
            >
              {copiedReportId ? (
                <Check className="h-3.5 w-3.5 text-emerald-600" aria-hidden="true" />
              ) : (
                <Copy className="h-3.5 w-3.5" aria-hidden="true" />
              )}
            </button>
          </div>
        </div>

        <div>
          <span className="text-slate-500 font-medium uppercase tracking-wider block">Observed Timestamp</span>
          <span className="font-semibold text-slate-900 mt-1 block flex items-center gap-1.5">
            <Calendar className="h-3.5 w-3.5 text-slate-400" aria-hidden="true" />
            {formattedDate}
          </span>
        </div>

        <div>
          <span className="text-slate-500 font-medium uppercase tracking-wider block">Evaluated Role</span>
          <span className="font-semibold text-slate-900 mt-1 block truncate">
            {jobTitle || 'Text Snippet / Unspecified Role'}
          </span>
        </div>

        <div>
          <span className="text-slate-500 font-medium uppercase tracking-wider block">Claimed Employer</span>
          <span className="font-semibold text-slate-900 mt-1 block truncate">
            {analysis.company_verification?.queried_name || claimedCompany || 'Text-Extracted / Unspecified'}
          </span>
        </div>

        {(jobUrl || analysis.job_url) && (
          <div className="sm:col-span-2 lg:col-span-4 pt-2.5 mt-1 border-t border-slate-100 flex flex-wrap items-center justify-between gap-2 text-xs">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-slate-500 font-medium flex items-center gap-1.5">
                <Globe className="h-3.5 w-3.5 text-blue-600" aria-hidden="true" />
                <span className="uppercase tracking-wider font-bold text-[10px]">Public Job URL Target:</span>
              </span>
              {analysis.page_type && (
                <span
                  className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded ${
                    analysis.page_type === 'JOB_POSTING'
                      ? 'bg-blue-100 text-blue-800'
                      : analysis.page_type === 'CAREERS_HOMEPAGE'
                      ? 'bg-indigo-100 text-indigo-800'
                      : 'bg-amber-100 text-amber-800'
                  }`}
                >
                  {analysis.page_type === 'CAREERS_HOMEPAGE'
                    ? 'Careers Portal / Index'
                    : analysis.page_type === 'ACCESS_RESTRICTED'
                    ? 'Access Restricted (Bot Protection)'
                    : analysis.page_type === 'JS_REQUIRED_OR_SPARSE_CONTENT'
                    ? 'SPA / JS Required'
                    : 'Job Posting'}
                </span>
              )}
            </div>
            <a
              href={jobUrl || analysis.job_url}
              target="_blank"
              rel="noopener noreferrer"
              className="font-mono text-blue-700 hover:text-blue-900 hover:underline truncate max-w-xl inline-flex items-center gap-1 font-medium"
            >
              <span className="truncate">{jobUrl || analysis.job_url}</span>
              <ExternalLink className="h-3 w-3 flex-shrink-0" aria-hidden="true" />
            </a>
          </div>
        )}

        {analysis.email_masked && (
          <div className="sm:col-span-2 lg:col-span-4 pt-2.5 mt-1 border-t border-slate-100 flex flex-wrap items-center justify-between gap-2 text-xs">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-slate-500 font-medium flex items-center gap-1.5">
                <Mail className="h-3.5 w-3.5 text-blue-600" aria-hidden="true" />
                <span className="uppercase tracking-wider font-bold text-[10px]">Recruiter Sender Address:</span>
              </span>
              <span className="font-mono font-bold text-slate-900 bg-slate-100 px-2 py-0.5 rounded">
                {analysis.email_masked}
              </span>
              {analysis.domain && (
                <span className="text-slate-500 font-mono text-[11px]">
                  (domain: {analysis.domain})
                </span>
              )}
            </div>
            {analysis.email_status && (
              <span
                className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded ${
                  analysis.email_status === 'DOMAIN_MATCH'
                    ? 'bg-emerald-100 text-emerald-800'
                    : analysis.email_status === 'FREE_EMAIL_PROVIDER'
                    ? 'bg-amber-100 text-amber-800'
                    : analysis.email_status === 'LOOKALIKE_WARNING' || analysis.email_status === 'MISMATCH_DETECTED'
                    ? 'bg-rose-100 text-rose-800'
                    : 'bg-slate-100 text-slate-800'
                }`}
              >
                {analysis.email_status}
              </span>
            )}
          </div>
        )}

        {analysis.file_name && (
          <div className="sm:col-span-2 lg:col-span-4 pt-2.5 mt-1 border-t border-slate-100 flex flex-wrap items-center justify-between gap-2 text-xs">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-slate-500 font-medium flex items-center gap-1.5">
                <FileText className="h-3.5 w-3.5 text-blue-600" aria-hidden="true" />
                <span className="uppercase tracking-wider font-bold text-[10px]">Offer Letter Document:</span>
              </span>
              <span className="font-mono font-bold text-slate-900 bg-slate-100 px-2 py-0.5 rounded">
                {analysis.file_name}
              </span>
              <span className="text-slate-500 text-[11px]">
                ({(analysis.file_size_bytes / 1024).toFixed(1)} KB · {analysis.page_count} {analysis.page_count === 1 ? 'page' : 'pages'})
              </span>
            </div>
            <div className="flex items-center gap-1.5">
              <span
                className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded ${
                  analysis.ocr_applied
                    ? 'bg-purple-100 text-purple-800'
                    : 'bg-emerald-100 text-emerald-800'
                }`}
              >
                {analysis.ocr_applied ? `OCR Processed (${analysis.ocr_engine || 'Tesseract'})` : 'Direct PDF Text'}
              </span>
              <span className="text-[10px] font-medium bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded">
                Zero Retention Active
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Prominent Warning Banner if applicable */}
      {analysis.warning && (
        <div
          role="alert"
          className="rounded-2xl border-2 border-amber-300 bg-amber-50/90 p-5 shadow-xs flex items-start gap-3.5 text-amber-950"
        >
          <AlertTriangle className="h-6 w-6 text-amber-700 flex-shrink-0 mt-0.5" aria-hidden="true" />
          <div className="space-y-1">
            <span className="font-bold text-sm block">Advisory Safety Caution</span>
            <p className="text-xs sm:text-sm text-amber-900 leading-relaxed">
              {analysis.warning}
            </p>
          </div>
        </div>
      )}

      {/* Section 1: Primary Composite Risk Indicator */}
      <section aria-labelledby="risk-summary-heading" className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 id="risk-summary-heading" className="text-lg font-bold text-slate-900 flex items-center gap-2">
            <Scale className="h-5 w-5 text-blue-700" aria-hidden="true" />
            <span>Composite Risk Assessment</span>
          </h2>
          <span className="text-xs font-semibold text-slate-500">
            Rules Weight: 45% · ML Weight: 55%
          </span>
        </div>

        <RiskIndicator
          score={analysis.risk_score}
          category={analysis.risk_category}
          size="lg"
        />

        {/* Safety Override Floor Alert if applicable */}
        {(analysis.override_floor_applied || analysis.override_floor_reason) && (
          <div className="rounded-xl border border-rose-300 bg-rose-50/90 p-3.5 text-xs text-rose-950 flex items-start gap-2.5 shadow-2xs">
            <ShieldAlert className="h-4 w-4 text-rose-600 flex-shrink-0 mt-0.5" aria-hidden="true" />
            <div className="space-y-0.5">
              <span className="font-bold text-rose-900 block">
                Rule Safety Override Floor Active:
              </span>
              <p className="text-rose-900/90 leading-relaxed">
                {analysis.override_floor_reason ||
                  'High-severity scam indicators (such as upfront fee solicitation) enforce a minimum risk score floor per docs/risk_scoring.md.'}
              </p>
            </div>
          </div>
        )}

        {/* Provisional Thresholds Disclosure */}
        {analysis.provisional_thresholds && (
          <div className="rounded-xl border border-slate-200 bg-slate-50/80 p-4 text-xs text-slate-600 space-y-2">
            <div className="flex items-center justify-between font-semibold text-slate-700">
              <span className="uppercase tracking-wider">
                Active Threshold Schedule: {analysis.provisional_thresholds.version}
              </span>
              <span className="bg-slate-200 text-slate-700 px-2 py-0.5 rounded text-[10px]">
                Production Baseline
              </span>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1 font-mono text-[11px]">
              <div className="bg-white p-2 rounded border border-slate-200">
                <span className="text-slate-400 block font-sans text-[10px] uppercase font-bold">Low Risk</span>
                &lt; 30.0
              </div>
              <div className="bg-white p-2 rounded border border-slate-200">
                <span className="text-slate-400 block font-sans text-[10px] uppercase font-bold">Moderate</span>
                30.0 – 59.9
              </div>
              <div className="bg-white p-2 rounded border border-slate-200">
                <span className="text-slate-400 block font-sans text-[10px] uppercase font-bold">High Risk</span>
                60.0 – 79.9
              </div>
              <div className="bg-white p-2 rounded border border-slate-200">
                <span className="text-slate-400 block font-sans text-[10px] uppercase font-bold">Critical</span>
                80.0 – 100.0
              </div>
            </div>
          </div>
        )}
      </section>

      {/* If Insufficient Evidence: Dedicated Guidance Card */}
      {isInsufficient && (
        <section aria-labelledby="insufficient-heading" className="rounded-2xl border border-blue-200 bg-blue-50/60 p-6 space-y-4">
          <div className="flex items-start gap-3">
            <HelpCircle className="h-6 w-6 text-blue-700 flex-shrink-0 mt-0.5" aria-hidden="true" />
            <div className="space-y-2">
              <h3 id="insufficient-heading" className="font-bold text-base text-blue-950">
                Why is the assessment marked as Insufficient Evidence?
              </h3>
              <p className="text-xs sm:text-sm text-blue-900 leading-relaxed">
                The submitted text did not contain enough substantive recruitment information (minimum 10 informative words required).
                Short snippets, isolated headlines, or single sentences lack sufficient linguistic and contextual signals for our multi-rule heuristics and statistical ML classifier to produce a reliable risk evaluation.
              </p>
              <div className="pt-2">
                <Link
                  to="/analyze"
                  className="inline-flex items-center gap-1.5 text-xs font-bold text-blue-800 bg-white hover:bg-blue-100 border border-blue-300 px-3.5 py-2 rounded-lg shadow-xs transition-colors"
                >
                  <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
                  <span>Return and Paste Complete Job Description</span>
                </Link>
              </div>
            </div>
          </div>
        </section>
      )}

      {/* Section: Offer Letter Analysis & Extracted Terms (Feature F7) */}
      {analysis.extracted_fields && (
        <section
          aria-labelledby="offer-letter-heading"
          className="rounded-2xl border border-slate-200 bg-white p-6 sm:p-7 shadow-xs space-y-6"
        >
          {/* Header */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-100 pb-4">
            <div>
              <div className="flex items-center gap-2">
                <FileText className="h-5 w-5 text-blue-600" aria-hidden="true" />
                <h2 id="offer-letter-heading" className="text-lg font-bold text-slate-900">
                  Offer Letter Analysis &amp; Extracted Contract Terms (Feature F7)
                </h2>
              </div>
              <p className="text-xs text-slate-500 mt-1">
                Extracted compensation, dates, employer identity, fee demand clauses, and contact credentials parsed via PyMuPDF and Tesseract OCR.
              </p>
            </div>
            <div className="flex items-center gap-2 self-start sm:self-auto">
              <span
                className={`text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-md border ${
                  analysis.extracted_fields.has_fee_demand || analysis.extracted_fields.has_sensitive_request
                    ? 'bg-rose-50 text-rose-800 border-rose-200'
                    : 'bg-emerald-50 text-emerald-800 border-emerald-200'
                }`}
              >
                {analysis.extracted_fields.has_fee_demand
                  ? 'FEE DEMANDS IDENTIFIED'
                  : analysis.extracted_fields.has_sensitive_request
                  ? 'SENSITIVE REQUEST IDENTIFIED'
                  : 'NO PAYMENT DEMANDS DETECTED'}
              </span>
            </div>
          </div>

          {/* CRITICAL CALLOUT: Advance Fee Demands (Red Flag) */}
          {analysis.extracted_fields.fee_demands && analysis.extracted_fields.fee_demands.length > 0 && (
            <div className="rounded-xl border-2 border-rose-300 bg-rose-50/90 p-5 space-y-3.5">
              <div className="flex items-center gap-2.5 text-rose-900">
                <AlertTriangle className="h-5 w-5 text-rose-700 flex-shrink-0" aria-hidden="true" />
                <div>
                  <h3 className="font-bold text-sm">
                    Advance Fee Demand Detected ({analysis.extracted_fields.fee_demands.length} {analysis.extracted_fields.fee_demands.length === 1 ? 'Clause' : 'Clauses'})
                  </h3>
                  <p className="text-xs text-rose-800">
                    Legitimate employers NEVER ask job seekers or new hires to pay upfront fees, training charges, registration costs, or equipment security deposits.
                  </p>
                </div>
              </div>

              <div className="space-y-3 pt-1">
                {analysis.extracted_fields.fee_demands.map((fee, idx) => (
                  <div
                    key={idx}
                    className="rounded-lg bg-white p-3.5 border border-rose-200 shadow-2xs space-y-2 text-xs"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className="font-bold font-mono text-[10px] uppercase bg-rose-100 text-rose-800 px-2 py-0.5 rounded">
                          {fee.category.replace(/_/g, ' ')}
                        </span>
                        {fee.amount && (
                          <span className="font-bold text-rose-900 font-mono text-xs">
                            Amount: {fee.amount}
                          </span>
                        )}
                      </div>
                      <span className="text-[11px] font-semibold text-slate-500">
                        Source Page: {fee.page}
                      </span>
                    </div>

                    <div className="font-mono text-[11px] bg-rose-50/50 p-2.5 rounded border border-rose-100 text-slate-800 italic">
                      "{fee.clause_text}"
                    </div>

                    {fee.is_refundable_claimed && (
                      <p className="text-[11px] text-amber-800 font-medium">
                        ⚠️ False refundability promise: Scammers frequently claim fees are "100% refundable" after joining to diminish candidate caution.
                      </p>
                    )}

                    <p className="text-[11px] text-rose-900 leading-relaxed">
                      <strong>Advisory:</strong> {fee.warning}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* SENSITIVE REQUESTS CALLOUT */}
          {analysis.extracted_fields.sensitive_requests && analysis.extracted_fields.sensitive_requests.length > 0 && (
            <div className="rounded-xl border border-amber-300 bg-amber-50/90 p-5 space-y-3">
              <div className="flex items-center gap-2.5 text-amber-950">
                <AlertTriangle className="h-5 w-5 text-amber-700 flex-shrink-0" aria-hidden="true" />
                <div>
                  <h3 className="font-bold text-sm">
                    Sensitive Information or Document Request ({analysis.extracted_fields.sensitive_requests.length})
                  </h3>
                  <p className="text-xs text-amber-800">
                    High-risk requests for banking credentials, OTPs, or retention of original identity/educational certificates.
                  </p>
                </div>
              </div>

              <div className="space-y-2.5 pt-1">
                {analysis.extracted_fields.sensitive_requests.map((req, idx) => (
                  <div
                    key={idx}
                    className="rounded-lg bg-white p-3 border border-amber-200 space-y-1.5 text-xs"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-bold font-mono text-[10px] uppercase bg-amber-100 text-amber-800 px-2 py-0.5 rounded">
                        {req.request_type.replace(/_/g, ' ')}
                      </span>
                      <span className="text-[11px] font-semibold text-slate-500">
                        Page {req.page}
                      </span>
                    </div>
                    <div className="font-mono text-[11px] bg-amber-50/40 p-2 rounded border border-amber-100 text-slate-800 italic">
                      "{req.clause_text}"
                    </div>
                    <p className="text-[11px] text-amber-900">
                      <strong>Risk Note:</strong> {req.warning}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Extracted Terms 6-Card Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3.5 text-xs">
            {/* Employer */}
            <div className="rounded-xl border border-slate-200 bg-slate-50/60 p-3.5 space-y-1">
              <div className="flex items-center justify-between text-slate-500">
                <span className="font-semibold uppercase tracking-wider text-[10px]">Claimed Employer</span>
                {analysis.extracted_fields.company_name?.page && (
                  <span className="text-[10px] font-mono">Page {analysis.extracted_fields.company_name.page}</span>
                )}
              </div>
              <p className="font-bold text-slate-900 text-sm">
                {analysis.extracted_fields.company_name?.value || 'Not extracted'}
              </p>
              {analysis.extracted_fields.company_name?.is_present && (
                <span className="text-[10px] text-slate-500">
                  Confidence: {Math.round((analysis.extracted_fields.company_name.confidence || 1) * 100)}%
                </span>
              )}
            </div>

            {/* Candidate */}
            <div className="rounded-xl border border-slate-200 bg-slate-50/60 p-3.5 space-y-1">
              <div className="flex items-center justify-between text-slate-500">
                <span className="font-semibold uppercase tracking-wider text-[10px]">Candidate Name</span>
                {analysis.extracted_fields.candidate_name?.page && (
                  <span className="text-[10px] font-mono">Page {analysis.extracted_fields.candidate_name.page}</span>
                )}
              </div>
              <p className="font-bold text-slate-900 text-sm">
                {analysis.extracted_fields.candidate_name?.value || 'Not extracted'}
              </p>
              <span className="text-[10px] text-slate-500 italic">
                Masked for privacy protection
              </span>
            </div>

            {/* Role / Job Title */}
            <div className="rounded-xl border border-slate-200 bg-slate-50/60 p-3.5 space-y-1">
              <div className="flex items-center justify-between text-slate-500">
                <span className="font-semibold uppercase tracking-wider text-[10px]">Designated Job Title</span>
                {analysis.extracted_fields.job_title?.page && (
                  <span className="text-[10px] font-mono">Page {analysis.extracted_fields.job_title.page}</span>
                )}
              </div>
              <p className="font-bold text-slate-900 text-sm">
                {analysis.extracted_fields.job_title?.value || 'Not extracted'}
              </p>
            </div>

            {/* Salary / Compensation */}
            <div className="rounded-xl border border-slate-200 bg-slate-50/60 p-3.5 space-y-1">
              <div className="flex items-center justify-between text-slate-500">
                <span className="font-semibold uppercase tracking-wider text-[10px]">Stipulated Salary</span>
                {analysis.extracted_fields.salary_compensation?.page && (
                  <span className="text-[10px] font-mono">Page {analysis.extracted_fields.salary_compensation.page}</span>
                )}
              </div>
              <p className="font-bold font-mono text-emerald-800 text-sm">
                {analysis.extracted_fields.salary_compensation?.value || 'Not extracted'}
              </p>
              {analysis.extracted_fields.salary_compensation?.snippet && (
                <p className="text-[10px] text-slate-500 truncate" title={analysis.extracted_fields.salary_compensation.snippet}>
                  Context: {analysis.extracted_fields.salary_compensation.snippet}
                </p>
              )}
            </div>

            {/* Offer & Joining Dates */}
            <div className="rounded-xl border border-slate-200 bg-slate-50/60 p-3.5 space-y-1">
              <span className="font-semibold uppercase tracking-wider text-[10px] text-slate-500 block">
                Offer / Joining Dates
              </span>
              <div className="space-y-0.5 text-xs text-slate-800">
                <div>
                  <span className="text-slate-500">Offer Date:</span>{' '}
                  <span className="font-semibold">{analysis.extracted_fields.offer_date?.value || 'N/A'}</span>
                </div>
                <div>
                  <span className="text-slate-500">Joining Date:</span>{' '}
                  <span className="font-semibold">{analysis.extracted_fields.joining_date?.value || 'N/A'}</span>
                </div>
                {analysis.extracted_fields.deadline_date?.value && (
                  <div>
                    <span className="text-slate-500">Acceptance Deadline:</span>{' '}
                    <span className="font-semibold text-rose-700">{analysis.extracted_fields.deadline_date.value}</span>
                  </div>
                )}
              </div>
            </div>

            {/* Contacts & Company Address */}
            <div className="rounded-xl border border-slate-200 bg-slate-50/60 p-3.5 space-y-1">
              <span className="font-semibold uppercase tracking-wider text-[10px] text-slate-500 block">
                Recruiter Contact Channels
              </span>
              <div className="space-y-1 text-xs">
                {analysis.extracted_fields.recruiter_contacts && analysis.extracted_fields.recruiter_contacts.length > 0 ? (
                  <div className="flex flex-wrap gap-1">
                    {analysis.extracted_fields.recruiter_contacts.map((contact, i) => (
                      <span key={i} className="font-mono text-[10px] bg-white px-2 py-0.5 rounded border border-slate-200 text-slate-800">
                        {contact}
                      </span>
                    ))}
                  </div>
                ) : (
                  <span className="text-slate-500 italic text-[11px]">No contact emails or phone numbers found</span>
                )}
                {analysis.extracted_fields.company_address?.value && (
                  <p className="text-[10px] text-slate-600 truncate mt-1" title={analysis.extracted_fields.company_address.value}>
                    Address: {analysis.extracted_fields.company_address.value}
                  </p>
                )}
              </div>
            </div>
          </div>

          {/* Domain Infrastructure Checks Table (if contacts present) */}
          {analysis.domain_checks && analysis.domain_checks.length > 0 && (
            <div className="space-y-3 pt-2 border-t border-slate-100">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700">
                  Contact Domain Security &amp; Email Authentication Checks
                </h3>
                <span className="text-[11px] text-slate-400">
                  {analysis.domain_checks.length} {analysis.domain_checks.length === 1 ? 'domain' : 'domains'} checked
                </span>
              </div>

              <div className="grid grid-cols-1 gap-3">
                {analysis.domain_checks.map((chk, idx) => (
                  <div
                    key={idx}
                    className="rounded-xl border border-slate-200 bg-slate-50/60 p-4 space-y-2.5 text-xs"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <Globe className="h-4 w-4 text-blue-600" aria-hidden="true" />
                        <span className="font-mono font-bold text-slate-900 text-sm">
                          {chk.domain}
                        </span>
                        {chk.lookalike_flags?.is_lookalike && (
                          <span className="text-[10px] font-bold bg-rose-100 text-rose-800 px-2 py-0.5 rounded">
                            LOOKALIKE DOMAIN
                          </span>
                        )}
                      </div>
                      <span className="text-[11px] text-slate-500 font-medium">
                        {chk.summary}
                      </span>
                    </div>

                    <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 text-xs">
                      <div className="rounded-lg bg-white p-2 border border-slate-100">
                        <span className="text-[10px] font-semibold text-slate-400 uppercase block">DNS</span>
                        <div className="font-bold text-slate-800 mt-0.5 flex items-center gap-1">
                          <span className={`h-2 w-2 rounded-full ${getDomainStatusDot(chk.dns_status)}`} />
                          <span>{chk.dns_status}</span>
                        </div>
                      </div>
                      <div className="rounded-lg bg-white p-2 border border-slate-100">
                        <span className="text-[10px] font-semibold text-slate-400 uppercase block">MX</span>
                        <div className="font-bold text-slate-800 mt-0.5 flex items-center gap-1">
                          <span className={`h-2 w-2 rounded-full ${getDomainStatusDot(chk.mx_status)}`} />
                          <span>{chk.mx_status}</span>
                        </div>
                      </div>
                      <div className="rounded-lg bg-white p-2 border border-slate-100">
                        <span className="text-[10px] font-semibold text-slate-400 uppercase block">SPF</span>
                        <div className="font-bold text-slate-800 mt-0.5 flex items-center gap-1">
                          <span className={`h-2 w-2 rounded-full ${getDomainStatusDot(chk.spf_status)}`} />
                          <span>{chk.spf_status}</span>
                        </div>
                      </div>
                      <div className="rounded-lg bg-white p-2 border border-slate-100">
                        <span className="text-[10px] font-semibold text-slate-400 uppercase block">DKIM</span>
                        <div className="font-bold text-slate-800 mt-0.5 flex items-center gap-1">
                          <span className={`h-2 w-2 rounded-full ${getDomainStatusDot(chk.dkim_status)}`} />
                          <span>{chk.dkim_status || 'UNKNOWN'}</span>
                        </div>
                      </div>
                      <div className="rounded-lg bg-white p-2 border border-slate-100">
                        <span className="text-[10px] font-semibold text-slate-400 uppercase block">DMARC</span>
                        <div className="font-bold text-slate-800 mt-0.5 flex items-center gap-1">
                          <span className={`h-2 w-2 rounded-full ${getDomainStatusDot(chk.dmarc_status)}`} />
                          <span>{chk.source_details?.dmarc_policy || chk.dmarc_status}</span>
                        </div>
                      </div>
                    </div>

                    {chk.lookalike_flags?.is_lookalike && (
                      <div className="rounded-lg bg-rose-50 border border-rose-200 p-2.5 text-xs text-rose-950">
                        <strong>Warning:</strong> {chk.lookalike_flags.warning}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Document Processing Audit Note */}
          <div className="rounded-lg bg-slate-50 p-3 text-[11px] text-slate-500 flex items-start gap-2 border border-slate-100 leading-relaxed">
            <Info className="h-3.5 w-3.5 text-slate-400 flex-shrink-0 mt-0.5" aria-hidden="true" />
            <div>
              <strong>Audit Record &amp; Zero Retention Verification:</strong> Document parsed across {analysis.page_count} pages ({analysis.ocr_applied ? `OCR engine: ${analysis.ocr_engine}` : 'direct PDF text streams'}). In compliance with privacy standards, original binary files and unmasked candidate identities were purged immediately after processing.
            </div>
          </div>
        </section>
      )}

      {/* Section 2: Model Feature Contributions & Linguistic Classification (F6) */}
      {mlAnalysis && (
        <section
          aria-labelledby="ml-analysis-heading"
          className="rounded-2xl border border-slate-200 bg-white p-6 sm:p-7 shadow-xs space-y-6"
        >
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-100 pb-4">
            <div>
              <div className="flex items-center gap-2">
                <Sparkles className="h-5 w-5 text-indigo-600" aria-hidden="true" />
                <h2 id="ml-analysis-heading" className="text-lg font-bold text-slate-900">
                  Model Feature Contributions &amp; ML Classification
                </h2>
              </div>
              <p className="text-xs text-slate-500 mt-1">
                {mlAnalysis.model_name || 'JobShield AI Text Fraud Classifier Baseline'} ({mlAnalysis.model_version || 'v1.1.0'}). Evaluates statistical text similarity to historical recruitment scam training data. Kept strictly distinct from composite score.
              </p>
            </div>
            <div className="flex items-center gap-2 flex-wrap self-start sm:self-auto">
              <span className="text-[11px] font-bold uppercase tracking-wider bg-indigo-50 text-indigo-700 border border-indigo-200 px-2.5 py-1 rounded-md">
                {mlAnalysis.score_type === 'log_odds_decision_score' ? 'Log-Odds Additive Model' : 'Platt-Scaled Sigmoid'}
              </span>
              {mlAnalysis.explanation_method && (
                <span className="text-[11px] font-mono text-slate-600 bg-slate-100 border border-slate-200 px-2 py-1 rounded-md">
                  Method: {mlAnalysis.explanation_method}
                </span>
              )}
            </div>
          </div>

          {/* ML Key Probability Metrics Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {/* Metric 1: Calibrated Probability */}
            <div className="rounded-xl border border-slate-200 bg-slate-50/60 p-4 space-y-1.5">
              <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider block">
                Calibrated Scam Probability
              </span>
              <div className="flex items-baseline gap-2">
                <span className="text-2xl font-mono font-extrabold text-slate-900">
                  {mlAnalysis.calibrated_probability !== null && mlAnalysis.calibrated_probability !== undefined
                    ? `${(mlAnalysis.calibrated_probability * 100).toFixed(1)}%`
                    : 'N/A'}
                </span>
                <span className="text-xs text-slate-500 font-mono">
                  (P(fraud|text))
                </span>
              </div>
              {/* Visual meter */}
              <div className="w-full bg-slate-200 h-2 rounded-full overflow-hidden mt-2">
                <div
                  className="bg-indigo-600 h-full rounded-full transition-all"
                  style={{ width: `${Math.min(100, (mlAnalysis.calibrated_probability || 0) * 100)}%` }}
                />
              </div>
            </div>

            {/* Metric 2: Operational Threshold */}
            <div className="rounded-xl border border-slate-200 bg-slate-50/60 p-4 space-y-1.5">
              <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider block">
                Calibrated Decision Threshold
              </span>
              <div className="flex items-baseline gap-2">
                <span className="text-2xl font-mono font-extrabold text-slate-900">
                  {((mlAnalysis.calibrated_threshold || mlAnalysis.decision_threshold || 0.4) * 100).toFixed(1)}%
                </span>
                <span className="text-xs text-slate-500 font-mono">
                  (Validation-tuned)
                </span>
              </div>
              <p className="text-[11px] text-slate-500 leading-tight pt-1">
                Calibrated threshold optimizes F1 on holdout validation data without test leakage.
              </p>
            </div>

            {/* Metric 3: Screening Classification */}
            <div className="rounded-xl border border-slate-200 bg-slate-50/60 p-4 space-y-1.5">
              <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider block">
                Model Classification Pattern
              </span>
              <div className="pt-0.5">
                {mlAnalysis.primary_prediction === 'FRAUDULENT' ? (
                  <span className="inline-flex items-center gap-1.5 text-xs font-bold text-rose-800 bg-rose-100 border border-rose-300 px-2.5 py-1 rounded-md">
                    <ShieldAlert className="h-3.5 w-3.5" aria-hidden="true" />
                    <span>Indicative of Scam Patterns</span>
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1.5 text-xs font-bold text-emerald-800 bg-emerald-100 border border-emerald-300 px-2.5 py-1 rounded-md">
                    <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
                    <span>Consistent with Standard Postings</span>
                  </span>
                )}
              </div>
              <p className="text-[11px] text-slate-500 leading-tight pt-1">
                Primary balanced classifier screening threshold: {((mlAnalysis.primary_threshold || 0.62) * 100).toFixed(1)}%. Target class: {mlAnalysis.target_class || 'FRAUDULENT'}.
              </p>
            </div>
          </div>

          {/* Mathematical Additivity & Score Reconciliation Card */}
          {mlAnalysis.decision_score !== null && mlAnalysis.decision_score !== undefined && (
            <div className="rounded-xl border border-indigo-100 bg-indigo-50/40 p-4.5 space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <Calculator className="h-4 w-4 text-indigo-700" aria-hidden="true" />
                  <span className="text-xs font-bold uppercase tracking-wider text-slate-800">
                    Decision Score Reconciliation (Log-Odds Scale)
                  </span>
                </div>
                {mlAnalysis.is_reconciled && (
                  <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-800 bg-emerald-100/90 border border-emerald-300 px-2.5 py-0.5 rounded-full">
                    <CheckCircle2 className="h-3.5 w-3.5 text-emerald-700" aria-hidden="true" />
                    <span>Exact Log-Odds Additivity Verified: b + Σφ = z</span>
                  </span>
                )}
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                <div className="bg-white/80 rounded-lg p-2.5 border border-indigo-100/80">
                  <span className="text-slate-500 text-[11px] block">Model Intercept (b)</span>
                  <span className="font-mono font-bold text-slate-800 text-sm">
                    {mlAnalysis.intercept !== null && mlAnalysis.intercept !== undefined
                      ? mlAnalysis.intercept.toFixed(4)
                      : 'N/A'}
                  </span>
                </div>
                <div className="bg-white/80 rounded-lg p-2.5 border border-indigo-100/80">
                  <span className="text-slate-500 text-[11px] block">Feature Contributions (Σφ)</span>
                  <span className="font-mono font-bold text-slate-800 text-sm">
                    {mlAnalysis.reconciled_score !== null && mlAnalysis.intercept !== null && mlAnalysis.reconciled_score !== undefined && mlAnalysis.intercept !== undefined
                      ? (mlAnalysis.reconciled_score - mlAnalysis.intercept >= 0 ? '+' : '') +
                        (mlAnalysis.reconciled_score - mlAnalysis.intercept).toFixed(4)
                      : 'N/A'}
                  </span>
                </div>
                <div className="bg-white/80 rounded-lg p-2.5 border border-indigo-100/80">
                  <span className="text-slate-500 text-[11px] block">Reconciled Score (b + Σφ)</span>
                  <span className="font-mono font-bold text-slate-800 text-sm">
                    {mlAnalysis.reconciled_score !== null && mlAnalysis.reconciled_score !== undefined
                      ? mlAnalysis.reconciled_score.toFixed(4)
                      : 'N/A'}
                  </span>
                </div>
                <div className="bg-white/80 rounded-lg p-2.5 border border-indigo-100/80">
                  <span className="text-slate-500 text-[11px] block">Decision Function (z)</span>
                  <span className="font-mono font-bold text-slate-800 text-sm">
                    {mlAnalysis.decision_score.toFixed(4)}
                  </span>
                </div>
              </div>
              <p className="text-[11px] text-slate-500 leading-relaxed">
                Linear decision score <span className="font-mono">z</span> is computed directly as the inner product of model weights and TF-IDF feature values plus intercept: <span className="font-mono">z = w<sup>T</sup>x + b</span>. The complete set of {mlAnalysis.active_feature_count !== undefined && mlAnalysis.active_feature_count !== null ? `${mlAnalysis.active_feature_count} active` : 'all'} vocabulary tokens reconciles with <span className="font-mono">z</span>. Top positive and negative contributors are detailed below.
              </p>
            </div>
          )}

          {/* Explanation Unavailable State (if applicable) */}
          {mlAnalysis.explanation_available === false && (
            <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-xs text-amber-900 space-y-1">
              <div className="flex items-center gap-2 font-bold text-amber-800">
                <AlertTriangle className="h-4 w-4 text-amber-600" aria-hidden="true" />
                <span>Model Feature Explanation Unavailable</span>
              </div>
              <p className="text-amber-700">
                {mlAnalysis.explanation_unavailable_reason ||
                  'Feature contribution explanation is unavailable for this model architecture or input.'}
              </p>
            </div>
          )}

          {/* Feature Contributions Breakdown (Positive and Negative) */}
          {mlAnalysis.explanation_available !== false && (
            <div className="space-y-4 pt-1">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800">
                    Model Feature Contributions (φ = w · x)
                  </h3>
                  <p className="text-[11px] text-slate-500 mt-0.5">
                    Individual vocabulary tokens that increased or decreased the model&apos;s decision score.
                  </p>
                </div>
                <span className="text-[11px] text-slate-400 font-mono">
                  {mlAnalysis.explanation_method || 'linear_coefficients'}
                </span>
              </div>

              {/* Two-Column Feature Contribution Grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Positive Contributions (Increases Fraud Score) */}
                <div className="rounded-xl border border-rose-200 bg-rose-50/40 p-4 space-y-3">
                  <div className="flex items-center justify-between pb-2 border-b border-rose-100">
                    <div className="flex items-center gap-1.5 text-rose-800 font-bold text-xs uppercase tracking-wider">
                      <TrendingUp className="h-4 w-4 text-rose-600" aria-hidden="true" />
                      <span>Positive Feature Contributions</span>
                    </div>
                    <span className="text-[10px] font-semibold text-rose-700 bg-rose-100 px-2 py-0.5 rounded-full">
                      Increases model score
                    </span>
                  </div>

                  {mlAnalysis.top_positive_features && mlAnalysis.top_positive_features.length > 0 ? (
                    <div className="space-y-2">
                      {mlAnalysis.top_positive_features.map((item, idx) => (
                        <div
                          key={`pos-${idx}`}
                          className="bg-white/90 rounded-lg p-2.5 border border-rose-100/90 text-xs flex items-center justify-between gap-2 shadow-2xs"
                        >
                          <div className="min-w-0">
                            <span className="font-mono font-bold text-slate-900 block truncate" title={item.feature}>
                              &quot;{item.feature}&quot;
                            </span>
                            <div className="flex items-center gap-2 text-[10px] text-slate-500 mt-0.5 font-mono">
                              <span>x: {item.feature_value !== undefined ? item.feature_value.toFixed(3) : '0'}</span>
                              <span>&middot;</span>
                              <span>w: {item.coefficient !== undefined ? item.coefficient.toFixed(3) : '0'}</span>
                            </div>
                          </div>
                          <div className="text-right flex-shrink-0">
                            <span className="font-mono font-bold text-rose-700 text-xs block">
                              {item.contribution !== undefined
                                ? `+${item.contribution.toFixed(4)}`
                                : `+${(item.weight || 0).toFixed(4)}`}
                            </span>
                            <span className="text-[9px] uppercase tracking-wider font-semibold text-rose-600">
                              {item.direction_label || 'increases model score'}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-slate-500 italic py-2">
                      No positive scam-indicative tokens detected in this text.
                    </p>
                  )}
                </div>

                {/* Negative Contributions (Decreases Fraud Score) */}
                <div className="rounded-xl border border-emerald-200 bg-emerald-50/40 p-4 space-y-3">
                  <div className="flex items-center justify-between pb-2 border-b border-emerald-100">
                    <div className="flex items-center gap-1.5 text-emerald-800 font-bold text-xs uppercase tracking-wider">
                      <TrendingDown className="h-4 w-4 text-emerald-600" aria-hidden="true" />
                      <span>Negative Feature Contributions</span>
                    </div>
                    <span className="text-[10px] font-semibold text-emerald-700 bg-emerald-100 px-2 py-0.5 rounded-full">
                      Decreases model score
                    </span>
                  </div>

                  {mlAnalysis.top_negative_features && mlAnalysis.top_negative_features.length > 0 ? (
                    <div className="space-y-2">
                      {mlAnalysis.top_negative_features.map((item, idx) => (
                        <div
                          key={`neg-${idx}`}
                          className="bg-white/90 rounded-lg p-2.5 border border-emerald-100/90 text-xs flex items-center justify-between gap-2 shadow-2xs"
                        >
                          <div className="min-w-0">
                            <span className="font-mono font-bold text-slate-900 block truncate" title={item.feature}>
                              &quot;{item.feature}&quot;
                            </span>
                            <div className="flex items-center gap-2 text-[10px] text-slate-500 mt-0.5 font-mono">
                              <span>x: {item.feature_value !== undefined ? item.feature_value.toFixed(3) : '0'}</span>
                              <span>&middot;</span>
                              <span>w: {item.coefficient !== undefined ? item.coefficient.toFixed(3) : '0'}</span>
                            </div>
                          </div>
                          <div className="text-right flex-shrink-0">
                            <span className="font-mono font-bold text-emerald-700 text-xs block">
                              {item.contribution !== undefined ? item.contribution.toFixed(4) : (item.weight || 0).toFixed(4)}
                            </span>
                            <span className="text-[9px] uppercase tracking-wider font-semibold text-emerald-600">
                              {item.direction_label || 'decreases model score'}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-slate-500 italic py-2">
                      No strong legitimate-indicative tokens identified.
                    </p>
                  )}
                </div>
              </div>

              {/* Visual Feature Comparison Chart */}
              <div className="space-y-2 pt-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-slate-700">
                    Top Linguistic Feature Contributions (Weights Chart)
                  </span>
                  <span className="text-[11px] text-slate-400">
                    Red = increases model score, Green = decreases model score
                  </span>
                </div>

                {featureChartData.length > 0 ? (
                  <div className="h-64 min-h-[250px] w-full bg-slate-50/50 p-2 rounded-xl border border-slate-100">
                    <ResponsiveContainer width="100%" height={240} minHeight={200}>
                      <BarChart
                        data={featureChartData}
                        layout="vertical"
                        margin={{ top: 5, right: 30, left: 60, bottom: 5 }}
                      >
                        <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                        <XAxis type="number" tick={{ fontSize: 11 }} domain={['auto', 'auto']} />
                        <YAxis
                          dataKey="name"
                          type="category"
                          tick={{ fontSize: 11, fill: '#334155' }}
                          width={90}
                        />
                        <Tooltip
                          formatter={(val, name, props) => [
                            `${val > 0 ? '+' : ''}${typeof val === 'number' ? val.toFixed(4) : val}`,
                            props.payload.direction === 'fraud_indicative' || props.payload.weight > 0
                              ? 'Increases Model Score (Fraud-Indicative)'
                              : 'Decreases Model Score (Legitimate-Indicative)',
                          ]}
                        />
                        <ReferenceLine x={0} stroke="#94a3b8" />
                        <Bar dataKey="weight" radius={[3, 3, 3, 3]}>
                          {featureChartData.map((entry, index) => (
                            <Cell
                              key={`cell-${index}`}
                              fill={entry.weight > 0 ? '#e11d48' : '#059669'}
                            />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                ) : (
                  <div className="h-32 flex flex-col items-center justify-center rounded-xl border border-dashed border-slate-200 bg-slate-50/50 p-4 text-center">
                    <Info className="h-5 w-5 text-slate-400 mb-1.5" aria-hidden="true" />
                    <span className="text-xs font-semibold text-slate-700">
                      No Discriminating Vocabulary Tokens Detected
                    </span>
                    <p className="text-[11px] text-slate-500 max-w-md mt-0.5">
                      The words in this text do not match any heavily weighted fraud-indicative or legitimate-indicative tokens in the model&apos;s 10,000-term vocabulary. The decision score relies primarily on the baseline model intercept.
                    </p>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Mandatory Non-Intent & Attribution Disclaimer Callout */}
          <div className="rounded-xl bg-indigo-50/70 border border-indigo-100 p-3.5 text-xs text-indigo-950 flex items-start gap-2.5 leading-relaxed">
            <Info className="h-4 w-4 text-indigo-600 flex-shrink-0 mt-0.5" aria-hidden="true" />
            <div className="space-y-1">
              <span className="font-bold text-indigo-900 block">
                Model Feature Attribution &amp; Non-Intent Principle:
              </span>
              <p className="text-indigo-900/90">
                {mlAnalysis.explanation_disclaimer ||
                  'These contributions describe how input features influenced this model\u2019s output. They do not establish intent, prove fraud, or independently verify the authenticity of a job offer.'}
              </p>
              <p className="text-[11px] text-indigo-800/80 pt-0.5">
                {mlAnalysis.disclaimer ||
                  'ML predictions are probabilistic estimates derived from historical text datasets. They do not constitute legal proof of fraud and should be evaluated alongside company verification.'}
              </p>
            </div>
          </div>
        </section>
      )}

      {/* Section 3: Evidence Signals List (Distinguishing Rules from ML) */}
      <section aria-labelledby="evidence-heading" className="space-y-4">
        <div>
          <h2 id="evidence-heading" className="text-lg font-bold text-slate-900 flex items-center gap-2">
            <Shield className="h-5 w-5 text-blue-700" aria-hidden="true" />
            <span>Detected Verification Evidence &amp; Heuristic Signals</span>
          </h2>
          <p className="text-xs text-slate-500 mt-1">
            Deterministic rule heuristics evaluate explicit triggers; ML evaluates statistical vocabulary patterns. Each finding is attributed to its source detector.
          </p>
        </div>

        <div className="space-y-3">
          {analysis.evidence && analysis.evidence.length > 0 ? (
            analysis.evidence.map((item, index) => {
              const isRule = item.evidence_type === 'rule_signal';
              const isML = item.evidence_type === 'ml_prediction';
              const isDetected = item.status === 'DETECTED';

              return (
                <div
                  key={index}
                  className={`rounded-xl border p-4 sm:p-5 transition-all bg-white shadow-2xs ${
                    isDetected
                      ? 'border-amber-200 bg-amber-50/20'
                      : 'border-slate-200'
                  }`}
                >
                  <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-2.5">
                    <div className="space-y-1.5 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        {/* Evidence Type Badge */}
                        <span
                          className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded ${
                            isRule
                              ? 'bg-blue-100 text-blue-800'
                              : isML
                              ? 'bg-indigo-100 text-indigo-800'
                              : 'bg-slate-100 text-slate-800'
                          }`}
                        >
                          {isRule
                            ? 'Rule-Based Heuristic'
                            : isML
                            ? 'Machine Learning Model'
                            : 'Data Quality Check'}
                        </span>

                        {/* Status Badge */}
                        <span
                          className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded flex items-center gap-1 ${
                            isDetected
                              ? 'bg-rose-100 text-rose-800'
                              : item.status === 'NOT_DETECTED'
                              ? 'bg-emerald-100 text-emerald-800'
                              : item.status === 'AMBIGUOUS'
                              ? 'bg-amber-100 text-amber-800 border border-amber-200'
                              : 'bg-slate-100 text-slate-700'
                          }`}
                        >
                          {isDetected && <AlertTriangle className="h-3 w-3" aria-hidden="true" />}
                          {!isDetected && item.status === 'NOT_DETECTED' && (
                            <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
                          )}
                          {item.status === 'AMBIGUOUS' && (
                            <HelpCircle className="h-3 w-3 text-amber-700" aria-hidden="true" />
                          )}
                          <span>{item.status.replace('_', ' ')}</span>
                        </span>

                        {item.details?.is_ambiguous_brand && (
                          <span className="text-[10px] font-semibold bg-amber-50 text-amber-800 border border-amber-200 px-2 py-0.5 rounded">
                            {item.details.brand_candidate_count || item.details.candidate_entities?.length} Candidates Identified
                          </span>
                        )}

                        <span className="font-bold text-sm text-slate-900">
                          {item.source_name}
                        </span>
                      </div>

                      <p className="text-xs sm:text-sm text-slate-700 leading-relaxed pt-0.5">
                        {item.summary}
                      </p>

                      {/* Caveats & Signal Limitations */}
                      {item.limitations && (
                        <p className="text-[11px] text-slate-500 italic pt-1">
                          Caveat: {item.limitations}
                        </p>
                      )}
                    </div>

                    {/* Metadata column */}
                    <div className="text-right flex sm:flex-col items-center sm:items-end justify-between sm:justify-start gap-1 flex-shrink-0 text-[11px] text-slate-400">
                      <span>Observed: {formattedDate}</span>
                      {item.confidence !== null && item.confidence !== undefined && (
                        <span className="font-mono font-medium text-slate-600">
                          Weight: {Math.round(item.confidence * 100)}%
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              );
            })
          ) : (
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-6 text-center text-xs text-slate-500">
              No individual heuristic or ML evidence signals recorded for this scan.
            </div>
          )}
        </div>
      </section>

      {/* Section 4: External Verification Status (Spec Section 4 Placeholders) */}
      <section aria-labelledby="external-checks-heading" className="space-y-4">
        <div>
          <h2 id="external-checks-heading" className="text-lg font-bold text-slate-900">
            External Corroboration &amp; Entity Status
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Text pattern analysis alone does not check legal registration. Official registries corroborate corporate entity status.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Company Verification Card */}
          <div className="rounded-xl border border-slate-200 bg-white p-5 space-y-3.5 shadow-2xs">
            <div className="flex items-center justify-between gap-2 flex-wrap">
              <span className="text-xs font-bold text-slate-700 uppercase tracking-wider flex items-center gap-1.5">
                <Building className="h-4 w-4 text-blue-600" aria-hidden="true" />
                <span>MCA-21 &amp; DPIIT Entity Status</span>
              </span>
              <span
                className={`text-[10px] font-bold px-2.5 py-0.5 rounded-full border ${
                  analysis.company_verification?.status === 'MATCHED'
                    ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                    : analysis.company_verification?.status === 'AMBIGUOUS_MATCH'
                    ? 'bg-amber-50 text-amber-800 border-amber-200'
                    : analysis.company_verification?.status === 'STALE'
                    ? 'bg-amber-50 text-amber-800 border-amber-200'
                    : analysis.company_verification?.status === 'NO_MATCH'
                    ? 'bg-slate-100 text-slate-700 border-slate-200'
                    : analysis.company_verification?.status === 'SOURCE_UNAVAILABLE'
                    ? 'bg-amber-50 text-amber-800 border-amber-200'
                    : 'bg-slate-100 text-slate-700 border-slate-200'
                }`}
              >
                {analysis.company_verification?.status || 'UNKNOWN'}
              </span>
            </div>

            {/* MCA and DPIIT Dual Registry Status Indicators */}
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="rounded-lg bg-slate-50 p-2.5 border border-slate-100">
                <div className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">
                  MCA Registration
                </div>
                <div className="font-semibold text-slate-800 mt-1 flex items-center gap-1.5">
                  <span
                    className={`h-2 w-2 rounded-full ${
                      (analysis.company_verification?.mca_status || '').toUpperCase() === 'ACTIVE' ||
                      (analysis.company_verification?.mca_status || '').toUpperCase() === 'ALLOCATED'
                        ? 'bg-emerald-500'
                        : (analysis.company_verification?.mca_status || '').toUpperCase() === 'AMBIGUOUS'
                        ? 'bg-amber-500'
                        : (analysis.company_verification?.mca_status || '').toUpperCase() === 'NOT_LOADED' ||
                          (analysis.company_verification?.mca_status || '').toUpperCase() === 'SOURCE_UNAVAILABLE'
                        ? 'bg-amber-400'
                        : 'bg-slate-400'
                    }`}
                  />
                  <span>{analysis.company_verification?.mca_status || 'NOT_FOUND'}</span>
                </div>
              </div>

              <div className="rounded-lg bg-slate-50 p-2.5 border border-slate-100">
                <div className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">
                  DPIIT Recognition
                </div>
                <div className="font-semibold text-slate-800 mt-1 flex items-center gap-1.5">
                  <span
                    className={`h-2 w-2 rounded-full ${
                      (analysis.company_verification?.dpiit_status || '').toUpperCase() === 'RECOGNIZED'
                        ? 'bg-emerald-500'
                        : (analysis.company_verification?.dpiit_status || '').toUpperCase() === 'UNVERIFIED'
                        ? 'bg-amber-500'
                        : (analysis.company_verification?.dpiit_status || '').toUpperCase() === 'NOT_LOADED' ||
                          (analysis.company_verification?.dpiit_status || '').toUpperCase() === 'SOURCE_UNAVAILABLE'
                        ? 'bg-amber-400'
                        : 'bg-slate-400'
                    }`}
                  />
                  <span>{analysis.company_verification?.dpiit_status || 'NOT_FOUND'}</span>
                </div>
              </div>
            </div>

            {/* Sourced/Extracted Checked Entity Name */}
            {analysis.company_verification?.queried_name && (
              <div className="rounded-lg bg-slate-50 p-2.5 border border-slate-100 flex items-center justify-between text-xs">
                <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">
                  Checked Entity:
                </span>
                <span className="font-semibold text-slate-900 truncate">
                  {analysis.company_verification.queried_name}
                </span>
              </div>
            )}

            {/* Summary description */}
            <p className="text-xs text-slate-600 leading-relaxed">
              {analysis.company_verification?.summary ||
                'Company legal status requires independent verification via Ministry of Corporate Affairs (MCA-21).'}
            </p>

            {/* SOURCE_UNAVAILABLE Informational Callout */}
            {analysis.company_verification?.status === 'SOURCE_UNAVAILABLE' && (
              <div className="rounded-lg bg-amber-50/70 border border-amber-200 p-2.5 text-xs text-amber-900 flex items-start gap-2">
                <AlertTriangle className="h-4 w-4 text-amber-600 flex-shrink-0 mt-0.5" aria-hidden="true" />
                <div className="space-y-0.5">
                  <span className="font-semibold">Notice: Verification source not loaded.</span>
                  <p className="text-[11px] text-amber-800 leading-normal">
                    The official MCA-21 company registry dataset has not been imported into the database. Entity verification could not be performed against this source snapshot.
                  </p>
                </div>
              </div>
            )}

            {/* NO_MATCH Safe Guidance Callout (Explicit requirement: NO_MATCH is not fraud) */}
            {analysis.company_verification?.status === 'NO_MATCH' && (
              <div className="rounded-lg bg-blue-50/70 border border-blue-200 p-2.5 text-xs text-blue-900 flex items-start gap-2">
                <Info className="h-4 w-4 text-blue-600 flex-shrink-0 mt-0.5" aria-hidden="true" />
                <div className="space-y-0.5">
                  <span className="font-semibold">Notice: NO_MATCH is not a fraud indicator.</span>
                  <p className="text-[11px] text-blue-800 leading-normal">
                    This status indicates no matching record was found in the indexed registry snapshot.
                    Unincorporated employers, sole proprietorships, or new businesses may be legitimate.
                  </p>
                </div>
              </div>
            )}

            {/* AMBIGUOUS_MATCH Disambiguation Callout & Candidates List */}
            {analysis.company_verification?.status === 'AMBIGUOUS_MATCH' && (
              <div className="rounded-lg bg-amber-50/80 border border-amber-200 p-3 text-xs text-amber-950 space-y-3">
                <div className="flex items-start gap-2.5">
                  <AlertTriangle className="h-4 w-4 text-amber-600 flex-shrink-0 mt-0.5" aria-hidden="true" />
                  <div className="space-y-1 flex-1">
                    <div className="flex items-center justify-between flex-wrap gap-1">
                      <span className="font-bold text-amber-900 text-xs">
                        Ambiguous company name ({candidateEntities.length} candidates found)
                      </span>
                      <span className="text-[10px] bg-amber-100 text-amber-800 font-semibold px-2 py-0.5 rounded-full border border-amber-200">
                        Disambiguation Required
                      </span>
                    </div>
                    <p className="text-[11px] text-amber-900/90 leading-relaxed">
                      The brand query <span className="font-semibold">"{analysis.company_verification?.queried_name}"</span> matches multiple distinct registered entities in the official MCA-21 registry with differing corporate statuses. JobShield AI does not automatically select an entity based on Active status, paid-up capital, or entity class.
                    </p>
                    <p className="text-[10px] text-amber-800 italic">
                      Notice: AMBIGUOUS_MATCH is NOT a fraud signal. Risk scoring remains strictly independent of registration status.
                    </p>
                  </div>
                </div>

                {/* Candidate List (Accessible card list for desktop and mobile) */}
                {candidateEntities.length > 0 && (
                  <div className="space-y-2 pt-1 border-t border-amber-200/60">
                    <div className="text-[11px] font-bold text-amber-900 flex items-center justify-between">
                      <span>Candidate Legal Entities ({candidateEntities.length}):</span>
                      <span className="text-[10px] font-normal text-amber-700">Click to verify entity</span>
                    </div>
                    <div className="grid grid-cols-1 gap-2 max-h-72 overflow-y-auto pr-1">
                      {candidateEntities.map((cand, idx) => {
                        const statusUpper = (cand.registry_status || 'UNKNOWN').toUpperCase();
                        const badgeClass =
                          statusUpper === 'ACTIVE'
                            ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                            : statusUpper === 'AMALGAMATED'
                            ? 'bg-blue-50 text-blue-800 border-blue-200'
                            : statusUpper === 'STRIKE OFF' || statusUpper === 'STRUCK OFF'
                            ? 'bg-rose-50 text-rose-800 border-rose-200'
                            : 'bg-slate-100 text-slate-700 border-slate-200';

                        return (
                          <div
                            key={cand.cin || idx}
                            className="bg-white rounded-lg border border-amber-200/80 p-2.5 shadow-2xs hover:border-amber-300 transition-colors flex flex-col sm:flex-row sm:items-center justify-between gap-2"
                          >
                            <div className="space-y-0.5 min-w-0 flex-1">
                              <div className="flex items-center gap-2 flex-wrap">
                                <span className="font-semibold text-slate-900 text-xs truncate block" title={cand.legal_name}>
                                  {cand.legal_name}
                                </span>
                                <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded border uppercase tracking-wider ${badgeClass}`}>
                                  {cand.registry_status || 'Unknown'}
                                </span>
                              </div>
                              <div className="flex items-center gap-3 text-[10px] text-slate-500 font-mono">
                                <span>CIN: {cand.cin || 'N/A'}</span>
                                {cand.entity_type && <span className="font-sans text-slate-400">• {cand.entity_type}</span>}
                              </div>
                            </div>

                            <button
                              type="button"
                              onClick={() => handleReverify(cand.cin || cand.legal_name)}
                              disabled={isReverifying}
                              className="inline-flex items-center justify-center gap-1 px-2.5 py-1 text-[11px] font-semibold text-amber-900 bg-amber-100/70 hover:bg-amber-200/70 border border-amber-300 rounded-md transition-colors flex-shrink-0 disabled:opacity-50 cursor-pointer"
                              title={`Re-verify specifically as ${cand.legal_name}`}
                            >
                              {isReverifying ? <Loader2 className="h-3 w-3 animate-spin" /> : <CheckCircle2 className="h-3 w-3 text-amber-700" />}
                              <span>Verify this Entity</span>
                            </button>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* Manual Exact Legal Name or CIN Input Form */}
                <div className="pt-2 border-t border-amber-200/60 space-y-2">
                  <label htmlFor="reverify-input" className="block text-[11px] font-bold text-amber-900">
                    Enter Exact Legal Name or CIN for New Verification:
                  </label>
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      handleReverify();
                    }}
                    className="flex flex-col sm:flex-row gap-2"
                  >
                    <div className="relative flex-1">
                      <input
                        id="reverify-input"
                        type="text"
                        value={reverifyInput}
                        onChange={(e) => setReverifyInput(e.target.value)}
                        placeholder="e.g. U85110PN1993PLC145950 or Capgemini Technology Services India Limited"
                        disabled={isReverifying}
                        className="w-full text-xs px-3 py-2 rounded-lg border border-amber-300 bg-white placeholder-slate-400 text-slate-900 focus:outline-none focus:ring-2 focus:ring-amber-500 focus:border-amber-500 disabled:bg-slate-50"
                      />
                    </div>
                    <button
                      type="submit"
                      disabled={isReverifying || !reverifyInput.trim()}
                      className="inline-flex items-center justify-center gap-1.5 px-4 py-2 text-xs font-semibold text-white bg-amber-700 hover:bg-amber-800 disabled:bg-slate-300 rounded-lg shadow-2xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-600 flex-shrink-0 cursor-pointer"
                    >
                      {isReverifying ? (
                        <>
                          <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                          <span>Verifying...</span>
                        </>
                      ) : (
                        <>
                          <Building className="h-3.5 w-3.5" aria-hidden="true" />
                          <span>Re-verify</span>
                        </>
                      )}
                    </button>
                  </form>
                  {reverifyError && (
                    <p className="text-[11px] text-rose-700 font-medium">{reverifyError}</p>
                  )}
                  {reverifySuccess && (
                    <p className="text-[11px] text-emerald-700 font-medium flex items-center gap-1">
                      <CheckCircle2 className="h-3 w-3" />
                      <span>{reverifySuccess}</span>
                    </p>
                  )}
                </div>
              </div>
            )}

            {/* Matched Details Metadata */}
            {analysis.company_verification?.status === 'MATCHED' && (
              <div className="rounded-lg bg-slate-50 border border-slate-200 p-3 space-y-2 text-xs">
                <div className="grid grid-cols-2 gap-2 text-[11px]">
                  <div>
                    <span className="text-slate-500 block">Matched Legal Entity</span>
                    <span
                      className="font-medium text-slate-900 truncate block"
                      title={analysis.company_verification.matched_name}
                    >
                      {analysis.company_verification.matched_name}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">CIN / Identifier</span>
                    <span className="font-mono text-slate-800">
                      {analysis.company_verification.cin || 'N/A'}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">Match Method</span>
                    <span className="font-medium text-slate-800">
                      {analysis.company_verification.match_method} (
                      {Math.round((analysis.company_verification.match_confidence || 1.0) * 100)}%)
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">Registry Source</span>
                    <span className="font-medium text-slate-800 truncate block">
                      {analysis.company_verification.source || 'MCA Master Data'}
                    </span>
                  </div>
                </div>

                {analysis.company_verification.dataset_version && (
                  <div className="text-[10px] text-slate-500 pt-1.5 border-t border-slate-200/60 flex items-center justify-between">
                    <span>Snapshot: {analysis.company_verification.dataset_version}</span>
                    {analysis.company_verification.checked_at && (
                      <span>
                        Checked:{' '}
                        {new Date(analysis.company_verification.checked_at).toLocaleDateString()}
                      </span>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* Expandable Company Entity Profile */}
            {analysis.company_verification?.company_id && (
              <div className="pt-1">
                <button
                  type="button"
                  onClick={() =>
                    handleToggleCompanyDetails(analysis.company_verification.company_id)
                  }
                  className="w-full inline-flex items-center justify-between px-3 py-2 text-xs font-semibold text-blue-700 bg-blue-50/70 hover:bg-blue-100/70 border border-blue-200 rounded-lg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600"
                >
                  <span className="flex items-center gap-1.5">
                    <Building className="h-3.5 w-3.5" aria-hidden="true" />
                    <span>View Sourced Registry Profile</span>
                  </span>
                  {isCompanyDetailsOpen ? (
                    <ChevronUp className="h-3.5 w-3.5" aria-hidden="true" />
                  ) : (
                    <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
                  )}
                </button>

                {isCompanyDetailsOpen && (
                  <div className="mt-2.5 rounded-lg border border-slate-200 bg-slate-50/50 p-3 space-y-3 text-xs">
                    {loadingCompany ? (
                      <div className="flex items-center justify-center py-4 gap-2 text-slate-500">
                        <Loader2 className="h-4 w-4 animate-spin" />
                        <span>Loading registry record...</span>
                      </div>
                    ) : companyError ? (
                      <p className="text-xs text-rose-600">{companyError}</p>
                    ) : companyDetails ? (
                      <div className="space-y-2.5">
                        <div className="grid grid-cols-2 gap-2 text-[11px]">
                          <div>
                            <span className="text-slate-400 block font-medium">Entity Type</span>
                            <span className="text-slate-800 font-semibold">
                              {companyDetails.entity_type || 'N/A'}
                            </span>
                          </div>
                          <div>
                            <span className="text-slate-400 block font-medium">Registry Status</span>
                            <span className="text-slate-800 font-semibold">
                              {companyDetails.registry_status || 'N/A'}
                            </span>
                          </div>
                        </div>

                        {companyDetails.source_records?.length > 0 && (
                          <div className="pt-2 border-t border-slate-200">
                            <span className="text-[10px] font-bold uppercase text-slate-500 block mb-1">
                              Source Provenance
                            </span>
                            {companyDetails.source_records.map((sr) => (
                              <div
                                key={sr.id}
                                className="text-[11px] text-slate-600 bg-white p-2 rounded border border-slate-200 mb-1"
                              >
                                <div className="font-semibold text-slate-800">{sr.source_name}</div>
                                {sr.source_url && (
                                  <a
                                    href={sr.source_url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="text-blue-600 underline text-[10px] truncate block"
                                  >
                                    {sr.source_url}
                                  </a>
                                )}
                                <div className="text-[10px] text-slate-500 mt-0.5">
                                  Method: {sr.match_method} (Confidence: {sr.match_confidence})
                                  {sr.source_updated_at &&
                                    ` • Updated: ${new Date(sr.source_updated_at).toLocaleDateString()}`}
                                </div>
                              </div>
                            ))}
                          </div>
                        )}

                        {companyDetails.startup_recognitions?.length > 0 && (
                          <div className="pt-2 border-t border-slate-200">
                            <span className="text-[10px] font-bold uppercase text-slate-500 block mb-1">
                              Startup Recognitions
                            </span>
                            {companyDetails.startup_recognitions.map((rec) => (
                              <div
                                key={rec.id}
                                className="text-[11px] text-slate-600 bg-white p-2 rounded border border-slate-200 mb-1"
                              >
                                <div className="flex justify-between items-center">
                                  <span className="font-semibold text-slate-800">
                                    DPIIT: {rec.recognition_id || 'N/A'}
                                  </span>
                                  <span className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-slate-100 text-slate-700">
                                    {rec.recognition_status}
                                  </span>
                                </div>
                                {rec.status_details && (
                                  <div className="text-[10px] text-slate-500 mt-1">
                                    {rec.status_details.sector && (
                                      <span>Sector: {rec.status_details.sector} • </span>
                                    )}
                                    {rec.status_details.industry && (
                                      <span>Industry: {rec.status_details.industry}</span>
                                    )}
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>
                        )}

                        <div className="text-[10px] text-slate-400 italic pt-1 border-t border-slate-200">
                          {companyDetails.disclaimer}
                        </div>
                      </div>
                    ) : null}
                  </div>
                )}
              </div>
            )}

            {/* Statutory Disclaimer (Explicit requirement) */}
            <div className="rounded bg-slate-50 p-2 text-[10px] text-slate-500 flex items-start gap-1.5 leading-normal border border-slate-100">
              <Info className="h-3 w-3 text-slate-400 flex-shrink-0 mt-0.5" aria-hidden="true" />
              <span>
                MCA registration and DPIIT recognition are separate entity statuses. Neither
                validates a specific vacancy, recruiter identity, or job offer.
              </span>
            </div>
          </div>

          {/* Domain Security & Technical Authentication Card (Feature F3 & F4) */}
          {analysis.domain_check ? (
            <div className="rounded-xl border border-slate-200 bg-white p-5 space-y-3.5 shadow-2xs">
              <div className="flex items-center justify-between gap-2 flex-wrap">
                <span className="text-xs font-bold text-slate-700 uppercase tracking-wider flex items-center gap-1.5">
                  {analysis.email_masked ? (
                    <Mail className="h-4 w-4 text-blue-600" aria-hidden="true" />
                  ) : (
                    <Globe className="h-4 w-4 text-blue-600" aria-hidden="true" />
                  )}
                  <span>
                    {analysis.email_masked
                      ? 'Recruiter Domain Security & Sender Auth'
                      : 'Domain Security & Email Auth'}
                  </span>
                </span>
                <span
                  className={`text-[10px] font-bold px-2.5 py-0.5 rounded-full border ${
                    analysis.domain_check.lookalike_flags?.is_lookalike ||
                    analysis.email_status === 'LOOKALIKE_WARNING' ||
                    analysis.email_status === 'MISMATCH_DETECTED'
                      ? 'bg-rose-50 text-rose-800 border-rose-200'
                      : analysis.is_free_email || analysis.email_status === 'FREE_EMAIL_PROVIDER'
                      ? 'bg-amber-50 text-amber-800 border-amber-200'
                      : analysis.email_status === 'DOMAIN_MATCH' || analysis.domain_check.dns_status === 'PASS'
                      ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                      : 'bg-slate-100 text-slate-700 border-slate-200'
                  }`}
                >
                  {analysis.email_status ||
                    (analysis.domain_check.lookalike_flags?.is_lookalike
                      ? 'LOOKALIKE_WARNING'
                      : `DNS_${analysis.domain_check.dns_status}`)}
                </span>
              </div>

              {/* Target Domain or Sender Details */}
              <div className="rounded-lg bg-slate-50 p-2.5 border border-slate-100 flex items-center justify-between text-xs">
                <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">
                  {analysis.email_masked ? 'Masked Sender Address:' : 'Target Domain:'}
                </span>
                <span className="font-mono font-bold text-slate-900 truncate">
                  {analysis.email_masked
                    ? `${analysis.email_masked} (domain: ${analysis.domain || analysis.domain_check.domain})`
                    : analysis.domain_check.domain}
                </span>
              </div>

              {/* 5-way technical grid: DNS, MX, SPF, DKIM, DMARC */}
              <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 text-xs">
                <div className="rounded-lg bg-slate-50 p-2 border border-slate-100">
                  <span className="text-[10px] font-semibold text-slate-500 uppercase block">DNS Resolution</span>
                  <div className="font-bold text-slate-800 mt-0.5 flex items-center gap-1">
                    <span className={`h-2 w-2 rounded-full ${getDomainStatusDot(analysis.domain_check.dns_status)}`} />
                    <span>{analysis.domain_check.dns_status}</span>
                  </div>
                </div>

                <div className="rounded-lg bg-slate-50 p-2 border border-slate-100">
                  <span className="text-[10px] font-semibold text-slate-500 uppercase block">MX Mail Route</span>
                  <div className="font-bold text-slate-800 mt-0.5 flex items-center gap-1">
                    <span className={`h-2 w-2 rounded-full ${getDomainStatusDot(analysis.domain_check.mx_status)}`} />
                    <span>{analysis.domain_check.mx_status}</span>
                  </div>
                </div>

                <div className="rounded-lg bg-slate-50 p-2 border border-slate-100">
                  <span className="text-[10px] font-semibold text-slate-500 uppercase block">SPF Record</span>
                  <div className="font-bold text-slate-800 mt-0.5 flex items-center gap-1">
                    <span className={`h-2 w-2 rounded-full ${getDomainStatusDot(analysis.domain_check.spf_status)}`} />
                    <span>{analysis.domain_check.spf_status}</span>
                  </div>
                </div>

                <div className="rounded-lg bg-slate-50 p-2 border border-slate-100">
                  <span className="text-[10px] font-semibold text-slate-500 uppercase block">DKIM Selector</span>
                  <div className="font-bold text-slate-800 mt-0.5 flex items-center gap-1">
                    <span className={`h-2 w-2 rounded-full ${getDomainStatusDot(analysis.domain_check.dkim_status)}`} />
                    <span>{analysis.domain_check.dkim_status || 'UNKNOWN'}</span>
                  </div>
                </div>

                <div className="rounded-lg bg-slate-50 p-2 border border-slate-100">
                  <span className="text-[10px] font-semibold text-slate-500 uppercase block">DMARC Policy</span>
                  <div className="font-bold text-slate-800 mt-0.5 flex items-center gap-1">
                    <span className={`h-2 w-2 rounded-full ${getDomainStatusDot(analysis.domain_check.dmarc_status)}`} />
                    <span>{analysis.domain_check.source_details?.dmarc_policy || analysis.domain_check.dmarc_status}</span>
                  </div>
                </div>
              </div>

              {/* Lookalike Warning Banner */}
              {analysis.domain_check.lookalike_flags?.is_lookalike && (
                <div className="rounded-lg bg-rose-50 border border-rose-200 p-3 text-xs text-rose-950 space-y-1.5">
                  <div className="flex items-center gap-2 text-rose-800 font-bold">
                    <AlertTriangle className="h-4 w-4 flex-shrink-0" aria-hidden="true" />
                    <span>Lookalike Domain / Typosquatting Warning</span>
                  </div>
                  <p className="text-[11px] leading-relaxed text-rose-900">
                    {analysis.domain_check.lookalike_flags.warning}
                  </p>
                  <div className="text-[10px] font-medium text-rose-700 bg-white/80 p-2 rounded border border-rose-200 grid grid-cols-2 gap-1 font-mono">
                    <div>Mimicked Domain: <span className="font-bold">{analysis.domain_check.lookalike_flags.matched_legitimate_domain}</span></div>
                    <div>Detection Type: <span>{analysis.domain_check.lookalike_flags.similarity_type}</span></div>
                  </div>
                </div>
              )}

              {/* Free Email Alert */}
              {analysis.is_free_email && (
                <div className="rounded-lg bg-amber-50 border border-amber-200 p-3 text-xs text-amber-950 space-y-1">
                  <div className="flex items-center gap-2 text-amber-800 font-bold">
                    <AlertTriangle className="h-4 w-4 flex-shrink-0" aria-hidden="true" />
                    <span>Public Free Webmail Provider Detected</span>
                  </div>
                  <p className="text-[11px] leading-relaxed text-amber-900">
                    The sender address uses a free public email provider (@{analysis.domain || analysis.domain_check.domain}). Legitimate corporate recruiters typically contact candidates from an authenticated company domain rather than free personal email services.
                  </p>
                </div>
              )}

              {/* Domain Mismatch Alert */}
              {analysis.email_status === 'MISMATCH_DETECTED' && (
                <div className="rounded-lg bg-rose-50 border border-rose-200 p-3 text-xs text-rose-950 space-y-1">
                  <div className="flex items-center gap-2 text-rose-800 font-bold">
                    <AlertTriangle className="h-4 w-4 flex-shrink-0" aria-hidden="true" />
                    <span>Sender Domain &amp; Claimed Employer Mismatch</span>
                  </div>
                  <p className="text-[11px] leading-relaxed text-rose-900">
                    The recruiter's sender domain '{analysis.domain || analysis.domain_check.domain}' does not align with the claimed employer's verified corporate domain.
                  </p>
                </div>
              )}

              {/* Summary & Limitations */}
              <p className="text-xs text-slate-600 leading-relaxed">
                {analysis.domain_check.summary}
              </p>

              {/* Extracted Contact Addresses */}
              {analysis.recruiter_checks?.detected_emails?.length > 0 && (
                <div className="pt-1.5 border-t border-slate-100 text-xs">
                  <span className="text-slate-500 block font-medium">Extracted contact emails:</span>
                  <span className="font-mono text-slate-800">
                    {analysis.recruiter_checks.detected_emails.join(', ')}
                  </span>
                </div>
              )}

              {/* Limitations Notice */}
              <div className="rounded bg-slate-50 p-2 text-[10px] text-slate-500 flex items-start gap-1.5 leading-normal border border-slate-100">
                <Info className="h-3 w-3 text-slate-400 flex-shrink-0 mt-0.5" aria-hidden="true" />
                <span>
                  {analysis.domain_check.limitations ||
                    'Domain authentication parameters evaluate sender delivery infrastructure; they do not prove individual vacancy authorization.'}
                </span>
              </div>

              {/* Statutory Non-Probing & Identity Disclaimer */}
              {analysis.email_masked && (
                <div className="rounded bg-blue-50/70 p-2.5 text-[11px] text-blue-900 flex items-start gap-2 border border-blue-200">
                  <Info className="h-4 w-4 text-blue-700 flex-shrink-0 mt-0.5" aria-hidden="true" />
                  <div className="space-y-0.5">
                    <span className="font-bold">Sender Identity &amp; Non-Probing Notice:</span>
                    <p className="text-[10px] text-blue-800 leading-normal">
                      A domain match indicates infrastructure alignment only; it does NOT definitively prove the sender's individual identity, as headers can be spoofed or corporate accounts compromised. Mailbox existence is never probed.
                    </p>
                  </div>
                </div>
              )}
            </div>
          ) : analysis.extracted_fields ? (
            /* Offer Letter Corroboration Companion Card */
            <div className="rounded-xl border border-slate-200 bg-white p-5 space-y-3.5 shadow-2xs">
              <div className="flex items-center justify-between gap-2 flex-wrap">
                <span className="text-xs font-bold text-slate-700 uppercase tracking-wider flex items-center gap-1.5">
                  <FileText className="h-4 w-4 text-blue-600" aria-hidden="true" />
                  <span>Document Authentication &amp; MCA Corroboration</span>
                </span>
                <span
                  className={`text-[10px] font-bold px-2.5 py-0.5 rounded-full border ${
                    analysis.extracted_fields.has_fee_demand || analysis.extracted_fields.has_sensitive_request
                      ? 'bg-rose-50 text-rose-800 border-rose-200'
                      : analysis.company_verification?.status === 'MATCHED'
                      ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                      : 'bg-slate-100 text-slate-700 border-slate-200'
                  }`}
                >
                  {analysis.extracted_fields.has_fee_demand
                    ? 'FEE DEMAND ALERT'
                    : analysis.company_verification?.status === 'MATCHED'
                    ? 'MCA CORROBORATED'
                    : 'DOCUMENT AUDITED'}
                </span>
              </div>

              <div className="space-y-1.5 text-xs text-slate-600 leading-relaxed">
                <p>
                  <strong>Extracted Employer:</strong> {analysis.extracted_fields.company_name?.value || 'Not extracted'}
                </p>
                <p>
                  <strong>MCA Corroboration:</strong> {analysis.company_verification?.status === 'MATCHED'
                    ? 'Employer name matches an active registered company in the MCA-21 database.'
                    : 'No unambiguous active company registration confirmed in MCA-21 database.'}
                </p>
                <p className="text-[11px] text-slate-500 italic">
                  Note: A registered MCA entity confirms legitimate incorporation, but does NOT certify that this specific offer letter was authorized by the company.
                </p>
              </div>
            </div>
          ) : (
            /* Recruiter Email Checks Card (Fallback when domain_check is not present) */
            <div className="rounded-xl border border-slate-200 bg-white p-5 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-slate-500 uppercase tracking-wider flex items-center gap-1.5">
                  <Mail className="h-4 w-4 text-slate-400" aria-hidden="true" />
                  <span>Recruiter Domain Checks</span>
                </span>
                <span
                  className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                    analysis.recruiter_checks?.free_email_detected
                      ? 'bg-rose-100 text-rose-800'
                      : 'bg-slate-100 text-slate-700'
                  }`}
                >
                  {analysis.recruiter_checks?.status || 'TEXT_EXTRACTED_ONLY'}
                </span>
              </div>
              <p className="text-sm font-semibold text-slate-900">Sender Domain Authentication</p>
              <p className="text-xs text-slate-600 leading-relaxed">
                {analysis.recruiter_checks?.summary ||
                  'Emails extracted from text must be checked against legitimate employer DNS records.'}
              </p>
              {analysis.recruiter_checks?.detected_emails?.length > 0 && (
                <div className="pt-1 text-xs">
                  <span className="text-slate-400 block font-medium">Extracted addresses:</span>
                  <span className="font-mono text-slate-800">
                    {analysis.recruiter_checks.detected_emails.join(', ')}
                  </span>
                </div>
              )}
            </div>
          )}
        </div>
      </section>

      {/* Section: Duplicate Posting & Impersonation Analysis (Feature F5) */}
      {analysis.duplicate_analysis && (
        <section
          aria-labelledby="duplicate-analysis-heading"
          className="rounded-2xl border border-slate-200 bg-white p-6 sm:p-7 shadow-xs space-y-4"
        >
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-100 pb-3">
            <div>
              <div className="flex items-center gap-2">
                <Copy className="h-5 w-5 text-indigo-600" aria-hidden="true" />
                <h2 id="duplicate-analysis-heading" className="text-base sm:text-lg font-bold text-slate-900">
                  Duplicate Posting &amp; Impersonation Detection (Feature F5)
                </h2>
              </div>
              <p className="text-xs text-slate-500 mt-0.5">
                Evaluates exact content hashes and TF-IDF cosine similarity to identify reposts, job board syndications, and suspicious copycat listings.
              </p>
            </div>
            <span
              className={`text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-md border self-start sm:self-auto ${
                analysis.duplicate_analysis.status === 'POTENTIAL_SUSPICIOUS_COPY'
                  ? 'bg-rose-50 text-rose-800 border-rose-200'
                  : analysis.duplicate_analysis.status === 'EXACT_DUPLICATE'
                  ? 'bg-indigo-50 text-indigo-800 border-indigo-200'
                  : analysis.duplicate_analysis.status === 'LIKELY_REPOST'
                  ? 'bg-blue-50 text-blue-800 border-blue-200'
                  : analysis.duplicate_analysis.status === 'NEAR_DUPLICATE'
                  ? 'bg-cyan-50 text-cyan-800 border-cyan-200'
                  : analysis.duplicate_analysis.status === 'UNIQUE_LISTING'
                  ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                  : 'bg-slate-100 text-slate-700 border-slate-200'
              }`}
            >
              {analysis.duplicate_analysis.status}
            </span>
          </div>

          {/* Impersonation Warning Banner if applicable */}
          {analysis.duplicate_analysis.impersonation_warning && (
            <div className="rounded-xl border border-rose-200 bg-rose-50 p-3.5 text-xs text-rose-950 flex items-start gap-2.5">
              <AlertTriangle className="h-4 w-4 text-rose-600 flex-shrink-0 mt-0.5" aria-hidden="true" />
              <div className="space-y-1">
                <span className="font-bold text-rose-900">Suspicious Impersonation Signal:</span>
                <p className="text-[11px] leading-relaxed text-rose-900">
                  {analysis.duplicate_analysis.impersonation_warning}
                </p>
                <p className="text-[10px] text-rose-700 italic">
                  Notice: Copied text is an impersonation signal requiring review, not conclusive proof of criminal intent.
                </p>
              </div>
            </div>
          )}

          {/* Summary */}
          <p className="text-xs text-slate-600 leading-relaxed">
            {analysis.duplicate_analysis.summary}
          </p>

          {/* Matching Listings List */}
          {analysis.duplicate_analysis.top_matches && analysis.duplicate_analysis.top_matches.length > 0 && (
            <div className="space-y-2.5 pt-2 border-t border-slate-100">
              <span className="text-xs font-bold text-slate-700 block">
                Matching &amp; Near-Duplicate Listings ({analysis.duplicate_analysis.total_matches_found}):
              </span>
              <div className="grid grid-cols-1 gap-2.5">
                {analysis.duplicate_analysis.top_matches.map((match, idx) => (
                  <div
                    key={match.match_id || idx}
                    className="rounded-xl border border-slate-200 bg-slate-50/60 p-3.5 space-y-2 text-xs"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="font-semibold text-slate-900">
                        {match.matched_title || 'Untitled Vacancy'} —{' '}
                        <span className="text-slate-600">{match.matched_company_name || 'Unspecified Employer'}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] font-mono font-bold bg-white px-2 py-0.5 rounded border border-slate-200">
                          {Math.round(match.similarity_score * 100)}% Similarity
                        </span>
                        <span className="text-[10px] font-semibold text-slate-500">
                          ({Math.round(match.confidence * 100)}% conf.)
                        </span>
                      </div>
                    </div>

                    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-slate-500">
                      {match.matched_domain && (
                        <span>
                          <strong>Domain:</strong> <span className="font-mono text-slate-700">{match.matched_domain}</span>
                        </span>
                      )}
                      {match.matched_source_url && (
                        <a
                          href={match.matched_source_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-blue-600 underline inline-flex items-center gap-0.5 max-w-xs truncate"
                        >
                          <span className="truncate">{match.matched_source_url}</span>
                          <ExternalLink className="h-2.5 w-2.5 flex-shrink-0" />
                        </a>
                      )}
                      {match.matched_collected_at && (
                        <span>
                          <strong>Observed:</strong> {new Date(match.matched_collected_at).toLocaleDateString()}
                        </span>
                      )}
                    </div>

                    {match.reasons && match.reasons.length > 0 && (
                      <ul className="text-[11px] text-slate-600 list-disc list-inside space-y-0.5 bg-white p-2.5 rounded border border-slate-100">
                        {match.reasons.map((r, rIdx) => (
                          <li key={rIdx}>{r}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Limitations notice */}
          <div className="rounded bg-slate-50 p-2 text-[10px] text-slate-500 flex items-start gap-1.5 leading-normal border border-slate-100">
            <Info className="h-3 w-3 text-slate-400 flex-shrink-0 mt-0.5" aria-hidden="true" />
            <span>{analysis.duplicate_analysis.limitations}</span>
          </div>
        </section>
      )}

      {/* Section: Community Feedback & Recruiter Reputation (Features F8 & F9) */}
      <section
        aria-labelledby="community-reputation-heading"
        className="rounded-2xl border border-slate-200 bg-white p-6 sm:p-7 shadow-xs space-y-4"
      >
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-100 pb-3">
          <div>
            <div className="flex items-center gap-2">
              <Users className="h-5 w-5 text-amber-600" aria-hidden="true" />
              <h2 id="community-reputation-heading" className="text-base sm:text-lg font-bold text-slate-900">
                Community Feedback &amp; Recruiter Reputation (Features F8 &amp; F9)
              </h2>
            </div>
            <p className="text-xs text-slate-500 mt-0.5">
              Bayesian-adjusted service experience ratings, verified candidate feedback, and separate fraud reports.
            </p>
          </div>
        </div>

        <CompanyReputationCard
          companyId={analysis.company_verification?.company_id}
          companyName={analysis.company_verification?.legal_name || analysis.company_name || claimedCompany}
          recruiterEmail={analysis.recruiter_email || analysis.email_masked}
          scanId={analysis.report_id || analysis.id}
        />
      </section>

      {/* Section 5: Recommended Safe Actions for Job Seekers */}
      {analysis.recommended_safe_actions && analysis.recommended_safe_actions.length > 0 && (
        <section
          aria-labelledby="safe-actions-heading"
          className="rounded-2xl border border-emerald-200 bg-emerald-50/70 p-6 sm:p-7 space-y-4"
        >
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-5 w-5 text-emerald-700 flex-shrink-0" aria-hidden="true" />
            <h2 id="safe-actions-heading" className="text-base sm:text-lg font-bold text-emerald-950">
              Recommended Safe Actions for Job Seekers
            </h2>
          </div>

          <ul className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs sm:text-sm text-emerald-950 leading-relaxed">
            {analysis.recommended_safe_actions.map((action, i) => (
              <li key={i} className="flex items-start gap-2.5 bg-white/70 p-3 rounded-xl border border-emerald-200/60 shadow-2xs">
                <span className="text-emerald-700 font-extrabold mt-0.5">•</span>
                <span>{action}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Section 6: Limitations & Disclaimer */}
      <section aria-labelledby="limitations-heading" className="rounded-2xl border border-slate-200 bg-slate-50 p-6 space-y-4 text-xs text-slate-600">
        <div>
          <h2 id="limitations-heading" className="text-sm font-bold text-slate-800 uppercase tracking-wider">
            Analysis Boundaries &amp; Limitations
          </h2>
          <p className="text-slate-500 mt-0.5">
            Review these technical and operational boundaries when interpreting results.
          </p>
        </div>

        <ul className="space-y-1.5 list-disc list-inside leading-relaxed text-slate-600">
          {analysis.limitations?.map((limit, i) => (
            <li key={i}>{limit}</li>
          ))}
        </ul>

        {/* Legal Disclaimer */}
        <div className="pt-3 border-t border-slate-200 text-[11px] text-slate-500 leading-normal">
          <p>
            <strong>Informational Notice:</strong> {analysis.disclaimer}
          </p>
        </div>
      </section>
    </div>
  );
}

export default Results;
