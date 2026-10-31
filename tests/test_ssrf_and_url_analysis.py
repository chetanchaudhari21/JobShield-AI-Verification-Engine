"""Comprehensive test suite for SSRF protections, technical domain checks, and Job URL analysis.

Conforms to Section 11 & Feature F3 of PROJECT_SPECIFICATION.md:
- Strict SSRF policy enforcement (localhost, 169.254.169.254, RFC-1918, metadata, redirects)
- Resource limit enforcement (1 MB body cap, timeouts, content-type)
- Domain security verification (DNS, MX, SPF, DMARC, DKIM)
- Lookalike / typosquatting detection against verified corporate domains
- End-to-end POST /api/v1/analyze/job-url API contract and persistence
"""

import socket
from unittest.mock import MagicMock, patch
import dns.resolver
import pytest

from app.models.domain import DomainCheck
from app.models.scan import ScanRequest
from app.schemas.analysis import JobUrlAnalysisResponse
from app.services.domain_checker import (
    WELL_KNOWN_LEGITIMATE_DOMAINS,
    check_domain_security,
    detect_lookalikes,
    extract_domain_from_url_or_host,
)
from app.services.html_extractor import extract_job_posting_from_html
from app.services.safe_fetch import (
    FetchNetworkError,
    FetchTimeoutError,
    InvalidContentTypeError,
    OversizedBodyError,
    PinnedIPSyncBackend,
    SafeFetchError,
    SafeFetchResult,
    SSRFBlockedError,
    is_ip_blocked,
    is_ipv4_blocked,
    is_ipv6_blocked,
    safe_fetch_url,
    validate_url_and_resolve_ips,
)


# ==============================================================================
# 1. SSRF Protection & Resource Limit Unit Tests
# ==============================================================================

