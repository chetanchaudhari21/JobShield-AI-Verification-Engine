"""HTML Content and Metadata Extractor for Public Job Postings.

Conforms to Section 11 & Feature F3 of PROJECT_SPECIFICATION.md:
- Pure HTML extraction without JavaScript execution
- Extracts page title, claimed company name, clean body text, and mailto links
- Prioritizes schema.org JobPosting microdata where available
- Strips script, style, navigation, and advertisement boilerplate
"""

import json
import logging
import re
from typing import Dict, List, Optional
from bs4 import BeautifulSoup

logger = logging.getLogger("jobshield.services.html_extractor")

EMAIL_REGEX = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)


class ExtractedJobDetails:
    """Structured fields extracted from sanitized web page HTML."""

    def __init__(
        self,
        title: Optional[str],
        company_name: Optional[str],
        clean_text: str,
        detected_emails: List[str],
        page_type: str = "JOB_POSTING",
        has_schema_job_posting: bool = False,
    ):
        self.title = title
        self.company_name = company_name
        self.clean_text = clean_text
        self.detected_emails = detected_emails
        self.page_type = page_type
        self.has_schema_job_posting = has_schema_job_posting


CAREERS_PORTAL_URL_PATTERNS = re.compile(
    r"(/([a-z]{2}(-[a-z]{2})?/)?(careers|jobs|opportunities|work-with-us|join-us|en/careers|en/jobs))/?$",
    re.I,
)

GENERIC_CAREERS_TITLE_PATTERNS = re.compile(
    r"\b(careers|jobs|explore careers|job opportunities|work with us|join us|life at|working at|current openings|career opportunities|global careers)\b",
    re.I,
)

SPECIFIC_JOB_MARKERS = re.compile(
    r"\b(responsibilities|requirements|qualifications|about the role|job summary|key skills|experience required|eligibility|what you'll do|what you will do|who you are|basic qualifications|preferred qualifications|apply now|compensation|perks)\b",
    re.I,
)


def classify_page_type(
    url: str,
    title: Optional[str],
    clean_text: str,
    has_schema: bool,
) -> str:
    """
    Distinguishes whether an extracted webpage represents:
    - 'JOB_POSTING': A specific employment vacancy description.
    - 'CAREERS_HOMEPAGE': A general corporate careers portal index or landing page.
    - 'SPARSE_CONTENT': Webpage with minimal static text (< 40 chars), likely requiring client-side JS.
    """
    if len(clean_text) < 40:
        return "SPARSE_CONTENT"

    if has_schema:
        return "JOB_POSTING"

    marker_count = len(SPECIFIC_JOB_MARKERS.findall(clean_text))
    parsed_path = ""
    if url:
        try:
            from urllib.parse import urlparse
            parsed_path = (urlparse(url).path or "").rstrip("/")
        except Exception:
            pass

    is_portal_path = bool(
        parsed_path in ("", "/careers", "/jobs", "/careers/india", "/en", "/en/jobs", "/en/careers")
        or CAREERS_PORTAL_URL_PATTERNS.search(parsed_path)
    )

    clean_title = (title or "").lower()
    is_generic_title = bool(
        clean_title in ("careers", "jobs", "explore careers", "join our team")
        or GENERIC_CAREERS_TITLE_PATTERNS.search(clean_title)
    )

    # If the URL or title indicates a general portal and lacks multiple vacancy markers:
    if is_portal_path and marker_count < 2:
        return "CAREERS_HOMEPAGE"

    if is_generic_title and marker_count < 2 and len(clean_text) < 500:
        return "CAREERS_HOMEPAGE"

    return "JOB_POSTING"


def clean_extracted_title(raw_title: str) -> Optional[str]:
    """Cleans up webpage titles by removing common branding separators."""
    if not raw_title:
        return None
    cleaned = raw_title.strip()
    # Strip site branding suffix like " | LinkedIn" or " - Indeed.com"
    for sep in (" | ", " - ", " – ", " — "):
        if sep in cleaned:
            parts = cleaned.split(sep)
            if len(parts[0].strip()) >= 5:
                cleaned = parts[0].strip()
                break
    return cleaned if len(cleaned) >= 3 else None


