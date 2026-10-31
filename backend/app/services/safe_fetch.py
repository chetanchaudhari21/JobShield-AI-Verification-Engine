"""SSRF-Safe HTTP Fetcher Module for JobShield AI.

Conforms to Section 11 & Feature F3 of PROJECT_SPECIFICATION.md:
- Scheme validation: only http and https allowed.
- IP Blacklisting: blocks localhost, loopback, private RFC-1918, link-local, multicast,
  and cloud metadata endpoints (169.254.169.254, metadata.google.internal).
- DNS Resolution & Validation: resolves hostnames and validates all resolved IPs.
- Re-validation on Redirects: manual redirect following with full re-validation at each hop.
- Resource Limits: timeouts (connect, read, total), maximum body size (1 MB), and allowed content types.
- Execution Safety: pure HTTP parsing; never executes downloaded JavaScript.
"""

import ipaddress
import logging
import socket
import typing
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

import httpcore
import httpx

logger = logging.getLogger("jobshield.security.safe_fetch")

MAX_REDIRECTS = 3
MAX_RESPONSE_BYTES = 1024 * 1024  # 1 MB
DEFAULT_CONNECT_TIMEOUT = 3.0
DEFAULT_READ_TIMEOUT = 8.0
DEFAULT_TOTAL_TIMEOUT = 15.0

ALLOWED_SCHEMES: Set[str] = {"http", "https"}
ALLOWED_CONTENT_TYPES: Tuple[str, ...] = (
    "text/html",
    "text/plain",
    "application/xhtml+xml",
    "application/xml",
    "text/xml",
)

BLOCKED_HOSTNAMES: Set[str] = {
    "localhost",
    "metadata.google.internal",
    "instance-data",
    "169.254.169.254",
}

NAT64_WELL_KNOWN_PREFIX = ipaddress.IPv6Network("64:ff9b::/96")

BLOCKED_IPV4_NETWORKS: List[ipaddress.IPv4Network] = [
    ipaddress.ip_network("0.0.0.0/8"),          # Current network (RFC 1122)
    ipaddress.ip_network("10.0.0.0/8"),         # Private RFC 1918
    ipaddress.ip_network("100.64.0.0/10"),      # Carrier-grade NAT (RFC 6598)
    ipaddress.ip_network("127.0.0.0/8"),        # Loopback (RFC 1122)
    ipaddress.ip_network("169.254.0.0/16"),     # Link-local / Cloud metadata (RFC 3927)
    ipaddress.ip_network("172.16.0.0/12"),      # Private RFC 1918
    ipaddress.ip_network("192.0.0.0/24"),       # IETF Protocol Assignments (RFC 6890)
    ipaddress.ip_network("192.0.2.0/24"),       # TEST-NET-1 (RFC 5737)
    ipaddress.ip_network("192.88.99.0/24"),     # 6to4 Anycast (RFC 7526)
    ipaddress.ip_network("192.168.0.0/16"),     # Private RFC 1918
    ipaddress.ip_network("198.18.0.0/15"),      # Benchmarking (RFC 2544)
    ipaddress.ip_network("198.51.100.0/24"),    # TEST-NET-2 (RFC 5737)
    ipaddress.ip_network("203.0.113.0/24"),     # TEST-NET-3 (RFC 5737)
    ipaddress.ip_network("224.0.0.0/4"),        # Multicast (RFC 5771)
    ipaddress.ip_network("240.0.0.0/4"),        # Reserved / Former Class E (RFC 1112)
    ipaddress.ip_network("255.255.255.255/32"), # Limited Broadcast (RFC 919)
]

BLOCKED_IPV6_NETWORKS: List[ipaddress.IPv6Network] = [
    ipaddress.ip_network("::/128"),             # Unspecified (RFC 4291)
    ipaddress.ip_network("::1/128"),            # Loopback (RFC 4291)
    ipaddress.ip_network("fc00::/7"),           # Unique local (RFC 4193)
    ipaddress.ip_network("fe80::/10"),          # Link-local (RFC 4291)
    ipaddress.ip_network("ff00::/8"),           # Multicast (RFC 4291)
    ipaddress.ip_network("2001:db8::/32"),      # Documentation (RFC 3849)
    ipaddress.ip_network("64:ff9b:1::/48"),     # Local-Use IPv4/IPv6 translation (RFC 8215)
]

