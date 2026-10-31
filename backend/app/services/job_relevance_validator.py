"""Job-Relevance Validation Service.

Validates whether submitted inputs (job text, job URL, offer letter PDF, or recruiter email)
are sufficiently related to employment, recruitment, job postings, or job offers before
initiating downstream fraud detection, ML inference, heuristic scoring, entity corroboration,
or report persistence.

Guarantees:
- Fast, deterministic multi-signal validation.
- Genuine job postings without salary or company details pass validation.
- Unrelated content (recipes, code, weather, essays, chat, product sales, invoices) is rejected
  with status='INVALID' and risk_category='INVALID_INPUT'.
- Ambiguous or unreadable content is classified as status='UNCERTAIN' and risk_category='UNCERTAIN'.
- Invalid/uncertain inputs do NOT invoke ML models or persist scan records in the database.
"""

from dataclasses import dataclass
import re
from typing import Any, Dict, List, Literal, Optional, Tuple
from pydantic import BaseModel, Field


class JobRelevanceResult(BaseModel):
    """Structured assessment of input job-relevance."""

    is_job_related: bool = Field(
        default=True,
        description="True if input is sufficiently related to employment or recruitment.",
    )
    status: Literal["VALID", "INVALID", "UNCERTAIN"] = Field(
        default="VALID",
        description="Validation outcome: 'VALID' (proceed), 'INVALID' (unrelated), 'UNCERTAIN' (ambiguous/sparse).",
    )
    input_type: str = Field(
        default="job_text",
        description="Input channel: 'job_text', 'job_url', 'offer_letter', or 'recruiter_email'.",
    )
    reason_code: str = Field(
        default="JOB_CONTENT_CONFIRMED",
        description="Machine-readable diagnostic code.",
    )
    user_message: str = Field(
        default="Please provide job-related input to continue.",
        description="Prominent user-facing alert header.",
    )
    supporting_message: str = Field(
        default=(
            "JobShield AI analyzes job descriptions, job posting URLs, offer letters, "
            "and recruiter emails. Please submit relevant content so we can assess potential recruitment risks."
        ),
        description="User-facing descriptive guidance.",
    )
    confidence: Optional[float] = Field(
        default=None,
        description="Confidence score for the validation classification (0.0 to 1.0).",
    )
    details: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Diagnostic details including detected categories and signal counts.",
    )


# -----------------------------------------------------------------------------
# Anti-Pattern Regex Collections (Disqualifiers for non-job content)
# -----------------------------------------------------------------------------

# Recipes and culinary instructions
RECIPE_TERMS = re.compile(
    r"\b("
    r"recipe|recipes|ingredients|preheat(?:ed)?(?:\s+oven)?|tablespoons?|teaspoons?|tbsp|tsp|"
    r"baking\s+sheet|baking\s+powder|baking\s+soda|bake\s+for|simmer|boil\s+water|chopped\s+onions?|"
    r"garnish\s+with|cook\s+over\s+medium|whisk(?:\s+together)?|knead\s+the\s+dough|servings?:\s*\d+|"
    r"cups?\s+(?:of\s+)?flour|granulated\s+sugar|softened\s+butter|olive\s+oil|pinch\s+of\s+salt|"
    r"chocolate\s+chips|vanilla\s+extract|marinate|roast\s+for|skillet|saucepan|deep\s+fry|"
    r"flour|sugar|butter|eggs"
    r")\b",
    re.IGNORECASE,
)

# Weather reports and meteorological forecasts
WEATHER_TERMS = re.compile(
    r"\b("
    r"weather\s+forecast|meteorological|celsius|fahrenheit|humidity|precipitation|"
    r"barometric\s+pressure|partly\s+cloudy|sunny\s+spells|wind\s+speed|gusts\s+up\s+to|"
    r"highs\s+and\s+lows|rainfall\s+amount|storm\s+warning|overcast\s+skies|dew\s+point|"
    r"weather\s+report|radar\s+map|uv\s+index"
    r")\b",
    re.IGNORECASE,
)

# Academic papers, scientific literature, historical treatises
ACADEMIC_TERMS = re.compile(
    r"\b("
    r"in\s+this\s+essay|literature\s+review|bibliography|methodology|historical\s+context|"
    r"century\s+bc|century\s+ad|photosynthesis|mitochondria|cellular\s+respiration|"
    r"dna\s+replication|thesis\s+statement|in\s+conclusion,\s+this\s+study|peer-reviewed\s+journal|"
    r"historiographical|concluding\s+remarks\s+on\s+this\s+historical|empirical\s+findings\s+suggest"
    r")\b",
    re.IGNORECASE,
)

