import React from 'react';
import { Shield, BookOpen, AlertCircle, CheckCircle2, Scale, ExternalLink } from 'lucide-react';

export function About() {
  const principles = [
    {
      title: 'Evidence First',
      desc: 'Every assessment shows why it was produced, identifying the exact source name, check timestamp, and technical limitations.',
    },
    {
      title: 'No Unsupported Accusations',
      desc: 'A machine-learning score, low community rating, or unverified domain is not definitive proof of fraud.',
    },
    {
      title: 'Unknown is Not Fraudulent',
      desc: 'A missing registry match or unavailable company website is marked as unverified or unknown, never automatically flagged as a scam.',
    },
    {
      title: 'Separate Facts from Predictions',
      desc: 'Official MCA registry records, technical DNS checks, ML probabilities, and user allegations are visibly separated into distinct categories.',
    },
    {
      title: 'Explain Uncertainty',
      desc: 'A low risk score does not prove a job is genuine. A high score is a recommendation for manual verification, not a criminal conclusion.',
    },
    {
      title: 'Privacy by Design',
      desc: 'JobShield AI minimizes personal data collection, never stores sensitive financial credentials, and excludes private offer letters from public datasets.',
    },
  ];

  return (
    <div className="max-w-4xl mx-auto py-8 px-4 sm:px-6 lg:px-8 space-y-12">
      {/* Page Title */}
      <div className="space-y-3">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-blue-50 border border-blue-200 text-blue-800 text-xs font-semibold">
          <BookOpen className="h-3.5 w-3.5" aria-hidden="true" />
          <span>Product Architecture & Ethics</span>
        </div>
        <h1 className="text-3xl sm:text-4xl font-extrabold text-slate-900 tracking-tight">
          About JobShield AI
        </h1>
        <p className="text-base text-slate-600 leading-relaxed">
          An explainable AI platform designed to empower job seekers, students, and interns by assessing recruitment offers against verifiable corporate registries, domain records, and machine learning pattern classifiers.
        </p>
      </div>

      {/* Product Principles (Section 2.3 of spec) */}
      <section id="principles" aria-labelledby="principles-heading" className="space-y-6">
        <h2 id="principles-heading" className="text-2xl font-bold text-slate-900 border-b border-slate-200 pb-3">
          Ethical & Technical Product Principles
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {principles.map((p, idx) => (
            <div
              key={idx}
              className="rounded-xl border border-slate-200 bg-white p-5 space-y-2 shadow-xs"
            >
              <div className="flex items-center gap-2 text-blue-700 font-bold text-sm">
                <CheckCircle2 className="h-4 w-4 flex-shrink-0" aria-hidden="true" />
                <span>{p.title}</span>
              </div>
              <p className="text-xs sm:text-sm text-slate-600 leading-relaxed">
                {p.desc}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* Data Sources and Provenance */}
      <section aria-labelledby="datasources-heading" className="space-y-4">
        <h2 id="datasources-heading" className="text-2xl font-bold text-slate-900 border-b border-slate-200 pb-3">
          Verification Data Sources
        </h2>
        <div className="space-y-3 text-sm text-slate-600 leading-relaxed">
          <p>
            JobShield AI connects with independent, publicly accessible repositories to verify corporate presence:
          </p>
          <ul className="list-disc list-inside space-y-2 pl-2">
            <li>
              <strong>Ministry of Corporate Affairs (MCA) Company Master Data:</strong> Corporate Identity Numbers (CIN), legal names, and registration status from official public catalogs.
            </li>
            <li>
              <strong>Startup India & DPIIT Registry:</strong> Recognition listings for registered Indian startups.
            </li>
            <li>
              <strong>Authoritative DNS & MX Infrastructure:</strong> Public mail exchange records, SPF/DKIM/DMARC email authentication records.
            </li>
          </ul>
        </div>
      </section>

      {/* Official Legal & Technical Disclaimer */}
      <section
        id="disclaimer"
        aria-labelledby="disclaimer-heading"
        className="rounded-2xl border-2 border-slate-300 bg-slate-100/80 p-6 space-y-4"
      >
        <div className="flex items-center gap-2 text-slate-900 font-bold text-lg">
          <Scale className="h-5 w-5 text-slate-700 flex-shrink-0" aria-hidden="true" />
          <h2 id="disclaimer-heading">Legal & Operational Disclaimer</h2>
        </div>

        <div className="text-xs sm:text-sm text-slate-700 leading-relaxed space-y-3">
          <p>
            <strong>Informational Decision Support Only:</strong> JobShield AI is an explainable decision-support platform designed to assist job seekers with preliminary verification. None of the risk scores, model evaluations, text extractions, or registry matches generated by this application constitute a formal, binding, or legal determination of fraud, deception, or legitimacy.
          </p>
          <p>
            <strong>No Guarantee of Accuracy:</strong> Registry records may be incomplete or out of date. Machine learning models produce probabilistic assessments based on training distributions and may produce false positives or false negatives.
          </p>
          <p>
            <strong>User Due Diligence:</strong> Users are advised to independently verify job offers directly through official employer domains, never send upfront monies or sensitive banking details, and report suspected criminal scams to appropriate local authorities or cybercrime portals.
          </p>
        </div>
      </section>
    </div>
  );
}

export default About;