BLOCKED_NETWORKS: List[ipaddress.IPv4Network | ipaddress.IPv6Network] = (
    BLOCKED_IPV4_NETWORKS + BLOCKED_IPV6_NETWORKS
)


class SafeFetchError(Exception):
    """Base error for SSRF safe fetcher violations."""
    pass


class SSRFBlockedError(SafeFetchError):
    """Raised when target URL violates SSRF safety policies."""
    pass


class OversizedBodyError(SafeFetchError):
    """Raised when response body exceeds maximum allowed size."""
    pass


class InvalidContentTypeError(SafeFetchError):
    """Raised when response Content-Type is not a permitted text/html format."""
    pass


class FetchTimeoutError(SafeFetchError):
    """Raised when network request times out."""
    pass


class FetchNetworkError(SafeFetchError):
    """Raised on connection failures or DNS resolution errors."""
    pass


class SafeFetchResult:
    """Encapsulates sanitized fetch output."""

    def __init__(
        self,
        final_url: str,
        status_code: int,
        content: str,
        content_type: str,
        redirect_history: List[str],
        resolved_ips: List[str],
    ):
        self.final_url = final_url
        self.status_code = status_code
        self.content = content
        self.content_type = content_type
        self.redirect_history = redirect_history
        self.resolved_ips = resolved_ips


def is_ipv4_blocked(ip: ipaddress.IPv4Address) -> bool:
    """Strictly checks whether an IPv4 address belongs to any blocked/private range."""
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or not ip.is_global
    ):
        return True

    for network in BLOCKED_IPV4_NETWORKS:
        if ip in network:
            return True
    return False


def is_ipv6_blocked(ip: ipaddress.IPv6Address) -> bool:
    """Strictly checks whether an IPv6 address belongs to any blocked/private range."""
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or not ip.is_global
    ):
        return True

    for network in BLOCKED_IPV6_NETWORKS:
        if ip in network:
            return True
    return False


def is_ip_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """
    Checks whether an IP address belongs to any blocked/private network.

    For addresses within the RFC 6052 Well-Known NAT64 prefix (64:ff9b::/96),
    the embedded IPv4 address (bits 96-127) is extracted and validated against
    the exact same strict IPv4 policy. This allows globally routable public IPv4
    destinations served over NAT64/DNS64 while strictly rejecting embedded
    private, loopback, link-local, multicast, or reserved ranges.
    """
    if isinstance(ip, ipaddress.IPv4Address):
        return is_ipv4_blocked(ip)

    if isinstance(ip, ipaddress.IPv6Address):
        # RFC 6052 Well-Known NAT64 Prefix: 64:ff9b::/96
        if ip in NAT64_WELL_KNOWN_PREFIX:
            embedded_v4_int = int(ip) & 0xFFFFFFFF
            embedded_v4 = ipaddress.IPv4Address(embedded_v4_int)
            return is_ipv4_blocked(embedded_v4)

        return is_ipv6_blocked(ip)

    return True


