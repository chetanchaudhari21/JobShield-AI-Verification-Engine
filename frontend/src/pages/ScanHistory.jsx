import React, { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import {
  History,
  FileText,
  Globe,
  Mail,
  FileCheck,
  Download,
  Trash2,
  AlertCircle,
  CheckCircle2,
  ArrowRight,
  Loader2,
  Filter,
  RotateCcw,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { api } from '../services/api';
import RiskIndicator from '../components/RiskIndicator';

export default function ScanHistory({ initialScans = [], initialLoading = undefined }) {
  const { isAuthenticated, loading: authLoading } = useAuth();

  const [scans, setScans] = useState(initialScans);
  const [loading, setLoading] = useState(initialLoading !== undefined ? initialLoading : true);
  const [error, setError] = useState(null);
  const [filterType, setFilterType] = useState('ALL');
  const [downloadingId, setDownloadingId] = useState(null);
  const [deletingId, setDeletingId] = useState(null);
  const [actionSuccess, setActionSuccess] = useState(null);

  const fetchScans = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getMyScans({ limit: 100, offset: 0 });
      // Robust response parsing: supports { scans: [...] } schema and raw array fallback
      const scanList = Array.isArray(data) ? data : (data?.scans || []);
      setScans(scanList);
    } catch (err) {
      setError(err.message || 'Failed to retrieve scan history. Please check your connection and try again.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!authLoading && isAuthenticated) {
      fetchScans();
    } else if (!authLoading && !isAuthenticated) {
      setLoading(false);
    }
  }, [authLoading, isAuthenticated, fetchScans]);

  const handleDownloadPdf = async (scanId) => {
    setDownloadingId(scanId);
    setError(null);
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
      setError(err.message || 'Unable to download verification report.');
    } finally {
      setDownloadingId(null);
    }
  };

  const handleDeleteScan = async (scanId) => {
    if (!window.confirm('Are you sure you want to delete this scan from your history? This action is irreversible.')) {
      return;
    }
    setDeletingId(scanId);
    setError(null);
    try {
      await api.deleteScan(scanId);
      setScans((prev) => prev.filter((s) => s.id !== scanId));
      setActionSuccess('Scan deleted successfully.');
      setTimeout(() => setActionSuccess(null), 4000);
    } catch (err) {
      setError(err.message || 'Failed to delete scan.');
    } finally {
      setDeletingId(null);
    }
  };

  const filteredScans = scans.filter((scan) => {
    if (filterType === 'ALL') return true;
    return scan.input_type?.toUpperCase() === filterType;
  });

  const getTypeIcon = (type) => {
    switch ((type || '').toUpperCase()) {
      case 'JOB_URL':
        return <Globe className="h-4 w-4 text-blue-600" />;
      case 'RECRUITER_EMAIL':
        return <Mail className="h-4 w-4 text-amber-600" />;
      case 'OFFER_LETTER':
        return <FileCheck className="h-4 w-4 text-purple-600" />;
      default:
        return <FileText className="h-4 w-4 text-slate-600" />;
    }
  };

  const formatTypeName = (type) => {
    switch ((type || '').toUpperCase()) {
      case 'JOB_URL':
        return 'Job URL';
      case 'RECRUITER_EMAIL':
        return 'Recruiter Email';
      case 'OFFER_LETTER':
        return 'Offer Letter';
      default:
        return 'Job Text';
    }
  };

  if (authLoading) {
    return (
      <div className="max-w-5xl mx-auto px-4 py-16 flex items-center justify-center">
        <Loader2 className="h-8 w-8 text-blue-600 animate-spin" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-16 text-center">
        <div className="bg-white rounded-2xl border border-slate-200 p-8 shadow-sm">
          <History className="h-12 w-12 text-blue-600 mx-auto mb-4" />
          <h1 className="text-2xl font-bold text-slate-900 mb-2">Scan History &amp; Records</h1>
          <p className="text-slate-600 text-sm mb-6">
            Sign in to securely access your personal verification history, track changes over time, and download verified PDF reports.
          </p>
          <div className="flex justify-center gap-3">
            <Link
              to="/login"
              className="py-2.5 px-5 bg-blue-600 hover:bg-blue-700 text-white font-medium text-sm rounded-lg transition-colors inline-flex items-center gap-2"
            >
              <span>Sign In</span>
              <ArrowRight className="h-4 w-4" />
            </Link>
            <Link
              to="/login?mode=register"
              className="py-2.5 px-5 bg-slate-100 hover:bg-slate-200 text-slate-800 font-medium text-sm rounded-lg transition-colors"
            >
              Create Account
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200 pb-5">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="h-8 w-8 rounded-lg bg-blue-50 text-blue-700 flex items-center justify-center">
              <History className="h-5 w-5" />
            </div>
            <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight">Personal Scan History</h1>
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Access, export, and manage your private verification scans ({scans.length} total)
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Link
            to="/analyze"
            className="py-2 px-4 bg-blue-600 hover:bg-blue-700 text-white font-medium text-sm rounded-lg transition-colors inline-flex items-center gap-1.5 shadow-sm"
          >
            <span>New Verification</span>
            <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-red-50 border border-red-200 text-red-800 text-sm flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-start gap-2.5">
            <AlertCircle className="h-5 w-5 text-red-600 shrink-0 mt-0.5" />
            <div>
              <p className="font-semibold">Unable to load scan history</p>
              <p className="text-xs text-red-700 mt-0.5">{error}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={fetchScans}
            disabled={loading}
            className="px-3.5 py-1.5 bg-red-600 hover:bg-red-700 text-white rounded-lg text-xs font-semibold shadow-xs transition-colors shrink-0 flex items-center justify-center gap-1.5 cursor-pointer disabled:opacity-50"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            <span>Retry</span>
          </button>
        </div>
      )}

      {actionSuccess && (
        <div className="p-4 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-sm flex items-start gap-2.5">
          <CheckCircle2 className="h-5 w-5 text-emerald-600 shrink-0 mt-0.5" />
          <span>{actionSuccess}</span>
        </div>
      )}

      {/* Filter Bar */}
      <div className="flex items-center justify-between gap-4 bg-white p-3.5 rounded-xl border border-slate-200">
        <div className="flex items-center gap-2 text-xs font-semibold text-slate-600">
          <Filter className="h-4 w-4 text-slate-400" />
          <span>Filter by type:</span>
        </div>
        <div className="flex gap-1.5 overflow-x-auto">
          {['ALL', 'JOB_TEXT', 'JOB_URL', 'RECRUITER_EMAIL', 'OFFER_LETTER'].map((t) => (
            <button
              key={t}
              onClick={() => setFilterType(t)}
              className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors cursor-pointer ${
                filterType === t
                  ? 'bg-blue-50 text-blue-700 font-semibold border border-blue-200'
                  : 'text-slate-600 hover:bg-slate-100 border border-transparent'
              }`}
            >
              {t === 'ALL' ? 'All Types' : formatTypeName(t)}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="py-16 text-center">
          <Loader2 className="h-8 w-8 text-blue-600 animate-spin mx-auto mb-2" />
          <p className="text-sm text-slate-500">Loading your scan records...</p>
        </div>
      ) : error && scans.length === 0 ? (
        <div className="bg-white rounded-2xl border border-red-200 p-12 text-center">
          <AlertCircle className="h-12 w-12 text-red-500 mx-auto mb-3" />
          <h3 className="text-lg font-bold text-slate-800 mb-1">Failed to Load Scans</h3>
          <p className="text-sm text-slate-500 max-w-md mx-auto mb-6">
            We were unable to retrieve your scan history. Please check your network connection or verify your session.
          </p>
          <button
            type="button"
            onClick={fetchScans}
            className="inline-flex items-center gap-2 py-2 px-4 bg-red-600 text-white rounded-lg text-sm font-medium hover:bg-red-700 transition-colors cursor-pointer"
          >
            <RotateCcw className="h-4 w-4" />
            <span>Try Again</span>
          </button>
        </div>
      ) : filteredScans.length === 0 ? (
        <div className="bg-white rounded-2xl border border-slate-200 p-12 text-center">
          <FileText className="h-12 w-12 text-slate-300 mx-auto mb-3" />
          <h3 className="text-lg font-bold text-slate-800 mb-1">No Scans Found</h3>
          <p className="text-sm text-slate-500 max-w-md mx-auto mb-6">
            {filterType !== 'ALL'
              ? `No scans matching filter "${formatTypeName(filterType)}".`
              : "You haven't performed any verification scans yet. Analyze a job description, URL, recruiter email, or offer letter to build your verification record."}
          </p>
          <Link
            to="/analyze"
            className="inline-flex items-center gap-2 py-2 px-4 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors"
          >
            <span>Start Your First Analysis</span>
            <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      ) : (
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-slate-600">
              <thead className="bg-slate-50 border-b border-slate-200 text-xs font-semibold text-slate-500 uppercase tracking-wider">
                <tr>
                  <th scope="col" className="px-6 py-3.5">Type &amp; Subject</th>
                  <th scope="col" className="px-6 py-3.5">Claimed Company</th>
                  <th scope="col" className="px-6 py-3.5">Risk Level</th>
                  <th scope="col" className="px-6 py-3.5">Date</th>
                  <th scope="col" className="px-6 py-3.5 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredScans.map((scan) => (
                  <tr key={scan.id} className="hover:bg-slate-50/70 transition-colors">
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-3">
                        <div className="p-2 rounded-lg bg-slate-100 shrink-0">
                          {getTypeIcon(scan.input_type)}
                        </div>
                        <div>
                          <div className="font-semibold text-slate-900">
                            {formatTypeName(scan.input_type)}
                          </div>
                          <div className="text-xs text-slate-400 font-mono">
                            {scan.id.slice(0, 8)}...
                          </div>
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="text-slate-800 font-medium">
                        {scan.claimed_company_name || scan.input_reference || 'Not specified'}
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <RiskIndicator
                        riskScore={scan.risk_score ?? scan.composite_risk_score ?? 0}
                        riskCategory={scan.risk_category || 'LOW'}
                        compact
                      />
                    </td>
                    <td className="px-6 py-4 text-xs text-slate-500 whitespace-nowrap">
                      {new Date(scan.created_at).toLocaleDateString(undefined, {
                        year: 'numeric',
                        month: 'short',
                        day: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </td>
                    <td className="px-6 py-4 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          type="button"
                          onClick={() => handleDownloadPdf(scan.id)}
                          disabled={downloadingId === scan.id}
                          className="p-1.5 text-blue-600 hover:text-blue-800 hover:bg-blue-50 rounded-lg transition-colors cursor-pointer"
                          title="Download Evidence-Based PDF Report"
                          aria-label={`Download PDF report for scan ${scan.id}`}
                        >
                          {downloadingId === scan.id ? (
                            <Loader2 className="h-4 w-4 animate-spin text-blue-600" />
                          ) : (
                            <Download className="h-4 w-4" />
                          )}
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDeleteScan(scan.id)}
                          disabled={deletingId === scan.id}
                          className="p-1.5 text-red-500 hover:text-red-700 hover:bg-red-50 rounded-lg transition-colors cursor-pointer"
                          title="Delete Scan from History"
                          aria-label={`Delete scan ${scan.id}`}
                        >
                          {deletingId === scan.id ? (
                            <Loader2 className="h-4 w-4 animate-spin text-red-600" />
                          ) : (
                            <Trash2 className="h-4 w-4" />
                          )}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