# Casual social conversations and personal chat
PERSONAL_CHAT_TERMS = re.compile(
    r"\b("
    r"hey\s+what'?s\s+up|how\s+are\s+you\s+doing\s+today\??|miss\s+you|love\s+you|"
    r"let'?s\s+hang\s+out|see\s+you\s+tomorrow|are\s+you\s+free\s+tonight\??|talk\s+to\s+you\s+later|"
    r"relationship\s+advice|dating\s+advice|haha\s+so\s+funny|lol\s+dude|bro\s+whats\s+up|"
    r"good\s+morning\s+sweetheart|can\s+you\s+pick\s+me\s+up"
    r")\b",
    re.IGNORECASE,
)

# E-commerce product listings and real estate listings
PRODUCT_SALES_TERMS = re.compile(
    r"\b("
    r"add\s+to\s+cart|buy\s+now|free\s+shipping|in\s+stock|out\s+of\s+stock|"
    r"order\s+tracking|checkout\s+now|discount\s+code|coupon\s+code|product\s+specifications|"
    r"bhk\s+apartment|sq\s+ft|for\s+sale:\s*\$?\d+|customer\s+reviews?\s*\(\d+\)|"
    r"warranty\s+card|item\s+condition:\s*new"
    r")\b",
    re.IGNORECASE,
)

# Document anti-patterns for offer letters (invoices, statements, leases, medical)
OFFER_DOCUMENT_ANTI_PATTERNS = re.compile(
    r"\b("
    r"tax\s+invoice|bill\s+to|ship\s+to|invoice\s+no|invoice\s+date|purchase\s+order|"
    r"payment\s+due|balance\s+due|subtotal|total\s+amount\s+due|gstin|hsn\s+code|"
    r"account\s+statement|bank\s+statement|statement\s+of\s+account|transaction\s+history|"
    r"credit\s+card\s+statement|opening\s+balance|closing\s+balance|debit\s+balance|"
    r"rental\s+agreement|lease\s+agreement|tenant|landlord|monthly\s+rent|lessor|lessee|"
    r"patient\s+name|clinical\s+report|blood\s+test|prescription|laboratory\s+findings|pathology|"
    r"marksheet|grade\s+report|transcript\s+of\s+records|semester\s+exam|cgpa"
    r")\b",
    re.IGNORECASE,
)

# -----------------------------------------------------------------------------
# Positive Recruitment & Employment Signals
# -----------------------------------------------------------------------------

# Dimension 1: Roles, Titles, Vacancy Indicators
RECRUITMENT_ROLE_TERMS = re.compile(
    r"\b("
    r"job|jobs|vacancy|vacancies|position|positions|role|roles|opening|openings|"
    r"career|careers|hiring|recruitment|recruit|recruiting|recruiter|employment|opportunity|opportunities|"
    r"engineer|developer|architect|designer|manager|analyst|associate|lead|director|"
    r"consultant|technician|administrator|intern|internship|trainee|executive|officer|"
    r"specialist|representative|coordinator|programmer|scientist|researcher|accountant|writer|editor|"
    r"producer|agent|operator|assistant|clerk|driver|nurse|doctor|teacher|instructor|"
    r"advisor|salesperson|cashier|worker|crew|staff|counselor|"
    r"data\s+scien(?:ce|tist)|machine\s+learning|ai\s+engineer|risk\s+analyst|fraud\s+analyst|"
    r"business\s+analyst|financial\s+analyst|operations\s+analyst|software\s+developer|qa\s+engineer|devops|"
    r"job\s+title|role\s+title|position\s+title|designation|about\s+the\s+role|about\s+the\s+job|"
    r"role\s+overview|job\s+overview|job\s+summary|position\s+summary|role\s+summary|job\s+profile|"
    r"role\s+description|job\s+description|open\s+positions?|employment\s+opportunity"
    r")\b",
    re.IGNORECASE,
)

# Dimension 2: Responsibilities & Duties
RECRUITMENT_RESPONSIBILITIES_TERMS = re.compile(
    r"\b("
    r"responsibilities|duties|what\s+you\s+will\s+do|what\s+you'?ll\s+do|key\s+tasks|"
    r"key\s+responsibilities|accountable\s+for|responsible\s+for|collaborate\s+with|"
    r"work\s+closely\s+with|deliver|develop|maintain|build|manage|execute|oversee|"
    r"design|lead\s+the\s+team|troubleshoot|implement|coordinate|perform|support|drive|"
    r"analyze|optimize|deploy|partner\s+with|contribute\s+to|solve|solution|algorithms?|models?|"
    r"key\s+deliverables|scope\s+of\s+work|day-to-day|role\s+and\s+responsibilities|accountabilit(?:y|ies)|"
    r"in\s+this\s+role|as\s+an?\s+[a-z]+,\s+you|your\s+mission|risk\s+management"
    r")\b",
    re.IGNORECASE,
)

