import React, { useState } from 'react';
import { Star, X, AlertTriangle, CheckCircle2, Loader2, ShieldAlert } from 'lucide-react';
import { api } from '../services/api';

const CATEGORIES = [
  { value: 'GENERAL_EXPERIENCE', label: 'General Experience' },
  { value: 'INTERVIEW_PROCESS', label: 'Interview Process' },
  { value: 'COMMUNICATION', label: 'Recruiter Communication' },
  { value: 'OFFER_CLARITY', label: 'Offer Clarity & Terms' },
  { value: 'WORK_CULTURE', label: 'Work Culture & Role Scope' },
];

export default function ReviewModal({
  isOpen,
  onClose,
  companyId,
  companyName,
  recruiterEmail,
  scanId,
  onSuccess,
}) {
  const [rating, setRating] = useState(5);
  const [hoverRating, setHoverRating] = useState(0);
  const [category, setCategory] = useState('GENERAL_EXPERIENCE');
  const [reviewText, setReviewText] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(false);

  if (!isOpen) return null;

  async function handleSubmit(e) {
    e.preventDefault();
    setIsSubmitting(true);
    setError(null);

    try {
      await api.submitReview({
        company_id: companyId || undefined,
        company_name: companyName || undefined,
        recruiter_email: recruiterEmail || undefined,
        scan_id: scanId || undefined,
        rating,
        category,
        review_text: reviewText.trim() || undefined,
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
      setError(err.message || 'Failed to submit review. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs">
      <div className="w-full max-w-lg bg-white rounded-2xl shadow-2xl border border-slate-200 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 bg-slate-50 border-b border-slate-200">
          <div>
            <h3 className="text-base font-semibold text-slate-900">
              Rate Recruitment Experience
            </h3>
            <p className="text-xs text-slate-500">
              {companyName ? `Sharing feedback for ${companyName}` : 'Share your interview or recruitment feedback'}
            </p>
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
              <span>Thank you! Your feedback has been recorded.</span>
            </div>
          )}

          {/* 1-5 Star Picker */}
          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1.5">
              Service Rating (1 to 5 Stars)
            </label>
            <div className="flex items-center gap-1.5">
              {[1, 2, 3, 4, 5].map((star) => (
                <button
                  key={star}
                  type="button"
                  onClick={() => setRating(star)}
                  onMouseEnter={() => setHoverRating(star)}
                  onMouseLeave={() => setHoverRating(0)}
                  className="p-1 rounded-md transition-transform hover:scale-110 focus:outline-hidden"
                  aria-label={`${star} star`}
                >
                  <Star
                    className={`w-7 h-7 transition-colors ${
                      (hoverRating || rating) >= star
                        ? 'fill-amber-400 text-amber-400'
                        : 'text-slate-300'
                    }`}
                  />
                </button>
              ))}
              <span className="ml-2 text-sm font-semibold text-slate-700">
                {rating} / 5
              </span>
            </div>
          </div>

          {/* Category Dropdown */}
          <div>
            <label htmlFor="review-category" className="block text-xs font-semibold text-slate-700 mb-1.5">
              Experience Category
            </label>
            <select
              id="review-category"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="w-full text-xs rounded-lg border border-slate-300 px-3 py-2 bg-white text-slate-800 focus:outline-hidden focus:ring-2 focus:ring-blue-500"
            >
              {CATEGORIES.map((cat) => (
                <option key={cat.value} value={cat.value}>
                  {cat.label}
                </option>
              ))}
            </select>
          </div>

          {/* Constructive Review Text */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label htmlFor="review-text" className="text-xs font-semibold text-slate-700">
                Review Comments (Optional)
              </label>
              <span className="text-[10px] text-slate-400">{reviewText.length}/2000</span>
            </div>
            <textarea
              id="review-text"
              rows={4}
              maxLength={2000}
              value={reviewText}
              onChange={(e) => setReviewText(e.target.value)}
              placeholder="Describe your recruitment experience, interview format, professionalism, or offer clarity..."
              className="w-full text-xs rounded-lg border border-slate-300 p-3 text-slate-800 focus:outline-hidden focus:ring-2 focus:ring-blue-500 placeholder:text-slate-400"
            />
          </div>

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
              disabled={isSubmitting || success}
              className="px-5 py-2 text-xs font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-lg shadow-xs flex items-center gap-1.5 transition-colors disabled:opacity-50"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  <span>Submitting...</span>
                </>
              ) : (
                'Submit Review'
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
