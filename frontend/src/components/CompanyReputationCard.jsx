import React, { useState, useEffect, useCallback } from 'react';
import {
  Star,
  AlertTriangle,
  Users,
  MessageSquare,
  AlertOctagon,
  ChevronDown,
  ChevronUp,
  Loader2,
  HelpCircle,
} from 'lucide-react';
import { api } from '../services/api';
import ReviewModal from './ReviewModal';
import ReportModal from './ReportModal';

export default function CompanyReputationCard({
  companyId,
  companyName,
  recruiterEmail,
  scanId,
  className = '',
}) {
  const [reputation, setReputation] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const [isReviewModalOpen, setIsReviewModalOpen] = useState(false);
  const [isReportModalOpen, setIsReportModalOpen] = useState(false);
  const [showRecentReviews, setShowRecentReviews] = useState(false);

  const fetchReputation = useCallback(async () => {
    if (!companyId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api.getCompanyReputation(companyId);
      setReputation(data);
    } catch (err) {
      setError(err.message || 'Unable to load company reputation data.');
    } finally {
      setLoading(false);
    }
  }, [companyId]);

  useEffect(() => {
    let active = true;
    if (companyId) {
      api.getCompanyReputation(companyId)
        .then((data) => {
          if (active) {
            setReputation(data);
            setLoading(false);
          }
        })
        .catch((err) => {
          if (active) {
            setError(err.message || 'Unable to load company reputation data.');
            setLoading(false);
          }
        });
    }
    return () => {
      active = false;
    };
  }, [companyId]);

  const bayesianRating = reputation?.bayesian_rating ?? 3.5;
  const totalReviews = reputation?.total_approved_reviews ?? 0;
  const confidenceScore = reputation?.confidence_score ?? 0;
  const confidencePct = Math.round(confidenceScore * 100);
  const rawMean = reputation?.raw_mean_rating;
  const distribution = reputation?.rating_distribution || { '1': 0, '2': 0, '3': 0, '4': 0, '5': 0 };
  const fraudReportsCount = reputation?.fraud_reports_count ?? 0;
  const fraudByType = reputation?.fraud_reports_by_type || {};

  return (
    <div className={`rounded-xl border border-slate-200 bg-white p-5 space-y-4 shadow-2xs ${className}`}>
      {/* Header */}
      <div className="flex items-center justify-between pb-3 border-b border-slate-100">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-amber-50 text-amber-600">
            <Users className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-slate-800">
              Community Reputation & Service Ratings
            </h3>
            <p className="text-[11px] text-slate-500">
              {companyName ? `Independent feedback for ${companyName}` : 'Aggregated community experience ratings'}
            </p>
          </div>
        </div>
        <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-600">
          Bayesian-Damped
        </span>
      </div>

      {loading ? (
        <div className="py-6 flex flex-col items-center justify-center gap-2 text-slate-500 text-xs">
          <Loader2 className="w-5 h-5 animate-spin text-blue-600" />
          <span>Loading verified community feedback...</span>
        </div>
      ) : error ? (
        <div className="p-3 rounded-lg bg-amber-50 border border-amber-200 text-amber-800 text-xs flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
            <span>{error}</span>
          </div>
          <button
            onClick={fetchReputation}
            className="text-xs font-semibold text-amber-900 underline hover:no-underline"
          >
            Retry
          </button>
        </div>
      ) : (
        <div className="space-y-4">
          {/* Main Bayesian Rating + Breakdown Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 items-center bg-slate-50/70 rounded-xl p-3.5 border border-slate-100">
            {/* Left: Star Rating & Prior Damping */}
            <div className="space-y-1.5">
              <div className="flex items-baseline gap-2">
                <span className="text-3xl font-bold tracking-tight text-slate-900">
                  {bayesianRating.toFixed(1)}
                </span>
                <span className="text-sm font-medium text-slate-500">/ 5.0</span>
              </div>
              <div className="flex items-center gap-1">
                {[1, 2, 3, 4, 5].map((star) => (
                  <Star
                    key={star}
                    className={`w-4 h-4 ${
                      bayesianRating >= star
                        ? 'fill-amber-400 text-amber-400'
                        : bayesianRating >= star - 0.5
                        ? 'fill-amber-200 text-amber-400'
                        : 'text-slate-300'
                    }`}
                  />
                ))}
                <span className="text-xs text-slate-500 ml-1">
                  ({totalReviews} {totalReviews === 1 ? 'review' : 'reviews'})
                </span>
              </div>
              <p className="text-[10px] text-slate-500 leading-tight">
                Bayesian adjusted (prior mean = 3.5, strength = 5.0) to prevent small-sample volatility.
                {rawMean !== null && rawMean !== undefined && ` Raw sample mean: ${rawMean.toFixed(1)}.`}
              </p>
            </div>

            {/* Right: Heuristic Confidence & Coverage Meter */}
            <div className="space-y-1.5 border-t sm:border-t-0 sm:border-l border-slate-200 pt-2 sm:pt-0 sm:pl-4">
              <div className="flex items-center justify-between text-xs font-medium text-slate-700">
                <span className="flex items-center gap-1">
                  Sample Confidence
                  <span
                    title="Empirical weight n / (n + m) reflecting the volume of verified reviews relative to the prior."
                    className="cursor-help text-slate-400"
                  >
                    <HelpCircle className="w-3.5 h-3.5 inline" />
                  </span>
                </span>
                <span className="font-semibold text-slate-800">{confidencePct}%</span>
              </div>
              <div className="w-full bg-slate-200 rounded-full h-2 overflow-hidden">
                <div
                  className="bg-blue-600 h-2 rounded-full transition-all duration-500"
                  style={{ width: `${Math.max(5, confidencePct)}%` }}
                />
              </div>
              <p className="text-[10px] text-slate-500 leading-tight">
                {totalReviews === 0
                  ? 'No reviews yet. Rating defaults conservatively to the platform prior.'
                  : `${totalReviews} approved submissions provide ${confidencePct}% empirical coverage.`}
              </p>
            </div>
          </div>

          {/* Star Distribution Histogram */}
          {totalReviews > 0 && (
            <div className="space-y-1 pt-1">
              <span className="text-[11px] font-semibold text-slate-700 block">Rating Distribution</span>
              <div className="space-y-1">
                {[5, 4, 3, 2, 1].map((stars) => {
                  const count = distribution[String(stars)] || 0;
                  const pct = totalReviews > 0 ? Math.round((count / totalReviews) * 100) : 0;
                  return (
                    <div key={stars} className="flex items-center gap-2 text-[11px] text-slate-600">
                      <span className="w-7 text-right font-medium">{stars} ★</span>
                      <div className="flex-1 bg-slate-100 rounded-full h-1.5 overflow-hidden">
                        <div
                          className="bg-amber-400 h-1.5 rounded-full"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                      <span className="w-6 text-right text-[10px] text-slate-400">{count}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* MANDATORY STRICT SEPARATION: Fraud Allegations / Recruiter Reports */}
          <div className="rounded-lg border border-rose-200 bg-rose-50/60 p-3 space-y-1.5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <AlertOctagon className="w-4 h-4 text-rose-600" />
                <span className="text-xs font-semibold text-rose-900">
                  Recruiter Fraud Allegations ({fraudReportsCount})
                </span>
              </div>
              {fraudReportsCount > 0 && (
                <span className="text-[10px] font-semibold uppercase tracking-wider text-rose-700 bg-rose-100/80 px-2 py-0.5 rounded-sm">
                  Active Reports
                </span>
              )}
            </div>

            <p className="text-[11px] text-rose-800 leading-relaxed">
              {fraudReportsCount === 0
                ? 'No active fraud allegations or fee-demand reports logged for this entity.'
                : `${fraudReportsCount} independent report(s) alleging fraud, fake offers, or upfront payment demands.`}
            </p>

            {Object.keys(fraudByType).length > 0 && (
              <div className="flex flex-wrap gap-1.5 pt-1">
                {Object.entries(fraudByType).map(([type, cnt]) => (
                  <span
                    key={type}
                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-white border border-rose-200 text-[10px] text-rose-800 font-medium"
                  >
                    <span>{type.replace(/_/g, ' ')}:</span>
                    <strong className="text-rose-900">{cnt}</strong>
                  </span>
                ))}
              </div>
            )}

            <div className="text-[10px] text-slate-500 italic pt-1 border-t border-rose-100">
              * Safety Mandate: Fraud reports are investigated separately and do not alter 1-5 star service metrics or determine mathematical risk scores.
            </div>
          </div>

          {/* Recent Reviews (Collapsible) */}
          {reputation?.recent_reviews?.length > 0 && (
            <div className="pt-1 border-t border-slate-100">
              <button
                type="button"
                onClick={() => setShowRecentReviews(!showRecentReviews)}
                className="flex items-center justify-between w-full py-1 text-xs font-medium text-slate-700 hover:text-slate-900"
              >
                <span>Recent Community Reviews ({reputation.recent_reviews.length})</span>
                {showRecentReviews ? (
                  <ChevronUp className="w-3.5 h-3.5 text-slate-400" />
                ) : (
                  <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
                )}
              </button>

              {showRecentReviews && (
                <div className="space-y-2 mt-2 pt-2 border-t border-slate-100">
                  {reputation.recent_reviews.map((rev) => (
                    <div key={rev.id} className="p-2.5 rounded-lg bg-slate-50 border border-slate-100 space-y-1 text-xs">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-1.5">
                          <div className="flex">
                            {[1, 2, 3, 4, 5].map((s) => (
                              <Star
                                key={s}
                                className={`w-3 h-3 ${
                                  rev.rating >= s ? 'fill-amber-400 text-amber-400' : 'text-slate-300'
                                }`}
                              />
                            ))}
                          </div>
                          <span className="text-[10px] font-semibold text-slate-700 uppercase tracking-wider">
                            {rev.category.replace(/_/g, ' ')}
                          </span>
                        </div>
                        <span className="text-[10px] text-slate-400">
                          {new Date(rev.created_at).toLocaleDateString()}
                        </span>
                      </div>
                      {rev.review_text && (
                        <p className="text-slate-700 text-xs italic">
                          "{rev.review_text}"
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Action Triggers */}
          <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-slate-100">
            <button
              type="button"
              onClick={() => setIsReviewModalOpen(true)}
              className="flex-1 min-w-[140px] px-3 py-2 text-xs font-medium text-blue-700 bg-blue-50 hover:bg-blue-100 rounded-lg transition-colors flex items-center justify-center gap-1.5"
            >
              <MessageSquare className="w-3.5 h-3.5" />
              <span>Rate Experience</span>
            </button>

            <button
              type="button"
              onClick={() => setIsReportModalOpen(true)}
              className="flex-1 min-w-[140px] px-3 py-2 text-xs font-medium text-rose-700 bg-rose-50 hover:bg-rose-100 rounded-lg transition-colors flex items-center justify-center gap-1.5"
            >
              <AlertOctagon className="w-3.5 h-3.5" />
              <span>Report Suspicious Recruiter</span>
            </button>
          </div>
        </div>
      )}

      {/* Review Modal */}
      <ReviewModal
        isOpen={isReviewModalOpen}
        onClose={() => setIsReviewModalOpen(false)}
        companyId={companyId}
        companyName={companyName}
        recruiterEmail={recruiterEmail}
        scanId={scanId}
        onSuccess={fetchReputation}
      />

      {/* Report Modal */}
      <ReportModal
        isOpen={isReportModalOpen}
        onClose={() => setIsReportModalOpen(false)}
        companyId={companyId}
        companyName={companyName}
        recruiterEmail={recruiterEmail}
        scanId={scanId}
        onSuccess={fetchReputation}
      />
    </div>
  );
}
