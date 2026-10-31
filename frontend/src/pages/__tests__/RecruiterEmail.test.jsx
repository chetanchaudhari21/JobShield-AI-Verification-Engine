import { describe, it, expect } from 'vitest';
import React from 'react';
import { renderToString } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { Analyze } from '../Analyze';
import { Results } from '../Results';

describe('Recruiter Email Verification Frontend (Feature F4)', () => {
  it('renders Recruiter Email tab and form elements in Analyze page', () => {
    const html = renderToString(
      <MemoryRouter>
        <Analyze />
      </MemoryRouter>
    );

    // Tab button is present and Active
    expect(html).toContain('Recruiter Email');
    expect(html).toContain('tab-recruiter-email');
    expect(html).not.toContain('Phase 2');
  });

  it('renders Results page with corporate DOMAIN_MATCH and non-probing identity disclaimer', () => {
    const analysisResult = {
      report_id: 'test-email-report-001',
      risk_score: 12.5,
      risk_category: 'LOW',
      timestamp: '2026-10-15T00:00:00Z',
      email_masked: 'c***s@tcs.com',
      domain: 'tcs.com',
      email_status: 'DOMAIN_MATCH',
      is_free_email: false,
      extracted_title: 'Senior Systems Engineer',
      extracted_company: 'Tata Consultancy Services Limited',
      domain_check: {
        domain: 'tcs.com',
        dns_status: 'PASS',
        mx_status: 'PASS',
        spf_status: 'PASS',
        dkim_status: 'PASS',
        dmarc_status: 'PASS',
        source_details: {
          dmarc_policy: 'reject',
        },
        lookalike_flags: {
          is_lookalike: false,
        },
        summary: "Domain security checks for 'tcs.com': DNS PASS, MX PASS, SPF PASS, DMARC PASS.",
        limitations: 'Technical domain checks evaluate email and DNS infrastructure; they do not guarantee authorization of specific individuals.',
      },
      recruiter_checks: {
        status: 'DOMAIN_MATCH',
        detected_emails: ['c***s@tcs.com'],
        free_email_detected: false,
        summary: "Recruiter domain 'tcs.com' matches claimed employer 'Tata Consultancy Services Limited'.",
      },
      company_verification: {
        status: 'MATCHED',
        queried_name: 'Tata Consultancy Services Limited',
        matched_name: 'TATA CONSULTANCY SERVICES LIMITED',
        cin: 'L22210MH1995PLC084781',
        match_method: 'LEGAL_NAME_EXACT',
        match_confidence: 1.0,
        mca_status: 'Active',
        dpiit_status: 'NOT_LOADED',
        source: 'MCA_COMPANY_MASTER',
      },
      evidence: [],
      recommended_safe_actions: [
        "Verify communication directly via the employer's official careers portal.",
      ],
      limitations: [
        'A domain match indicates infrastructure alignment only; it does not prove the sender identity.',
      ],
      disclaimer: 'JobShield AI provides informational risk assessments.',
    };

    const html = renderToString(
      <MemoryRouter
        initialEntries={[
          {
            pathname: '/results',
            state: {
              analysisResult,
              claimedCompany: 'Tata Consultancy Services Limited',
              claimedCin: 'L22210MH1995PLC084781',
              jobTitle: 'Senior Systems Engineer',
              recruiterEmail: 'c***s@tcs.com',
            },
          },
        ]}
      >
        <Results />
      </MemoryRouter>
    );

    // 1. Header displays masked recruiter email
    expect(html).toContain('Recruiter Sender Address:');
    expect(html).toContain('c***s@tcs.com');
    expect(html).toContain('DOMAIN_MATCH');

    // 2. Domain Security Card renders with Recruiter header
    expect(html).toContain('Recruiter Domain Security &amp; Sender Auth');
    expect(html).toContain('Masked Sender Address:');
    expect(html).toContain('tcs.com');
    expect(html).toContain('DNS Resolution');
    expect(html).toContain('MX Mail Route');
    expect(html).toContain('SPF Record');
    expect(html).toContain('DMARC Policy');

    // 3. Sender Identity & Non-Probing Notice
    expect(html).toContain('Sender Identity &amp; Non-Probing Notice:');
    expect(html).toContain('infrastructure alignment only');
    expect(html).toContain('Mailbox existence is never probed');
  });

  it('renders Results page with FREE_EMAIL_PROVIDER alert for public webmail', () => {
    const freeEmailResult = {
      report_id: 'test-email-report-002',
      risk_score: 55.0,
      risk_category: 'MODERATE',
      warning: 'Caution: Recruiter used a public free webmail address (@gmail.com).',
      timestamp: '2026-10-15T00:00:00Z',
      email_masked: 'i***t@gmail.com',
      domain: 'gmail.com',
      email_status: 'FREE_EMAIL_PROVIDER',
      is_free_email: true,
      domain_check: {
        domain: 'gmail.com',
        dns_status: 'PASS',
        mx_status: 'PASS',
        spf_status: 'PASS',
        dkim_status: 'PASS',
        dmarc_status: 'PASS',
        lookalike_flags: { is_lookalike: false },
        summary: 'Free webmail provider domain.',
        limitations: 'Public email services do not indicate corporate employer affiliation.',
      },
      recruiter_checks: {
        status: 'FREE_EMAIL_PROVIDER',
        detected_emails: ['i***t@gmail.com'],
        free_email_detected: true,
        summary: 'Public webmail provider detected.',
      },
      company_verification: {
        status: 'MATCHED',
        queried_name: 'Infosys Limited',
        matched_name: 'INFOSYS LIMITED',
        cin: 'L85110KA1981PLC013115',
        mca_status: 'Active',
      },
      evidence: [],
      recommended_safe_actions: [
        'Request contact from the recruiter via an official corporate domain.',
      ],
      limitations: [],
      disclaimer: 'JobShield AI provides informational risk assessments.',
    };

    const html = renderToString(
      <MemoryRouter
        initialEntries={[
          {
            pathname: '/results',
            state: {
              analysisResult: freeEmailResult,
              claimedCompany: 'Infosys Limited',
              recruiterEmail: 'i***t@gmail.com',
            },
          },
        ]}
      >
        <Results />
      </MemoryRouter>
    );

    // Free webmail warnings
    expect(html).toContain('FREE_EMAIL_PROVIDER');
    expect(html).toContain('Public Free Webmail Provider Detected');
    expect(html).toContain('gmail.com');
  });

  it('renders Results page with MISMATCH_DETECTED alert when domain does not match claimed employer', () => {
    const mismatchResult = {
      report_id: 'test-email-report-003',
      risk_score: 65.0,
      risk_category: 'HIGH',
      timestamp: '2026-10-15T00:00:00Z',
      email_masked: 'r***r@random-unrelated.org',
      domain: 'random-unrelated.org',
      email_status: 'MISMATCH_DETECTED',
      is_free_email: false,
      domain_check: {
        domain: 'random-unrelated.org',
        dns_status: 'PASS',
        mx_status: 'PASS',
        spf_status: 'PASS',
        dkim_status: 'UNKNOWN',
        dmarc_status: 'NOT_FOUND',
        lookalike_flags: { is_lookalike: false },
        summary: 'Sender domain does not match claimed employer.',
      },
      recruiter_checks: {
        status: 'MISMATCH_DETECTED',
        detected_emails: ['r***r@random-unrelated.org'],
        free_email_detected: false,
        summary: 'Domain mismatch detected.',
      },
      company_verification: {
        status: 'MATCHED',
        queried_name: 'Tata Consultancy Services Limited',
        matched_name: 'TATA CONSULTANCY SERVICES LIMITED',
        cin: 'L22210MH1995PLC084781',
      },
      evidence: [],
      recommended_safe_actions: [],
      limitations: [],
      disclaimer: 'JobShield AI provides informational risk assessments.',
    };

    const html = renderToString(
      <MemoryRouter
        initialEntries={[
          {
            pathname: '/results',
            state: {
              analysisResult: mismatchResult,
              claimedCompany: 'Tata Consultancy Services Limited',
              recruiterEmail: 'r***r@random-unrelated.org',
            },
          },
        ]}
      >
        <Results />
      </MemoryRouter>
    );

    expect(html).toContain('MISMATCH_DETECTED');
    expect(html).toContain('Sender Domain &amp; Claimed Employer Mismatch');
  });
});
