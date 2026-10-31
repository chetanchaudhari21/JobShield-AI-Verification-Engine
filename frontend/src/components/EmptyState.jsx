import React from 'react';
import { Inbox } from 'lucide-react';

export function EmptyState({
  title = 'No Data Available',
  description = 'No scans or verification records have been generated yet.',
  action = null,
}) {
  return (
    <div className="flex flex-col items-center justify-center p-8 rounded-xl bg-slate-50 border border-dashed border-slate-300 text-center">
      <div className="p-3 bg-white rounded-full border border-slate-200 shadow-xs mb-3">
        <Inbox className="h-6 w-6 text-slate-400" aria-hidden="true" />
      </div>
      <h3 className="font-semibold text-slate-900 text-base">{title}</h3>
      <p className="text-slate-500 text-sm max-w-sm mt-1 mb-4 leading-relaxed">{description}</p>
      {action}
    </div>
  );
}

export default EmptyState;