# Dimension 3: Qualifications & Requirements
RECRUITMENT_QUALIFICATIONS_TERMS = re.compile(
    r"\b("
    r"qualifications?|requirements?|required\s+skills|skills\s+required|eligibility|"
    r"experience|years\s+of\s+experience|degree|bachelor'?s?|master'?s?|diploma|"
    r"b\.?tech|b\.?e\.?|m\.?tech|m\.?s\.?|mba|phd|bca|mca|b\.?sc|m\.?sc|"
    r"proficiency\s+(?:in|with)|proficient\s+(?:in|with)|"
    r"hands-on\s+experience|knowledge\s+of|familiarity\s+with|must\s+have|good\s+to\s+have|"
    r"skillset|certifications?|track\s+record|prior\s+experience|relevant\s+experience|work\s+experience|"
    r"experience\s+with|expertise\s+in|skilled\s+in|background\s+in|minimum\s+\d+\s+years?|"
    r"\d+\s*[-–+to]+\s*\d*\s*(?:years?|yrs?)(?:\s+of)?(?:\s+experience|\s+exp)?|"
    r"what\s+we\s+are\s+looking\s+for|who\s+you\s+are|preferred\s+qualifications|basic\s+qualifications|"
    r"minimum\s+qualifications|key\s+skills|technical\s+skills|competenc(?:y|ies)"
    r")\b",
    re.IGNORECASE,
)

# Dimension 4: Employment Terms, Benefits, Compensation
RECRUITMENT_TERMS_CONDITIONS = re.compile(
    r"("
    r"\b("
    r"full-time|part-time|contract|permanent|temporary|internship|remote|hybrid|on-site|"
    r"work\s+from\s+home|wfh|salary|compensation|stipend|ctc|lpa|per\s+annum|per\s+month|"
    r"benefits|perks|health\s+insurance|provident\s+fund|probation|notice\s+period|shifts|working\s+hours|"
    r"paid\s+time\s+off|pto|equity|stock\s+options|location|job\s+location|work\s+location|"
    r"employment\s+type|job\s+type|industry\s+type|department|functional\s+area|not\s+disclosed|"
    r"registration\s+deposit|refundable\s+deposit|security\s+deposit|equipment\s+deposit|"
    r"registration\s+fee|deposit|joining\s+kit|company\s+laptop|joining\s+bonus|laptop|"
    r"training\s+fee|processing\s+fee|fee|fees"
    r")\b|"
    r"(?:[\$₹£€]|(?:inr|usd|cad|aud|eur|gbp)\b)\s*\d+(?:,\d+)*(?:\s*(?:k|lakhs?|pa|pm))?"
    r")",
    re.IGNORECASE,
)

# Dimension 5: Hiring Call to Action & Application Channels
RECRUITMENT_CTA_TERMS = re.compile(
    r"\b("
    r"apply\s+now|apply\s+today|send\s+resume|send\s+cv|submit\s+resume|submit\s+cv|"
    r"submit\s+application|email\s+your\s+resume|send\s+your\s+profile|interested\s+candidates|"
    r"walk-in\s+interview|urgent\s+hiring|immediate\s+joiner|job\s+id|req\s+id|requisition|"
    r"how\s+to\s+apply|apply\s+at|reach\s+out\s+to|forward\s+your\s+resume|shortlisted\s+candidates|"
    r"shortlisted(?:\s+for)?|congratulations|contact\s+(?:hr|the\s+recruiter|manager|us|immediately)|"
    r"contact\s+.*?\b(?:on|via)\s+(?:whatsapp|telegram|email)|whatsapp|"
    r"explore\s+careers|discover\s+open\s+roles|find\s+your\s+next\s+role|current\s+openings|open\s+roles|"
    r"join\s+(?:a|our|the)\s+(?:global\s+leader|team|company)|"
    r"search(?:ing)?\s+(?:for|through)?\s*(?:our\s+)?(?:current\s+)?(?:jobs|roles|openings|vacancies)|"
    r"please\s+send\s+portfolio|to\s+apply|join\s+(?:our|the)\s+team|we\s+are\s+hiring|now\s+hiring|"
    r"posted\s+by|posted\s+on|posted\s+\d+\s+days?\s+ago|open\s+positions?|interested\s+applicants?|recruiter\s+details"
    r")\b",
    re.IGNORECASE,
)

