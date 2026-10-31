import React from 'react';
import { AlertCircle, RefreshCw } from 'lucide-react';

export function ErrorState({
  title = 'Service Error Encountered',
  message = 'Unable to reach the JobShield AI backend service. Please check your connection.',
  onRetry = null,
}) {
  return (
    <div
      role="alert"
      className="rounded-xl border border-rose-300 bg-rose-50 p-6 text-rose-950 shadow-sm"
    >
      <div className="flex items-start gap-3">
        <AlertCircle className="h-6 w-6 text-rose-700 flex-shrink-0 mt-0.5" aria-hidden="true" />
        <div className="flex-1">
          <h3 className="font-semibold text-base text-rose-950">{title}</h3>
          <p className="mt-1 text-sm text-rose-800 leading-relaxed">{message}</p>
          {onRetry && (
            <button
              type="button"
              onClick={onRetry}
              className="mt-3 inline-flex items-center gap-1.5 px-3.5 py-1.5 bg-rose-700 hover:bg-rose-800 text-white text-xs font-semibold rounded-lg shadow transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-500"
            >
              <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
              Retry Request
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export default ErrorState;