class TestSSRFProtections:
    """Tests SSRF prevention rules under Section 11 of project specification."""

    def test_disallowed_schemes_blocked(self):
        """Verifies that non-HTTP/HTTPS schemes are strictly rejected."""
        disallowed = [
            "ftp://example.com/file.txt",
            "file:///etc/passwd",
            "gopher://example.com",
            "ws://example.com",
            "javascript:alert(1)",
        ]
        for url in disallowed:
            with pytest.raises(SSRFBlockedError) as exc_info:
                validate_url_and_resolve_ips(url)
            assert "not permitted" in str(exc_info.value).lower() or "invalid" in str(exc_info.value).lower()

    def test_localhost_and_loopback_blocked(self):
        """Rejects localhost hostname and loopback IPv4/IPv6 addresses."""
        targets = [
            "http://localhost/jobs",
            "http://localhost:8000/api",
            "http://127.0.0.1/careers",
            "http://127.0.0.2:8080/index.html",
            "http://[::1]/",
        ]
        for url in targets:
            with pytest.raises(SSRFBlockedError):
                validate_url_and_resolve_ips(url)

    def test_cloud_metadata_endpoints_blocked(self):
        """Rejects AWS, GCP, Azure, and OpenStack instance metadata endpoints."""
        metadata_targets = [
            "http://169.254.169.254/latest/meta-data/",
            "http://169.254.169.254/computeMetadata/v1/",
            "http://metadata.google.internal/computeMetadata/v1/",
            "http://instance-data/latest/meta-data/",
        ]
        for url in metadata_targets:
            with pytest.raises(SSRFBlockedError):
                validate_url_and_resolve_ips(url)

    def test_private_rfc1918_addresses_blocked(self):
        """Rejects private network ranges (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)."""
        private_ips = [
            "http://10.0.0.1/admin",
            "http://10.255.255.254/",
            "http://172.16.0.1/internal",
            "http://172.31.255.255/",
            "http://192.168.1.1/router",
            "http://192.168.0.100:3000/",
        ]
        for url in private_ips:
            with pytest.raises(SSRFBlockedError):
                validate_url_and_resolve_ips(url)

    def test_domain_resolving_to_private_ip_is_blocked(self):
        """Rejects public hostnames that resolve to internal or private IP addresses."""
        with patch("socket.getaddrinfo") as mock_gai:
            # Simulate DNS returning an RFC 1918 private address
            mock_gai.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.50", 80))
            ]
            with pytest.raises(SSRFBlockedError) as exc_info:
                validate_url_and_resolve_ips("http://internal-corp-service.com/job")
            assert "resolved to blocked ip" in str(exc_info.value).lower()

    def test_redirect_to_private_ip_is_blocked(self):
        """Ensures that redirects to private/internal IPs are caught and aborted."""
        # Hop 0: Valid public URL; returns redirect Location to 127.0.0.1
        mock_response = MagicMock()
        mock_response.status_code = 302
        mock_response.headers = {"location": "http://127.0.0.1:8000/secret"}

        with patch("app.services.safe_fetch.validate_url_and_resolve_ips") as mock_validate:
            # First call for initial public URL succeeds
            # Second call for redirect target raises SSRFBlockedError
            mock_validate.side_effect = [
                ("legit-public-site.com", ["93.184.216.34"]),
                SSRFBlockedError("Destination IP is blocked (private/loopback address)"),
            ]

            with patch("httpx.Client.stream") as mock_stream:
                mock_stream.return_value.__enter__.return_value = mock_response

                with pytest.raises(SSRFBlockedError) as exc_info:
                    safe_fetch_url("http://legit-public-site.com/job")
                assert "blocked" in str(exc_info.value).lower()

    def test_oversized_body_aborts_download(self):
        """Verifies that response bodies exceeding 1 MB are terminated during download."""
        chunk = b"A" * 65536  # 64 KB per chunk
        num_chunks = 20        # Total 1.28 MB (> 1 MB limit)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_response.iter_bytes.return_value = iter([chunk] * num_chunks)

        with patch("app.services.safe_fetch.validate_url_and_resolve_ips") as mock_validate:
            mock_validate.return_value = ("example.com", ["93.184.216.34"])

            with patch("httpx.Client.stream") as mock_stream:
                mock_stream.return_value.__enter__.return_value = mock_response

                with pytest.raises(OversizedBodyError) as exc_info:
                    safe_fetch_url("http://example.com/huge-job-page.html", max_bytes=1024 * 1024)
                assert "exceeded maximum limit" in str(exc_info.value).lower()

    def test_invalid_content_type_rejected(self):
        """Verifies that non-text/html responses (e.g. binary downloads) are rejected."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/octet-stream"}

        with patch("app.services.safe_fetch.validate_url_and_resolve_ips") as mock_validate:
            mock_validate.return_value = ("example.com", ["93.184.216.34"])

            with patch("httpx.Client.stream") as mock_stream:
                mock_stream.return_value.__enter__.return_value = mock_response

                with pytest.raises(InvalidContentTypeError) as exc_info:
                    safe_fetch_url("http://example.com/malware.exe")
                assert "unsupported content type" in str(exc_info.value).lower()

    def test_nat64_valid_public_ip_accepted(self):
        """
        Verifies that globally routable IPv4 addresses encoded in the RFC 6052
        Well-Known NAT64 prefix (64:ff9b::/96) are accepted without false-positive SSRF rejections.
        Example: 64:ff9b::1739:cea3 embeds 23.57.206.163 (Akamai public CDN).
        """
        import ipaddress
        ip = ipaddress.ip_address("64:ff9b::1739:cea3")
        assert is_ip_blocked(ip) is False

        # Verify DNS resolution of a host returning this NAT64 IP succeeds
        with patch("socket.getaddrinfo") as mock_gai:
            mock_gai.return_value = [
                (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("64:ff9b::1739:cea3", 443, 0, 0))
            ]
            hostname, resolved = validate_url_and_resolve_ips("https://www.tcs.com/careers/india")
            assert hostname == "www.tcs.com"
            assert "64:ff9b::1739:cea3" in resolved

        # Verify direct IP literal in URL is accepted
        host, ips = validate_url_and_resolve_ips("https://[64:ff9b::1739:cea3]/careers")
        assert host == "64:ff9b::1739:cea3"
        assert ips == ["64:ff9b::1739:cea3"]

    def test_nat64_with_private_embedded_ipv4_blocked(self):
        """
        Verifies that RFC 6052 NAT64 addresses embedding private RFC 1918 IPv4
        addresses (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16) are strictly blocked.
        """
        import ipaddress
        private_nat64 = [
            ("64:ff9b::a00:1", "10.0.0.1"),
            ("64:ff9b::ac10:1", "172.16.0.1"),
            ("64:ff9b::c0a8:101", "192.168.1.1"),
        ]
        for ip_str, embedded in private_nat64:
            ip = ipaddress.ip_address(ip_str)
            assert is_ip_blocked(ip) is True, f"NAT64 address {ip_str} (embedded {embedded}) should be blocked"

            with pytest.raises(SSRFBlockedError) as exc_info:
                validate_url_and_resolve_ips(f"http://[{ip_str}]/admin")
            assert "blocked" in str(exc_info.value).lower()

    def test_nat64_with_loopback_embedded_ipv4_blocked(self):
        """Rejects NAT64 address embedding 127.0.0.1 loopback address."""
        import ipaddress
        loopback_nat64 = ipaddress.ip_address("64:ff9b::7f00:1")
        assert is_ip_blocked(loopback_nat64) is True

        with pytest.raises(SSRFBlockedError):
            validate_url_and_resolve_ips("http://[64:ff9b::7f00:1]/internal")

    def test_nat64_with_cloud_metadata_and_link_local_blocked(self):
        """Rejects NAT64 address embedding 169.254.169.254 link-local metadata address."""
        import ipaddress
        metadata_nat64 = ipaddress.ip_address("64:ff9b::a9fe:a9fe")
        assert is_ip_blocked(metadata_nat64) is True

        with pytest.raises(SSRFBlockedError):
            validate_url_and_resolve_ips("http://[64:ff9b::a9fe:a9fe]/computeMetadata/v1/")

    def test_nat64_with_multicast_and_reserved_blocked(self):
        """Rejects NAT64 addresses embedding multicast, reserved, unspecified, broadcast, and CGNAT."""
        import ipaddress
        prohibited_nat64 = [
            ("64:ff9b::e000:1", "224.0.0.1"),          # Multicast
            ("64:ff9b::f000:1", "240.0.0.1"),          # Reserved
            ("64:ff9b::0", "0.0.0.0"),                 # Unspecified
            ("64:ff9b::ffff:ffff", "255.255.255.255"), # Broadcast
            ("64:ff9b::6440:1", "100.64.0.1"),         # CGNAT
            ("64:ff9b::c633:6401", "198.51.100.1"),     # TEST-NET-2
            ("64:ff9b::cb00:7101", "203.0.113.1"),     # TEST-NET-3
            ("64:ff9b::c000:201", "192.0.2.1"),        # TEST-NET-1
        ]
        for ip_str, embedded in prohibited_nat64:
            ip = ipaddress.ip_address(ip_str)
            assert is_ip_blocked(ip) is True, f"NAT64 address {ip_str} (embedded {embedded}) should be blocked"

    def test_mixed_dns_answers_rejected_if_any_ip_blocked(self):
        """
        Per specification: Validate every A and AAAA result; reject hostname if
        ANY returned destination is prohibited.
        """
        # Case 1: Valid NAT64 address mixed with 127.0.0.1
        with patch("socket.getaddrinfo") as mock_gai:
            mock_gai.return_value = [
                (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("64:ff9b::1739:cea3", 443, 0, 0)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
            ]
            with pytest.raises(SSRFBlockedError) as exc_info:
                validate_url_and_resolve_ips("https://mixed-legit-and-evil.com/jobs")
            assert "resolved to blocked ip" in str(exc_info.value).lower()
            assert "127.0.0.1" in str(exc_info.value)

        # Case 2: Valid public IPv4 mixed with cloud metadata IPv4
        with patch("socket.getaddrinfo") as mock_gai:
            mock_gai.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 80)),
            ]
            with pytest.raises(SSRFBlockedError) as exc_info:
                validate_url_and_resolve_ips("http://mixed-metadata.com/jobs")
            assert "resolved to blocked ip" in str(exc_info.value).lower()
            assert "169.254.169.254" in str(exc_info.value)

    def test_redirect_to_nat64_prohibited_destination_blocked(self):
        """Ensures redirects to prohibited NAT64 addresses are caught and rejected on subsequent hops."""
        mock_response = MagicMock()
        mock_response.status_code = 302
        mock_response.headers = {"location": "http://[64:ff9b::7f00:1]:8080/admin"}

        with patch("app.services.safe_fetch.validate_url_and_resolve_ips") as mock_validate:
            mock_validate.side_effect = [
                ("legit-public-site.com", ["93.184.216.34"]),
                SSRFBlockedError("Destination IP is blocked (private/loopback address)"),
            ]

            with patch("httpx.Client.stream") as mock_stream:
                mock_stream.return_value.__enter__.return_value = mock_response

                with pytest.raises(SSRFBlockedError) as exc_info:
                    safe_fetch_url("http://legit-public-site.com/job")
                assert "blocked" in str(exc_info.value).lower()

    def test_normal_public_ipv4_and_ipv6_accepted(self):
        """Ensures that normal public IPv4 and IPv6 addresses are permitted."""
        import ipaddress
        # Cloudflare public DNS IPv6
        cf_v6 = ipaddress.ip_address("2606:4700:4700::1111")
        assert is_ipv6_blocked(cf_v6) is False
        assert is_ip_blocked(cf_v6) is False

        # Google public DNS IPv6
        google_v6 = ipaddress.ip_address("2001:4860:4860::8888")
        assert is_ipv6_blocked(google_v6) is False
        assert is_ip_blocked(google_v6) is False

        # Public IPv4
        public_v4 = ipaddress.ip_address("93.184.216.34")
        assert is_ipv4_blocked(public_v4) is False
        assert is_ip_blocked(public_v4) is False

        # Private IPv6 should still be blocked
        assert is_ipv6_blocked(ipaddress.ip_address("fc00::1")) is True
        assert is_ipv6_blocked(ipaddress.ip_address("fe80::1")) is True
        assert is_ipv6_blocked(ipaddress.ip_address("::1")) is True

    def test_dns_pinning_backend_protects_against_unpinned_hosts(self):
        """
        Verifies that PinnedIPSyncBackend enforces destination pinning:
        attempting to connect to an unpinned host raises SSRFBlockedError.
        """
        backend = PinnedIPSyncBackend()
        backend.pin_host("allowed.example.com", ["93.184.216.34"])

        # Unpinned host is rejected immediately before socket connection
        with pytest.raises(SSRFBlockedError) as exc_info:
            backend.connect_tcp("unpinned-rebinding-target.com", 80)
        assert "not pre-validated or pinned" in str(exc_info.value)


# ==============================================================================
# 2. Domain Security & Lookalike Detection Tests
# ==============================================================================

class TestDomainChecker:
    """Tests technical domain verification and typosquatting/lookalike detection."""

    def test_extract_domain_from_url_or_host(self):
        assert extract_domain_from_url_or_host("https://careers.infosys.com/job/101") == "careers.infosys.com"
        assert extract_domain_from_url_or_host("http://www.capgemini.com/jobs") == "capgemini.com"
        assert extract_domain_from_url_or_host("tcs.com:443") == "tcs.com"
        assert extract_domain_from_url_or_host("wipro.com") == "wipro.com"

    def test_lookalike_homoglyph_detection(self):
        """Detects visual character substitution (e.g. '0' for 'o')."""
        flags = detect_lookalikes("inf0sys.com", WELL_KNOWN_LEGITIMATE_DOMAINS)
        assert flags["is_lookalike"] is True
        assert flags["similarity_type"] == "homoglyph_substitution"
        assert flags["matched_legitimate_domain"] == "infosys.com"
        assert flags["confidence"] >= 0.90

    def test_lookalike_edit_distance_detection(self):
        """Detects typosquatting within Levenshtein edit distance <= 2."""
        flags = detect_lookalikes("capgeminl.com", WELL_KNOWN_LEGITIMATE_DOMAINS)
        assert flags["is_lookalike"] is True
        assert flags["similarity_type"] == "edit_distance_typosquat"
        assert flags["matched_legitimate_domain"] == "capgemini.com"
        assert flags["edit_distance"] == 1

    def test_lookalike_brand_suffix_detection(self):
        """Detects unauthorized brand keyword hyphenation."""
        flags = detect_lookalikes("infosys-careers.com", WELL_KNOWN_LEGITIMATE_DOMAINS)
        assert flags["is_lookalike"] is True
        assert flags["similarity_type"] == "brand_prefix_suffix_spoof"
        assert flags["matched_legitimate_domain"] == "infosys.com"

    def test_authentic_domain_not_flagged_as_lookalike(self):
        """Ensures that legitimate verified corporate domains are recognized as authentic."""
        flags = detect_lookalikes("infosys.com", WELL_KNOWN_LEGITIMATE_DOMAINS)
        assert flags["is_lookalike"] is False
        assert flags.get("is_official_domain") is True

    def test_domain_security_check_with_db_persistence(self, db_session):
        """Verifies that check_domain_security records an entry in the domain_checks table."""
        # Mock DNS resolver queries to avoid live network flakiness in unit tests
        mock_a = MagicMock()
        mock_a.__iter__.return_value = ["93.184.216.34"]

        # Mock MX record answer
        mock_mx = MagicMock()
        mock_mx_item = MagicMock()
        mock_mx_item.exchange = "mail.example.com."
        mock_mx_item.preference = 10
        mock_mx.__iter__.return_value = [mock_mx_item]

        # Mock TXT record answer (SPF)
        mock_txt = MagicMock()
        mock_txt_item = MagicMock()
        mock_txt_item.strings = [b"v=spf1 include:_spf.google.com ~all"]
        mock_txt.__iter__.return_value = [mock_txt_item]

        def resolve_side_effect(qname, rdtype, **kwargs):
            if rdtype == "A":
                return mock_a
            if rdtype == "MX":
                return mock_mx
            if rdtype == "TXT":
                return mock_txt
            raise dns.resolver.NoAnswer()

        with patch("app.services.domain_checker.dns.resolver.Resolver.resolve", side_effect=resolve_side_effect):
            res = check_domain_security("example.com", db=db_session)

            assert res.domain == "example.com"
            assert res.dns_status == "PASS"
            assert res.mx_status == "PASS"
            assert res.spf_status == "PASS"

            # Check that record is persisted in domain_checks table
            persisted = db_session.query(DomainCheck).filter(DomainCheck.domain == "example.com").first()
            assert persisted is not None
            assert persisted.dns_status == "PASS"
            assert persisted.mx_status == "PASS"


# ==============================================================================
# 3. HTML Content Extractor Tests
# ==============================================================================

class TestHTMLExtractor:
    """Tests HTML parsing, JSON-LD microdata extraction, and text cleaning."""

    def test_extract_from_json_ld_schema(self):
        html = """
        <!DOCTYPE html>
        <html>
        <head>
          <script type="application/ld+json">
          {
            "@context": "https://schema.org/",
            "@type": "JobPosting",
            "title": "Software Engineer II",
            "description": "<p>Responsible for developing robust web services using Python and FastAPI.</p>",
            "hiringOrganization": {
              "@type": "Organization",
              "name": "Acme Technologies India Private Limited"
            }
          }
          </script>
        </head>
        <body>
          <h1>Careers</h1>
        </body>
        </html>
        """
        details = extract_job_posting_from_html(html)
        assert details.title == "Software Engineer II"
        assert details.company_name == "Acme Technologies India Private Limited"
        assert "FastAPI" in details.clean_text

    def test_extract_standard_meta_and_body(self):
        html = """
        <!DOCTYPE html>
        <html>
        <head>
          <title>Senior DevOps Architect - CloudCorp Careers</title>
          <meta property="og:site_name" content="CloudCorp Solutions">
        </head>
        <body>
          <nav><a href="/">Home</a></nav>
          <main>
            <h1>Senior DevOps Architect</h1>
            <p>We are looking for an experienced DevOps architect to manage Kubernetes clusters.</p>
            <p>Direct applications to hr@cloudcorp.com or recruiters@cloudcorp.com.</p>
          </main>
          <footer>Copyright 2026</footer>
        </body>
        </html>
        """
        details = extract_job_posting_from_html(html)
        assert details.title == "Senior DevOps Architect"
        assert details.company_name == "CloudCorp Solutions"
        assert "Kubernetes" in details.clean_text
        assert "Copyright" not in details.clean_text  # footer stripped
        assert "Home" not in details.clean_text       # nav stripped
        assert "hr@cloudcorp.com" in details.detected_emails
        assert "recruiters@cloudcorp.com" in details.detected_emails


# ==============================================================================
# 4. End-to-End POST /api/v1/analyze/job-url API Contract Tests
# ==============================================================================

class TestJobUrlAnalysisEndpoint:
    """Tests POST /api/v1/analyze/job-url endpoint via FastAPI test client."""

    def test_job_url_localhost_blocked_by_ssrf(self, test_client):
        """Verifies endpoint returns HTTP 400 when user submits a localhost URL."""
        response = test_client.post(
            "/api/v1/analyze/job-url",
            json={"url": "http://localhost:8000/internal-job"},
        )
        assert response.status_code == 400
        data = response.json()
        assert "security policy" in data["detail"].lower()

    def test_job_url_cloud_metadata_blocked(self, test_client):
        """Verifies endpoint returns HTTP 400 when user submits cloud metadata IP."""
        response = test_client.post(
            "/api/v1/analyze/job-url",
            json={"url": "http://169.254.169.254/latest/meta-data"},
        )
        assert response.status_code == 400
        data = response.json()
        assert "security policy" in data["detail"].lower()

    def test_job_url_insufficient_text_returns_sparse_content_partial_report(self, test_client):
        """Verifies endpoint returns structured partial report with JS_REQUIRED_OR_SPARSE_CONTENT when page has < 20 chars."""
        with patch("app.api.v1.analyze.safe_fetch_url") as mock_fetch:
            mock_fetch.return_value = SafeFetchResult(
                final_url="https://jobs.example.com/empty",
                status_code=200,
                content="<html><body><p>Hi</p></body></html>",
                content_type="text/html",
                redirect_history=[],
                resolved_ips=["93.184.216.34"],
            )

            response = test_client.post(
                "/api/v1/analyze/job-url",
                json={"url": "https://jobs.example.com/empty"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["page_type"] == "JS_REQUIRED_OR_SPARSE_CONTENT"
            assert data["risk_category"] == "INSUFFICIENT_EVIDENCE"
            assert data["risk_score"] is None
            assert any("copy" in action.lower() and "paste" in action.lower() for action in data["recommended_safe_actions"])

    def test_job_url_success_with_company_verification_and_domain_security(self, test_client, db_session):
        """Tests successful end-to-end URL analysis, extracting content, verifying entity, and checking domain."""
        sample_html = """
        <!DOCTYPE html>
        <html>
        <head>
          <title>Lead Java Architect - Infosys Limited</title>
          <meta property="og:site_name" content="Infosys Limited">
        </head>
        <body>
          <main>
            <h1>Lead Java Architect</h1>
            <p>Infosys is seeking a Lead Java Architect with 10+ years of enterprise Spring Boot experience.</p>
            <p>Must possess deep expertise in microservices architecture, Docker, and distributed systems.</p>
            <p>Submit your application or portfolio to careers@infosys.com.</p>
          </main>
        </body>
        </html>
        """

        with patch("app.api.v1.analyze.safe_fetch_url") as mock_fetch:
            mock_fetch.return_value = SafeFetchResult(
                final_url="https://careers.infosys.com/job/lead-java-architect",
                status_code=200,
                content=sample_html,
                content_type="text/html",
                redirect_history=[],
                resolved_ips=["93.184.216.34"],
            )

            response = test_client.post(
                "/api/v1/analyze/job-url",
                json={
                    "url": "https://careers.infosys.com/job/lead-java-architect",
                    "company_name": "Infosys Limited",
                },
            )

            assert response.status_code == 200
            data = response.json()

            # Validate response schema fields
            assert data["job_url"] == "https://careers.infosys.com/job/lead-java-architect"
            assert "Lead Java Architect" in data["extracted_title"]
            assert data["extracted_company"] == "Infosys Limited"
            assert data["risk_category"] in ("LOW", "MODERATE", "HIGH", "CRITICAL")
            assert "domain_check" in data
            assert data["domain_check"]["domain"] == "careers.infosys.com"
            assert "careers@infosys.com" in data["recruiter_checks"]["detected_emails"]

            # Verify scan request was persisted in DB with input_type='job_url'
            scan_rec = db_session.query(ScanRequest).filter(ScanRequest.id == data["report_id"]).first()
            assert scan_rec is not None
            assert scan_rec.input_type == "job_url"
            assert scan_rec.input_reference == "https://careers.infosys.com/job/lead-java-architect"

    def test_job_url_with_lookalike_domain_triggers_warning_evidence(self, test_client):
        """Verifies that lookalike URL domain triggers explicit lookalike evidence and caution banner."""
        sample_html = """
        <!DOCTYPE html>
        <html>
        <head><title>Urgent Remote Hiring</title></head>
        <body>
          <main>
            <h1>Data Entry Operator - Immediate Joining</h1>
            <p>Earn daily income working from home. No interview required.</p>
            <p>Send your resume immediately to hr@inf0sys-jobs.com.</p>
          </main>
        </body>
        </html>
        """

        with patch("app.api.v1.analyze.safe_fetch_url") as mock_fetch:
            mock_fetch.return_value = SafeFetchResult(
                final_url="https://inf0sys-careers.com/apply",
                status_code=200,
                content=sample_html,
                content_type="text/html",
                redirect_history=[],
                resolved_ips=["93.184.216.34"],
            )

            response = test_client.post(
                "/api/v1/analyze/job-url",
                json={"url": "https://inf0sys-careers.com/apply"},
            )

            assert response.status_code == 200
            data = response.json()

            # Lookalike flag should be True
            assert data["domain_check"]["lookalike_flags"]["is_lookalike"] is True
            assert data["domain_check"]["lookalike_flags"]["matched_legitimate_domain"] == "infosys.com"

            # Evidence should contain domain_lookalike_warning
            evidence_types = [e["evidence_type"] for e in data["evidence"]]
            assert "domain_lookalike_warning" in evidence_types

            # Safe actions should advise verifying authentic domain
            safe_actions = " ".join(data["recommended_safe_actions"]).lower()
            assert "verify" in safe_actions or "authentic" in safe_actions

    def test_job_url_access_restricted_403_returns_partial_report(self, test_client):
        """Verifies HTTP 403 bot protection returns structured ACCESS_RESTRICTED partial report instead of 422."""
        with patch("app.api.v1.analyze.safe_fetch_url") as mock_fetch:
            mock_fetch.return_value = SafeFetchResult(
                final_url="https://amazon.jobs/en/jobs/9999",
                status_code=403,
                content="<html><head><title>Access Denied</title></head><body>Cloudflare / Akamai Bot Protection</body></html>",
                content_type="text/html",
                redirect_history=[],
                resolved_ips=["54.239.28.85"],
            )

            response = test_client.post(
                "/api/v1/analyze/job-url",
                json={"url": "https://amazon.jobs/en/jobs/9999", "company_name": "Amazon"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["page_type"] == "ACCESS_RESTRICTED"
            assert data["fetch_status_code"] == 403
            assert data["risk_category"] == "INSUFFICIENT_EVIDENCE"
            assert data["risk_score"] is None
            evidence_types = [e["evidence_type"] for e in data["evidence"]]
            assert "access_restriction" in evidence_types
            assert "domain_technical_auth" in evidence_types
            assert any("copy and paste" in action.lower() for action in data["recommended_safe_actions"])

    def test_job_url_careers_homepage_classification(self, test_client):
        """Verifies generic corporate careers portal is classified as CAREERS_HOMEPAGE with prominent notice."""
        careers_html = """
        <!DOCTYPE html>
        <html>
        <head><title>Tata Consultancy Services Careers - India Portal</title></head>
        <body>
          <h1>Explore Careers at TCS</h1>
          <p>Join a global leader in IT consulting and digital transformation. Discover open roles across our hubs.</p>
          <p>Find your next role by searching through our current openings in software engineering and cloud services.</p>
        </body>
        </html>
        """
        with patch("app.api.v1.analyze.safe_fetch_url") as mock_fetch:
            mock_fetch.return_value = SafeFetchResult(
                final_url="https://www.tcs.com/careers/india",
                status_code=200,
                content=careers_html,
                content_type="text/html",
                redirect_history=[],
                resolved_ips=["23.57.9.234"],
            )

            response = test_client.post(
                "/api/v1/analyze/job-url",
                json={"url": "https://www.tcs.com/careers/india", "company_name": "Tata Consultancy Services"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["page_type"] == "CAREERS_HOMEPAGE"
            evidence_types = [e["evidence_type"] for e in data["evidence"]]
            assert "careers_homepage_notice" in evidence_types
            assert any("not confirm" in e["limitations"].lower() or "not prove" in e["limitations"].lower()
                       for e in data["evidence"] if e["evidence_type"] == "careers_homepage_notice")

    def test_job_url_with_embedded_credentials_blocked(self, test_client):
        """Verifies URLs with user:password embedded credentials are strictly rejected by security policy."""
        response = test_client.post(
            "/api/v1/analyze/job-url",
            json={"url": "http://attacker:secret@jobs.company.com/listing"},
        )
        assert response.status_code == 400
        assert "security policy" in response.json()["detail"].lower()


class TestBoundedDNSCache:
    """Verifies thread-safe bounded DNS caching behavior."""

    def test_cache_set_get_and_expiration(self):
        from app.services.domain_checker import BoundedDNSCache
        import time

        cache = BoundedDNSCache(max_items=3, ttl_seconds=1)
        cache.set("example.com", "A", ("PASS", ["93.184.216.34"]))
        assert cache.get("example.com", "A") == ("PASS", ["93.184.216.34"])
        assert cache.get("example.com", "MX") is None

        # Expiration
        time.sleep(1.1)
        assert cache.get("example.com", "A") is None

    def test_cache_max_entries_eviction(self):
        from app.services.domain_checker import BoundedDNSCache

        cache = BoundedDNSCache(max_items=2, ttl_seconds=60)
        cache.set("a.com", "A", ("PASS", ["1.1.1.1"]))
        cache.set("b.com", "A", ("PASS", ["2.2.2.2"]))
        cache.set("c.com", "A", ("PASS", ["3.3.3.3"]))

        # Oldest should be evicted
        assert cache.get("a.com", "A") is None
        assert cache.get("b.com", "A") == ("PASS", ["2.2.2.2"])
        assert cache.get("c.com", "A") == ("PASS", ["3.3.3.3"])

