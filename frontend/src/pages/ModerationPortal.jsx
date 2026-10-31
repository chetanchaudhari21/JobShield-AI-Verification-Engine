import React, { useState, useEffect, useCallback } from 'react';
import {
  ShieldAlert,
  CheckCircle2,
  XCircle,
  Flag,
  AlertTriangle,
  Loader2,
  Shield,
  AlertCircle,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { api } from '../services/api';

export default function ModerationPortal() {
  const { role, loading: authLoading } = useAuth();
  const isModeratorOrAdmin = role === 'MODERATOR' || role === 'ADMIN';

  const [activeTab, setActiveTab] = useState('queue'); // 'queue' | 'audit'
  const [queueItems, setQueueItems] = useState([]);
  const [auditItems, setAuditItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [actionSuccess, setActionSuccess] = useState(null);

  // Decision Modal State
  const [selectedItem, setSelectedItem] = useState(null);
  const [decisionNotes, setDecisionNotes] = useState('');
  const [decisionCategory, setDecisionCategory] = useState('');
  const [processingDecision, setProcessingDecision] = useState(false);

  const fetchQueue = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getModerationQueue({ limit: 50, offset: 0 });
      setQueueItems(data?.items || []);
    } catch (err) {
      setError(err.message || 'Failed to load moderation queue.');
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchAuditTrail = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getModerationAuditTrail({ limit: 50, offset: 0 });
      setAuditItems(data?.items || []);
    } catch (err) {
      setError(err.message || 'Failed to load moderation audit trail.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!authLoading && isModeratorOrAdmin) {
      if (activeTab === 'queue') {
        fetchQueue();
      } else if (activeTab === 'audit') {
        fetchAuditTrail();
      }
    } else if (!authLoading && !isModeratorOrAdmin) {
      setLoading(false);
    }
  }, [authLoading, isModeratorOrAdmin, activeTab, fetchQueue, fetchAuditTrail]);

  const handleApplyDecision = async (decision) => {
    if (!selectedItem) return;
    setProcessingDecision(true);
    setError(null);
    try {
      await api.submitModerationDecision({
        item_type: selectedItem.target_type,
        item_id: selectedItem.id,
        decision,
        notes: decisionNotes,
        reason_category: decisionCategory || undefined,
      });
      setActionSuccess(`Decision "${decision}" applied atomically with append-only audit trail.`);
      setSelectedItem(null);
      setDecisionNotes('');
      setDecisionCategory('');
      fetchQueue();
      setTimeout(() => setActionSuccess(null), 5000);
    } catch (err) {
      setError(err.message || 'Failed to submit moderation decision.');
    } finally {
      setProcessingDecision(false);
    }
  };

  if (authLoading) {
    return (
      <div className="max-w-5xl mx-auto px-4 py-16 flex items-center justify-center">
        <Loader2 className="h-8 w-8 text-blue-600 animate-spin" />
      </div>
    );
  }

  if (!isModeratorOrAdmin) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-16 text-center">
        <div className="bg-white rounded-2xl border border-red-200 p-8 shadow-sm">
          <ShieldAlert className="h-12 w-12 text-red-600 mx-auto mb-4" />
          <h1 className="text-2xl font-bold text-slate-900 mb-2">Access Restricted</h1>
          <p className="text-slate-600 text-sm mb-4">
            The Moderation Portal requires verified Moderator or Administrator privileges.
          </p>
          <span className="text-xs text-slate-400">
            Current role: {role || 'VISITOR'}
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200 pb-5">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="h-8 w-8 rounded-lg bg-indigo-50 text-indigo-700 flex items-center justify-center">
              <Shield className="h-5 w-5" />
            </div>
            <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight">Moderation Portal</h1>
            <span className="text-xs px-2.5 py-0.5 rounded-full font-bold bg-indigo-100 text-indigo-800">
              {role}
            </span>
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Review community submissions, resolve appeals, and maintain trusted intelligence
          </p>
        </div>

        {/* Training Label Invariant Callout */}
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 text-xs text-amber-900 max-w-md">
          <span className="font-semibold flex items-center gap-1.5 text-amber-800 mb-0.5">
            <AlertTriangle className="h-3.5 w-3.5 text-amber-600" />
            Training Isolation Invariant
          </span>
          Decisions taken here strictly manage community visibility and reputation. They <strong>never</strong> modify ML training labels or ground-truth datasets.
        </div>
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-red-50 border border-red-200 text-red-800 text-sm flex items-start gap-2.5">
          <AlertCircle className="h-5 w-5 text-red-600 shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {actionSuccess && (
        <div className="p-4 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-sm flex items-start gap-2.5">
          <CheckCircle2 className="h-5 w-5 text-emerald-600 shrink-0 mt-0.5" />
          <span>{actionSuccess}</span>
        </div>
      )}

      {/* Tabs */}
      <div className="flex border-b border-slate-200">
        <button
          type="button"
          onClick={() => setActiveTab('queue')}
          className={`px-5 py-3 text-sm font-semibold border-b-2 transition-colors cursor-pointer ${
            activeTab === 'queue'
              ? 'border-indigo-600 text-indigo-700'
              : 'border-transparent text-slate-500 hover:text-slate-800'
          }`}
        >
          Pending Review Queue ({queueItems.length})
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('audit')}
          className={`px-5 py-3 text-sm font-semibold border-b-2 transition-colors cursor-pointer ${
            activeTab === 'audit'
              ? 'border-indigo-600 text-indigo-700'
              : 'border-transparent text-slate-500 hover:text-slate-800'
          }`}
        >
          Append-Only Audit Trail
        </button>
      </div>

      {loading ? (
        <div className="py-16 text-center">
          <Loader2 className="h-8 w-8 text-indigo-600 animate-spin mx-auto mb-2" />
          <p className="text-sm text-slate-500">Loading moderation records...</p>
        </div>
      ) : activeTab === 'queue' ? (
        queueItems.length === 0 ? (
          <div className="bg-white rounded-2xl border border-slate-200 p-12 text-center">
            <CheckCircle2 className="h-12 w-12 text-emerald-500 mx-auto mb-3" />
            <h3 className="text-lg font-bold text-slate-800 mb-1">Queue Clear</h3>
            <p className="text-sm text-slate-500 max-w-md mx-auto">
              There are no pending community reviews or fraud reports awaiting moderation review.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {queueItems.map((item) => (
              <div
                key={`${item.target_type}-${item.id}`}
                className="bg-white rounded-xl border border-slate-200 p-5 shadow-xs hover:border-slate-300 transition-colors"
              >
                <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                  <div className="space-y-1.5 flex-1">
                    <div className="flex items-center gap-2">
                      <span className={`text-[11px] font-bold px-2.5 py-0.5 rounded-full uppercase tracking-wider ${
                        item.target_type === 'review'
                          ? 'bg-blue-100 text-blue-800'
                          : 'bg-amber-100 text-amber-800'
                      }`}>
                        {item.target_type === 'review' ? 'Service Review' : 'Fraud Incident Report'}
                      </span>
                      <span className="text-xs text-slate-400">
                        ID: {item.id.slice(0, 8)}...
                      </span>
                      <span className="text-xs text-slate-400">•</span>
                      <span className="text-xs text-slate-500">
                        {new Date(item.created_at).toLocaleString()}
                      </span>
                    </div>

                    <div className="text-slate-900 font-medium text-sm pt-1">
                      {item.text_snippet || <span className="text-slate-400 italic">No text provided</span>}
                    </div>

                    <div className="flex flex-wrap items-center gap-4 text-xs text-slate-500 pt-1">
                      {item.rating && (
                        <span>Rating: <strong>{item.rating} / 5</strong></span>
                      )}
                      {item.report_type && (
                        <span>Category: <strong>{item.report_type}</strong></span>
                      )}
                      {item.company_name && (
                        <span>Company: <strong>{item.company_name}</strong></span>
                      )}
                      {item.recruiter_email_masked && (
                        <span>Recruiter Email: <strong className="font-mono">{item.recruiter_email_masked}</strong></span>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-2 shrink-0 pt-2 sm:pt-0">
                    <button
                      type="button"
                      onClick={() => {
                        setSelectedItem(item);
                        setDecisionNotes('');
                        setDecisionCategory('');
                      }}
                      className="px-3.5 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-semibold shadow-xs transition-colors flex items-center gap-1.5 cursor-pointer"
                    >
                      <span>Take Action</span>
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )
      ) : (
        /* Audit Trail Tab */
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="p-4 bg-slate-50 border-b border-slate-200 flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-600 uppercase tracking-wider">
              Append-Only Security Audit Records ({auditItems.length})
            </span>
            <span className="text-xs text-slate-400 italic">
              Immutable logs with zero application-level edit/delete operations
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-slate-600">
              <thead className="bg-slate-100 border-b border-slate-200 text-xs font-semibold text-slate-500 uppercase tracking-wider">
                <tr>
                  <th scope="col" className="px-6 py-3">Timestamp</th>
                  <th scope="col" className="px-6 py-3">Moderator ID</th>
                  <th scope="col" className="px-6 py-3">Item Type &amp; ID</th>
                  <th scope="col" className="px-6 py-3">Decision</th>
                  <th scope="col" className="px-6 py-3">Notes &amp; Reason</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-mono text-xs">
                {auditItems.map((item) => (
                  <tr key={item.id} className="hover:bg-slate-50/70">
                    <td className="px-6 py-3.5 text-slate-500 whitespace-nowrap">
                      {new Date(item.created_at).toLocaleString()}
                    </td>
                    <td className="px-6 py-3.5 text-slate-800 font-medium">
                      {item.moderator_id}
                    </td>
                    <td className="px-6 py-3.5">
                      <span className="uppercase text-[11px] font-bold text-slate-600 block">
                        {item.item_type}
                      </span>
                      <span className="text-slate-400">
                        {item.item_id.slice(0, 10)}...
                      </span>
                    </td>
                    <td className="px-6 py-3.5">
                      <span className={`px-2 py-0.5 rounded-full font-bold text-[10px] uppercase ${
                        item.decision === 'APPROVED'
                          ? 'bg-emerald-100 text-emerald-800'
                          : item.decision === 'REJECTED'
                          ? 'bg-rose-100 text-rose-800'
                          : 'bg-amber-100 text-amber-800'
                      }`}>
                        {item.decision}
                      </span>
                    </td>
                    <td className="px-6 py-3.5 font-sans text-xs text-slate-600">
                      {item.notes || <span className="text-slate-400 italic">None</span>}
                      {item.reason_category && (
                        <span className="block text-[11px] text-slate-400">
                          Category: {item.reason_category}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Decision Modal */}
      {selectedItem && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs">
          <div className="bg-white rounded-2xl max-w-lg w-full p-6 shadow-xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <h3 className="font-bold text-base text-slate-900">
                Commit Moderation Decision
              </h3>
              <button
                type="button"
                onClick={() => setSelectedItem(null)}
                className="text-slate-400 hover:text-slate-600 text-lg leading-none p-1 cursor-pointer"
              >
                &times;
              </button>
            </div>

            <div className="text-xs text-slate-500 bg-slate-50 p-3 rounded-lg space-y-1">
              <div>Type: <strong>{selectedItem.target_type}</strong></div>
              <div>Item ID: <strong className="font-mono">{selectedItem.id}</strong></div>
              {selectedItem.text_snippet && <div>Snippet: &quot;{selectedItem.text_snippet}&quot;</div>}
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
                Reason Category (Optional)
              </label>
              <input
                type="text"
                value={decisionCategory}
                onChange={(e) => setDecisionCategory(e.target.value)}
                placeholder="e.g. SPAM, IMPERSONATION, VERIFIED_EVIDENCE"
                className="w-full px-3 py-2 text-xs rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
                Moderation Notes &amp; Rationale
              </label>
              <textarea
                rows={3}
                value={decisionNotes}
                onChange={(e) => setDecisionNotes(e.target.value)}
                placeholder="Explain the evidentiary basis for this moderation decision..."
                className="w-full px-3 py-2 text-xs rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>

            <div className="grid grid-cols-3 gap-2 pt-2">
              <button
                type="button"
                disabled={processingDecision}
                onClick={() => handleApplyDecision('APPROVED')}
                className="py-2.5 px-3 bg-emerald-600 hover:bg-emerald-700 text-white font-semibold text-xs rounded-lg shadow-xs flex items-center justify-center gap-1.5 cursor-pointer disabled:opacity-50"
              >
                <CheckCircle2 className="h-4 w-4" />
                <span>Approve</span>
              </button>
              <button
                type="button"
                disabled={processingDecision}
                onClick={() => handleApplyDecision('REJECTED')}
                className="py-2.5 px-3 bg-rose-600 hover:bg-rose-700 text-white font-semibold text-xs rounded-lg shadow-xs flex items-center justify-center gap-1.5 cursor-pointer disabled:opacity-50"
              >
                <XCircle className="h-4 w-4" />
                <span>Reject</span>
              </button>
              <button
                type="button"
                disabled={processingDecision}
                onClick={() => handleApplyDecision('FLAGGED')}
                className="py-2.5 px-3 bg-amber-500 hover:bg-amber-600 text-white font-semibold text-xs rounded-lg shadow-xs flex items-center justify-center gap-1.5 cursor-pointer disabled:opacity-50"
              >
                <Flag className="h-4 w-4" />
                <span>Flag</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
