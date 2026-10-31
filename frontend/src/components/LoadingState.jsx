import React from 'react';
import { Loader2 } from 'lucide-react';

export function LoadingState({ message = 'Loading verification data...', detail = 'Please wait while we consult verification engines.' }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex flex-col items-center justify-center p-8 rounded-xl bg-white border border-slate-200 text-center shadow-sm"
    >
      <Loader2 className="h-8 w-8 text-blue-600 animate-spin mb-3" aria-hidden="true" />
      <span className="font-semibold text-slate-900 text-base">{message}</span>
      {detail && <span className="text-slate-500 text-sm mt-1">{detail}</span>}
      <span className="sr-only">Loading content, please wait</span>
    </div>
  );
}

export default LoadingState;
