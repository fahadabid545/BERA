"""A security scan of the public address (and, optionally, of the server's own address).

    python scripts/scan_public_address.py https://www.example.com
    python scripts/scan_public_address.py https://www.example.com --origin-ip 203.0.113.10

It checks, from the outside: the certificate, that old TLS versions are refused, that http goes to
https, the security headers, that no version is announced, that private pages ask search engines to
stay away, that the payment notification address still reaches our app (nothing in front of it
blocks it), and, with --origin-ip, that the server itself ignores anyone who is not Cloudflare.
It only reads and sends harmless requests. Exit status 1 when any check fails.

Run it against staging and against production. It is no replacement for the outside scanners
named in the README (SSL Labs, securityheaders.com); it is the one that can run on every deploy.
"""

import argparse
import socket
import ssl
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from http.client import HTTPConnection, HTTPSConnection
from urllib.parse import urlsplit

PASS, FAIL, WARN, INFO = "PASS", "FAIL", "WARN", "INFO"
CERTIFICATE_FAIL_DAYS = 14
CERTIFICATE_WARN_DAYS = 30
HSTS_MINIMUM_SECONDS = 15_552_000  # 180 days
TIMEOUT_SECONDS = 8
WEBHOOK_PATH = "/api/payments/stripe/webhook/"
PRIVATE_PAGES = ("/admin/", "/company/", "/reset-password/example")
REQUIRED_HEADERS = (
    "X-Content-Type-Options",
    "Referrer-Policy",
    "X-Frame-Options",
    "Permissions-Policy",
    "Cross-Origin-Opener-Policy",
)
# Never reachable from outside: databases, the app's own ports, the queue's.
PORTS_THAT_MUST_BE_CLOSED = (3000, 3001, 3002, 5432, 6379, 8000, 8001, 8002)


@dataclass(frozen=True)
class Result:
    name: str
    status: str
    detail: str


@dataclass(frozen=True)
class Response:
    status: int
    headers: dict  # lower-case names
    body: str = ""


