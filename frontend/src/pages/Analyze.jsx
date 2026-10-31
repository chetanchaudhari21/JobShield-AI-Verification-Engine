import React, { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  FileText,
  Globe,
  Mail,
  Upload,
  Sparkles,
  Info,
  Loader2,
  Lock,
  File,
  X,
} from 'lucide-react';
import { api } from '../services/api';
import { ErrorState } from '../components/ErrorState';

export function Analyze() {
  const navigate = useNavigate();
  const location = useLocation();
  const [activeTab, setActiveTab] = useState(location.state?.activeTab || 'job-text');

  // Form State
  const [companyName, setCompanyName] = useState('');
  const [cin, setCin] = useState('');
  const [jobTitle, setJobTitle] = useState('');
  const [jobDescription, setJobDescription] = useState('');

  // UI States
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState(null);

  // Job URL Form State (Feature F3)
  const [jobUrl, setJobUrl] = useState('');
  const [urlCompanyName, setUrlCompanyName] = useState('');
  const [urlCin, setUrlCin] = useState('');
  const [isSubmittingUrl, setIsSubmittingUrl] = useState(false);
  const [submitUrlError, setSubmitUrlError] = useState(null);

  // Recruiter Email Form State (Feature F4)
  const [recruiterEmail, setRecruiterEmail] = useState('');
  const [recruiterCompanyName, setRecruiterCompanyName] = useState('');
  const [recruiterCin, setRecruiterCin] = useState('');
  const [recruiterMessage, setRecruiterMessage] = useState('');
  const [isSubmittingEmail, setIsSubmittingEmail] = useState(false);
  const [submitEmailError, setSubmitEmailError] = useState(null);

  // Offer Letter Form State (Feature F7)
  const [offerFile, setOfferFile] = useState(null);
  const [offerCompanyName, setOfferCompanyName] = useState('');
  const [offerCin, setOfferCin] = useState('');
  const [isSubmittingOffer, setIsSubmittingOffer] = useState(false);
  const [submitOfferError, setSubmitOfferError] = useState(null);
  const [dragOver, setDragOver] = useState(false);

  const sampleSuspiciousJobText = `Position: Remote Customer Operations Specialist
Company: Acme Dynamic Cloud Solutions
Location: Remote (Global)
Salary: $5,000 weekly payout
Experience: Freshers welcome, no experience needed!

Job Description:
Immediate joining today! We are hiring for data entry and customer support operations.
A company laptop and home office setup will be dispatched upon completion of onboarding.

Requirements:
- Strong typing communication skills.
- Must possess a valid national ID card.
- To secure your laptop equipment and complete background verification, candidates must pay an upfront refundable security deposit of $150 prior to shipping hardware.

Contact HR manager immediately on WhatsApp: +1 555-019-2834.
Send your resume to hr.hiring.fast@gmail.com for instant interview onboarding.`;

  const sampleStandardJobText = `Position: Senior Backend Engineer (Python / FastAPI)
Company: Nexa Enterprise Systems Ltd.
Location: London, UK (Hybrid)
Salary: £85,000 - £100,000 per annum + pension

About the Role:
We are looking for an experienced Backend Engineer to scale our distributed cloud architecture.
You will collaborate with cross-functional teams to design high-throughput RESTful APIs,
maintain PostgreSQL database schemas, and deploy containerized services on Kubernetes.

Requirements:
- 5+ years of software development experience with Python.
- Deep familiarity with FastAPI, SQLAlchemy, and automated test frameworks.
- Solid understanding of asynchronous programming and database indexing.
- Bachelor's degree in Computer Science or equivalent practical experience.

Benefits:
- Competitive salary and comprehensive private medical insurance.
- 28 days paid annual leave and flexible hybrid working arrangements.
- Tuition fee reimbursement for continuous professional certifications.

How to Apply:
Submit your CV through our official careers portal at https://careers.nexaenterprise.example.com.`;

  function handleLoadSuspiciousSample() {
    setCompanyName('Acme Dynamic Cloud Solutions');
    setCin('');
    setJobTitle('Remote Customer Operations Specialist');
    setJobDescription(sampleSuspiciousJobText);
    setSubmitError(null);
  }

  function handleLoadStandardSample() {
    setCompanyName('Nexa Enterprise Systems Ltd.');
    setCin('');
    setJobTitle('Senior Backend Engineer');
    setJobDescription(sampleStandardJobText);
    setSubmitError(null);
  }

  function handleClear() {
    setCompanyName('');
    setCin('');
    setJobTitle('');
    setJobDescription('');
    setSubmitError(null);
  }

  function handleLoadLegitUrlSample() {
    setJobUrl('https://careers.infosys.com/job/lead-java-architect');
    setUrlCompanyName('Infosys Limited');
    setUrlCin('L85110KA1981PLC013115');
    setSubmitUrlError(null);
  }

  function handleLoadSuspiciousUrlSample() {
    setJobUrl('https://inf0sys-careers.com/apply/urgent-hiring');
    setUrlCompanyName('Infosys');
    setUrlCin('');
    setSubmitUrlError(null);
  }

  function handleClearUrl() {
    setJobUrl('');
    setUrlCompanyName('');
    setUrlCin('');
    setSubmitUrlError(null);
  }

  async function handleSubmitUrl(e) {
    if (e && e.preventDefault) e.preventDefault();
    if (isSubmittingUrl) return;

    const trimmedUrl = jobUrl.trim();
    if (!trimmedUrl) {
      setSubmitUrlError('Please enter a valid job posting URL (e.g., https://example.com/careers/job-123).');
      return;
    }

    if (!trimmedUrl.startsWith('http://') && !trimmedUrl.startsWith('https://')) {
      setSubmitUrlError('Job URL must begin with http:// or https://');
      return;
    }

    setIsSubmittingUrl(true);
    setSubmitUrlError(null);

    try {
      const result = await api.analyzeJobUrl({
        url: trimmedUrl,
        company_name: urlCompanyName.trim() || undefined,
        cin: urlCin.trim() || undefined,
      });

      navigate('/results', {
        state: {
          analysisResult: result,
          jobUrl: trimmedUrl,
          jobText: '',
          claimedCompany: urlCompanyName.trim() || result.extracted_company || result.company_verification?.queried_name || '',
          claimedCin: urlCin.trim() || result.company_verification?.cin || '',
          jobTitle: result.extracted_title || '',
        },
      });
    } catch (err) {
      if (err.isTimeout || err.status === 504) {
        setSubmitUrlError(
          'Request timed out while connecting to or analyzing the job URL. The remote website or its DNS servers may be slow to respond. You can retry now, or copy and paste the job text into the Job Text tab.'
        );
      } else if (err.status === 502) {
        setSubmitUrlError(
          `Unable to reach destination host (${err.message}). The remote web server may be offline or unreachable. Please verify the URL or paste the job text directly.`
        );
      } else if (err.status === 413) {
        setSubmitUrlError(
          'The target webpage size exceeds the maximum allowed limit (1 MB). Please copy and paste the job text directly into the Job Text tab.'
        );
      } else {
        setSubmitUrlError(err.message || 'Failed to analyze job posting URL. Please verify the address and try again.');
      }
    } finally {
      setIsSubmittingUrl(false);
    }
  }

  function handleLoadLegitEmailSample() {
    setRecruiterEmail('careers@tcs.com');
    setRecruiterCompanyName('Tata Consultancy Services Limited');
    setRecruiterCin('L22210MH1995PLC084781');
    setRecruiterMessage(
      'Dear Candidate,\n\nWe have reviewed your application for the Senior Systems Engineer position at Tata Consultancy Services. Please find attached the interview schedule details and technical assessment link.\n\nWarm regards,\nTalent Acquisition Team\nTata Consultancy Services'
    );
    setSubmitEmailError(null);
  }

  function handleLoadFreeWebmailSample() {
    setRecruiterEmail('infosys.hr.recruitment@gmail.com');
    setRecruiterCompanyName('Infosys Limited');
    setRecruiterCin('L85110KA1981PLC013115');
    setRecruiterMessage(
      'Congratulations! You have been selected for immediate remote onboarding at Infosys. To reserve your hardware laptop and complete security clearance, deposit a refundable registration fee of $150 via Western Union or Google Pay within 24 hours.'
    );
    setSubmitEmailError(null);
  }

  function handleLoadLookalikeEmailSample() {
    setRecruiterEmail('recruiting@inf0sys-careers.com');
    setRecruiterCompanyName('Infosys Limited');
    setRecruiterCin('L85110KA1981PLC013115');
    setRecruiterMessage(
      'Urgent opening for remote data entry and operations executive. Immediate interview. Send your passport copy and bank account details for instant appointment letter generation.'
    );
    setSubmitEmailError(null);
  }

  function handleClearEmail() {
    setRecruiterEmail('');
    setRecruiterCompanyName('');
    setRecruiterCin('');
    setRecruiterMessage('');
    setSubmitEmailError(null);
  }

  async function handleSubmitEmail(e) {
    if (e && e.preventDefault) e.preventDefault();
    if (isSubmittingEmail) return;

    const trimmedEmail = recruiterEmail.trim();
    if (!trimmedEmail) {
      setSubmitEmailError('Please enter a recruiter or sender email address to analyze.');
      return;
    }

    if (!trimmedEmail.includes('@') || trimmedEmail.startsWith('@') || trimmedEmail.endsWith('@')) {
      setSubmitEmailError('Please enter a valid email address (e.g., recruiter@company.com).');
      return;
    }

    setIsSubmittingEmail(true);
    setSubmitEmailError(null);

    try {
      const result = await api.analyzeRecruiterEmail({
        email: trimmedEmail,
        company_name: recruiterCompanyName.trim() || undefined,
        cin: recruiterCin.trim() || undefined,
        message_text: recruiterMessage.trim() || undefined,
      });

      navigate('/results', {
        state: {
          analysisResult: result,
          jobText: recruiterMessage.trim(),
          claimedCompany:
            recruiterCompanyName.trim() ||
            result.extracted_company ||
            result.company_verification?.queried_name ||
            '',
          claimedCin: recruiterCin.trim() || result.company_verification?.cin || '',
          jobTitle: result.extracted_title || '',
          recruiterEmail: result.email_masked,
        },
      });
    } catch (err) {
      if (err.isTimeout || err.status === 504) {
        setSubmitEmailError(
          'Request timed out while checking recruiter domain DNS/MX/SPF records. DNS servers may be slow to respond. Please try again.'
        );
      } else {
        setSubmitEmailError(
          err.message || 'Failed to analyze recruiter email. Please verify the address and try again.'
        );
      }
    } finally {
      setIsSubmittingEmail(false);
    }
  }

  function handleOfferFileChange(e) {
    const file = e.target.files?.[0];
    if (file) {
      if (file.type && file.type !== 'application/pdf' && !file.name.toLowerCase().endsWith('.pdf')) {
        setSubmitOfferError('Please select a valid PDF document (.pdf). Other file formats are not supported.');
        setOfferFile(null);
        return;
      }
      if (file.size > 10 * 1024 * 1024) {
        setSubmitOfferError('File exceeds maximum allowed upload size of 10 MB. Please provide a smaller document.');
        setOfferFile(null);
        return;
      }
      setOfferFile(file);
      setSubmitOfferError(null);
    }
  }

  function handleOfferDrop(e) {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer?.files?.[0];
    if (file) {
      if (file.type && file.type !== 'application/pdf' && !file.name.toLowerCase().endsWith('.pdf')) {
        setSubmitOfferError('Please select a valid PDF document (.pdf). Other file formats are not supported.');
        setOfferFile(null);
        return;
      }
      if (file.size > 10 * 1024 * 1024) {
        setSubmitOfferError('File exceeds maximum allowed upload size of 10 MB. Please provide a smaller document.');
        setOfferFile(null);
        return;
      }
      setOfferFile(file);
      setSubmitOfferError(null);
    }
  }

  function handleClearOffer() {
    setOfferFile(null);
    setOfferCompanyName('');
    setOfferCin('');
    setSubmitOfferError(null);
  }

  async function handleSubmitOffer(e) {
    if (e && e.preventDefault) e.preventDefault();
    if (isSubmittingOffer) return;

    if (!offerFile) {
      setSubmitOfferError('Please upload or drag-and-drop an offer letter PDF file to begin analysis.');
      return;
    }

    setIsSubmittingOffer(true);
    setSubmitOfferError(null);

    try {
      const result = await api.analyzeOfferLetter(
        offerFile,
        offerCompanyName.trim() || undefined,
        offerCin.trim() || undefined
      );

      navigate('/results', {
        state: {
          analysisResult: result,
          jobText: '',
          claimedCompany:
            offerCompanyName.trim() ||
            result.extracted_fields?.company_name?.value ||
            result.company_verification?.queried_name ||
            '',
          claimedCin: offerCin.trim() || result.company_verification?.cin || '',
          jobTitle: result.extracted_fields?.job_title?.value || '',
          fileName: result.file_name,
        },
      });
    } catch (err) {
      if (err.isTimeout || err.status === 504) {
        setSubmitOfferError(
          'Analysis timed out while processing document or performing OCR. The document may be large or complex. You can retry with a shorter excerpt or text-based document.'
        );
      } else if (err.status === 413) {
        setSubmitOfferError(
          'Document exceeds the maximum permitted size limit of 10 MB. Please upload a smaller PDF.'
        );
      } else {
        setSubmitOfferError(
          err.message || 'Failed to analyze offer letter. Please verify the document format and try again.'
        );
      }
    } finally {
      setIsSubmittingOffer(false);
    }
  }

  async function handleSubmit(e) {
    if (e && e.preventDefault) e.preventDefault();
    if (isSubmitting) return;

    let fullText = jobDescription.trim();
    if (!fullText) {
      setSubmitError('Please paste or enter the job description text to begin analysis.');
      return;
    }

    // Prepend job title, claimed company, or CIN if provided so model and rules see full context
    const headerLines = [];
    if (jobTitle.trim()) headerLines.push(`Title: ${jobTitle.trim()}`);
    if (companyName.trim()) headerLines.push(`Company: ${companyName.trim()}`);
    if (cin.trim()) headerLines.push(`CIN: ${cin.trim()}`);
    if (headerLines.length > 0) {
      fullText = `${headerLines.join('\n')}\n\n${fullText}`;
    }

    if (fullText.length < 20) {
      setSubmitError('Job text is too short to analyze (minimum 20 characters required).');
      return;
    }

    if (fullText.length > 50000) {
      setSubmitError('Job text exceeds maximum allowed size (maximum 50,000 characters).');
      return;
    }

    setIsSubmitting(true);
    setSubmitError(null);

    try {
      const result = await api.analyzeJobText({
        text: fullText,
        company_name: companyName.trim() || undefined,
        cin: cin.trim() || undefined,
      });

      // Navigate to results view passing verified analysis payload
      navigate('/results', {
        state: {
          analysisResult: result,
          jobText: fullText,
          claimedCompany: companyName.trim() || result.company_verification?.queried_name || '',
          claimedCin: cin.trim() || result.company_verification?.cin || '',
          jobTitle: jobTitle.trim(),
        },
      });
    } catch (err) {
      setSubmitError(err.message || 'Failed to submit job description for analysis.');
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="max-w-4xl mx-auto py-8 px-4 sm:px-6 lg:px-8 space-y-8">
      {/* Page Title & Phase 1 Active Notice */}
      <div className="space-y-3">
        <h1 className="text-3xl font-extrabold text-slate-900 tracking-tight">
          Analyze Job Posting or Offer
        </h1>
        <p className="text-slate-600 text-sm leading-relaxed">
          Submit recruitment communication or vacancy text for multi-signal heuristic verification and calibrated Machine Learning fraud detection.
        </p>

        {/* Multi-Signal Verification Disclosure */}
        <div
          role="note"
          aria-label="Active verification status"
          className="rounded-xl border border-blue-200 bg-blue-50/70 p-4 text-blue-950 text-xs sm:text-sm flex items-start gap-3"
        >
          <Info className="h-5 w-5 text-blue-700 flex-shrink-0 mt-0.5" aria-hidden="true" />
          <div className="space-y-1">
            <span className="font-bold">Multi-Signal Verification Active:</span>
            <p className="text-blue-900 leading-normal">
              Submissions are analyzed against contextual rule heuristics and the versioned, calibrated Machine Learning fraud classifier (v1.1.0). Strict privacy is enforced: submitted text is never stored in logs or database records.
            </p>
          </div>
        </div>
      </div>

      {/* Tabs Navigation (Accessible with role="tablist") */}
      <div className="border-b border-slate-200">
        <nav
          className="flex flex-wrap gap-2 sm:gap-4 -mb-px"
          role="tablist"
          aria-label="Analysis Input Modes"
        >
          {/* Tab 1: Job Description Text (Active) */}
          <button
            type="button"
            role="tab"
            id="tab-job-text"
            aria-selected={activeTab === 'job-text'}
            aria-controls="panel-job-text"
            onClick={() => setActiveTab('job-text')}
            className={`inline-flex items-center gap-2 py-3 px-4 border-b-2 font-semibold text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 rounded-t-lg ${
              activeTab === 'job-text'
                ? 'border-blue-600 text-blue-700 bg-white'
                : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'
            }`}
          >
            <FileText className="h-4 w-4" aria-hidden="true" />
            <span>Job Text</span>
            <span className="text-[10px] font-bold uppercase tracking-wider bg-emerald-100 text-emerald-800 px-1.5 py-0.5 rounded">
              Active
            </span>
          </button>

          {/* Tab 2: Job URL (Active - Feature F3) */}
          <button
            type="button"
            role="tab"
            id="tab-job-url"
            aria-selected={activeTab === 'job-url'}
            aria-controls="panel-job-url"
            onClick={() => setActiveTab('job-url')}
            className={`inline-flex items-center gap-2 py-3 px-4 border-b-2 font-semibold text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 rounded-t-lg ${
              activeTab === 'job-url'
                ? 'border-blue-600 text-blue-700 bg-white'
                : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'
            }`}
          >
            <Globe className="h-4 w-4" aria-hidden="true" />
            <span>Job URL</span>
            <span className="text-[10px] font-bold uppercase tracking-wider bg-emerald-100 text-emerald-800 px-1.5 py-0.5 rounded">
              Active
            </span>
          </button>

          {/* Tab 3: Recruiter Email (Active - Feature F4) */}
          <button
            type="button"
            role="tab"
            id="tab-recruiter-email"
            aria-selected={activeTab === 'recruiter-email'}
            aria-controls="panel-recruiter-email"
            onClick={() => setActiveTab('recruiter-email')}
            className={`inline-flex items-center gap-2 py-3 px-4 border-b-2 font-semibold text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 rounded-t-lg ${
              activeTab === 'recruiter-email'
                ? 'border-blue-600 text-blue-700 bg-white'
                : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'
            }`}
          >
            <Mail className="h-4 w-4" aria-hidden="true" />
            <span>Recruiter Email</span>
            <span className="text-[10px] font-bold uppercase tracking-wider bg-emerald-100 text-emerald-800 px-1.5 py-0.5 rounded">
              Active
            </span>
          </button>

          {/* Tab 4: Offer Letter PDF (Active - Feature F7) */}
          <button
            type="button"
            role="tab"
            id="tab-offer-letter"
            aria-selected={activeTab === 'offer-letter'}
            aria-controls="panel-offer-letter"
            onClick={() => setActiveTab('offer-letter')}
            className={`inline-flex items-center gap-2 py-3 px-4 border-b-2 font-semibold text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 rounded-t-lg ${
              activeTab === 'offer-letter'
                ? 'border-blue-600 text-blue-700 bg-white'
                : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'
            }`}
          >
            <Upload className="h-4 w-4" aria-hidden="true" />
            <span>Offer Letter (PDF)</span>
            <span className="text-[10px] font-bold uppercase tracking-wider bg-emerald-100 text-emerald-800 px-1.5 py-0.5 rounded">
              Active
            </span>
          </button>
        </nav>
      </div>

      {/* Error state if submission fails */}
      {submitError && (
        <ErrorState
          title="Submission Error"
          message={submitError}
          onRetry={handleSubmit}
        />
      )}

      {/* Tab Panels */}
      {activeTab === 'job-text' && (
        <div
          id="panel-job-text"
          role="tabpanel"
          aria-labelledby="tab-job-text"
          className="rounded-2xl border border-slate-200 bg-white p-6 sm:p-8 shadow-sm space-y-6"
        >
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-4">
            <div>
              <h2 className="text-lg font-bold text-slate-900">Pasted Job Description</h2>
              <p className="text-xs text-slate-500">Paste the complete job advert or communication text.</p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={handleLoadSuspiciousSample}
                className="inline-flex items-center gap-1.5 text-xs font-semibold text-rose-700 hover:text-rose-800 bg-rose-50 hover:bg-rose-100 border border-rose-200 px-3 py-1.5 rounded-lg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-600"
              >
                <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
                <span>Load Suspicious Sample</span>
              </button>
              <button
                type="button"
                onClick={handleLoadStandardSample}
                className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-700 hover:text-slate-800 bg-slate-100 hover:bg-slate-200 border border-slate-200 px-3 py-1.5 rounded-lg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-600"
              >
                <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
                <span>Load Standard Sample</span>
              </button>
            </div>
          </div>

          <form onSubmit={handleSubmit} className="space-y-6">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div>
                <label
                  htmlFor="claimed-company"
                  className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1"
                >
                  Claimed Company Name (Optional)
                </label>
                <input
                  type="text"
                  id="claimed-company"
                  value={companyName}
                  onChange={(e) => setCompanyName(e.target.value)}
                  placeholder="e.g. Acme Cloud Corp"
                  className="w-full px-3.5 py-2.5 text-sm rounded-lg border border-slate-300 focus:border-blue-600 focus:ring-2 focus:ring-blue-100 focus:outline-none"
                />
              </div>

              <div>
                <label
                  htmlFor="claimed-cin"
                  className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1"
                >
                  CIN / Reg. No. (Optional)
                </label>
                <input
                  type="text"
                  id="claimed-cin"
                  value={cin}
                  onChange={(e) => setCin(e.target.value)}
                  placeholder="e.g. U72200MH2020PTC123456"
                  className="w-full px-3.5 py-2.5 text-sm rounded-lg border border-slate-300 focus:border-blue-600 focus:ring-2 focus:ring-blue-100 focus:outline-none font-mono text-xs uppercase"
                />
              </div>

              <div>
                <label
                  htmlFor="job-title"
                  className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1"
                >
                  Job Title (Optional)
                </label>
                <input
                  type="text"
                  id="job-title"
                  value={jobTitle}
                  onChange={(e) => setJobTitle(e.target.value)}
                  placeholder="e.g. Remote Data Specialist"
                  className="w-full px-3.5 py-2.5 text-sm rounded-lg border border-slate-300 focus:border-blue-600 focus:ring-2 focus:ring-blue-100 focus:outline-none"
                />
              </div>
            </div>

            <div>
              <div className="flex justify-between items-center mb-1">
                <label
                  htmlFor="job-description"
                  className="block text-xs font-bold uppercase tracking-wider text-slate-700"
                >
                  Job Description Text <span className="text-rose-600">*</span>
                </label>
                <span className="text-xs text-slate-400">
                  {jobDescription.length} characters (min 20)
                </span>
              </div>
              <textarea
                id="job-description"
                rows="9"
                required
                value={jobDescription}
                onChange={(e) => setJobDescription(e.target.value)}
                placeholder="Paste the job requirements, compensation details, interview instructions, and sender notes here..."
                className="w-full p-3.5 text-sm rounded-lg border border-slate-300 focus:border-blue-600 focus:ring-2 focus:ring-blue-100 focus:outline-none leading-relaxed font-sans"
              />
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-slate-100">
              <button
                type="button"
                onClick={handleClear}
                className="text-xs font-medium text-slate-500 hover:text-slate-800 px-3 py-2 rounded-lg hover:bg-slate-100 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
              >
                Clear Fields
              </button>

              <button
                type="submit"
                disabled={isSubmitting}
                className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-blue-700 hover:bg-blue-800 disabled:bg-blue-400 text-white font-semibold text-sm shadow-md transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600"
              >
                {isSubmitting ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                    <span>Analyzing Job Posting...</span>
                  </>
                ) : (
                  <span>Analyze Job Posting (Run ML & Heuristic Check)</span>
                )}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Tab Panel for Job URL (Active - Feature F3) */}
      {activeTab === 'job-url' && (
        <div
          id="panel-job-url"
          role="tabpanel"
          aria-labelledby="tab-job-url"
          className="rounded-2xl border border-slate-200 bg-white p-6 sm:p-8 shadow-sm space-y-6"
        >
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-4">
            <div>
              <h2 className="text-lg font-bold text-slate-900">Public Job URL Ingestion</h2>
              <p className="text-xs text-slate-500">
                Safely inspects public job postings with SSRF protection, technical domain authentication, and lookalike detection.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={handleLoadLegitUrlSample}
                className="inline-flex items-center gap-1.5 text-xs font-semibold text-emerald-800 hover:text-emerald-900 bg-emerald-50 hover:bg-emerald-100 border border-emerald-200 px-3 py-1.5 rounded-lg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600"
              >
                <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
                <span>Load Legitimate URL</span>
              </button>
              <button
                type="button"
                onClick={handleLoadSuspiciousUrlSample}
                className="inline-flex items-center gap-1.5 text-xs font-semibold text-rose-700 hover:text-rose-800 bg-rose-50 hover:bg-rose-100 border border-rose-200 px-3 py-1.5 rounded-lg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-600"
              >
                <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
                <span>Load Lookalike URL</span>
              </button>
            </div>
          </div>

          {submitUrlError && (
            <ErrorState
              title="URL Analysis Error"
              message={submitUrlError}
              onRetry={handleSubmitUrl}
            />
          )}

          <form onSubmit={handleSubmitUrl} className="space-y-6">
            <div>
              <label
                htmlFor="job-url-input"
                className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1"
              >
                Job Posting URL <span className="text-rose-600">*</span>
              </label>
              <input
                type="url"
                id="job-url-input"
                required
                value={jobUrl}
                onChange={(e) => setJobUrl(e.target.value)}
                placeholder="https://company.example.com/careers/job-posting-id"
                className="w-full px-3.5 py-2.5 text-sm rounded-lg border border-slate-300 focus:border-blue-600 focus:ring-2 focus:ring-blue-100 focus:outline-none font-mono text-xs"
              />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label
                  htmlFor="url-claimed-company"
                  className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1"
                >
                  Claimed Company Name (Optional)
                </label>
                <input
                  type="text"
                  id="url-claimed-company"
                  value={urlCompanyName}
                  onChange={(e) => setUrlCompanyName(e.target.value)}
                  placeholder="e.g. Infosys Limited"
                  className="w-full px-3.5 py-2.5 text-sm rounded-lg border border-slate-300 focus:border-blue-600 focus:ring-2 focus:ring-blue-100 focus:outline-none"
                />
              </div>

              <div>
                <label
                  htmlFor="url-claimed-cin"
                  className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1"
                >
                  CIN / Reg. No. (Optional)
                </label>
                <input
                  type="text"
                  id="url-claimed-cin"
                  value={urlCin}
                  onChange={(e) => setUrlCin(e.target.value)}
                  placeholder="e.g. L85110KA1981PLC013115"
                  className="w-full px-3.5 py-2.5 text-sm rounded-lg border border-slate-300 focus:border-blue-600 focus:ring-2 focus:ring-blue-100 focus:outline-none font-mono text-xs uppercase"
                />
              </div>
            </div>

            {/* SSRF Safety & Technical Domain Inspection Disclosure */}
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-slate-700 text-xs space-y-2">
              <span className="font-bold flex items-center gap-1.5 text-slate-900">
                <Info className="h-4 w-4 text-blue-600" aria-hidden="true" />
                <span>SSRF Safety &amp; Technical Domain Inspection</span>
              </span>
              <p className="leading-relaxed text-slate-600">
                Private RFC-1918 networks, loopback addresses (127.0.0.1/localhost), link-local subnets, and cloud metadata endpoints (169.254.169.254) are strictly blocked. In addition to text heuristics, JobShield AI inspects technical domain security (DNS resolution, MX mail routes, SPF, DMARC policy, and DKIM deployment) and scans for lookalike domains / typosquatting.
              </p>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-slate-100">
              <button
                type="button"
                onClick={handleClearUrl}
                className="text-xs font-medium text-slate-500 hover:text-slate-800 px-3 py-2 rounded-lg hover:bg-slate-100 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
              >
                Clear Fields
              </button>

              <button
                type="submit"
                disabled={isSubmittingUrl}
                className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-blue-700 hover:bg-blue-800 disabled:bg-blue-400 text-white font-semibold text-sm shadow-md transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600"
              >
                {isSubmittingUrl ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                    <span>Fetching &amp; Analyzing URL...</span>
                  </>
                ) : (
                  <span>Analyze Job URL (Safe Fetch &amp; Domain Security)</span>
                )}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Tab Panel for Recruiter Email (Active - Feature F4) */}
      {activeTab === 'recruiter-email' && (
        <div
          id="panel-recruiter-email"
          role="tabpanel"
          aria-labelledby="tab-recruiter-email"
          className="rounded-2xl border border-slate-200 bg-white p-6 sm:p-8 shadow-sm space-y-6"
        >
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-4">
            <div>
              <h2 className="text-lg font-bold text-slate-900">Recruiter Email &amp; Communication Verification</h2>
              <p className="text-xs text-slate-500">
                Verifies sender email domain authentication, free webmail indicators, employer registry alignment, and message text heuristics.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={handleLoadLegitEmailSample}
                className="inline-flex items-center gap-1.5 text-xs font-semibold text-emerald-800 hover:text-emerald-900 bg-emerald-50 hover:bg-emerald-100 border border-emerald-200 px-3 py-1.5 rounded-lg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600"
              >
                <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
                <span>Legitimate Recruiter</span>
              </button>
              <button
                type="button"
                onClick={handleLoadFreeWebmailSample}
                className="inline-flex items-center gap-1.5 text-xs font-semibold text-amber-800 hover:text-amber-900 bg-amber-50 hover:bg-amber-100 border border-amber-200 px-3 py-1.5 rounded-lg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-600"
              >
                <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
                <span>Free Webmail Warning (@gmail)</span>
              </button>
              <button
                type="button"
                onClick={handleLoadLookalikeEmailSample}
                className="inline-flex items-center gap-1.5 text-xs font-semibold text-rose-700 hover:text-rose-800 bg-rose-50 hover:bg-rose-100 border border-rose-200 px-3 py-1.5 rounded-lg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-600"
              >
                <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
                <span>Lookalike Domain Warning</span>
              </button>
            </div>
          </div>

          {submitEmailError && (
            <ErrorState
              title="Recruiter Verification Error"
              message={submitEmailError}
              onRetry={handleSubmitEmail}
            />
          )}

          <form onSubmit={handleSubmitEmail} className="space-y-6">
            <div>
              <label
                htmlFor="recruiter-email-input"
                className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1"
              >
                Recruiter / Sender Email Address <span className="text-rose-600">*</span>
              </label>
              <input
                type="email"
                id="recruiter-email-input"
                required
                value={recruiterEmail}
                onChange={(e) => setRecruiterEmail(e.target.value)}
                placeholder="recruiter@company.com"
                className="w-full px-3.5 py-2.5 text-sm rounded-lg border border-slate-300 focus:border-blue-600 focus:ring-2 focus:ring-blue-100 focus:outline-none font-mono text-xs"
              />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label
                  htmlFor="recruiter-claimed-company"
                  className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1"
                >
                  Claimed Company Name (Optional)
                </label>
                <input
                  type="text"
                  id="recruiter-claimed-company"
                  value={recruiterCompanyName}
                  onChange={(e) => setRecruiterCompanyName(e.target.value)}
                  placeholder="e.g. Tata Consultancy Services Limited"
                  className="w-full px-3.5 py-2.5 text-sm rounded-lg border border-slate-300 focus:border-blue-600 focus:ring-2 focus:ring-blue-100 focus:outline-none"
                />
              </div>

              <div>
                <label
                  htmlFor="recruiter-claimed-cin"
                  className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1"
                >
                  CIN / Reg. No. (Optional)
                </label>
                <input
                  type="text"
                  id="recruiter-claimed-cin"
                  value={recruiterCin}
                  onChange={(e) => setRecruiterCin(e.target.value)}
                  placeholder="e.g. L22210MH1995PLC084781"
                  className="w-full px-3.5 py-2.5 text-sm rounded-lg border border-slate-300 focus:border-blue-600 focus:ring-2 focus:ring-blue-100 focus:outline-none font-mono text-xs uppercase"
                />
              </div>
            </div>

            <div>
              <label
                htmlFor="recruiter-message-input"
                className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1"
              >
                Recruitment Message / Email Body (Optional)
              </label>
              <textarea
                id="recruiter-message-input"
                rows={4}
                value={recruiterMessage}
                onChange={(e) => setRecruiterMessage(e.target.value)}
                placeholder="Paste the recruiter's message, interview invitation, job offer text, or WhatsApp / Telegram communication..."
                className="w-full px-3.5 py-2.5 text-sm rounded-lg border border-slate-300 focus:border-blue-600 focus:ring-2 focus:ring-blue-100 focus:outline-none leading-relaxed"
              />
            </div>

            {/* Privacy & Anti-Probing Policy Disclosure */}
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-slate-700 text-xs space-y-2">
              <span className="font-bold flex items-center gap-1.5 text-slate-900">
                <Info className="h-4 w-4 text-blue-600" aria-hidden="true" />
                <span>Privacy &amp; Non-Intrusive Infrastructure Check</span>
              </span>
              <p className="leading-relaxed text-slate-600">
                <strong>Privacy-First:</strong> Recruiter email addresses are strictly masked in stored records and analysis reports (e.g., <code>c***s@domain.com</code>). Raw email addresses are never retained.
              </p>
              <p className="leading-relaxed text-slate-600">
                <strong>No Mailbox Probing:</strong> JobShield AI inspects publicly advertised domain infrastructure (DNS resolution, MX mail routes, SPF policies, DMARC records, and DKIM deployment). We never connect to port 25 or send SMTP probes.
              </p>
              <p className="leading-relaxed text-slate-600 italic">
                <strong>Identity Limitation:</strong> A domain match indicates infrastructure alignment only; it does NOT definitively prove the sender's individual identity, as headers can be spoofed or corporate accounts compromised.
              </p>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-slate-100">
              <button
                type="button"
                onClick={handleClearEmail}
                className="text-xs font-medium text-slate-500 hover:text-slate-800 px-3 py-2 rounded-lg hover:bg-slate-100 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
              >
                Clear Fields
              </button>

              <button
                type="submit"
                disabled={isSubmittingEmail}
                className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-blue-700 hover:bg-blue-800 disabled:bg-blue-400 text-white font-semibold text-sm shadow-md transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600"
              >
                {isSubmittingEmail ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                    <span>Verifying Recruiter Domain...</span>
                  </>
                ) : (
                  <span>Verify Recruiter Communication (Domain Auth &amp; Heuristics)</span>
                )}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Tab 4: Offer Letter PDF (Active - Feature F7) */}
      {activeTab === 'offer-letter' && (
        <div
          id="panel-offer-letter"
          role="tabpanel"
          aria-labelledby="tab-offer-letter"
          className="rounded-2xl border border-slate-200 bg-white p-6 sm:p-8 shadow-sm space-y-6"
        >
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-4">
            <div>
              <h2 className="text-lg font-bold text-slate-900">Offer Letter PDF Analyzer</h2>
              <p className="text-xs text-slate-500">
                Upload an employment offer or appointment letter (PDF) to parse terms, detect fee demands, identify sensitive data requests, and corroborate employer &amp; recruiter contact legitimacy.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-emerald-800 bg-emerald-50 border border-emerald-200 px-3 py-1.5 rounded-lg">
                <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
                <span>PyMuPDF + Tesseract OCR Active</span>
              </span>
            </div>
          </div>

          {submitOfferError && (
            <ErrorState
              title="Offer Letter Analysis Error"
              message={submitOfferError}
              onRetry={handleSubmitOffer}
            />
          )}

          <form onSubmit={handleSubmitOffer} className="space-y-6">
            {/* PDF Upload Dropzone */}
            <div className="space-y-2">
              <label className="block text-xs font-bold uppercase tracking-wider text-slate-700">
                Offer Letter Document (PDF) <span className="text-rose-600">*</span>
              </label>

              {!offerFile ? (
                <div
                  onDragOver={(e) => {
                    e.preventDefault();
                    setDragOver(true);
                  }}
                  onDragLeave={() => setDragOver(false)}
                  onDrop={handleOfferDrop}
                  onClick={() => document.getElementById('offer-file-input')?.click()}
                  className={`border-2 border-dashed rounded-2xl p-8 sm:p-12 text-center cursor-pointer transition-all ${
                    dragOver
                      ? 'border-blue-500 bg-blue-50/50 scale-[1.005]'
                      : 'border-slate-300 hover:border-blue-400 bg-slate-50/50 hover:bg-slate-50'
                  }`}
                >
                  <input
                    type="file"
                    id="offer-file-input"
                    accept="application/pdf,.pdf"
                    onChange={handleOfferFileChange}
                    className="hidden"
                  />
                  <div className="h-12 w-12 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center mx-auto mb-3">
                    <Upload className="h-6 w-6" aria-hidden="true" />
                  </div>
                  <p className="text-sm font-bold text-slate-800">
                    Click to select an offer letter PDF or drag &amp; drop here
                  </p>
                  <p className="text-xs text-slate-500 mt-1">
                    Standard PDF documents up to 10 MB and 10 pages. Scanned pages are automatically processed via Tesseract OCR.
                  </p>
                </div>
              ) : (
                <div className="rounded-xl border border-blue-200 bg-blue-50/40 p-4 flex items-center justify-between gap-4">
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="h-10 w-10 rounded-lg bg-blue-100 text-blue-700 flex items-center justify-center flex-shrink-0">
                      <File className="h-5 w-5" aria-hidden="true" />
                    </div>
                    <div className="min-w-0">
                      <p className="text-sm font-bold text-slate-900 truncate">
                        {offerFile.name}
                      </p>
                      <p className="text-xs text-slate-500">
                        {(offerFile.size / 1024).toFixed(1)} KB · Ready for parsing &amp; OCR
                      </p>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={handleClearOffer}
                    className="p-1.5 text-slate-400 hover:text-rose-600 rounded-lg hover:bg-rose-50 transition-colors"
                    title="Remove selected file"
                  >
                    <X className="h-5 w-5" aria-hidden="true" />
                  </button>
                </div>
              )}
            </div>

            {/* Optional Corroboration Fields */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-1">
              <div>
                <label
                  htmlFor="offer-company-name"
                  className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1"
                >
                  Claimed Company Name <span className="text-slate-400 font-normal">(Optional)</span>
                </label>
                <input
                  type="text"
                  id="offer-company-name"
                  value={offerCompanyName}
                  onChange={(e) => setOfferCompanyName(e.target.value)}
                  placeholder="e.g. Tata Consultancy Services Limited"
                  className="w-full px-3.5 py-2.5 text-sm rounded-lg border border-slate-300 focus:border-blue-600 focus:ring-2 focus:ring-blue-100 focus:outline-none"
                />
                <span className="text-[11px] text-slate-500 mt-0.5 block">
                  Leave blank to auto-detect employer name from the document.
                </span>
              </div>

              <div>
                <label
                  htmlFor="offer-company-cin"
                  className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1"
                >
                  Company CIN <span className="text-slate-400 font-normal">(Optional)</span>
                </label>
                <input
                  type="text"
                  id="offer-company-cin"
                  value={offerCin}
                  onChange={(e) => setOfferCin(e.target.value)}
                  placeholder="e.g. L22210MH1995PLC084781"
                  className="w-full px-3.5 py-2.5 text-sm rounded-lg border border-slate-300 focus:border-blue-600 focus:ring-2 focus:ring-blue-100 focus:outline-none font-mono text-xs uppercase"
                  maxLength={21}
                />
                <span className="text-[11px] text-slate-500 mt-0.5 block">
                  Official 21-character MCA Corporate Identification Number.
                </span>
              </div>
            </div>

            {/* Privacy & Zero-Retention Security Notice */}
            <div className="rounded-xl bg-slate-50 border border-slate-200 p-4 space-y-2 text-xs">
              <div className="flex items-center gap-2 font-bold text-slate-800">
                <Info className="h-4 w-4 text-blue-600 flex-shrink-0" aria-hidden="true" />
                <span>Zero-Storage &amp; PII Privacy Safeguards</span>
              </div>
              <ul className="space-y-1 text-slate-600 leading-relaxed list-disc list-inside">
                <li>
                  <strong>Zero Document Retention:</strong> Uploaded PDF files are processed strictly in memory or temporary isolated directories and purged immediately. Original binaries are never permanently stored or shared.
                </li>
                <li>
                  <strong>PII Masking:</strong> Candidate personal details, email addresses, and phone numbers are masked in all generated audit logs and reports.
                </li>
                <li>
                  <strong>Local OCR Execution:</strong> Scanned pages are read via local Tesseract OCR without transmitting document images to third-party cloud services.
                </li>
                <li>
                  <strong>Verification Limitation:</strong> MCA company registration corroborates corporate existence but does not guarantee an individual document's authenticity. Always verify offers directly through company-advertised contact channels.
                </li>
              </ul>
            </div>

            {/* Form Actions */}
            <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-slate-100">
              <button
                type="button"
                onClick={handleClearOffer}
                className="text-xs font-medium text-slate-500 hover:text-slate-800 px-3 py-2 rounded-lg hover:bg-slate-100 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
              >
                Clear Fields
              </button>

              <button
                type="submit"
                disabled={isSubmittingOffer || !offerFile}
                className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-blue-700 hover:bg-blue-800 disabled:bg-blue-400 text-white font-semibold text-sm shadow-md transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600"
              >
                {isSubmittingOffer ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                    <span>Analyzing PDF &amp; Running OCR...</span>
                  </>
                ) : (
                  <span>Analyze Offer Letter (OCR &amp; Terms Verification)</span>
                )}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Tab Panels for Inactive Modes (Fallback) */}
      {activeTab !== 'job-text' && activeTab !== 'job-url' && activeTab !== 'recruiter-email' && activeTab !== 'offer-letter' && (
        <div
          role="tabpanel"
          className="rounded-2xl border border-slate-200 bg-white p-12 text-center space-y-4"
        >
          <div className="h-12 w-12 rounded-full bg-slate-100 text-slate-500 flex items-center justify-center mx-auto">
            <HelpCircle className="h-6 w-6" aria-hidden="true" />
          </div>
          <h2 className="text-lg font-bold text-slate-900">
            Select an Analysis Mode
          </h2>
          <p className="text-sm text-slate-500 max-w-md mx-auto leading-relaxed">
            Please choose a supported verification mode: Job Text, Job URL, Recruiter Email, or Offer Letter PDF.
          </p>
          <button
            type="button"
            onClick={() => setActiveTab('job-text')}
            className="text-xs font-semibold text-blue-700 hover:underline"
          >
            Return to Job Text Analysis
          </button>
        </div>
      )}
    </div>
  );
}

export default Analyze;
