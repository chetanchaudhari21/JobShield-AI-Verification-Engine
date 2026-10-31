import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import {
  Shield,
  Search,
  Building2,
  Mail,
  FileText,
  AlertTriangle,
  CheckCircle2,
  Info,
  Server,
  ArrowRight,
} from 'lucide-react';
import { api } from '../services/api';

export function Landing() {
  const [healthData, setHealthData] = useState(null);
  const [readinessData, setReadinessData] = useState(null);
  const [loadingHealth, setLoadingHealth] = useState(true);
  const [errorHealth, setErrorHealth] = useState(null);

  async function checkServices() {
    setLoadingHealth(true);
    setErrorHealth(null);
    try {
      const [health, ready] = await Promise.allSettled([
        api.checkHealth(),
        api.checkReadiness(),
      ]);

      if (health.status === 'fulfilled') {
        setHealthData(health.value);
      } else {
        throw health.reason;
      }

      if (ready.status === 'fulfilled') {
        setReadinessData(ready.value);
      } else {
        setReadinessData(ready.reason?.data || { status: 'not_ready', dependencies: { database: 'unavailable' } });
      }
    } catch (err) {
      setErrorHealth(err.message || 'Failed to connect to backend server');
    } finally {
      setLoadingHealth(false);
    }
  }

  useEffect(() => {
    checkServices();
  }, []);

  return (
    <div className="space-y-12 py-8 px-4 sm:px-6 lg:px-8 max-w-7xl mx-auto">
      {/* 1. Hero Section */}
      <section className="text-center space-y-6 pt-4 pb-8 max-w-4xl mx-auto">
        <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-blue-50 border border-blue-200 text-blue-800 text-xs font-semibold">
          <Shield className="h-4 w-4" aria-hidden="true" />
          <span>Explainable AI-Powered Verification Platform</span>
        </div>

        <h1 className="text-4xl sm:text-5xl font-black text-slate-900 tracking-tight leading-tight">
          Protect Job Seekers with <br className="hidden sm:inline" />
          <span className="text-blue-700">Evidence-Backed</span> Verification
        </h1>

        <p className="text-lg text-slate-600 max-w-2xl mx-auto leading-relaxed">
          Combines machine-learning job analysis, corporate registry cross-checks (MCA & Startup India), recruiter domain inspection, and offer letter text extraction to protect against employment scams.
        </p>

        <div className="flex flex-wrap justify-center items-center gap-4 pt-2">
          <Link
            to="/analyze"
            className="inline-flex items-center gap-2 px-6 py-3.5 rounded-xl bg-blue-700 hover:bg-blue-800 text-white font-semibold text-base shadow-md transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600"
          >
            <Search className="h-5 w-5" aria-hidden="true" />
            <span>Launch Analysis Form</span>
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </Link>

          <Link
            to="/about"
            className="inline-flex items-center gap-2 px-6 py-3.5 rounded-xl bg-white hover:bg-slate-100 text-slate-800 font-semibold text-base border border-slate-300 shadow-sm transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
          >
            <Info className="h-5 w-5 text-slate-500" aria-hidden="true" />
            <span>Project Principles & Limitations</span>
          </Link>
        </div>
      </section>

      {/* 3. Live System Health Check Widget */}
      <section
        aria-labelledby="backend-status-heading"
        className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
      >
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-100 pb-4 mb-4">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-blue-50 text-blue-700">
              <Server className="h-5 w-5" aria-hidden="true" />
            </div>
            <div>
              <h2 id="backend-status-heading" className="text-base font-bold text-slate-900">
                Backend Services Integration Status
              </h2>
              <p className="text-xs text-slate-500">Live communication check with FastAPI server</p>
            </div>
          </div>

          <button
            type="button"
            onClick={checkServices}
            disabled={loadingHealth}
            className="px-3.5 py-1.5 text-xs font-semibold rounded-lg border border-slate-300 hover:bg-slate-50 text-slate-700 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 disabled:opacity-50"
          >
            {loadingHealth ? 'Querying Endpoints...' : 'Refresh Health Status'}
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Liveness Check Card */}
          <div className="rounded-xl border border-slate-100 bg-slate-50/60 p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
                Liveness Probe (GET /health)
              </span>
              {healthData ? (
                <span className="inline-flex items-center gap-1 text-xs font-bold text-emerald-800 bg-emerald-100 px-2 py-0.5 rounded-full">
                  <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
                  200 OK — Healthy
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 text-xs font-bold text-rose-800 bg-rose-100 px-2 py-0.5 rounded-full">
                  <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
                  Unavailable
                </span>
              )}
            </div>
            {healthData ? (
              <div className="text-xs font-mono text-slate-700 bg-white p-2.5 rounded border border-slate-200">
                App: {healthData.app} | Environment: {healthData.environment}
              </div>
            ) : (
              <p className="text-xs text-slate-500">
                Backend server is not running or port 8000 is unreachable.
              </p>
            )}
          </div>

          {/* Readiness Check Card */}
          <div className="rounded-xl border border-slate-100 bg-slate-50/60 p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
                Readiness Probe (GET /api/v1/health/ready)
              </span>
              {readinessData?.status === 'ready' ? (
                <span className="inline-flex items-center gap-1 text-xs font-bold text-emerald-800 bg-emerald-100 px-2 py-0.5 rounded-full">
                  <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
                  Ready (DB Connected)
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 text-xs font-bold text-amber-800 bg-amber-100 px-2 py-0.5 rounded-full">
                  <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
                  {readinessData?.dependencies?.database === 'unavailable' ? 'DB Pending' : 'Not Ready'}
                </span>
              )}
            </div>
            <div className="text-xs font-mono text-slate-700 bg-white p-2.5 rounded border border-slate-200">
              Database Dependency: {readinessData?.dependencies?.database || 'Pending connection'}
            </div>
          </div>
        </div>
      </section>

      {/* 4. Four Core Pillars of JobShield AI */}
      <section aria-labelledby="pillars-heading" className="space-y-6">
        <div className="text-center space-y-2">
          <h2 id="pillars-heading" className="text-2xl font-bold text-slate-900">
            Four Pillars of Multimodal Verification
          </h2>
          <p className="text-sm text-slate-600 max-w-xl mx-auto">
            A single machine learning score or database check is never sufficient to determine legitimacy.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          <div className="rounded-xl border border-slate-200 bg-white p-6 space-y-3 shadow-xs">
            <div className="h-10 w-10 rounded-lg bg-blue-100 text-blue-700 flex items-center justify-center">
              <FileText className="h-5 w-5" aria-hidden="true" />
            </div>
            <h3 className="font-bold text-slate-900 text-base">ML Text Classification</h3>
            <p className="text-xs text-slate-600 leading-relaxed">
              Trained on validated job-fraud corpora with TF-IDF, gradient boosting, and SHAP explainability. Flags upfront fees and urgency.
            </p>
            <span className="inline-block text-[11px] font-semibold text-blue-700 bg-blue-50 px-2 py-0.5 rounded">
              Active &amp; Operational
            </span>
          </div>

          <div className="rounded-xl border border-slate-200 bg-white p-6 space-y-3 shadow-xs">
            <div className="h-10 w-10 rounded-lg bg-indigo-100 text-indigo-700 flex items-center justify-center">
              <Building2 className="h-5 w-5" aria-hidden="true" />
            </div>
            <h3 className="font-bold text-slate-900 text-base">Entity Registry Checks</h3>
            <p className="text-xs text-slate-600 leading-relaxed">
              Cross-references MCA Master Data, Startup India portal, and DPIIT recognition catalogues with full source provenance.
            </p>
            <span className="inline-block text-[11px] font-semibold text-indigo-700 bg-indigo-50 px-2 py-0.5 rounded">
              Active &amp; Operational
            </span>
          </div>

          <div className="rounded-xl border border-slate-200 bg-white p-6 space-y-3 shadow-xs">
            <div className="h-10 w-10 rounded-lg bg-purple-100 text-purple-700 flex items-center justify-center">
              <Mail className="h-5 w-5" aria-hidden="true" />
            </div>
            <h3 className="font-bold text-slate-900 text-base">Recruiter & Domain Checks</h3>
            <p className="text-xs text-slate-600 leading-relaxed">
              Performs DNS/MX lookups, detects lookalike domains, and checks for free-tier email impersonation of established brands.
            </p>
            <span className="inline-block text-[11px] font-semibold text-purple-700 bg-purple-50 px-2 py-0.5 rounded">
              Active &amp; Operational
            </span>
          </div>

          <div className="rounded-xl border border-slate-200 bg-white p-6 space-y-3 shadow-xs">
            <div className="h-10 w-10 rounded-lg bg-emerald-100 text-emerald-700 flex items-center justify-center">
              <Shield className="h-5 w-5" aria-hidden="true" />
            </div>
            <h3 className="font-bold text-slate-900 text-base">Offer Letter OCR Analysis</h3>
            <p className="text-xs text-slate-600 leading-relaxed">
              Parses PDF offer letters using PyMuPDF and Tesseract OCR to spot security-deposit clauses and training fee demands.
            </p>
            <span className="inline-block text-[11px] font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded">
              Active &amp; Operational
            </span>
          </div>
        </div>
      </section>
    </div>
  );
}

export default Landing;