class PinnedIPSyncBackend(httpcore._backends.sync.SyncBackend):
    """
    Custom network backend for httpcore that pins outgoing TCP connections
    to pre-validated destination IP addresses.

    Prevents DNS rebinding and Time-Of-Check to Time-Of-Use (TOCTOU) attacks
    by connecting directly to an IP already verified by SSRF checks, while
    preserving standard TLS certificate validation, SNI, and HTTP Host header
    against the original target hostname.
    """

    def __init__(self, pinned_hosts: Optional[Dict[str, List[str]]] = None):
        super().__init__()
        self.pinned_hosts: Dict[str, List[str]] = {
            k.lower(): list(v) for k, v in (pinned_hosts or {}).items()
        }

    def pin_host(self, host: str, ips: List[str]) -> None:
        self.pinned_hosts[host.lower()] = list(ips)

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Optional[typing.Iterable[typing.Any]] = None,
    ) -> httpcore._backends.sync.SyncStream:
        ips_to_try = self.pinned_hosts.get(host.lower())
        if not ips_to_try:
            # Host was not pre-validated and pinned; abort immediately to prevent unvalidated DNS lookups
            raise SSRFBlockedError(
                f"Connection to host '{host}' aborted: destination was not pre-validated or pinned by SSRF policy."
            )

        last_exc: Optional[Exception] = None
        for ip in ips_to_try:
            clean_ip = ip.strip("[]")
            try:
                logger.debug("Connecting to host '%s' via pinned IP %s:%d", host, clean_ip, port)
                return super().connect_tcp(
                    host=clean_ip,
                    port=port,
                    timeout=timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except (socket.error, OSError, httpcore.ConnectError, httpcore.ConnectTimeout) as exc:
                logger.warning("Failed connecting to host '%s' via pinned IP %s:%d: %s", host, clean_ip, port, exc)
                last_exc = exc
                continue

        if last_exc:
            raise last_exc
        raise httpcore.ConnectError(f"Failed to connect to any resolved IP for host '{host}'.")


def validate_url_and_resolve_ips(url_str: str) -> Tuple[str, List[str]]:
    """
    Parses and validates a URL for SSRF vulnerabilities:
    - Verifies scheme is http or https.
    - Rejects blocked hostnames.
    - Resolves all A/AAAA records and ensures none are private, loopback, or metadata IPs.
    Returns: (hostname, list_of_validated_ips)
    """
    try:
        parsed = urlparse(url_str)
    except Exception as exc:
        raise SSRFBlockedError(f"Invalid URL structure: {exc}") from exc

    if len(url_str) > 2048:
        raise SSRFBlockedError("URL length exceeds maximum permitted limit of 2048 characters.")

    scheme = (parsed.scheme or "").lower()
    if scheme not in ALLOWED_SCHEMES:
        raise SSRFBlockedError(
            f"Scheme '{scheme}' is not permitted. Only HTTP and HTTPS are allowed."
        )

    if parsed.username or parsed.password:
        raise SSRFBlockedError(
            "URLs containing embedded credentials (user:password@host) are rejected by SSRF security policy."
        )

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise SSRFBlockedError("URL must include a valid hostname.")

    # Check hostname against blocklist and local patterns
    if (
        hostname in BLOCKED_HOSTNAMES
        or hostname.endswith(".localhost")
        or hostname.endswith(".local")
        or hostname.endswith(".internal")
    ):
        raise SSRFBlockedError(f"Access to host '{hostname}' is blocked by SSRF policy.")

    # Try parsing hostname directly as IP literal
    try:
        ip = ipaddress.ip_address(hostname)
        if is_ip_blocked(ip):
            raise SSRFBlockedError(
                f"Destination IP '{ip}' is blocked (private/loopback/cloud metadata address)."
            )
        return hostname, [str(ip)]
    except ValueError:
        # Hostname is a domain name, proceed to DNS resolution
        pass

    port = parsed.port or (443 if scheme == "https" else 80)

    try:
        addr_info = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise FetchNetworkError(f"DNS resolution failed for '{hostname}': {exc}") from exc
    except Exception as exc:
        raise FetchNetworkError(f"Unexpected error resolving '{hostname}': {exc}") from exc

    if not addr_info:
        raise FetchNetworkError(f"No IP addresses resolved for '{hostname}'.")

    resolved_ips: List[str] = []
    seen: Set[str] = set()
    for entry in addr_info:
        sockaddr = entry[4]
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            raise SSRFBlockedError(f"Invalid resolved IP '{ip_str}' for host '{hostname}'.")

        if is_ip_blocked(ip):
            raise SSRFBlockedError(
                f"Host '{hostname}' resolved to blocked IP '{ip}' (private/loopback/cloud metadata address)."
            )
        if str(ip) not in seen:
            seen.add(str(ip))
            resolved_ips.append(str(ip))

    return hostname, resolved_ips


def safe_fetch_url(
    url: str,
    max_bytes: int = MAX_RESPONSE_BYTES,
    max_redirects: int = MAX_REDIRECTS,
    timeout_seconds: float = DEFAULT_TOTAL_TIMEOUT,
) -> SafeFetchResult:
    """
    Performs an SSRF-safe HTTP GET request with:
    - Pre-fetch DNS resolution & IP validation
    - Step-by-step manual redirect following with re-validation
    - Strict response size limits (streaming byte count)
    - Content-type enforcement (text/html, text/plain)
    """
    current_url = url
    redirect_history: List[str] = []
    all_resolved_ips: List[str] = []

    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0"
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    timeouts = httpx.Timeout(
        timeout=timeout_seconds,
        connect=DEFAULT_CONNECT_TIMEOUT,
        read=DEFAULT_READ_TIMEOUT,
    )

    pinned_backend = PinnedIPSyncBackend()
    transport = httpx.HTTPTransport(verify=True)
    transport._pool = httpcore.ConnectionPool(
        ssl_context=transport._pool._ssl_context,
        network_backend=pinned_backend,
    )

    with httpx.Client(
        transport=transport,
        timeout=timeouts,
        headers=headers,
        follow_redirects=False,
    ) as client:
        for hop in range(max_redirects + 1):
            # Validate URL and resolve IPs before opening connection
            hostname, resolved_ips = validate_url_and_resolve_ips(current_url)
            pinned_backend.pin_host(hostname, resolved_ips)
            all_resolved_ips.extend(resolved_ips)

            try:
                # Issue request with stream=True to check headers before downloading
                with client.stream("GET", current_url) as response:
                    # Check for redirect status codes (301, 302, 303, 307, 308)
                    if response.status_code in (301, 302, 303, 307, 308):
                        location = response.headers.get("location")
                        if not location:
                            raise FetchNetworkError(
                                f"Redirect status {response.status_code} received without Location header."
                            )

                        redirect_history.append(current_url)
                        next_url = urljoin(current_url, location)
                        logger.info("Following safe redirect [%d]: %s -> %s", hop + 1, current_url, next_url)
                        current_url = next_url
                        continue

                    # Validate Content-Type
                    content_type_header = response.headers.get("content-type", "")
                    content_type_clean = content_type_header.split(";")[0].strip().lower()
                    if content_type_clean and not any(
                        content_type_clean.startswith(allowed) for allowed in ALLOWED_CONTENT_TYPES
                    ):
                        raise InvalidContentTypeError(
                            f"Unsupported content type '{content_type_clean}'. Only HTML and text documents can be analyzed."
                        )

                    # Validate Content-Length if provided
                    content_length = response.headers.get("content-length")
                    if content_length:
                        try:
                            cl_int = int(content_length)
                            if cl_int > max_bytes:
                                raise OversizedBodyError(
                                    f"Response content length ({cl_int} bytes) exceeds maximum limit of {max_bytes} bytes."
                                )
                        except ValueError:
                            pass

                    # Stream response content while enforcing strict byte cap
                    downloaded_chunks = []
                    total_bytes = 0
                    for chunk in response.iter_bytes(chunk_size=8192):
                        total_bytes += len(chunk)
                        if total_bytes > max_bytes:
                            raise OversizedBodyError(
                                f"Response body exceeded maximum limit of {max_bytes} bytes during download."
                            )
                        downloaded_chunks.append(chunk)

                    raw_body = b"".join(downloaded_chunks)

                    # Decode content
                    encoding = response.encoding or "utf-8"
                    try:
                        decoded_text = raw_body.decode(encoding, errors="replace")
                    except Exception:
                        decoded_text = raw_body.decode("utf-8", errors="replace")

                    return SafeFetchResult(
                        final_url=current_url,
                        status_code=response.status_code,
                        content=decoded_text,
                        content_type=content_type_clean or "text/html",
                        redirect_history=redirect_history,
                        resolved_ips=list(set(all_resolved_ips)),
                    )

            except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.TimeoutException) as exc:
                raise FetchTimeoutError(f"Connection timed out while fetching '{current_url}': {exc}") from exc
            except (httpx.ConnectError, httpx.NetworkError) as exc:
                raise FetchNetworkError(f"Network connection failed for '{current_url}': {exc}") from exc

        raise SSRFBlockedError(f"Exceeded maximum allowed redirects ({max_redirects}).")
