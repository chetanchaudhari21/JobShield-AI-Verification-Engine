import { describe, it, expect } from 'vitest';
import React from 'react';
import { renderToString } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { Analyze } from '../Analyze';
import { Results } from '../Results';

describe('Offer Letter Tab & PDF Analysis Rendering (Feature F7)', () => {
  it('renders Offer Letter (PDF) tab as Active with no lock icon', () => {
    const html = renderToString(
      <MemoryRouter>
        <Analyze />
      </MemoryRouter>
    );

    expect(html).toContain('Offer Letter (PDF)');
    expect(html).toContain('tab-offer-letter');
    expect(html).not.toContain('Phase 4');
  });

  it('renders Results page with Offer Letter Contract Terms, Fee Demand Callout, and Domain Checks', () => {
    const offerAnalysisResult = {
      report_id: 'test-offer-report-777',
      risk_score: 95.0,
      risk_category: 'CRITICAL',
      warning: 'Caution: This offer letter contains advance fee demands and unverified contact domains.',
      timestamp: '2026-10-15T00:00:00Z',
      file_name: 'tcs_appointment_letter.pdf',
      file_size_bytes: 45000,
      page_count: 2,
      is_scanned: false,
      ocr_applied: false,
      ocr_engine: null,
      summary: 'High-risk offer letter identified with advance laptop deposit requirement.',
      extracted_fields: {
        company_name: {
          value: 'Tata Consultancy Services Limited',
          page: 1,
          confidence: 0.95,
          snippet: 'Tata Consultancy Services Limited hereby appoints...',
          is_present: true,
        },
        candidate_name: {
          value: 'J*** D***',
          page: 1,
          confidence: 0.9,
          snippet: 'Dear J*** D***, we are pleased to offer...',
          is_present: true,
        },
        job_title: {
          value: 'Senior Systems Engineer',
          page: 1,
          confidence: 0.95,
          snippet: 'Role: Senior Systems Engineer',
          is_present: true,
        },
        salary_compensation: {
          value: '₹12,00,000 per annum',
          page: 1,
          confidence: 0.95,
          snippet: 'Total CTC: ₹12,00,000 per annum',
          is_present: true,
        },
        offer_date: {
          value: '15-10-2026',
          page: 1,
          confidence: 0.9,
          snippet: 'Date: 15-10-2026',
          is_present: true,
        },
        joining_date: {
          value: '01-11-2026',
          page: 1,
          confidence: 0.9,
          snippet: 'Date of joining: 01-11-2026',
          is_present: true,
        },
        deadline_date: {
          value: '20-10-2026',
          page: 2,
          confidence: 0.85,
          snippet: 'Accept by: 20-10-2026',
          is_present: true,
        },
        recruiter_contacts: ['hr@tcs-careers-portal.com', '+91 98765 43210'],
        domains_or_urls: ['tcs-careers-portal.com'],
        company_address: {
          value: 'TCS House, Raveline Street, Fort, Mumbai 400001',
          page: 1,
          confidence: 0.9,
          snippet: 'Registered Office: TCS House, Raveline Street, Fort, Mumbai 400001',
          is_present: true,
        },
        fee_demands: [
          {
            category: 'SECURITY_DEPOSIT',
            amount: '₹10,000',
            clause_text: 'A mandatory refundable security deposit of ₹10,000 must be paid prior to laptop hardware dispatch.',
            page: 2,
            is_refundable_claimed: true,
            warning: 'Legitimate employers never demand refundable equipment deposits.',
          },
        ],
        sensitive_requests: [
          {
            request_type: 'BANK_ACCOUNT_DETAILS',
            clause_text: 'Submit netbanking password and OTP to activate payroll account.',
            page: 2,
            warning: 'Never disclose banking passwords or OTPs.',
          },
        ],
        has_fee_demand: true,
        has_sensitive_request: true,
        raw_character_count: 1500,
      },
      company_verification: {
        status: 'MATCHED',
        queried_name: 'Tata Consultancy Services Limited',
        matched_name: 'TATA CONSULTANCY SERVICES LIMITED',
        cin: 'L22210MH1995PLC084781',
        mca_status: 'ACTIVE',
        confidence: 1.0,
        match_type: 'EXACT',
        limitations: 'MCA registration corroborates entity existence only; it does not authenticate individual employment offers.',
      },
      domain_checks: [
        {
          domain: 'tcs-careers-portal.com',
          dns_status: 'PASS',
          mx_status: 'PASS',
          spf_status: 'PASS',
          dkim_status: 'SELECTOR_NOT_FOUND',
          dmarc_status: 'PASS',
          source_details: { dmarc_policy: 'none' },
          lookalike_flags: {
            is_lookalike: true,
            matched_legitimate_domain: 'tcs.com',
            similarity_type: 'brand_prefix_suffix_spoof',
            confidence: 0.9,
            warning: "Lookalike domain: 'tcs-careers-portal.com' mimics verified brand 'tcs.com'.",
          },
          summary: "Contact domain security checks for 'tcs-careers-portal.com': DNS PASS, MX PASS, SPF PASS.",
          limitations: 'Infrastructure parameters do not prove individual vacancy authorization.',
        },
      ],
      evidence: [],
      recommended_safe_actions: [
        'Never transfer funds for laptop deposits, registration fees, or onboarding training.',
        'Contact the employer directly through their official career portal at tcs.com.',
      ],
      limitations: [
        'Automated document parsing is heuristic and does not constitute formal legal verification.',
      ],
      disclaimer: 'Informational analysis only.',
    };

    const locationMock = {
      state: {
        analysisResult: offerAnalysisResult,
        jobText: '',
        claimedCompany: 'Tata Consultancy Services Limited',
        claimedCin: 'L22210MH1995PLC084781',
        jobTitle: 'Senior Systems Engineer',
        fileName: 'tcs_appointment_letter.pdf',
      },
    };

    // Vitest mock for useLocation
    const html = renderToString(
      <MemoryRouter initialEntries={[{ pathname: '/results', state: locationMock.state }]}>
        <Results />
      </MemoryRouter>
    );

    // Verify document metadata
    expect(html).toContain('tcs_appointment_letter.pdf');
    expect(html).toContain('43.9');
    expect(html).toContain('KB');
    expect(html).toContain('Direct PDF Text');
    expect(html).toContain('Zero Retention Active');

    // Verify Offer Letter Extracted Terms Section
    expect(html).toContain('Offer Letter Analysis &amp; Extracted Contract Terms (Feature F7)');
    expect(html).toContain('FEE DEMANDS IDENTIFIED');
    expect(html).toContain('Advance Fee Demand Detected');
    expect(html).toContain('SECURITY DEPOSIT');
    expect(html).toContain('₹10,000');
    expect(html).toContain('False refundability promise');
    expect(html).toContain('Sensitive Information or Document Request');
    expect(html).toContain('BANK ACCOUNT DETAILS');

    // Verify Extracted Contract Terms Grid
    expect(html).toContain('Tata Consultancy Services Limited');
    expect(html).toContain('J*** D***');
    expect(html).toContain('Senior Systems Engineer');
    expect(html).toContain('₹12,00,000 per annum');
    expect(html).toContain('15-10-2026');
    expect(html).toContain('01-11-2026');
    expect(html).toContain('hr@tcs-careers-portal.com');

    // Verify Contact Domain Infrastructure Checks
    expect(html).toContain('tcs-careers-portal.com');
    expect(html).toContain('LOOKALIKE DOMAIN');

    // Verify Zero Retention and Privacy Audit Note
    expect(html).toContain('Audit Record &amp; Zero Retention Verification');
  });
});
