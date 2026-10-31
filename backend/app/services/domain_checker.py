"""Domain verification, DNS records, email authentication, and lookalike detection service.

Conforms to Section 8, Section 11 & Feature F3 of PROJECT_SPECIFICATION.md:
- DNS A / AAAA host resolution
- MX route availability
- SPF (Sender Policy Framework) TXT evaluation
- DMARC (Domain-based Message Authentication) policy parsing
- DKIM (DomainKeys Identified Mail) selector probing
- Lookalike / typosquatting detection against verified company domains
- Audit trail persistence into the `domain_checks` database table
"""

from datetime import datetime, timezone
import ipaddress
import logging
from threading import Lock
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import dns
import dns.exception
import dns.resolver
from sqlalchemy.orm import Session

from app.models.company import CompanyDomain
from app.models.domain import DomainCheck

logger = logging.getLogger("jobshield.verification.domain_checker")

DEFAULT_DNS_TIMEOUT = 2.0
DEFAULT_DNS_LIFETIME = 2.5
DEFAULT_DOMAIN_CHECK_BUDGET = 8.0


class BoundedDNSCache:
    """Thread-safe in-memory cache for DNS query results with bounded size and TTL."""

    def __init__(self, max_items: int = 256, ttl_seconds: float = 60.0):
        self.max_items = max_items
        self.ttl = ttl_seconds
        self._cache: Dict[Tuple[str, str], Tuple[float, Any]] = {}
        self._lock = Lock()

    def get(self, qname: str, rdtype: str) -> Optional[Any]:
        key = (qname.lower().rstrip("."), rdtype.upper())
        with self._lock:
            item = self._cache.get(key)
            if not item:
                return None
            timestamp, value = item
            if time.monotonic() - timestamp > self.ttl:
                del self._cache[key]
                return None
            return value

    def set(self, qname: str, rdtype: str, value: Any) -> None:
        key = (qname.lower().rstrip("."), rdtype.upper())
        with self._lock:
            if len(self._cache) >= self.max_items:
                # Evict oldest 20% of entries
                sorted_keys = sorted(self._cache.keys(), key=lambda k: self._cache[k][0])
                for k in sorted_keys[: max(1, self.max_items // 5)]:
                    self._cache.pop(k, None)
            self._cache[key] = (time.monotonic(), value)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()


dns_cache = BoundedDNSCache()

# Known top employers to protect against typosquatting even if company_domains table is empty
WELL_KNOWN_LEGITIMATE_DOMAINS: List[str] = [
    "infosys.com",
    "capgemini.com",
    "tcs.com",
    "wipro.com",
    "hcltech.com",
    "techmahindra.com",
    "accenture.com",
    "cognizant.com",
    "google.com",
    "microsoft.com",
    "amazon.com",
    "apple.com",
    "meta.com",
    "ibm.com",
]

COMMON_DKIM_SELECTORS: List[str] = [
    "default",
    "google",
    "k1",
    "selector1",
    "mail",
    "mailjet",
    "mandrill",
    "s1",
    "s2",
]


def extract_domain_from_url_or_host(target: str) -> str:
    """Extracts a clean, normalized base domain or host string.

    Handles full URLs (e.g. 'https://careers.infosys.com/jobs/123'),
    raw domains ('infosys.com'), and domains with ports ('example.com:8080').
    Strips 'www.' and converts to lowercase.
    """
    clean_target = (target or "").strip().lower()
    if not clean_target:
        return ""

    if "://" in clean_target:
        parsed = urlparse(clean_target)
        host = parsed.hostname or ""
    else:
        # Check if user passed host:port or host/path
        parsed = urlparse(f"http://{clean_target}")
        host = parsed.hostname or clean_target.split("/")[0].split(":")[0]

    if host.startswith("www."):
        host = host[4:]

    return host.strip()


def levenshtein_distance(s1: str, s2: str) -> int:
    """Computes the Levenshtein edit distance between two strings."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)

    previous_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


def normalize_homoglyphs(s: str) -> str:
    """Replaces common visually confusable characters with canonical ASCII equivalents."""
    replacements = {
        "0": "o",
        "1": "l",
        "3": "e",
        "5": "s",
        "8": "b",
        "vv": "w",
        "rn": "m",
    }
    res = s
    for k, v in replacements.items():
        res = res.replace(k, v)
    return res


def get_base_name_and_tld(domain: str) -> Tuple[str, str]:
    """Splits 'infosys.com' into ('infosys', 'com') or 'sub.corp.co.in' into ('sub.corp', 'co.in')."""
    parts = domain.split(".")
    if len(parts) <= 1:
        return domain, ""
    if len(parts) >= 3 and parts[-2] in ("co", "com", "gov", "ac", "org", "net"):
        return ".".join(parts[:-2]), ".".join(parts[-2:])
    return ".".join(parts[:-1]), parts[-1]


def detect_lookalikes(domain: str, reference_domains: List[str]) -> Dict[str, Any]:
    """Detects typosquatting, homoglyphs, and lookalike patterns against verified legitimate domains.

    Returns a structured dictionary of lookalike flags and evidence.
    """
    clean_domain = extract_domain_from_url_or_host(domain)
    if not clean_domain:
        return {"is_lookalike": False}

    domain_base, domain_tld = get_base_name_and_tld(clean_domain)
    domain_homoglyph = normalize_homoglyphs(domain_base)

    for ref in reference_domains:
        clean_ref = extract_domain_from_url_or_host(ref)
        if not clean_ref:
            continue

        ref_base, ref_tld = get_base_name_and_tld(clean_ref)

        # Exact match to legitimate domain is authentic, not a lookalike
        if clean_domain == clean_ref:
            return {
                "is_lookalike": False,
                "is_official_domain": True,
                "matched_legitimate_domain": clean_ref,
            }

        # Check both raw domain base and homoglyph-normalized base
        candidate_bases = [domain_base]
        if domain_homoglyph != domain_base:
            candidate_bases.append(domain_homoglyph)

        # 1. Homoglyph detection (e.g., 'inf0sys.com' vs 'infosys.com')
        if domain_base != ref_base and domain_homoglyph == ref_base:
            return {
                "is_lookalike": True,
                "similarity_type": "homoglyph_substitution",
                "matched_legitimate_domain": clean_ref,
                "confidence": 0.95,
                "warning": (
                    f"Suspicious homoglyph substitution detected: '{clean_domain}' "
                    f"mimics verified legitimate domain '{clean_ref}'."
                ),
            }

        # 2. Levenshtein edit distance check on the base domain (e.g. 'capgeminl.com' vs 'capgemini.com')
        for cand in candidate_bases:
            dist = levenshtein_distance(cand, ref_base)
            if 1 <= dist <= 2 and len(ref_base) >= 5:
                return {
                    "is_lookalike": True,
                    "similarity_type": "edit_distance_typosquat",
                    "matched_legitimate_domain": clean_ref,
                    "edit_distance": dist,
                    "confidence": 0.85 if dist == 1 else 0.70,
                    "warning": (
                        f"Possible typosquatting detected (edit distance {dist}): '{clean_domain}' "
                        f"closely resembles verified company domain '{clean_ref}'."
                    ),
                }

        # 3. Suspicious brand prefix/suffix/hyphenation (e.g. 'infosys-careers.com' or 'inf0sys-careers.com')
        for cand in candidate_bases:
            if (
                cand.startswith(f"{ref_base}-")
                or cand.endswith(f"-{ref_base}")
                or f"-{ref_base}-" in cand
                or cand.startswith(f"{ref_base}recruitment")
                or cand.startswith(f"{ref_base}careers")
                or cand.startswith(f"{ref_base}jobs")
            ):
                return {
                    "is_lookalike": True,
                    "similarity_type": "brand_prefix_suffix_spoof",
                    "matched_legitimate_domain": clean_ref,
                    "confidence": 0.80,
                    "warning": (
                        f"Suspicious domain naming pattern: '{clean_domain}' incorporates "
                        f"brand keyword of verified company '{clean_ref}' with hyphenated recruitment terms."
                    ),
                }

    return {"is_lookalike": False}


def check_dns_resolution(
    domain: str,
    resolver: dns.resolver.Resolver,
    use_cache: bool = True,
) -> Tuple[str, List[str]]:
    """Resolves A and AAAA records for the target domain."""
    if use_cache:
        cached = dns_cache.get(domain, "ADDR")
        if cached is not None:
            return cached

    resolved_ips: List[str] = []
    status = "NOT_FOUND"
    try:
        # A records (IPv4)
        try:
            answers_a = resolver.resolve(domain, "A")
            for rdata in answers_a:
                resolved_ips.append(str(rdata))
        except (dns.resolver.NoAnswer, dns.resolver.NoNameservers):
            pass

        # AAAA records (IPv6)
        try:
            answers_aaaa = resolver.resolve(domain, "AAAA")
            for rdata in answers_aaaa:
                resolved_ips.append(str(rdata))
        except (dns.resolver.NoAnswer, dns.resolver.NoNameservers):
            pass

        if resolved_ips:
            status = "PASS"
        else:
            status = "NOT_FOUND"

    except dns.resolver.NXDOMAIN:
        status = "NOT_FOUND"
    except (dns.exception.Timeout, dns.resolver.LifetimeTimeout):
        status = "TIMEOUT"
    except Exception as exc:
        logger.warning("DNS resolution check failed for '%s': %s", domain, exc)
        status = "ERROR"

    result = (status, resolved_ips)
    if use_cache and status != "ERROR":
        dns_cache.set(domain, "ADDR", result)
    return result


def check_mx_records(
    domain: str,
    resolver: dns.resolver.Resolver,
    use_cache: bool = True,
) -> Tuple[str, List[Dict[str, Any]]]:
    """Queries Mail Exchange (MX) records to verify active mail routing capability."""
    if use_cache:
        cached = dns_cache.get(domain, "MX")
        if cached is not None:
            return cached

    try:
        answers = resolver.resolve(domain, "MX")
        mx_records: List[Dict[str, Any]] = []
        for rdata in answers:
            mx_records.append({
                "exchange": str(rdata.exchange).rstrip("."),
                "preference": int(rdata.preference),
            })
        mx_records.sort(key=lambda x: x["preference"])
        result = ("PASS", mx_records) if mx_records else ("NOT_FOUND", [])
    except (dns.resolver.NoAnswer, dns.resolver.NoNameservers, dns.resolver.NXDOMAIN):
        result = ("NOT_FOUND", [])
    except (dns.exception.Timeout, dns.resolver.LifetimeTimeout):
        result = ("TIMEOUT", [])
    except Exception as exc:
        logger.warning("MX check failed for '%s': %s", domain, exc)
        result = ("ERROR", [])

    if use_cache and result[0] != "ERROR":
        dns_cache.set(domain, "MX", result)
    return result


def check_spf_record(
    domain: str,
    resolver: dns.resolver.Resolver,
    use_cache: bool = True,
) -> Tuple[str, Optional[str], Optional[str]]:
    """Queries TXT records on the root domain to locate and evaluate SPF policy."""
    if use_cache:
        cached = dns_cache.get(domain, "SPF")
        if cached is not None:
            return cached

    try:
        answers = resolver.resolve(domain, "TXT")
        for rdata in answers:
            txt_string = "".join(s.decode("utf-8", errors="replace") for s in rdata.strings)
            if txt_string.startswith("v=spf1"):
                policy = "NEUTRAL"
                if "-all" in txt_string:
                    policy = "HARD_FAIL"
                elif "~all" in txt_string:
                    policy = "SOFT_FAIL"
                elif "+all" in txt_string:
                    policy = "PERMISSIVE_PASS"
                elif "?all" in txt_string:
                    policy = "NEUTRAL"

                result = ("PASS", txt_string, policy)
                if use_cache:
                    dns_cache.set(domain, "SPF", result)
                return result

        result = ("NOT_FOUND", None, None)
    except (dns.resolver.NoAnswer, dns.resolver.NoNameservers, dns.resolver.NXDOMAIN):
        result = ("NOT_FOUND", None, None)
    except (dns.exception.Timeout, dns.resolver.LifetimeTimeout):
        result = ("TIMEOUT", None, None)
    except Exception as exc:
        logger.warning("SPF check failed for '%s': %s", domain, exc)
        result = ("ERROR", None, None)

    if use_cache and result[0] != "ERROR":
        dns_cache.set(domain, "SPF", result)
    return result


def check_dmarc_record(
    domain: str,
    resolver: dns.resolver.Resolver,
    use_cache: bool = True,
) -> Tuple[str, Optional[str], Optional[str]]:
    """Queries TXT record on '_dmarc.<domain>' for DMARC enforcement policy."""
    dmarc_domain = f"_dmarc.{domain}"
    if use_cache:
        cached = dns_cache.get(dmarc_domain, "DMARC")
        if cached is not None:
            return cached

    try:
        answers = resolver.resolve(dmarc_domain, "TXT")
        for rdata in answers:
            txt_string = "".join(s.decode("utf-8", errors="replace") for s in rdata.strings)
            if txt_string.startswith("v=DMARC1"):
                policy = "none"
                for tag in txt_string.split(";"):
                    tag_clean = tag.strip().lower()
                    if tag_clean.startswith("p="):
                        policy = tag_clean.split("=")[1].strip()
                        break
                result = ("PASS", txt_string, policy)
                if use_cache:
                    dns_cache.set(dmarc_domain, "DMARC", result)
                return result

        result = ("NOT_FOUND", None, None)
    except (dns.resolver.NoAnswer, dns.resolver.NoNameservers, dns.resolver.NXDOMAIN):
        result = ("NOT_FOUND", None, None)
    except (dns.exception.Timeout, dns.resolver.LifetimeTimeout):
        result = ("TIMEOUT", None, None)
    except Exception as exc:
        logger.warning("DMARC check failed for '%s': %s", dmarc_domain, exc)
        result = ("ERROR", None, None)

    if use_cache and result[0] != "ERROR":
        dns_cache.set(dmarc_domain, "DMARC", result)
    return result


def check_dkim_selector(
    domain: str,
    resolver: dns.resolver.Resolver,
    selectors: Optional[List[str]] = None,
    time_limit_func: Optional[Any] = None,
    use_cache: bool = True,
) -> Tuple[str, Optional[str], Optional[str]]:
    """Probes well-known standard DKIM selectors on '<selector>._domainkey.<domain>'."""
    if use_cache:
        cached = dns_cache.get(domain, "DKIM")
        if cached is not None:
            return cached

    # Limit standard selectors to top common selectors to bound DNS overhead
    probed_selectors = selectors or COMMON_DKIM_SELECTORS[:4]
    had_timeout = False

    for sel in probed_selectors:
        if time_limit_func and time_limit_func() < 0.4:
            break

        dkim_domain = f"{sel}._domainkey.{domain}"
        try:
            answers = resolver.resolve(dkim_domain, "TXT")
            for rdata in answers:
                txt_string = "".join(s.decode("utf-8", errors="replace") for s in rdata.strings)
                if "v=DKIM1" in txt_string or "p=" in txt_string:
                    result = ("PASS", sel, txt_string)
                    if use_cache:
                        dns_cache.set(domain, "DKIM", result)
                    return result
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers):
            continue
        except (dns.exception.Timeout, dns.resolver.LifetimeTimeout):
            had_timeout = True
            continue
        except Exception:
            continue

    status = "TIMEOUT" if had_timeout else "NOT_FOUND"
    result = (status, None, None)
    if use_cache and status != "ERROR":
        dns_cache.set(domain, "DKIM", result)
    return result


class DomainCheckResult:
    """Consolidated result for domain security and email authentication checks."""

    def __init__(
        self,
        domain: str,
        dns_status: str,
        mx_status: str,
        spf_status: str,
        dkim_status: str,
        dmarc_status: str,
        lookalike_flags: Dict[str, Any],
        source_details: Dict[str, Any],
        checked_at: datetime,
    ):
        self.domain = domain
        self.dns_status = dns_status
        self.mx_status = mx_status
        self.spf_status = spf_status
        self.dkim_status = dkim_status
        self.dmarc_status = dmarc_status
        self.lookalike_flags = lookalike_flags
        self.source_details = source_details
        self.checked_at = checked_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "domain": self.domain,
            "dns_status": self.dns_status,
            "mx_status": self.mx_status,
            "spf_status": self.spf_status,
            "dkim_status": self.dkim_status,
            "dmarc_status": self.dmarc_status,
            "lookalike_flags": self.lookalike_flags,
            "source_details": self.source_details,
            "checked_at": self.checked_at.isoformat(),
        }


def check_domain_security(
    domain_or_url: str,
    db: Optional[Session] = None,
    timeout: float = DEFAULT_DNS_TIMEOUT,
    lifetime: float = DEFAULT_DNS_LIFETIME,
    max_budget_seconds: float = DEFAULT_DOMAIN_CHECK_BUDGET,
    use_cache: bool = True,
) -> DomainCheckResult:
    """Executes bounded domain verification pipeline and optionally persists results in domain_checks."""
    domain = extract_domain_from_url_or_host(domain_or_url)
    checked_at = datetime.now(timezone.utc)

    # Check if domain is an IP address or empty
    is_ip = False
    if domain:
        try:
            ipaddress.ip_address(domain.strip("[]"))
            is_ip = True
        except ValueError:
            is_ip = False

    if not domain or is_ip:
        return DomainCheckResult(
            domain=domain_or_url,
            dns_status="NOT_APPLICABLE",
            mx_status="NOT_APPLICABLE",
            spf_status="NOT_APPLICABLE",
            dkim_status="NOT_APPLICABLE",
            dmarc_status="NOT_APPLICABLE",
            lookalike_flags={"is_lookalike": False, "note": "Target is an IP literal or invalid domain"},
            source_details={"note": "Technical domain email checks are not applicable to IP literals."},
            checked_at=checked_at,
        )

    # Time budget tracker
    start_time = time.monotonic()

    def time_remaining() -> float:
        return max(0.0, max_budget_seconds - (time.monotonic() - start_time))

    # Configure DNS resolver with dynamic bounded timeouts
    resolver = dns.resolver.Resolver()
    resolver.timeout = min(timeout, max(0.8, time_remaining()))
    resolver.lifetime = min(lifetime, max(1.0, time_remaining()))

    # 1. DNS Resolution
    dns_status, resolved_ips = check_dns_resolution(domain, resolver, use_cache=use_cache)

    # 2. MX Mail Exchange Route
    if time_remaining() < 0.5:
        mx_status, mx_records = "SKIPPED", []
    else:
        resolver.timeout = min(timeout, max(0.8, time_remaining()))
        resolver.lifetime = min(lifetime, max(1.0, time_remaining()))
        mx_status, mx_records = check_mx_records(domain, resolver, use_cache=use_cache)

    # 3. SPF Authentication
    if time_remaining() < 0.5:
        spf_status, spf_record, spf_policy = "SKIPPED", None, None
    else:
        resolver.timeout = min(timeout, max(0.8, time_remaining()))
        resolver.lifetime = min(lifetime, max(1.0, time_remaining()))
        spf_status, spf_record, spf_policy = check_spf_record(domain, resolver, use_cache=use_cache)

    # 4. DMARC Authentication
    if time_remaining() < 0.5:
        dmarc_status, dmarc_record, dmarc_policy = "SKIPPED", None, None
    else:
        resolver.timeout = min(timeout, max(0.8, time_remaining()))
        resolver.lifetime = min(lifetime, max(1.0, time_remaining()))
        dmarc_status, dmarc_record, dmarc_policy = check_dmarc_record(domain, resolver, use_cache=use_cache)

    # 5. DKIM Common Selector Probe
    if time_remaining() < 0.5:
        dkim_status, dkim_selector, dkim_record = "SKIPPED", None, None
    else:
        resolver.timeout = min(timeout, max(0.8, time_remaining()))
        resolver.lifetime = min(lifetime, max(1.0, time_remaining()))
        dkim_status, dkim_selector, dkim_record = check_dkim_selector(
            domain,
            resolver,
            time_limit_func=time_remaining,
            use_cache=use_cache,
        )

    # 6. Lookalike / Typosquatting Detection
    reference_domains = list(WELL_KNOWN_LEGITIMATE_DOMAINS)
    if db is not None:
        try:
            # Query verified official domains from CompanyDomain table
            db_domains = (
                db.query(CompanyDomain.domain)
                .filter(CompanyDomain.domain.isnot(None))
                .distinct()
                .all()
            )
            for row in db_domains:
                if row[0]:
                    reference_domains.append(row[0].strip().lower())
        except Exception as exc:
            logger.warning("Could not query company_domains table: %s", exc)

    lookalike_flags = detect_lookalikes(domain, reference_domains)

    source_details = {
        "resolved_ips": resolved_ips,
        "mx_records": mx_records,
        "spf_record": spf_record,
        "spf_policy": spf_policy,
        "dmarc_record": dmarc_record,
        "dmarc_policy": dmarc_policy,
        "dkim_selector_found": dkim_selector,
        "dkim_record": dkim_record,
        "dkim_note": (
            "Probed standard selectors. Full DKIM verification requires an inbound email signature header."
        ),
    }

    result = DomainCheckResult(
        domain=domain,
        dns_status=dns_status,
        mx_status=mx_status,
        spf_status=spf_status,
        dkim_status=dkim_status,
        dmarc_status=dmarc_status,
        lookalike_flags=lookalike_flags,
        source_details=source_details,
        checked_at=checked_at,
    )

    # Persist audit record in domain_checks table if DB session is supplied
    if db is not None:
        try:
            record = DomainCheck(
                domain=domain,
                dns_status=dns_status,
                mx_status=mx_status,
                spf_status=spf_status,
                dkim_status=dkim_status,
                dmarc_status=dmarc_status,
                lookalike_flags=lookalike_flags,
                source_details=source_details,
                checked_at=checked_at,
            )
            db.add(record)
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.error("Failed to persist domain_check for %s: %s", domain, exc)

    return result