# Offer Letter Key Clauses
OFFER_LETTER_SPECIFIC_TERMS = re.compile(
    r"\b("
    r"offer\s+of\s+employment|appointment\s+letter|letter\s+of\s+appointment|"
    r"employment\s+agreement|employment\s+offer|we\s+are\s+pleased\s+to\s+offer|"
    r"pleased\s+to\s+offer\s+you\s+the\s+position|terms\s+of\s+employment|"
    r"commencement\s+date|date\s+of\s+joining|joining\s+date|annual\s+ctc|"
    r"gross\s+salary|basic\s+salary|reporting\s+manager|acceptance\s+deadline|"
    r"probation\s+period|duties\s+and\s+responsibilities|confidentiality\s+agreement|"
    r"code\s+of\s+conduct|non-disclosure|sign\s+and\s+return|duplicate\s+copy\s+of\s+this\s+letter|"
    r"formal\s+offer|letter\s+of\s+intent"
    r")\b",
    re.IGNORECASE,
)


# -----------------------------------------------------------------------------
# Validation Helper Functions
# -----------------------------------------------------------------------------

def is_low_entropy_or_gibberish(text: str) -> bool:
    """Detects repetitive keystrokes, spam strings, or low-entropy gibberish."""
    trimmed = text.strip()
    if len(trimmed) < 20:
        return False

    # Check long repetitive non-whitespace character sequences (e.g. 'aaaaaaaa', '11111111')
    if re.search(r"([^\s])\1{7,}", trimmed):
        return True

    # Check repetitive 2-4 alphanumeric char patterns (e.g. 'asdfasdfasdfasdf', 'abcabcabcabc')
    if re.search(r"([a-zA-Z0-9]{2,4})\1{4,}", trimmed):
        return True

    # Check very low unique character diversity on short texts (20-60 chars)
    alphanumeric = [c for c in trimmed.lower() if c.isalnum()]
    if 20 <= len(alphanumeric) <= 60 and len(set(alphanumeric)) <= 3:
        return True

    return False