def extract_schema_org_job_data(soup: BeautifulSoup) -> Dict[str, Optional[str]]:
    """Attempts to parse JSON-LD Schema.org JobPosting microdata."""
    results: Dict[str, Optional[str]] = {"title": None, "company": None, "description": None}

    scripts = soup.find_all("script", type="application/ld+json")
    for script in scripts:
        try:
            if not script.string:
                continue
            data = json.loads(script.string.strip())
            items = data if isinstance(data, list) else [data]

            for item in items:
                if not isinstance(item, dict):
                    continue
                type_name = item.get("@type", "")
                if type_name == "JobPosting":
                    if not results["title"] and item.get("title"):
                        results["title"] = str(item["title"]).strip()

                    org = item.get("hiringOrganization")
                    if isinstance(org, dict) and org.get("name"):
                        results["company"] = str(org["name"]).strip()
                    elif isinstance(org, str):
                        results["company"] = org.strip()

                    if not results["description"] and item.get("description"):
                        # Description may contain embedded HTML
                        desc_soup = BeautifulSoup(str(item["description"]), "html.parser")
                        results["description"] = desc_soup.get_text(separator="\n", strip=True)

                    if results["title"] and results["company"]:
                        return results
        except Exception:
            continue

    return results


def extract_job_posting_from_html(html_content: str, url: str = "") -> ExtractedJobDetails:
    """Parses HTML content safely using BeautifulSoup and extracts relevant job text and metadata."""
    soup = BeautifulSoup(html_content, "html.parser")

    # 1. Parse JSON-LD metadata if present
    schema_data = extract_schema_org_job_data(soup)

    # 2. Extract Title
    title = schema_data.get("title")
    if not title:
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            title = clean_extracted_title(str(og_title["content"]))

    if not title and soup.title and soup.title.string:
        title = clean_extracted_title(soup.title.string)

    if not title:
        h1 = soup.find("h1")
        if h1 and h1.get_text(strip=True):
            title = clean_extracted_title(h1.get_text(strip=True))

    # 3. Extract Company Name
    company_name = schema_data.get("company")
    if not company_name:
        og_site = soup.find("meta", property="og:site_name")
        if og_site and og_site.get("content"):
            company_name = str(og_site["content"]).strip()

    if not company_name:
        # Check standard data attributes or CSS classes
        company_tag = (
            soup.find(attrs={"data-company-name": True})
            or soup.find(class_=re.compile(r"company[_-]?name|employer", re.I))
        )
        if company_tag:
            extracted_cn = company_tag.get_text(strip=True)
            if 2 <= len(extracted_cn) <= 80:
                company_name = extracted_cn

    # 4. Extract Emails (mailto links and regex)
    emails: List[str] = []
    for link in soup.find_all("a", href=True):
        href = str(link["href"]).strip()
        if href.lower().startswith("mailto:"):
            email_val = href.split(":", 1)[1].split("?")[0].strip().lower()
            if EMAIL_REGEX.match(email_val):
                emails.append(email_val)

    # 5. Extract Text Content (strip scripts, styles, navigations, headers, footers)
    for tag in soup(["script", "style", "noscript", "svg", "header", "footer", "nav", "aside", "form"]):
        tag.decompose()

    # Look for main content container
    main_container = (
        soup.find("main")
        or soup.find("article")
        or soup.find(attrs={"role": "main"})
        or soup.find(class_=re.compile(r"job[-_]?description|job[-_]?details|posting[-_]?content", re.I))
        or soup.find(id=re.compile(r"job[-_]?description|job[-_]?details|posting[-_]?content", re.I))
    )

    if main_container:
        text = main_container.get_text(separator="\n", strip=True)
    else:
        text = soup.get_text(separator="\n", strip=True)

    # Clean multi-line whitespace
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    clean_text = "\n".join(lines)

    # If Schema.org JobPosting microdata description is richer, use it
    if schema_data.get("description"):
        schema_desc = schema_data["description"].strip()
        if len(schema_desc) > len(clean_text) or len(clean_text) < 50:
            clean_text = schema_desc

    # Also search body text for emails
    for match in EMAIL_REGEX.finditer(clean_text):
        found = match.group(0).lower()
        if not found.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
            emails.append(found)

    unique_emails = list(dict.fromkeys(emails))

    has_schema = bool(schema_data.get("title") and (schema_data.get("description") or schema_data.get("company")))
    page_type = classify_page_type(url=url, title=title, clean_text=clean_text, has_schema=has_schema)

    return ExtractedJobDetails(
        title=title,
        company_name=company_name,
        clean_text=clean_text,
        detected_emails=unique_emails,
        page_type=page_type,
        has_schema_job_posting=has_schema,
    )
