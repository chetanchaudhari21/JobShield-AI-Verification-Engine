import { describe, it, expect } from 'vitest';
import React from 'react';
import { renderToString } from 'react-dom/server';
import CompanyReputationCard from '../../components/CompanyReputationCard';
import ReviewModal from '../../components/ReviewModal';
import ReportModal from '../../components/ReportModal';

describe('Community Reputation & Feedback (F8 & F9) UI Components', () => {
  it('renders CompanyReputationCard with Bayesian score and confidence elements', () => {
    const html = renderToString(
      <CompanyReputationCard
        companyId={42}
        companyName="Tata Consultancy Services Limited"
        scanId="test-scan-uuid-123"
      />
    );

    // Verify Bayesian reputation header and badge
    expect(html).toContain('Community Reputation &amp; Service Ratings');
    expect(html).toContain('Bayesian-Damped');
    expect(html).toContain('Tata Consultancy Services Limited');

    // Verify Bayesian rating and prior parameters explanation
    expect(html).toContain('Bayesian adjusted (prior mean = 3.5, strength = 5.0)');
    expect(html).toContain('Sample Confidence');

    // Verify strict separation of fraud allegations
    expect(html).toContain('Recruiter Fraud Allegations');
    expect(html).toContain('Safety Mandate: Fraud reports are investigated separately');

    // Verify action buttons
    expect(html).toContain('Rate Experience');
    expect(html).toContain('Report Suspicious Recruiter');
  });

  it('renders ReviewModal with 1-5 star selector, categories, and mandatory privacy notice', () => {
    const html = renderToString(
      <ReviewModal
        isOpen={true}
        onClose={() => {}}
        companyId={42}
        companyName="Infosys Limited"
      />
    );

    expect(html).toContain('Rate Recruitment Experience');
    expect(html).toContain('Sharing feedback for Infosys Limited');

    // Mandatory Privacy & Security Notice
    expect(html).toContain('Privacy &amp; Security Notice');
    expect(html).toContain(
      'Do not include passwords, one-time passwords (OTPs), bank details, payment credentials, or other sensitive personal information in reviews or reports.'
    );

    // Rating and categories
    expect(html).toContain('Service Rating (1 to 5 Stars)');
    expect(html).toContain('General Experience');
    expect(html).toContain('Interview Process');
    expect(html).toContain('Recruiter Communication');
    expect(html).toContain('Submit Review');
  });

  it('renders ReportModal with report types and mandatory privacy warning', () => {
    const html = renderToString(
      <ReportModal
        isOpen={true}
        onClose={() => {}}
        companyId={42}
        companyName="Fake Recruiter Corp"
      />
    );

    expect(html).toContain('Report Suspicious Recruiter Activity');
    expect(html).toContain('Reporting allegation regarding Fake Recruiter Corp');

    // Mandatory Privacy Warning
    expect(html).toContain('Privacy &amp; Security Notice');
    expect(html).toContain(
      'Do not include passwords, one-time passwords (OTPs), bank details, payment credentials, or other sensitive personal information in reviews or reports.'
    );

    // Types
    expect(html).toContain('Fake or Unsolicited Job Offer');
    expect(html).toContain('Upfront Fee / Security Deposit Demand');
    expect(html).toContain('Recruiter / Company Brand Impersonation');
    expect(html).toContain('Submit Fraud Report');
  });
});
