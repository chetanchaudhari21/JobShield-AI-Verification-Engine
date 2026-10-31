"""Rule-Based Signal Engine for JobShield AI.

Implements Section 5 (F1) and Section 4 of PROJECT_SPECIFICATION.md:
- Detects upfront fees, sensitive-info requests, urgency, unrealistic pay,
  suspicious contact instructions, and free-email recruiter contact.
- Discloses all findings as separate 'rule_signal' evidence types, distinctly
  separated from machine learning findings.
- Enforces the core requirement: NO SINGLE KEYWORD DECIDES THE OUTCOME.
  Every rule employs contextual regex patterns and compound indicators.
"""

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set
from app.schemas.analysis import EvidenceItem

# Compile contextual regular expressions
FEE_CONTEXT_RE = re.compile(
    r"\b(?:pay\s+(?:an?\s+)?(?:upfront|advance|registration|security|refundable)|"
    r"(?:registration|application|interview|training|equipment|laptop|security|courier|uniform|onboarding|verification)\s*"
    r"(?:fee|deposit|charge|cost|amount|payment)|"
    r"send\s+(?:money|funds|cash|crypto|payment)\s+(?:before|for|prior\s+to)\s+(?:interview|joining|equipment|offer))\b",
    re.IGNORECASE,
)

FEE_NEGATION_RE = re.compile(
    r"\b(?:no\s+(?:fee|charge|deposit|payment)|free\s+of\s+cost|fee\s+waiver|tuition\s+fee\s+reimbursement|"
    r"we\s+do\s+not\s+(?:charge|ask\s+for)\s+(?:any\s+)?fee)\b",
    re.IGNORECASE,
)

SENSITIVE_INFO_RE = re.compile(
    r"\b(?:(?:bank\s+account\s+number|debit\s+card|credit\s+card\s+number|cvv|net\s*banking\s*password|atm\s*pin|otp\s+code|routing\s+number)|"
    r"(?:send|submit|provide|share)\s+(?:your\s+)?(?:bank\s+details|card\s+number|login\s+credentials|atm\s*pin)|"
    r"(?:aadhaar|pan\s+card|ssn|social\s+security|passport)\s+(?:number|copy|scan|details)\s+(?:required|needed|submit|send)\s+(?:for\s+interview|before\s+screening|upfront))\b",
    re.IGNORECASE,
)

URGENCY_RE = re.compile(
    r"\b(?:immediate\s+(?:joining|start|placement)|urgent\s+hiring|urgently\s+required|"
    r"apply\s+immediately|limited\s+(?:slots|vacancies|openings|seats)|only\s+\d+\s+spots?\s+left|"
    r"offer\s+expires\s+in\s+\d+\s+(?:hours|mins?|minutes))\b",
    re.IGNORECASE,
)

UNREALISTIC_PAY_RE = re.compile(
    r"\b(?:(?:earn|make|payout)\s+(?:up\s+to\s+)?(?:[$₹]|rs\.?|inr|usd)?\s*(?:\d{4,6}|\d{2,4}\s*(?:per|/|\bhourly\b|\bdaily\b))\s+(?:daily|per\s+day|per\s+hour|per\s+task|from\s+home\s+no\s+experience)|"
    r"earn\s+(?:from\s+home|without\s+skills|with\s+no\s+experience)\s+(?:thousands|daily|weekly)|"
    r"guaranteed\s+(?:daily|weekly|hourly)\s+(?:income|returns|payout))\b",
    re.IGNORECASE,
)

SUSPICIOUS_CONTACT_RE = re.compile(
    r"\b(?:(?:contact|reach\s+out|message|dm|text|chat)\b[^\n.]{0,35}\b(?:on|via|at)\s+(?:whatsapp|telegram|signal|viber)|"
    r"(?:whatsapp|telegram)\s*(?:number|group|channel|link|chat)?\s*[:\-]?\s*(?:\+?\d+|t\.me|wa\.me|@\w+)|"
    r"send\s+(?:resume|cv|details|hi|hello)\s+(?:to|on)\s*(?:whatsapp|telegram))\b",
    re.IGNORECASE,
)

EMAIL_EXTRACT_RE = re.compile(
    r"\b[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b",
    re.IGNORECASE,
)

FREE_WEBMAIL_DOMAINS: Set[str] = {
    "gmail.com",
    "yahoo.com",
    "ymail.com",
    "hotmail.com",
    "outlook.com",
    "rediffmail.com",
    "yandex.com",
    "proton.me",
    "protonmail.com",
    "aol.com",
    "zoho.com",
    "mail.com",
    "live.com",
}


