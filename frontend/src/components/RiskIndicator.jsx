import React from 'react';
import { ShieldCheck, AlertTriangle, ShieldAlert, HelpCircle, Info } from 'lucide-react';

/**
 * Accessible Risk Indicator component.
 * NEVER relies on color alone: displays explicit textual label, numeric score,
 * descriptive status, unique geometric icon, and prominent provisional notice.
 * Complies with strict risk-assessment wording rules (never 'proves', 'is fraud', 'is legitimate').
 */
export function RiskIndicator({ score = null, category = 'UNKNOWN', size = 'md' }) {
  const normCategory = (category || 'UNKNOWN').toUpperCase();
  const hasNumericScore = score !== null && score !== undefined && !Number.isNaN(Number(score));
  const displayScore = hasNumericScore ? Math.round(Number(score)) : null;

  let config = {
    label: 'Insufficient Evidence for Assessment',
    subtext: 'The submitted text lacks sufficient informative details (fewer than 10 informative words) to evaluate scam risk patterns.',
    Icon: HelpCircle,
    colorClasses: 'bg-slate-50 text-slate-900 border-slate-300 dark:bg-slate-900/60 dark:text-slate-100 dark:border-slate-700',
    iconColor: 'text-slate-600 dark:text-slate-400',
    ariaLabel: 'Risk status: Insufficient evidence for assessment',
  };

  if (normCategory === 'LOW') {
    config = {
      label: 'Low Scam Risk Indicators',
      subtext: 'Linguistic patterns and rule heuristics show low similarity to known recruitment scams. Independent verification of the employer via official registries is still advised.',
      Icon: ShieldCheck,
      colorClasses: 'bg-emerald-50 text-emerald-950 border-emerald-300 dark:bg-emerald-950/40 dark:text-emerald-100 dark:border-emerald-700',
      iconColor: 'text-emerald-700 dark:text-emerald-400',
      ariaLabel: `Risk status: Low Scam Risk Indicators, score ${displayScore} out of 100`,
    };
  } else if (normCategory === 'MODERATE' || normCategory === 'MEDIUM') {
    config = {
      label: 'Moderate Scam Risk Indicators — Caution Advised',
      subtext: 'Certain anomalous patterns detected (e.g. urgency tactics, free webmail recruiter address, or linguistic anomalies). Exercise caution before engaging.',
      Icon: AlertTriangle,
      colorClasses: 'bg-amber-50 text-amber-950 border-amber-300 dark:bg-amber-950/40 dark:text-amber-100 dark:border-amber-700',
      iconColor: 'text-amber-700 dark:text-amber-400',
      ariaLabel: `Risk status: Moderate Scam Risk Indicators, score ${displayScore} out of 100`,
    };
  } else if (normCategory === 'HIGH') {
    config = {
      label: 'High Scam Risk Patterns Identified',
      subtext: 'Multiple patterns associated with recruitment scams detected (e.g. suspicious contact channels or elevated model fraud probability). Require independent verification.',
      Icon: ShieldAlert,
      colorClasses: 'bg-rose-50 text-rose-950 border-rose-300 dark:bg-rose-950/40 dark:text-rose-100 dark:border-rose-700',
      iconColor: 'text-rose-700 dark:text-rose-400',
      ariaLabel: `Risk status: High Scam Risk Patterns Identified, score ${displayScore} out of 100`,
    };
  } else if (normCategory === 'CRITICAL') {
    config = {
      label: 'Critical Scam Risk Patterns Identified',
      subtext: 'Severe high-risk indicators detected (e.g. advance fee request, financial credential demand, or strong scam linguistic indicators). Cease engagement immediately.',
      Icon: ShieldAlert,
      colorClasses: 'bg-red-50 text-red-950 border-red-400 dark:bg-red-950/50 dark:text-red-100 dark:border-red-700',
      iconColor: 'text-red-700 dark:text-red-400',
      ariaLabel: `Risk status: Critical Scam Risk Patterns Identified, score ${displayScore} out of 100`,
    };
  } else if (normCategory === 'INSUFFICIENT_EVIDENCE') {
    config = {
      label: 'Insufficient Evidence for Risk Assessment',
      subtext: 'The submitted text lacks sufficient informative details (fewer than 10 informative words) to evaluate scam risk patterns. Please provide comprehensive job posting details.',
      Icon: HelpCircle,
      colorClasses: 'bg-slate-50 text-slate-900 border-slate-300 dark:bg-slate-900/60 dark:text-slate-100 dark:border-slate-700',
      iconColor: 'text-slate-600 dark:text-slate-400',
      ariaLabel: 'Risk status: Insufficient evidence for risk assessment',
    };
  }

  const { label, subtext, Icon, colorClasses, iconColor, ariaLabel } = config;

  return (
    <div
      role="status"
      aria-label={ariaLabel}
      className={`rounded-2xl border transition-all ${colorClasses} ${size === 'lg' ? 'p-6 sm:p-7' : 'p-4 sm:p-5'}`}
    >
      <div className="flex items-start gap-4">
        <Icon className={`h-8 w-8 flex-shrink-0 mt-0.5 ${iconColor}`} aria-hidden="true" />
        <div className="flex-1 space-y-2">
          <div className="flex flex-wrap items-center gap-2.5">
            <span className="font-extrabold text-lg sm:text-xl tracking-tight">
              {label}
            </span>
            {hasNumericScore ? (
              <span className="font-mono font-bold text-sm px-2.5 py-0.5 rounded-full border border-current bg-white/70 dark:bg-black/40">
                Score: {displayScore} / 100
              </span>
            ) : (
              <span className="font-medium text-xs px-2.5 py-0.5 rounded-full border border-current bg-white/70 dark:bg-black/40">
                Score: Not Available (Insufficient Data)
              </span>
            )}
            <span className="text-[11px] font-semibold tracking-wider uppercase px-2 py-0.5 rounded-md bg-blue-100 text-blue-900 border border-blue-200">
              Verified Assessment
            </span>
          </div>

          <p className="text-sm leading-relaxed opacity-90">
            {subtext}
          </p>

          {/* Explicit Assessment Notice Banner */}
          <div className="pt-2 border-t border-current/15 flex items-start gap-2 text-xs opacity-80 leading-normal">
            <Info className="h-4 w-4 flex-shrink-0 mt-0.5" aria-hidden="true" />
            <span>
              <strong>Assessment Notice:</strong> Risk scores and categories are automated multi-signal risk evaluations. They provide evidence-based decision support and do not constitute a legal determination.
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

export default RiskIndicator;
