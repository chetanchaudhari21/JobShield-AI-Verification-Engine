"""Tests for company name normalization, abbreviation handling, and stem matching."""

import pytest
from app.verification.normalization import (
    extract_company_stem,
    match_company_names,
    normalize_company_name,
)


def test_normalize_company_name_abbreviations():
    """Verify that common Indian corporate legal forms and abbreviations normalize identically."""
    # Pvt. Ltd. variants
    assert normalize_company_name("Acme Solutions Pvt. Ltd.") == "ACME SOLUTIONS PRIVATE LIMITED"
    assert normalize_company_name("Acme Solutions Pvt Ltd") == "ACME SOLUTIONS PRIVATE LIMITED"
    assert normalize_company_name("Acme Solutions Private Limited") == "ACME SOLUTIONS PRIVATE LIMITED"
    assert normalize_company_name("Acme Solutions P. Ltd.") == "ACME SOLUTIONS PRIVATE LIMITED"

    # Ltd variants
    assert normalize_company_name("Global Logistics Ltd.") == "GLOBAL LOGISTICS LIMITED"
    assert normalize_company_name("Global Logistics Limited") == "GLOBAL LOGISTICS LIMITED"

    # OPC (One Person Company) variants
    assert normalize_company_name("Kritendra Enterprises (OPC) Private Limited") == "KRITENDRA ENTERPRISES OPC PRIVATE LIMITED"
    assert normalize_company_name("Kritendra Enterprises OPC Pvt Ltd") == "KRITENDRA ENTERPRISES OPC PRIVATE LIMITED"

    # LLP variants
    assert normalize_company_name("Fintech Advisors L.L.P.") == "FINTECH ADVISORS LLP"
    assert normalize_company_name("Fintech Advisors LLP") == "FINTECH ADVISORS LLP"
    assert normalize_company_name("Fintech Advisors Limited Liability Partnership") == "FINTECH ADVISORS LLP"


def test_normalize_company_name_punctuation_and_symbols():
    """Verify ampersand expansion, special character stripping, and whitespace collapsing."""
    assert (
        normalize_company_name("New Unnat India Techno Solutions & Innovation Pvt Ltd")
        == "NEW UNNAT INDIA TECHNO SOLUTIONS AND INNOVATION PRIVATE LIMITED"
    )
    assert (
        normalize_company_name("  Tata    Consultancy   Services,   Ltd.  ")
        == "TATA CONSULTANCY SERVICES LIMITED"
    )
    assert normalize_company_name("E2E A.I. Solutions (P) Ltd") == "E2E AI SOLUTIONS PRIVATE LIMITED"
    assert normalize_company_name("") == ""
    assert normalize_company_name(None) == ""


def test_extract_company_stem():
    """Verify that corporate designators are stripped for base entity matching."""
    assert extract_company_stem("INFOSYS LIMITED") == "INFOSYS"
    assert extract_company_stem("ARYAANDARYA MANAGEMENT PRIVATE LIMITED") == "ARYAANDARYA MANAGEMENT"
    assert extract_company_stem("NEXUS ADVISORY LLP") == "NEXUS ADVISORY"
    assert extract_company_stem("SOLAR WINDS OPC PRIVATE LIMITED") == "SOLAR WINDS"
    assert extract_company_stem("ABC") == "ABC"


def test_match_company_names():
    """Verify match classification and confidence calculation across name representations."""
    # Exact legal
    res1 = match_company_names(
        "TATA CONSULTANCY SERVICES LIMITED",
        "TATA CONSULTANCY SERVICES LIMITED",
    )
    assert res1["is_match"] is True
    assert res1["match_method"] == "EXACT_LEGAL"
    assert res1["confidence"] == 1.0

    # Exact normalized
    res2 = match_company_names(
        "Tata Consultancy Services Pvt. Ltd.",
        "TATA CONSULTANCY SERVICES PRIVATE LIMITED",
    )
    assert res2["is_match"] is True
    assert res2["match_method"] == "EXACT_NORMALIZED"
    assert res2["confidence"] == 0.98

    # Stem match
    res3 = match_company_names(
        "Wipro Limited",
        "Wipro",
    )
    assert res3["is_match"] is True
    assert res3["match_method"] == "STEM_MATCH"
    assert res3["confidence"] == 0.85

    # No match
    res4 = match_company_names(
        "Reliance Industries Limited",
        "Infosys Limited",
    )
    assert res4["is_match"] is False
    assert res4["match_method"] == "NO_MATCH"
    assert res4["confidence"] == 0.0
