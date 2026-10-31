import React from 'react';
import { Link } from 'react-router-dom';
import { AlertCircle, Shield } from 'lucide-react';

export function Footer() {
  return (
    <footer className="bg-slate-900 text-slate-300 mt-auto border-t border-slate-800">
      {/* Top Warning Banner */}
      <div className="bg-slate-950/80 border-b border-slate-800 py-3 px-4">
        <div className="max-w-7xl mx-auto flex items-center justify-center gap-2 text-xs text-amber-300 text-center font-medium">
          <AlertCircle className="h-4 w-4 flex-shrink-0" aria-hidden="true" />
          <span>
            <strong>Decision-Support Notice:</strong> Verification results and risk signals provide evidentiary decision support to aid job seekers and do not constitute a definitive legal finding.
          </span>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-8">
          <div className="md:col-span-2 space-y-3">
            <div className="flex items-center gap-2 text-white font-bold text-lg">
              <Shield className="h-5 w-5 text-blue-400" aria-hidden="true" />
              <span>JobShield AI</span>
            </div>
            <p className="text-sm text-slate-400 leading-relaxed max-w-md">
              Explainable AI-Powered Job & Internship Verification Platform. Combining machine-learning text classification, multi-source company registries (MCA / Startup India), and domain checks to safeguard job seekers.
            </p>
          </div>

          <div>
            <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Platform</h4>
            <ul className="space-y-2 text-sm">
              <li>
                <Link to="/" className="hover:text-white transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-blue-400 rounded">
                  Home
                </Link>
              </li>
              <li>
                <Link to="/analyze" className="hover:text-white transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-blue-400 rounded">
                  Analyze Posting
                </Link>
              </li>
              <li>
                <Link to="/results" className="hover:text-white transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-blue-400 rounded">
                  Analysis Results
                </Link>
              </li>
            </ul>
          </div>

          <div>
            <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Principles & Governance</h4>
            <ul className="space-y-2 text-sm">
              <li>
                <Link to="/about" className="hover:text-white transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-blue-400 rounded">
                  About the Project
                </Link>
              </li>
              <li>
                <Link to="/about#disclaimer" className="hover:text-white transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-blue-400 rounded">
                  Legal Disclaimer
                </Link>
              </li>
              <li>
                <Link to="/about#principles" className="hover:text-white transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-blue-400 rounded">
                  Product Principles
                </Link>
              </li>
            </ul>
          </div>
        </div>

        <div className="mt-8 pt-6 border-t border-slate-800 text-xs text-slate-500 flex flex-col sm:flex-row justify-between items-center gap-2">
          <span>&copy; {new Date().getFullYear()} JobShield AI. Built for responsible and evidence-backed verification.</span>
          <span>Never pay upfront application or training fees for any job offer.</span>
        </div>
      </div>
    </footer>
  );
}

export default Footer;
