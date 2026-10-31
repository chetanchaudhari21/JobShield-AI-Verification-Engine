import { describe, it, expect } from 'vitest';
import React from 'react';
import { renderToString } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { Analyze } from '../Analyze';
import { Results } from '../Results';

describe('Job URL Tab & Domain Security Rendering (Feature F3)', () => {
  it('renders Job URL tab as Active with no lock icon', () => {
    const html = renderToString(
      <MemoryRouter>
        <Analyze />
      </MemoryRouter>
    );

    // Job URL and Recruiter Email tabs exist and are marked Active
    expect(html).toContain('Job URL');
    expect(html).toContain('tab-job-url');
    expect(html).toContain('Recruiter Email');
    expect(html).toContain('tab-recruiter-email');
    // Offer letter tab exists and is marked Active (Feature F7)
    expect(html).toContain('Offer Letter (PDF)');
    expect(html).toContain('tab-offer-letter');
  });

  it('renders Results page with Domain Security Card and lookalike warning', () => {
    const urlAnalysisResult = {
      report_id: 'test-url-report-001',
      risk_score: 85.0,
      risk_category: 'CRITICAL',
      warning: "Caution: The job URL domain 'inf0sys-careers.com' closely mimics verified domain 'infosys.com'.",
      timestamp: '2026-10-15T00:00:00Z',
      job_url: 'https://inf0sys-careers.com/apply/urgent-hiring',
      extracted_title: 'Data Entry Operator - Immediate Joining',
      extracted_company: 'Infosys Limited',
      domain_check: {
        domain: 'inf0sys-careers.com',
        dns_status: 'PASS',
        mx_status: 'PASS',
        spf_status: 'PASS',
        dkim_status: 'SELECTOR_NOT_FOUND',
        dmarc_status: 'PASS',
        source_details: {
          dmarc_policy: 'quarantine',
        },
        lookalike_flags: {
          is_lookalike: true,
          matched_legitimate_domain: 'infosys.com',
          similarity_type: 'brand_prefix_suffix_spoof',
          confidence: 0.85,
          warning: "Suspicious domain naming pattern: 'inf0sys-careers.com' incorporates brand keyword of verified company 'infosys.com'.",
        },
        summary: "Domain security checks for 'inf0sys-careers.com': DNS PASS, MX PASS, SPF PASS, DMARC PASS.",
        limitations: 'Technical domain checks evaluate email and DNS infrastructure; they do not guarantee authorization of specific individuals.',
      },
      recruiter_checks: {
        status: 'TEXT_AND_URL_EXTRACTED',
        detected_emails: ['hr@inf0sys-jobs.com'],
        free_email_detected: false,
        summary: 'Contact emails extracted from job text and webpage source.',
      },
      company_verification: {
        status: 'MATCHED',
        queried_name: 'Infosys Limited',
        matched_name: 'INFOSYS LIMITED',
        cin: 'L85110KA1981PLC013115',
        match_method: 'LEGAL_NAME_EXACT',
        match_confidence: 1.0,
        mca_status: 'Active',
        dpiit_status: 'NOT_LOADED',
        source: 'MCA_COMPANY_MASTER',
      },
      evidence: [
        {
          evidence_type: 'domain_lookalike_warning',
          source_name: 'Lookalike Detector: inf0sys-careers.com',
          status: 'DETECTED',
          confidence: 0.85,
          summary: "Domain 'inf0sys-careers.com' mimics legitimate corporate domain 'infosys.com'.",
          details: { is_lookalike: true },
        },
      ],
      recommended_safe_actions: [
        "Verify whether 'inf0sys-careers.com' is the authentic corporate domain for 'infosys.com'.",
      ],
      limitations: [
        'Job URL analysis processes static HTML; pages that rely on dynamic client-side JavaScript rendering may omit content.',
      ],
      disclaimer: 'JobShield AI provides informational risk assessments.',
    };

    const html = renderToString(
      <MemoryRouter
        initialEntries={[
          {
            pathname: '/results',
            state: {
              analysisResult: urlAnalysisResult,
              jobUrl: 'https://inf0sys-careers.com/apply/urgent-hiring',
              claimedCompany: 'Infosys Limited',
              claimedCin: 'L85110KA1981PLC013115',
              jobTitle: 'Data Entry Operator - Immediate Joining',
            },
          },
        ]}
      >
        <Results />
      </MemoryRouter>
    );

    // 1. Target URL displayed in header
    expect(html).toContain('Public Job URL Target:');
    expect(html).toContain('https://inf0sys-careers.com/apply/urgent-hiring');

    // 2. Domain Security Card rendered
    expect(html).toContain('Domain Security &amp; Email Auth');
    expect(html).toContain('inf0sys-careers.com');
    expect(html).toContain('DNS Resolution');
    expect(html).toContain('MX Mail Route');
    expect(html).toContain('SPF Record');
    expect(html).toContain('DMARC Policy');

    // 3. Lookalike Warning Banner rendered
    expect(html).toContain('Lookalike Domain / Typosquatting Warning');
    expect(html).toContain('infosys.com');
    expect(html).toContain('brand_prefix_suffix_spoof');

    // 4. Extracted contact email
    expect(html).toContain('hr@inf0sys-jobs.com');
  });
});