@dataclass
class RuleEvaluationResult:
    rule_name: str
    detected: bool
    confidence: float
    summary: str
    severity_weight: float
    limitations: str
    details: Dict[str, Any]


def evaluate_upfront_fees_rule(text: str) -> RuleEvaluationResult:
    """Evaluates whether job posting requests advance fees or security deposits."""
    if FEE_NEGATION_RE.search(text):
        return RuleEvaluationResult(
            rule_name="Rule: Upfront Fees Request",
            detected=False,
            confidence=0.1,
            summary="No advance fee detected (text contains explicit fee negation or waiver phrasing).",
            severity_weight=0.0,
            limitations="Contextual negation detected; does not guarantee legitimate employer.",
            details={"negation_found": True},
        )

    match = FEE_CONTEXT_RE.search(text)
    if match:
        snippet = match.group(0)
        return RuleEvaluationResult(
            rule_name="Rule: Upfront Fees Request",
            detected=True,
            confidence=0.90,
            summary=f"Detected request for upfront payment, application fee, or security deposit: '{snippet}'. Legitimate employers never charge candidates for job applications.",
            severity_weight=35.0,
            limitations="Rule-based compound pattern match; must be corroborated by candidate offer letter.",
            details={"matched_phrase": snippet},
        )

    return RuleEvaluationResult(
        rule_name="Rule: Upfront Fees Request",
        detected=False,
        confidence=0.0,
        summary="No upfront fee or registration payment requests detected.",
        severity_weight=0.0,
        limitations="Scammers may request fees in subsequent off-platform communications.",
        details={},
    )


def evaluate_sensitive_info_rule(text: str) -> RuleEvaluationResult:
    """Evaluates whether job posting requests sensitive banking or identity credentials upfront."""
    match = SENSITIVE_INFO_RE.search(text)
    if match:
        snippet = match.group(0)
        return RuleEvaluationResult(
            rule_name="Rule: Sensitive Information Request",
            detected=True,
            confidence=0.85,
            summary=f"Detected request for sensitive banking, payment, or identity details upfront: '{snippet}'. Legitimate employers only request bank details after formal hiring.",
            severity_weight=25.0,
            limitations="Rule-based pattern; identity documents may be requested during legitimate post-offer onboarding.",
            details={"matched_phrase": snippet},
        )

    return RuleEvaluationResult(
        rule_name="Rule: Sensitive Information Request",
        detected=False,
        confidence=0.0,
        summary="No upfront requests for banking credentials or sensitive identity tokens detected.",
        severity_weight=0.0,
        limitations="Candidates should remain vigilant if asked for credentials during interviews.",
        details={},
    )


def evaluate_urgency_rule(text: str) -> RuleEvaluationResult:
    """Evaluates whether high-pressure urgency or artificial scarcity tactics are present."""
    match = URGENCY_RE.search(text)
    if match:
        snippet = match.group(0)
        return RuleEvaluationResult(
            rule_name="Rule: High Urgency Pressure",
            detected=True,
            confidence=0.70,
            summary=f"Detected artificial urgency or pressure tactics: '{snippet}'. Scammers use urgency to induce impulsive compliance.",
            severity_weight=15.0,
            limitations="Urgent hiring is sometimes utilized by genuine businesses with immediate staffing gaps.",
            details={"matched_phrase": snippet},
        )

    return RuleEvaluationResult(
        rule_name="Rule: High Urgency Pressure",
        detected=False,
        confidence=0.0,
        summary="No artificial urgency or deadline pressure detected.",
        severity_weight=0.0,
        limitations="Standard recruitment hiring windows apply.",
        details={},
    )


def evaluate_unrealistic_pay_rule(text: str) -> RuleEvaluationResult:
    """Evaluates whether extravagant compensation claims are made for entry-level work."""
    match = UNREALISTIC_PAY_RE.search(text)
    if match:
        snippet = match.group(0)
        return RuleEvaluationResult(
            rule_name="Rule: Unrealistic Compensation",
            detected=True,
            confidence=0.80,
            summary=f"Detected unrealistic compensation claim for generic or entry-level tasks: '{snippet}'.",
            severity_weight=20.0,
            limitations="High-paying legitimate executive positions may advertise similar numbers without being fraudulent.",
            details={"matched_phrase": snippet},
        )

    return RuleEvaluationResult(
        rule_name="Rule: Unrealistic Compensation",
        detected=False,
        confidence=0.0,
        summary="No unrealistic compensation claims detected.",
        severity_weight=0.0,
        limitations="Compensation rates vary significantly across global regions and industries.",
        details={},
    )