class NetworkProbe:
    """The real thing: plain sockets and the standard library."""

    def __init__(self, host, port=443):
        self.host, self.port = host, port

    def get(self, path, *, method="GET", body=None, secure=True, port=None):
        if secure:
            connection = HTTPSConnection(
                self.host,
                port or self.port,
                timeout=TIMEOUT_SECONDS,
                context=ssl.create_default_context(),
            )
        else:
            connection = HTTPConnection(self.host, port or 80, timeout=TIMEOUT_SECONDS)
        try:
            connection.request(method, path, body=body, headers={"User-Agent": "bera-scan"})
            answer = connection.getresponse()
            text = answer.read(20000).decode("utf-8", "replace")
            return Response(answer.status, {k.lower(): v for k, v in answer.getheaders()}, text)
        finally:
            connection.close()

    def certificate_days_left(self):
        context = ssl.create_default_context()
        with socket.create_connection((self.host, self.port), TIMEOUT_SECONDS) as raw:
            with context.wrap_socket(raw, server_hostname=self.host) as wrapped:
                expires = ssl.cert_time_to_seconds(wrapped.getpeercert()["notAfter"])
        return int((expires - datetime.now(UTC).timestamp()) // 86400)

    def accepts_tls_at_most(self, version):
        """True when the server completes a handshake limited to `version` (old, so bad)."""
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        context.minimum_version = ssl.TLSVersion.MINIMUM_SUPPORTED
        context.maximum_version = version
        try:
            with socket.create_connection((self.host, self.port), TIMEOUT_SECONDS) as raw:
                with context.wrap_socket(raw, server_hostname=self.host):
                    return True
        except (ssl.SSLError, OSError, ValueError):
            return False

    def origin_answers(self, address, port, *, host=None):
        """What the server's own address does with a visitor that is not Cloudflare:
        "silent" (nothing, refused or closed) or "answered" (it sent a web answer)."""
        try:
            with socket.create_connection((address, port), 4) as raw:
                if port == 443:
                    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE
                    raw = context.wrap_socket(raw, server_hostname=host)
                raw.settimeout(4)
                raw.sendall(
                    f"GET / HTTP/1.1\r\nHost: {host or address}\r\n"
                    "Connection: close\r\n\r\n".encode()
                )
                return "answered" if raw.recv(16).startswith(b"HTTP/") else "silent"
        except (OSError, ssl.SSLError):
            return "silent"

    def port_is_open(self, address, port):
        try:
            with socket.create_connection((address, port), 3):
                return True
        except OSError:
            return False


def check_certificate(probe):
    try:
        days = probe.certificate_days_left()
    except (OSError, ssl.SSLError, KeyError):
        return Result("certificate", FAIL, "no valid certificate for this name")
    if days < CERTIFICATE_FAIL_DAYS:
        return Result("certificate", FAIL, f"expires in {days} days")
    if days < CERTIFICATE_WARN_DAYS:
        return Result("certificate", WARN, f"expires in {days} days")
    return Result("certificate", PASS, f"valid, {days} days left")


def check_old_tls_refused(probe):
    old = [
        v.name
        for v in (ssl.TLSVersion.TLSv1, ssl.TLSVersion.TLSv1_1)
        if probe.accepts_tls_at_most(v)
    ]
    return (
        Result("old TLS refused", FAIL, f"still accepted: {', '.join(old)}")
        if old
        else Result("old TLS refused", PASS, "TLS 1.0 and 1.1 are refused")
    )


def check_http_goes_to_https(probe):
    answer = probe.get("/", secure=False)
    where = answer.headers.get("location", "")
    if answer.status in (301, 308) and where.startswith("https://"):
        return Result("http to https", PASS, f"{answer.status} to https")
    return Result(
        "http to https", FAIL, f"http answered {answer.status} without sending visitors to https"
    )


def check_headers(probe):
    answer = probe.get("/")
    problems = []
    seconds = answer.headers.get("strict-transport-security", "")
    maximum = next((part.split("=")[1] for part in seconds.split(";") if "max-age" in part), "0")
    if not maximum.strip().isdigit() or int(maximum) < HSTS_MINIMUM_SECONDS:
        problems.append("Strict-Transport-Security is missing or too short")
    policy = answer.headers.get("content-security-policy", "")
    if "frame-ancestors" not in policy or "default-src" not in policy:
        problems.append("Content-Security-Policy is missing or incomplete")
    scripts = next((d for d in policy.split(";") if d.strip().startswith("script-src")), "")
    if "unsafe-inline" in scripts and "nonce-" not in scripts:
        problems.append("scripts may run inline without a one-time code")
    problems += [
        f"{name} is missing" for name in REQUIRED_HEADERS if name.lower() not in answer.headers
    ]
    if answer.headers.get("x-content-type-options", "").lower() != "nosniff":
        problems.append("X-Content-Type-Options is not nosniff")
    return (
        Result("security headers", FAIL, "; ".join(problems))
        if problems
        else Result("security headers", PASS, "all present")
    )


def check_no_version_announced(probe):
    headers = probe.get("/").headers
    announced = [
        f"{name}: {headers[name]}"
        for name in ("server", "x-powered-by")
        if name in headers and (name == "x-powered-by" or any(c.isdigit() for c in headers[name]))
    ]
    return (
        Result("no version announced", FAIL, "; ".join(announced))
        if announced
        else Result("no version announced", PASS, "no software version in the headers")
    )


def check_private_pages_not_indexed(probe):
    open_to_search = []
    for path in PRIVATE_PAGES:
        answer = probe.get(path)
        if "noindex" not in answer.headers.get("x-robots-tag", "").lower():
            open_to_search.append(path)
    robots = probe.get("/robots.txt").body.lower()
    listed = [path for path in ("/admin", "/company") if path in robots]
    problems = [f"{path} has no noindex" for path in open_to_search] + [
        f"robots.txt lists {path}" for path in listed
    ]
    return (
        Result("private pages hidden from search", FAIL, "; ".join(problems))
        if problems
        else Result(
            "private pages hidden from search", PASS, "noindex on private pages, none listed"
        )
    )


def check_payment_notification_reaches_the_app(probe):
    """An unsigned request must be refused by OUR app (400, invalid_signature). Anything else
    means something in front (Cloudflare's firewall or bot rules, the proxy) changed the answer."""
    answer = probe.get(WEBHOOK_PATH, method="POST", body="{}")
    if answer.status == 400 and "invalid_signature" in answer.body:
        return Result(
            "payment notification path", PASS, "reaches the app and is refused without a signature"
        )
    return Result(
        "payment notification path",
        FAIL,
        f"answered {answer.status} instead of the app's refusal: "
        "check Cloudflare rules for this path",
    )


def check_origin_ignores_visitors(probe, address, host):
    problems = []
    for port in (80, 443):
        if probe.origin_answers(address, port, host=host) == "answered":
            problems.append(f"port {port} answered a visitor that is not Cloudflare")
    open_ports = [p for p in PORTS_THAT_MUST_BE_CLOSED if probe.port_is_open(address, p)]
    if open_ports:
        problems.append("ports open to everyone: " + ", ".join(map(str, open_ports)))
    return (
        Result("server's own address", FAIL, "; ".join(problems))
        if problems
        else Result(
            "server's own address", PASS, "no web answer without Cloudflare, internal ports closed"
        )
    )


def run_checks(probe, *, origin_ip=None, host=None):
    results = [
        check_certificate(probe),
        check_old_tls_refused(probe),
        check_http_goes_to_https(probe),
        check_headers(probe),
        check_no_version_announced(probe),
        check_private_pages_not_indexed(probe),
        check_payment_notification_reaches_the_app(probe),
    ]
    if origin_ip:
        results.append(check_origin_ignores_visitors(probe, origin_ip, host))
        ssh = "open (expected: key-only)" if probe.port_is_open(origin_ip, 22) else "closed"
        results.append(Result("ssh port", INFO, ssh))
    else:
        results.append(Result("server's own address", INFO, "not checked (give --origin-ip)"))
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("address", help="https://www.example.com")
    parser.add_argument(
        "--origin-ip", help="the server's own address, to prove Cloudflare is needed"
    )
    arguments = parser.parse_args(argv)
    parts = urlsplit(arguments.address)
    if parts.scheme != "https" or not parts.hostname or parts.path not in ("", "/"):
        parser.error("give the public address as https://name, nothing after it")
    results = run_checks(
        NetworkProbe(parts.hostname, parts.port or 443),
        origin_ip=arguments.origin_ip,
        host=parts.hostname,
    )
    for result in results:
        print(f"{result.status:5} {result.name}: {result.detail}")
    failed = [result for result in results if result.status == FAIL]
    print(f"\n{'FAILED' if failed else 'PASSED'}: {len(failed)} failed check(s).")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
