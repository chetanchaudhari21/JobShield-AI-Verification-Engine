import { describe, it, expect } from 'vitest';
import React from 'react';
import { renderToString } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { Results } from '../Results';

describe('Results Page Component Rendering', () => {
  const capgeminiAnalysis = {
    report_id: 'test-report-capgemini-001',
    risk_score: 0.12,
    risk_category: 'LOW',
    timestamp: '2026-10-15T00:00:00Z',
    company_verification: {
      status: 'AMBIGUOUS_MATCH',
      queried_name: 'Capgemini',
      match_method: 'AMBIGUOUS_BRAND',
      match_confidence: 0.0,
      mca_status: 'AMBIGUOUS',
      dpiit_status: 'NOT_LOADED',
      source: 'MCA_COMPANY_MASTER',
      summary: "Query 'Capgemini' matches 7 distinct registered entities in the official MCA-21 company registry with differing corporate statuses.",
      limitations: "IMPORTANT: Multiple legal entities operate under or share the brand prefix 'Capgemini'.",
      is_fraud_signal: false,
      candidate_entities: [
        {
          legal_name: 'CAPGEMINI TECHNOLOGY SERVICES INDIA LIMITED',
          cin: 'U85110PN1993PLC145950',
          registry_status: 'Active',
          entity_type: 'PLC',
        },
        {
          legal_name: 'CAPGEMINI IT SOLUTIONS INDIA PRIVATE LIMITED',
          cin: 'U74995MH2018FTC330429',
          registry_status: 'Active',
          entity_type: 'FTC',
        },
        {
          legal_name: 'CAPGEMINI INDIA PRIVATE LIMITED',
          cin: 'U72200MH1992PTC197069',
          registry_status: 'Amalgamated',
          entity_type: 'PTC',
        },
        {
          legal_name: 'CAPGEMINI BUSINESS SERVICES (INDIA) PRIVATE LIMITED',
          cin: 'U74140MH2008PTC187989',
          registry_status: 'Amalgamated',
          entity_type: 'PTC',
        },
        {
          legal_name: 'CAPGEMINI FINANCIAL SERVICES INDIA PRIVATE LIMITED',
          cin: 'U72200MH2006PTC160533',
          registry_status: 'Amalgamated',
          entity_type: 'PTC',
        },
        {
          legal_name: 'CAPGEMINI CONSULTING INDIA PRIVATE LIMITED',
          cin: 'U74140MH2000PTC126581',
          registry_status: 'Amalgamated',
          entity_type: 'PTC',
        },
        {
          legal_name: 'CAPGEMINI CONSULTING INDIA SERVICES PRIVATE LIMITED',
          cin: 'U45200MH1999PTC123118',
          registry_status: 'Strike Off',
          entity_type: 'PTC',
        },
      ],
    },
    evidence: [
      {
        evidence_type: 'rule_signal',
        source_name: 'MCA-21 & DPIIT Registry Verifier',
        status: 'AMBIGUOUS',
        confidence: 0.0,
        summary: "Brand query matches 7 candidates.",
        details: {
          is_ambiguous_brand: true,
          brand_candidate_count: 7,
          candidate_entities: [],
        },
      },
    ],
  };

  it('renders AMBIGUOUS_MATCH badge, clear message, candidate count, and all 7 entities', () => {
    const html = renderToString(
      <MemoryRouter
        initialEntries={[
          {
            pathname: '/results',
            state: {
              analysisResult: capgeminiAnalysis,
              claimedCompany: 'Capgemini',
              jobText: 'Software engineer opening at Capgemini in Bangalore.',
            },
          },
        ]}
      >
        <Results />
      </MemoryRouter>
    );

    // 1. Status badge & MCA status
    expect(html).toContain('AMBIGUOUS_MATCH');
    expect(html).toContain('AMBIGUOUS');

    // 2. Clear heading and message
    expect(html).toContain('Ambiguous company name');
    expect(html).toContain('candidates found');
    expect(html).toContain('Disambiguation Required');
    expect(html).toContain('Notice: AMBIGUOUS_MATCH is NOT a fraud signal');

    // 3. All 7 candidate legal names and statuses
    expect(html).toContain('CAPGEMINI TECHNOLOGY SERVICES INDIA LIMITED');
    expect(html).toContain('U85110PN1993PLC145950');
    expect(html).toContain('Active');

    expect(html).toContain('CAPGEMINI IT SOLUTIONS INDIA PRIVATE LIMITED');
    expect(html).toContain('U74995MH2018FTC330429');

    expect(html).toContain('CAPGEMINI INDIA PRIVATE LIMITED');
    expect(html).toContain('U72200MH1992PTC197069');
    expect(html).toContain('Amalgamated');

    expect(html).toContain('CAPGEMINI CONSULTING INDIA SERVICES PRIVATE LIMITED');
    expect(html).toContain('U45200MH1999PTC123118');
    expect(html).toContain('Strike Off');

    // 4. Action button and manual re-verification input
    expect(html).toContain('Verify this Entity');
    expect(html).toContain('Enter Exact Legal Name or CIN for New Verification');
    expect(html).toContain('Re-verify');
  });

  it('renders genuine NO_MATCH without candidate entity list', () => {
    const noMatchAnalysis = {
      report_id: 'test-report-nomatch-002',
      risk_score: 0.05,
      risk_category: 'LOW',
      timestamp: '2026-10-15T00:00:00Z',
      company_verification: {
        status: 'NO_MATCH',
        queried_name: 'NonExistentRandomCorp999',
        match_method: 'NO_MATCH',
        match_confidence: 0.0,
        mca_status: 'NOT_FOUND',
        dpiit_status: 'NOT_LOADED',
        source: 'MCA_COMPANY_MASTER',
        summary: "No corporate entity matching 'NonExistentRandomCorp999' was found.",
        limitations: 'IMPORTANT: NO_MATCH is NOT proof of fraud.',
        is_fraud_signal: false,
        candidate_entities: null,
      },
      evidence: [],
    };

    const html = renderToString(
      <MemoryRouter
        initialEntries={[
          {
            pathname: '/results',
            state: {
              analysisResult: noMatchAnalysis,
              claimedCompany: 'NonExistentRandomCorp999',
            },
          },
        ]}
      >
        <Results />
      </MemoryRouter>
    );

    expect(html).toContain('NO_MATCH');
    expect(html).toContain('Notice: NO_MATCH is not a fraud indicator');
    expect(html).not.toContain('Ambiguous company name');
    expect(html).not.toContain('Candidate Legal Entities');
  });

  it('renders exact MATCHED company profile with 100% confidence', () => {
    const matchedAnalysis = {
      report_id: 'test-report-matched-003',
      risk_score: 0.02,
      risk_category: 'LOW',
      timestamp: '2026-10-15T00:00:00Z',
      company_verification: {
        status: 'MATCHED',
        queried_name: 'Capgemini Technology Services India Limited',
        matched_name: 'CAPGEMINI TECHNOLOGY SERVICES INDIA LIMITED',
        cin: 'U85110PN1993PLC145950',
        match_method: 'LEGAL_NAME_EXACT',
        match_confidence: 1.0,
        mca_status: 'Active',
        dpiit_status: 'NOT_LOADED',
        source: 'MCA_COMPANY_MASTER',
        summary: "Matched registered entity 'CAPGEMINI TECHNOLOGY SERVICES INDIA LIMITED'.",
        limitations: 'MCA registration validates entity existence only.',
        is_fraud_signal: false,
      },
      evidence: [],
    };

    const html = renderToString(
      <MemoryRouter
        initialEntries={[
          {
            pathname: '/results',
            state: {
              analysisResult: matchedAnalysis,
              claimedCompany: 'Capgemini Technology Services India Limited',
            },
          },
        ]}
      >
        <Results />
      </MemoryRouter>
    );

    expect(html).toContain('MATCHED');
    expect(html).toContain('Matched Legal Entity');
    expect(html).toContain('CAPGEMINI TECHNOLOGY SERVICES INDIA LIMITED');
    expect(html).toContain('U85110PN1993PLC145950');
    expect(html).toContain('LEGAL_NAME_EXACT');
    expect(html).toContain('100');
    expect(html).not.toContain('Ambiguous company name');
  });

  it('renders F6 Model Feature Contributions, decision score reconciliation, and non-intent disclaimer', () => {
    const xaiAnalysis = {
      report_id: 'test-report-xai-001',
      risk_score: 72.5,
      risk_category: 'HIGH',
      timestamp: '2026-10-16T12:00:00Z',
      ml_analysis: {
        model_name: 'JobShield AI Text Fraud Classifier Baseline',
        model_version: 'v1.1.0',
        score_type: 'log_odds_decision_score',
        target_class: 'FRAUDULENT',
        primary_prediction: 'FRAUDULENT',
        primary_threshold: 0.62,
        calibrated_prediction: 'FRAUDULENT',
        calibrated_probability: 0.685,
        calibrated_threshold: 0.40,
        decision_threshold: 0.40,
        decision_score: 0.8421,
        intercept: -0.4331,
        reconciled_score: 0.8421,
        is_reconciled: true,
        explanation_method: 'linear_coefficients',
        explanation_available: true,
        top_positive_features: [
          {
            feature: 'wire',
            feature_value: 0.354,
            coefficient: 2.15,
            contribution: 0.7611,
            direction_label: 'increases model score',
            direction: 'fraud_indicative',
            weight: 0.7611,
            sign: '+',
          },
          {
            feature: 'registration fee',
            feature_value: 0.28,
            coefficient: 1.83,
            contribution: 0.5141,
            direction_label: 'increases model score',
            direction: 'fraud_indicative',
            weight: 0.5141,
            sign: '+',
          },
        ],
        top_negative_features: [
          {
            feature: 'experience',
            feature_value: 0.42,
            coefficient: -0.85,
            contribution: -0.357,
            direction_label: 'decreases model score',
            direction: 'legitimate_indicative',
            weight: -0.357,
            sign: '-',
          },
        ],
        top_features: [],
        explanation_disclaimer:
          "These contributions describe how input features influenced this model's output. They do not establish intent, prove fraud, or independently verify the authenticity of a job offer.",
        disclaimer:
          'ML predictions are probabilistic estimates derived from historical text datasets.',
      },
      evidence: [],
    };

    const html = renderToString(
      <MemoryRouter
        initialEntries={[
          {
            pathname: '/results',
            state: {
              analysisResult: xaiAnalysis,
              jobText: 'Please wire registration fee for employment consideration.',
            },
          },
        ]}
      >
        <Results />
      </MemoryRouter>
    );

    // Verify Model Feature Contributions header and model name
    expect(html).toContain('Model Feature Contributions &amp; ML Classification');
    expect(html).toContain('JobShield AI Text Fraud Classifier Baseline');
    expect(html).toContain('v1.1.0');
    expect(html).toContain('Log-Odds Additive Model');

    // Verify Decision Score Reconciliation Card
    expect(html).toContain('Decision Score Reconciliation (Log-Odds Scale)');
    expect(html).toContain('Exact Log-Odds Additivity Verified: b + Σφ = z');
    expect(html).toContain('-0.4331'); // intercept
    expect(html).toContain('0.8421'); // decision score

    // Verify Positive & Negative Contributions
    expect(html).toContain('Positive Feature Contributions');
    expect(html).toContain('wire');
    expect(html).toContain('+0.7611');
    expect(html).toContain('registration fee');
    expect(html).toContain('Negative Feature Contributions');
    expect(html).toContain('experience');
    expect(html).toContain('-0.3570');
    expect(html).toContain('increases model score');
    expect(html).toContain('decreases model score');

    // Verify Mandatory Non-Intent Disclaimer
    expect(html).toContain('Model Feature Attribution &amp; Non-Intent Principle:');
    expect(html).toContain(
      "These contributions describe how input features influenced this model&#x27;s output. They do not establish intent, prove fraud, or independently verify the authenticity of a job offer."
    );
  });

  it('renders honest unavailable state when explanation_available is false', () => {
    const unavailableAnalysis = {
      report_id: 'test-report-unavailable-002',
      risk_score: 45.0,
      risk_category: 'MODERATE',
      timestamp: '2026-10-16T12:00:00Z',
      ml_analysis: {
        model_name: 'JobShield AI Text Fraud Classifier Baseline',
        model_version: 'v1.1.0',
        score_type: 'log_odds_decision_score',
        target_class: 'FRAUDULENT',
        primary_prediction: 'LEGITIMATE',
        primary_threshold: 0.62,
        calibrated_prediction: 'LEGITIMATE',
        calibrated_probability: 0.25,
        calibrated_threshold: 0.40,
        decision_threshold: 0.40,
        explanation_available: false,
        explanation_unavailable_reason:
          'SHAP explanation is only supported for linear and tree-based models with valid background reference.',
        top_positive_features: [],
        top_negative_features: [],
        top_features: [],
      },
      evidence: [],
    };

    const html = renderToString(
      <MemoryRouter
        initialEntries={[
          {
            pathname: '/results',
            state: {
              analysisResult: unavailableAnalysis,
              jobText: 'Generic job description with no specific scam cues.',
            },
          },
        ]}
      >
        <Results />
      </MemoryRouter>
    );

    expect(html).toContain('Model Feature Explanation Unavailable');
    expect(html).toContain(
      'SHAP explanation is only supported for linear and tree-based models with valid background reference.'
    );
  });

  it('renders chart empty state when no discriminating vocabulary tokens exist', () => {
    const emptyTokensAnalysis = {
      report_id: 'test-report-empty-tokens-003',
      risk_score: 15.0,
      risk_category: 'LOW',
      timestamp: '2026-10-16T12:00:00Z',
      ml_analysis: {
        model_name: 'JobShield AI Text Fraud Classifier Baseline',
        model_version: 'v1.1.0',
        score_type: 'log_odds_decision_score',
        target_class: 'FRAUDULENT',
        primary_prediction: 'LEGITIMATE',
        primary_threshold: 0.62,
        calibrated_prediction: 'LEGITIMATE',
        calibrated_probability: 0.12,
        calibrated_threshold: 0.40,
        decision_threshold: 0.40,
        decision_score: -0.4331,
        intercept: -0.4331,
        reconciled_score: -0.4331,
        is_reconciled: true,
        explanation_available: true,
        active_feature_count: 0,
        total_feature_contribution: 0.0,
        top_positive_features: [],
        top_negative_features: [],
        top_features: [],
      },
      evidence: [],
    };

    const html = renderToString(
      <MemoryRouter
        initialEntries={[
          {
            pathname: '/results',
            state: {
              analysisResult: emptyTokensAnalysis,
              jobText: 'Out of vocabulary text without any heavy weights.',
            },
          },
        ]}
      >
        <Results />
      </MemoryRouter>
    );

    expect(html).toContain('Top Linguistic Feature Contributions (Weights Chart)');
    expect(html).toContain('No Discriminating Vocabulary Tokens Detected');
    expect(html).toContain('0 active');
  });

  it('renders rule safety override floor alert when override_floor_applied is present', () => {
    const overrideAnalysis = {
      report_id: 'test-report-override-004',
      risk_score: 85.0,
      risk_category: 'CRITICAL',
      timestamp: '2026-10-16T12:00:00Z',
      override_floor_applied: 'CRITICAL_COMPOUND_FEE_OVERRIDE_85',
      override_floor_reason:
        'High-severity compound safety override: Upfront fee solicitation combined with suspicious contact channel enforces a minimum risk score of 85.0 (CRITICAL).',
      evidence: [],
    };

    const html = renderToString(
      <MemoryRouter
        initialEntries={[
          {
            pathname: '/results',
            state: {
              analysisResult: overrideAnalysis,
              jobText: 'Job posting demanding money via Western Union.',
            },
          },
        ]}
      >
        <Results />
      </MemoryRouter>
    );

    expect(html).toContain('Rule Safety Override Floor Active:');
    expect(html).toContain('High-severity compound safety override');
    expect(html).toContain('enforces a minimum risk score of 85.0');
  });

  it('renders active Download PDF Report button with report_id and accessibility attributes (Feature F10)', () => {
    const validAnalysis = {
      report_id: 'test-scan-f10-valid-001',
      risk_score: 42.5,
      risk_category: 'MODERATE',
      timestamp: '2026-10-16T12:00:00Z',
      evidence: [],
    };

    const html = renderToString(
      <MemoryRouter
        initialEntries={[
          {
            pathname: '/results',
            state: {
              analysisResult: validAnalysis,
              jobText: 'Standard job posting text for download testing.',
            },
          },
        ]}
      >
        <Results />
      </MemoryRouter>
    );

    expect(html).toContain('Download PDF Report');
    expect(html).toContain('aria-label="Download Evidence-Based PDF Verification Report"');
    expect(html).toContain('title="Download official evidence-based verification report in PDF format"');
    expect(html).toContain('test-scan-f10-valid-001');
    expect(html).not.toContain('Download PDF (Phase 4)');
  });

  it('disables Download PDF Report button when scan report_id is absent', () => {
    const noIdAnalysis = {
      risk_score: 10.0,
      risk_category: 'LOW',
      timestamp: '2026-10-16T12:00:00Z',
      evidence: [],
    };

    const html = renderToString(
      <MemoryRouter
        initialEntries={[
          {
            pathname: '/results',
            state: {
              analysisResult: noIdAnalysis,
            },
          },
        ]}
      >
        <Results />
      </MemoryRouter>
    );

    expect(html).toContain('Download PDF Report');
    expect(html).toContain('disabled=""');
  });

  it('renders scan loading indicator when visited with ?scan_id= query param', () => {
    const html = renderToString(
      <MemoryRouter initialEntries={['/results?scan_id=test-scan-f11-query-001']}>
        <Results />
      </MemoryRouter>
    );

    // Initial render shows the loading state for the requested scan ID
    expect(html).toContain('Loading scan verification report...');
  });

  it('renders Invalid Input Guard view when is_job_related is false and suppresses fraud report sections', () => {
    const invalidAnalysis = {
      report_id: 'test-invalid-input-001',
      risk_score: null,
      risk_category: 'INVALID_INPUT',
      warning: 'Please provide job-related input to continue.',
      is_job_related: false,
      relevance: {
        is_job_related: false,
        status: 'INVALID',
        reason_code: 'RECIPE_DETECTED',
        user_message: 'Please provide job-related input to continue.',
        supporting_message: 'The submitted text appears to be a cooking recipe rather than a job posting.',
      },
      evidence: [],
    };

    const html = renderToString(
      <MemoryRouter
        initialEntries={[
          {
            pathname: '/results',
            state: {
              analysisResult: invalidAnalysis,
              jobText: 'Preheat oven to 350 degrees F. Mix flour, eggs, and sugar in a bowl.',
            },
          },
        ]}
      >
        <Results />
      </MemoryRouter>
    );

    // 1. Must render exact heading and supporting message
    expect(html).toContain('Please provide job-related input to continue.');
    expect(html).toContain(
      'JobShield AI analyzes job descriptions, job posting URLs, offer letters, and recruiter emails. Please submit relevant content so we can assess potential recruitment risks.'
    );

    // 2. Must render diagnostic context feedback
    expect(html).toContain('The submitted text appears to be a cooking recipe rather than a job posting.');

    // 3. Must render navigation button to return to analyze form
    expect(html).toContain('Back to Analyze Form');

    // 4. Must SUPPRESS the full fraud assessment UI
    expect(html).not.toContain('Job Posting Risk Assessment Report');
    expect(html).not.toContain('Composite Risk Assessment');
    expect(html).not.toContain('Download PDF Report');
    expect(html).not.toContain('Linguistic ML Prediction Analysis');
    expect(html).not.toContain('MCA-21 &amp; DPIIT Corroboration');
  });

  it('renders Invalid Input Guard view when document is an unrelated non-offer PDF', () => {
    const invoiceAnalysis = {
      report_id: 'test-invalid-invoice-002',
      risk_score: null,
      risk_category: 'INVALID_INPUT',
      warning: 'Please provide job-related input to continue.',
      is_job_related: false,
      relevance: {
        is_job_related: false,
        status: 'INVALID',
        reason_code: 'NON_OFFER_DOCUMENT',
        user_message: 'Please provide job-related input to continue.',
        supporting_message: 'This document does not appear to be an employment offer letter. Please upload a job-related offer letter.',
      },
      file_name: 'invoice_october.pdf',
      evidence: [],
    };

    const html = renderToString(
      <MemoryRouter
        initialEntries={[
          {
            pathname: '/results',
            state: {
              analysisResult: invoiceAnalysis,
            },
          },
        ]}
      >
        <Results />
      </MemoryRouter>
    );

    expect(html).toContain('Please provide job-related input to continue.');
    expect(html).toContain('This document does not appear to be an employment offer letter. Please upload a job-related offer letter.');
    expect(html).toContain('Back to Analyze Form');
    expect(html).not.toContain('Job Posting Risk Assessment Report');
  });
});