def evaluate_suspicious_contact_rule(text: str) -> RuleEvaluationResult:
    """Evaluates whether posting directs communication to unmonitored encrypted chats."""
    match = SUSPICIOUS_CONTACT_RE.search(text)
    if match:
        snippet = match.group(0)
        return RuleEvaluationResult(
            rule_name="Rule: Suspicious Contact Instructions",
            detected=True,
            confidence=0.85,
            summary=f"Detected directive routing communication to external chat channels: '{snippet}'. Scammers avoid corporate ATS platforms to evade moderation.",
            severity_weight=20.0,
            limitations="Some micro-businesses in specific regions use WhatsApp for initial outreach.",
            details={"matched_phrase": snippet},
        )

    return RuleEvaluationResult(
        rule_name="Rule: Suspicious Contact Instructions",
        detected=False,
        confidence=0.0,
        summary="No suspicious off-platform messaging directives detected.",
        severity_weight=0.0,
        limitations="Recruiters should always be contacted through verified corporate channels.",
        details={},
    )


def evaluate_free_email_contact_rule(text: str) -> tuple[RuleEvaluationResult, List[str], bool]:
    """Evaluates whether recruiter contact email uses free webmail domains."""
    matches = list(re.finditer(r"\b[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b", text))
    all_emails = [m.group(0) for m in matches]
    free_emails = [
        m.group(0)
        for m in matches
        if m.group(1).lower() in FREE_WEBMAIL_DOMAINS
    ]

    if free_emails:
        primary_free = free_emails[0]
        result = RuleEvaluationResult(
            rule_name="Rule: Free Webmail Contact",
            detected=True,
            confidence=0.75,
            summary=f"Recruiter contact email uses a free public webmail address: '{primary_free}'. Corporate recruiters typically email from their company domain.",
            severity_weight=15.0,
            limitations="Early-stage startups or solo proprietors occasionally use Gmail or Outlook before configuring corporate domains.",
            details={"detected_free_emails": free_emails, "all_emails": all_emails},
        )
        return result, all_emails, True

    result = RuleEvaluationResult(
        rule_name="Rule: Free Webmail Contact",
        detected=False,
        confidence=0.0,
        summary="No free webmail contact addresses detected.",
        severity_weight=0.0,
        limitations="Scammers may also register lookalike domains.",
        details={"all_emails": all_emails},
    )
    return result, all_emails, False


def run_all_rules(text: str) -> tuple[List[RuleEvaluationResult], float, List[EvidenceItem], List[str], bool]:
    """Executes the full suite of rule detectors and converts findings into structured EvidenceItem models.

    Returns:
        eval_results: List of raw rule evaluation results.
        raw_rule_score: Weighted composite rule score (0.0 to 100.0).
        evidence_items: Formatted list of EvidenceItem objects labeled as 'rule_signal'.
        detected_emails: List of all extracted email addresses.
        free_email_flag: Boolean indicating if free webmail address was found.
    """
    rule_fees = evaluate_upfront_fees_rule(text)
    rule_sensitive = evaluate_sensitive_info_rule(text)
    rule_urgency = evaluate_urgency_rule(text)
    rule_pay = evaluate_unrealistic_pay_rule(text)
    rule_contact = evaluate_suspicious_contact_rule(text)
    rule_email, all_emails, free_email_flag = evaluate_free_email_contact_rule(text)

    eval_results = [
        rule_fees,
        rule_sensitive,
        rule_urgency,
        rule_pay,
        rule_contact,
        rule_email,
    ]

    # Calculate rule risk score
    # Baseline sum of severity weights
    detected_rules = [r for r in eval_results if r.detected]
    total_severity = sum(r.severity_weight for r in detected_rules)

    # Multi-signal synergy boost:
    # If 2 or more rules are detected, increase score non-linearly
    if len(detected_rules) >= 3:
        total_severity += 15.0
    elif len(detected_rules) >= 2:
        total_severity += 10.0

    # Ensure rule score is bounded strictly between 0.0 and 100.0
    raw_rule_score = max(0.0, min(100.0, total_severity))

    # Convert to EvidenceItem models labeled strictly as 'rule_signal'
    evidence_items: List[EvidenceItem] = []
    for r in eval_results:
        # Include all detected rules, or include negative confirmations for clarity
        if r.detected:
            evidence_items.append(
                EvidenceItem(
                    evidence_type="rule_signal",
                    source_name=r.rule_name,
                    status="DETECTED",
                    confidence=r.confidence,
                    summary=r.summary,
                    limitations=r.limitations,
                    details=r.details,
                )
            )

    return eval_results, raw_rule_score, evidence_items, all_emails, free_email_flag