def is_raw_source_code(text: str) -> bool:
    """Detects raw programming source code or shell scripts without job context."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return False

    code_line_markers = [
        r"^(?:import|from)\s+[a-zA-Z0-9_\.]+",
        r"^def\s+[a-zA-Z_][a-zA-Z0-9_]*\s*\(.*\)\s*:",
        r"^class\s+[a-zA-Z_][a-zA-Z0-9_]*",
        r"^function\s+[a-zA-Z_][a-zA-Z0-9_]*\s*\(",
        r"^(?:const|let|var)\s+[a-zA-Z_][a-zA-Z0-9_]*\s*=",
        r"^console\.log\(",
        r"^(?:public|private|protected)\s+(?:static\s+)?[a-zA-Z0-9_<>]+\s+[a-zA-Z0-9_]+\s*\(",
        r"^System\.out\.println\(",
        r"^SELECT\s+.+\s+FROM\s+",
        r"^#!\s*\/bin\/",
        r"^(?:sudo\s+)?apt(?:-get)?\s+",
        r"^(?:npm|pip|cargo|mvn)\s+install",
        r"[{}\[\];]$",
    ]
    code_pattern = re.compile("|".join(code_line_markers))

    code_lines_count = sum(1 for line in lines if code_pattern.search(line))
    ratio = code_lines_count / len(lines)

    # If >= 40% of lines are code patterns, and no recruitment CTA/titles
    return ratio >= 0.40 and len(lines) >= 3


def count_recruitment_dimensions(text: str) -> Tuple[int, Dict[str, int]]:
    """Evaluates how many distinct recruitment dimensions are matched in the text."""
    counts = {
        "roles": len(RECRUITMENT_ROLE_TERMS.findall(text)),
        "responsibilities": len(RECRUITMENT_RESPONSIBILITIES_TERMS.findall(text)),
        "qualifications": len(RECRUITMENT_QUALIFICATIONS_TERMS.findall(text)),
        "terms": len(RECRUITMENT_TERMS_CONDITIONS.findall(text)),
        "cta": len(RECRUITMENT_CTA_TERMS.findall(text)),
    }
    dimensions_matched = sum(1 for k, v in counts.items() if v > 0)
    return dimensions_matched, counts


# -----------------------------------------------------------------------------
# Main Validator Functions
# -----------------------------------------------------------------------------

def validate_job_text(text: str) -> JobRelevanceResult:
    """Validates submitted job posting text for employment and recruitment relevance.

    Returns:
        JobRelevanceResult with status 'VALID', 'INVALID', or 'UNCERTAIN'.
    """
    clean_text = text.strip()

    # 1. Check for repetitive spam / gibberish
    if is_low_entropy_or_gibberish(clean_text):
        return JobRelevanceResult(
            is_job_related=False,
            status="INVALID",
            input_type="job_text",
            reason_code="REPETITIVE_GIBBERISH",
            user_message="Please provide job-related input to continue.",
            supporting_message=(
                "The submitted text lacks readable language or informative content. "
                "JobShield AI analyzes job descriptions, job posting URLs, offer letters, "
                "and recruiter emails. Please submit relevant content so we can assess potential recruitment risks."
            ),
            confidence=0.95,
            details={"category": "gibberish"},
        )

    # 2. Check for raw source code scripts
    if is_raw_source_code(clean_text):
        # Double check if there's strong recruitment context (e.g. job description for coding role)
        dims, _ = count_recruitment_dimensions(clean_text)
        if dims < 2:
            return JobRelevanceResult(
                is_job_related=False,
                status="INVALID",
                input_type="job_text",
                reason_code="SOURCE_CODE_DETECTED",
                user_message="Please provide job-related input to continue.",
                supporting_message=(
                    "The submitted text appears to be raw source code or a script without recruitment context. "
                    "JobShield AI analyzes job descriptions, job posting URLs, offer letters, "
                    "and recruiter emails. Please submit relevant content so we can assess potential recruitment risks."
                ),
                confidence=0.92,
                details={"category": "source_code"},
            )

    # 3. Check for specific anti-patterns
    recipe_matches = len(RECIPE_TERMS.findall(clean_text))
    weather_matches = len(WEATHER_TERMS.findall(clean_text))
    academic_matches = len(ACADEMIC_TERMS.findall(clean_text))
    personal_matches = len(PERSONAL_CHAT_TERMS.findall(clean_text))
    sales_matches = len(PRODUCT_SALES_TERMS.findall(clean_text))

    dims_matched, dim_counts = count_recruitment_dimensions(clean_text)
    # A genuine job posting has structured hiring context (e.g. responsibilities + qualifications)
    has_deep_job_structure = (dim_counts["responsibilities"] >= 1 and dim_counts["qualifications"] >= 1)

    # If recipe signals are strong and not a structured job posting
    if recipe_matches >= 2 and not has_deep_job_structure and dims_matched <= 1:
        return JobRelevanceResult(
            is_job_related=False,
            status="INVALID",
            input_type="job_text",
            reason_code="RECIPE_DETECTED",
            user_message="Please provide job-related input to continue.",
            supporting_message=(
                "The submitted text appears to be a cooking recipe rather than a job posting. "
                "JobShield AI analyzes job descriptions, job posting URLs, offer letters, "
                "and recruiter emails. Please submit relevant content so we can assess potential recruitment risks."
            ),
            confidence=0.95,
            details={"category": "recipe", "matches": recipe_matches},
        )

    # If weather signals are strong and not a structured job posting
    if weather_matches >= 2 and not has_deep_job_structure and dims_matched <= 1:
        return JobRelevanceResult(
            is_job_related=False,
            status="INVALID",
            input_type="job_text",
            reason_code="WEATHER_FORECAST",
            user_message="Please provide job-related input to continue.",
            supporting_message=(
                "The submitted text appears to be a weather forecast or meteorological report. "
                "JobShield AI analyzes job descriptions, job posting URLs, offer letters, "
                "and recruiter emails. Please submit relevant content so we can assess potential recruitment risks."
            ),
            confidence=0.95,
            details={"category": "weather", "matches": weather_matches},
        )

    # If academic essay signals are strong and not a structured job posting
    if academic_matches >= 2 and not has_deep_job_structure and dims_matched <= 1:
        return JobRelevanceResult(
            is_job_related=False,
            status="INVALID",
            input_type="job_text",
            reason_code="ACADEMIC_ESSAY",
            user_message="Please provide job-related input to continue.",
            supporting_message=(
                "The submitted text appears to be an academic paper or general essay. "
                "JobShield AI analyzes job descriptions, job posting URLs, offer letters, "
                "and recruiter emails. Please submit relevant content so we can assess potential recruitment risks."
            ),
            confidence=0.90,
            details={"category": "academic_essay", "matches": academic_matches},
        )

    # If personal chat signals are strong and not a structured job posting
    if personal_matches >= 2 and not has_deep_job_structure and dims_matched <= 1:
        return JobRelevanceResult(
            is_job_related=False,
            status="INVALID",
            input_type="job_text",
            reason_code="PERSONAL_CHAT",
            user_message="Please provide job-related input to continue.",
            supporting_message=(
                "The submitted text appears to be a personal conversation or casual chat. "
                "JobShield AI analyzes job descriptions, job posting URLs, offer letters, "
                "and recruiter emails. Please submit relevant content so we can assess potential recruitment risks."
            ),
            confidence=0.90,
            details={"category": "personal_chat", "matches": personal_matches},
        )

    # If e-commerce / sales signals are strong and not a structured job posting
    if sales_matches >= 2 and not has_deep_job_structure and dims_matched <= 1:
        return JobRelevanceResult(
            is_job_related=False,
            status="INVALID",
            input_type="job_text",
            reason_code="PRODUCT_SALES",
            user_message="Please provide job-related input to continue.",
            supporting_message=(
                "The submitted text appears to be an e-commerce product or commercial sales listing. "
                "JobShield AI analyzes job descriptions, job posting URLs, offer letters, "
                "and recruiter emails. Please submit relevant content so we can assess potential recruitment risks."
            ),
            confidence=0.90,
            details={"category": "product_sales", "matches": sales_matches},
        )

    # 4. Check for Collapsed Snippet
    is_collapsed = bool(re.search(r"(?:\.\.\.|…)\s*(?:read|view|show)\s*more\b|(?:\bread|show|view\s*more\b\s*$)", clean_text, re.IGNORECASE))
    if is_collapsed:
        return JobRelevanceResult(
            is_job_related=False,
            status="UNCERTAIN",
            input_type="job_text",
            reason_code="AMBIGUOUS_SHORT_TEXT",
            user_message="Job description appears incomplete or ambiguous.",
            supporting_message=(
                "The job description appears collapsed or truncated. "
                "Please expand the full job description or paste the complete text so we can assess potential recruitment risks."
            ),
            confidence=0.60,
            details={"dimensions_matched": dims_matched, "is_collapsed": True},
        )

    # 5. Check for Positive Recruitment Dimensions
    # Legitimate job postings (even without salary or company name) will match at least 2 dimensions
    # (e.g. role title + requirements, or role title + responsibilities, or terms + CTA, etc.)
    if dims_matched >= 2:
        return JobRelevanceResult(
            is_job_related=True,
            status="VALID",
            input_type="job_text",
            reason_code="JOB_CONTENT_CONFIRMED",
            user_message="Input validated as job-related.",
            supporting_message="Text contains confirmed employment and recruitment patterns.",
            confidence=0.95,
            details={"dimensions_matched": dims_matched, "dimension_counts": dim_counts},
        )

    # If only 1 dimension matched:
    if dims_matched == 1:
        # Check if text contains career service advertisements or advice articles
        has_service_cue = bool(re.search(r"\b(resume\s+writing|resume\s+sample|resume\s+critique|resume\s+templates?|download\s+resume|career\s+advice|interview\s+tips)\b", clean_text, re.IGNORECASE))
        if has_service_cue:
            return JobRelevanceResult(
                is_job_related=False,
                status="INVALID",
                input_type="job_text",
                reason_code="UNRELATED_CONTENT",
                user_message="Please provide job-related input to continue.",
                supporting_message=(
                    "The submitted text appears to be a career service advertisement or article rather than a job vacancy. "
                    "JobShield AI analyzes job descriptions, job posting URLs, offer letters, "
                    "and recruiter emails. Please submit relevant content so we can assess potential recruitment risks."
                ),
                confidence=0.90,
                details={"category": "career_service"},
            )

        # If it's a brief snippet (< 120 chars) with 1 dimension
        if len(clean_text) < 120:
            return JobRelevanceResult(
                is_job_related=False,
                status="UNCERTAIN",
                input_type="job_text",
                reason_code="AMBIGUOUS_SHORT_TEXT",
                user_message="Job description appears incomplete or ambiguous.",
                supporting_message=(
                    "The submitted text contains insufficient recruitment details. "
                    "Please provide the full job description, qualifications, and responsibilities so we can assess potential recruitment risks."
                ),
                confidence=0.50,
                details={"dimensions_matched": dims_matched, "dimension_counts": dim_counts},
            )

        # Longer text (> 120 chars) with only 1 isolated recruitment token and NO responsibilities, qualifications, terms, or cta
        # is usually an article, essay, or non-job content where an employment word appears incidentally
        if dim_counts["responsibilities"] == 0 and dim_counts["qualifications"] == 0 and dim_counts["terms"] == 0 and dim_counts["cta"] == 0:
            return JobRelevanceResult(
                is_job_related=False,
                status="INVALID",
                input_type="job_text",
                reason_code="UNRELATED_CONTENT",
                user_message="Please provide job-related input to continue.",
                supporting_message=(
                    "The submitted content does not appear to be related to employment or recruitment. "
                    "JobShield AI analyzes job descriptions, job posting URLs, offer letters, "
                    "and recruiter emails. Please submit relevant content so we can assess potential recruitment risks."
                ),
                confidence=0.90,
                details={"dimensions_matched": dims_matched, "dimension_counts": dim_counts},
            )

        return JobRelevanceResult(
            is_job_related=True,
            status="VALID",
            input_type="job_text",
            reason_code="JOB_CONTENT_CONFIRMED",
            user_message="Input validated as job-related.",
            supporting_message="Text contains employment recruitment signals.",
            confidence=0.85,
            details={"dimensions_matched": dims_matched, "dimension_counts": dim_counts},
        )

    # If 0 dimensions matched but text contains weak recruitment cues in short text:
    weak_cues_pattern = re.compile(
        r"\b(work|need|urgent|calling|call\s+me|details|contact|join\s+us|earn|part-?time|full-?time|salary|income|opening|openings|opportunity)\b",
        re.IGNORECASE,
    )
    if len(clean_text) < 120 and weak_cues_pattern.search(clean_text):
        return JobRelevanceResult(
            is_job_related=False,
            status="UNCERTAIN",
            input_type="job_text",
            reason_code="AMBIGUOUS_SHORT_TEXT",
            user_message="Job description appears incomplete or ambiguous.",
            supporting_message=(
                "The submitted text contains ambiguous or insufficient recruitment context. "
                "Please provide the full job description, qualifications, and responsibilities so we can assess potential recruitment risks."
            ),
            confidence=0.50,
            details={"dimensions_matched": 0, "weak_cues": True},
        )

    # 0 dimensions matched and no explicit anti-pattern: Completely unrelated text
    return JobRelevanceResult(
        is_job_related=False,
        status="INVALID",
        input_type="job_text",
        reason_code="UNRELATED_CONTENT",
        user_message="Please provide job-related input to continue.",
        supporting_message=(
            "The submitted content does not appear to be related to employment or recruitment. "
            "JobShield AI analyzes job descriptions, job posting URLs, offer letters, "
            "and recruiter emails. Please submit relevant content so we can assess potential recruitment risks."
        ),
        confidence=0.90,
        details={"dimensions_matched": 0},
    )


def validate_job_url(
    clean_text: str,
    title: Optional[str] = None,
    status_code: int = 200,
    url: str = "",
    page_type: Optional[str] = None,
) -> JobRelevanceResult:
    """Validates fetched webpage content and status for job-posting relevance."""
    # 0. Corporate careers portal index or landing page -> VALID per F3 specification
    if page_type == "CAREERS_HOMEPAGE":
        return JobRelevanceResult(
            is_job_related=True,
            status="VALID",
            input_type="job_url",
            reason_code="CAREERS_PORTAL_CONFIRMED",
            user_message="Webpage validated as corporate careers portal.",
            supporting_message="Webpage is a recognized corporate careers or job search portal.",
            confidence=0.90,
            details={"page_type": "CAREERS_HOMEPAGE"},
        )

    # 1. Anti-bot protection (403, 429) or sparse text (< 20 chars) -> UNCERTAIN per Section 2.B
    if status_code in (403, 429) or len((clean_text or "").strip()) < 20:
        return JobRelevanceResult(
            is_job_related=False,
            status="UNCERTAIN",
            input_type="job_url",
            reason_code="BOT_PROTECTION_OR_SPARSE",
            user_message="Please provide job-related input to continue.",
            supporting_message=(
                "This webpage could not be verified as a job posting due to bot protection or sparse content. "
                "Please paste the job description text directly."
            ),
            confidence=0.70,
            details={"status_code": status_code, "text_length": len((clean_text or "").strip())},
        )

    # 2. Check title for strong job cues (e.g. 'Careers', 'Job Opening', 'Vacancy')
    combined_content = f"{title or ''}\n\n{clean_text}".strip()

    # Validate content using text validator
    text_result = validate_job_text(combined_content)
    if text_result.status == "VALID":
        return JobRelevanceResult(
            is_job_related=True,
            status="VALID",
            input_type="job_url",
            reason_code="JOB_CONTENT_CONFIRMED",
            user_message="Webpage content validated as a job posting.",
            supporting_message="Webpage content contains confirmed job posting and recruitment details.",
            confidence=text_result.confidence,
            details=text_result.details,
        )

    # If invalid or uncertain
    return JobRelevanceResult(
        is_job_related=False,
        status="INVALID" if text_result.status == "INVALID" else "UNCERTAIN",
        input_type="job_url",
        reason_code=text_result.reason_code if text_result.reason_code != "JOB_CONTENT_CONFIRMED" else "UNRELATED_CONTENT",
        user_message="Please provide job-related input to continue.",
        supporting_message=(
            "The webpage content at this URL does not appear to be a job posting or recruitment advertisement. "
            "JobShield AI analyzes job descriptions, job posting URLs, offer letters, "
            "and recruiter emails. Please submit relevant content so we can assess potential recruitment risks."
        ),
        confidence=text_result.confidence,
        details=text_result.details,
    )


def validate_offer_letter(
    text: str,
    file_name: Optional[str] = None,
    extracted_fields: Optional[Any] = None,
) -> JobRelevanceResult:
    """Validates extracted PDF text and structure for employment offer letter characteristics."""
    clean_text = (text or "").strip()

    # 1. Unreadable / empty / insufficient text (< 30 characters after OCR) -> UNCERTAIN
    if len(clean_text) < 30:
        return JobRelevanceResult(
            is_job_related=False,
            status="UNCERTAIN",
            input_type="offer_letter",
            reason_code="UNREADABLE_DOCUMENT",
            user_message="Please provide job-related input to continue.",
            supporting_message=(
                "This document has unreadable or insufficient text. "
                "OCR could not extract enough readable text to verify this as an employment offer letter. "
                "Please upload a clear, legible PDF document."
            ),
            confidence=0.85,
            details={"raw_length": len(clean_text)},
        )

    # 2. Check for offer-letter specific clauses
    has_offer_clause = bool(OFFER_LETTER_SPECIFIC_TERMS.search(clean_text))
    dims_matched, dim_counts = count_recruitment_dimensions(clean_text)

    # 3. Check for non-offer document anti-patterns (invoices, statements, leases, medical)
    anti_matches = len(OFFER_DOCUMENT_ANTI_PATTERNS.findall(clean_text))

    if anti_matches >= 2 and not has_offer_clause:
        return JobRelevanceResult(
            is_job_related=False,
            status="INVALID",
            input_type="offer_letter",
            reason_code="NON_OFFER_DOCUMENT",
            user_message="Please provide job-related input to continue.",
            supporting_message=(
                "This document does not appear to be an employment offer letter. "
                "Please upload a job-related offer letter."
            ),
            confidence=0.92,
            details={"anti_pattern_matches": anti_matches},
        )

    # If offer clause is present OR (at least 2 recruitment dimensions matched e.g. role + compensation/terms)
    if has_offer_clause or (dims_matched >= 2 and (dim_counts["roles"] > 0 or dim_counts["terms"] > 0)):
        return JobRelevanceResult(
            is_job_related=True,
            status="VALID",
            input_type="offer_letter",
            reason_code="OFFER_LETTER_CONFIRMED",
            user_message="Document validated as employment offer letter.",
            supporting_message="Document contains recognized employment offer clauses and appointment terms.",
            confidence=0.95,
            details={"has_offer_clause": has_offer_clause, "dimensions_matched": dims_matched},
        )

    # Fallback: Document without offer clauses or recruitment dimensions
    return JobRelevanceResult(
        is_job_related=False,
        status="INVALID",
        input_type="offer_letter",
        reason_code="NON_OFFER_DOCUMENT",
        user_message="Please provide job-related input to continue.",
        supporting_message=(
            "This document does not appear to be an employment offer letter. "
            "Please upload a job-related offer letter."
        ),
        confidence=0.90,
        details={"has_offer_clause": False, "dimensions_matched": dims_matched},
    )


def validate_recruiter_email(
    email: str,
    message_text: Optional[str] = None,
) -> JobRelevanceResult:
    """Validates recruiter email submission.

    - If message_text is provided, evaluates for recruitment context.
    - If email only, marks message-level risk as UNCERTAIN while allowing domain security checks.
    """
    clean_msg = (message_text or "").strip()

    if not clean_msg:
        # Email address provided without message text
        return JobRelevanceResult(
            is_job_related=True,
            status="UNCERTAIN",
            input_type="recruiter_email",
            reason_code="EMAIL_ONLY_NO_CONTEXT",
            user_message="Recruiter email domain security evaluated.",
            supporting_message=(
                "Without the email message body, content-based fraud patterns cannot be evaluated. "
                "Technical domain authentication and company corroboration are provided below."
            ),
            confidence=0.60,
            details={"message_level_risk": "UNCERTAIN"},
        )

    # If message text is provided, validate it
    text_result = validate_job_text(clean_msg)
    if text_result.status == "VALID":
        return JobRelevanceResult(
            is_job_related=True,
            status="VALID",
            input_type="recruiter_email",
            reason_code="JOB_CONTENT_CONFIRMED",
            user_message="Recruitment communication validated.",
            supporting_message="Message content contains recognized recruitment communication patterns.",
            confidence=text_result.confidence,
            details=text_result.details,
        )

    # Message text is unrelated (e.g. recipe or pure personal chat)
    return JobRelevanceResult(
        is_job_related=False,
        status=text_result.status,
        input_type="recruiter_email",
        reason_code=text_result.reason_code,
        user_message="Please provide job-related input to continue.",
        supporting_message=(
            "The message text provided with this recruiter email does not appear to be a recruitment communication. "
            "JobShield AI analyzes job descriptions, job posting URLs, offer letters, "
            "and recruiter emails. Please submit relevant content so we can assess potential recruitment risks."
        ),
        confidence=text_result.confidence,
        details=text_result.details,
    )
