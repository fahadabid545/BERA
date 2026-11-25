import socket
import threading

import pytest

import scan_public_address as scan
from scan_public_address import FAIL, INFO, PASS, WARN, Response

GOOD_HEADERS = {
    "strict-transport-security": "max-age=31536000; includeSubDomains",
    "content-security-policy": "default-src 'self'; script-src 'self' 'nonce-abc'; "
    "frame-ancestors 'none'",
    "x-content-type-options": "nosniff",
    "referrer-policy": "strict-origin-when-cross-origin",
    "x-frame-options": "DENY",
    "permissions-policy": "camera=()",
    "cross-origin-opener-policy": "same-origin",
    "server": "cloudflare",
}


class FakeProbe:
    """A site whose answers a test can change."""

    def __init__(self):
        self.days = 80
        self.old_tls = set()
        self.pages = {}
        self.origin = {80: "silent", 443: "silent"}
        self.open_ports = set()

    def certificate_days_left(self):
        if self.days is None:
            raise OSError
        return self.days

    def accepts_tls_at_most(self, version):
        return version.name in self.old_tls

    def get(self, path, *, method="GET", body=None, secure=True, port=None):
        if not secure:
            return self.pages.get("http", Response(301, {"location": "https://www.example.com/"}))
        if (method, path) in self.pages:
            return self.pages[(method, path)]
        return self.pages.get(path, self.default(path))

    def default(self, path):
        if path == "/robots.txt":
            return Response(200, {}, "User-agent: *\nAllow: /\nSitemap: https://x/sitemap.xml")
        if path == scan.WEBHOOK_PATH:
            return Response(400, {}, '{"error":{"code":"invalid_signature"}}')
        if path in scan.PRIVATE_PAGES:
            return Response(200, {**GOOD_HEADERS, "x-robots-tag": "noindex, nofollow"})
        return Response(200, GOOD_HEADERS)

    def origin_answers(self, address, port, *, host=None):
        return self.origin[port]

    def port_is_open(self, address, port):
        return port in self.open_ports


def by_name(results):
    return {result.name: result for result in results}


def test_a_well_set_up_site_passes_everything():
    results = scan.run_checks(FakeProbe(), origin_ip="203.0.113.7", host="www.example.com")
    assert [r.status for r in results if r.status == FAIL] == []
    assert by_name(results)["ssh port"].status == INFO


def test_without_an_origin_address_that_check_is_only_noted():
    results = by_name(scan.run_checks(FakeProbe()))
    assert results["server's own address"].status == INFO


class TestCertificate:
    @pytest.mark.parametrize(("days", "status"), [(80, PASS), (29, WARN), (13, FAIL), (None, FAIL)])
    def test_days_left(self, days, status):
        probe = FakeProbe()
        probe.days = days
        assert scan.check_certificate(probe).status == status


class TestTransport:
    def test_old_tls_still_accepted_fails_and_is_named(self):
        probe = FakeProbe()
        probe.old_tls = {"TLSv1_1"}
        result = scan.check_old_tls_refused(probe)
        assert result.status == FAIL and "TLSv1_1" in result.detail

    def test_http_must_go_to_https(self):
        probe = FakeProbe()
        assert scan.check_http_goes_to_https(probe).status == PASS
        probe.pages["http"] = Response(200, {})
        assert scan.check_http_goes_to_https(probe).status == FAIL
        probe.pages["http"] = Response(302, {"location": "http://www.example.com/"})
        assert scan.check_http_goes_to_https(probe).status == FAIL


class TestHeaders:
    @pytest.mark.parametrize(
        "missing",
        [
            "strict-transport-security",
            "content-security-policy",
            "x-content-type-options",
            "referrer-policy",
            "x-frame-options",
            "permissions-policy",
            "cross-origin-opener-policy",
        ],
    )
    def test_each_missing_header_fails(self, missing):
        probe = FakeProbe()
        probe.pages["/"] = Response(200, {k: v for k, v in GOOD_HEADERS.items() if k != missing})
        assert scan.check_headers(probe).status == FAIL

    def test_a_short_hsts_fails(self):
        probe = FakeProbe()
        probe.pages["/"] = Response(
            200, {**GOOD_HEADERS, "strict-transport-security": "max-age=60"}
        )
        assert scan.check_headers(probe).status == FAIL

    def test_inline_scripts_without_a_one_time_code_fail(self):
        probe = FakeProbe()
        policy = "default-src 'self'; script-src 'self' 'unsafe-inline'; frame-ancestors 'none'"
        probe.pages["/"] = Response(200, {**GOOD_HEADERS, "content-security-policy": policy})
        assert "inline" in scan.check_headers(probe).detail

    @pytest.mark.parametrize(
        "headers", [{"server": "nginx/1.24.0"}, {"server": "Apache 2"}, {"x-powered-by": "Next.js"}]
    )
    def test_an_announced_version_fails(self, headers):
        probe = FakeProbe()
        probe.pages["/"] = Response(200, {**GOOD_HEADERS, **headers})
        assert scan.check_no_version_announced(probe).status == FAIL

    def test_a_plain_server_name_passes(self):
        probe = FakeProbe()
        probe.pages["/"] = Response(200, {**GOOD_HEADERS, "server": "nginx"})
        assert scan.check_no_version_announced(probe).status == PASS


class TestPrivatePagesAndPayments:
    def test_a_private_page_without_noindex_fails_and_is_named(self):
        probe = FakeProbe()
        probe.pages["/admin/"] = Response(200, GOOD_HEADERS)
        result = scan.check_private_pages_not_indexed(probe)
        assert result.status == FAIL and "/admin/" in result.detail

    def test_robots_listing_a_private_path_fails(self):
        probe = FakeProbe()
        probe.pages["/robots.txt"] = Response(200, {}, "Disallow: /admin\n")
        assert scan.check_private_pages_not_indexed(probe).status == FAIL

    def test_the_payment_path_must_reach_our_app(self):
        probe = FakeProbe()
        assert scan.check_payment_notification_reaches_the_app(probe).status == PASS

    @pytest.mark.parametrize(
        "answer",
        [
            Response(403, {"cf-mitigated": "challenge"}, "Just a moment"),
            Response(200, {}, "ok"),
            Response(503, {}, ""),
            Response(400, {}, "<html>blocked</html>"),
        ],
    )
    def test_anything_else_means_something_in_front_changed_it(self, answer):
        probe = FakeProbe()
        probe.pages[("POST", scan.WEBHOOK_PATH)] = answer
        assert scan.check_payment_notification_reaches_the_app(probe).status == FAIL


class TestTheServerOwnAddress:
    def test_an_answer_without_cloudflare_fails(self):
        probe = FakeProbe()
        probe.origin[443] = "answered"
        result = scan.check_origin_ignores_visitors(probe, "203.0.113.7", "www.example.com")
        assert result.status == FAIL and "443" in result.detail

    def test_internal_ports_open_to_everyone_fail(self):
        probe = FakeProbe()
        probe.open_ports = {5432, 22}
        result = scan.check_origin_ignores_visitors(probe, "203.0.113.7", "www.example.com")
        assert result.status == FAIL and "5432" in result.detail and "22" not in result.detail

    def test_ssh_is_reported_but_never_a_failure(self):
        probe = FakeProbe()
        probe.open_ports = {22}
        results = by_name(scan.run_checks(probe, origin_ip="203.0.113.7", host="x"))
        assert results["ssh port"].status == INFO and "key-only" in results["ssh port"].detail


class TestTheRealProbeOnThisComputer:
    def serve(self, reply):
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)

        def answer():
            connection, _ = listener.accept()
            connection.recv(1024)
            connection.sendall(reply)
            connection.close()
            listener.close()

        threading.Thread(target=answer, daemon=True).start()
        return listener.getsockname()[1]

    def test_a_web_answer_is_seen_as_answered(self):
        port = self.serve(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n")
        assert scan.NetworkProbe("x").origin_answers("127.0.0.1", port) == "answered"

    def test_a_closed_connection_is_silent(self):
        port = self.serve(b"")
        assert scan.NetworkProbe("x").origin_answers("127.0.0.1", port) == "silent"

    def test_a_port_nobody_listens_on_is_silent_and_closed(self):
        probe = scan.NetworkProbe("x")
        free = socket.socket()
        free.bind(("127.0.0.1", 0))
        port = free.getsockname()[1]
        free.close()
        assert probe.origin_answers("127.0.0.1", port) == "silent"
        assert probe.port_is_open("127.0.0.1", port) is False


class TestTheCommand:
    def run_main(self, monkeypatch, probe, *extra):
        monkeypatch.setattr(scan, "NetworkProbe", lambda host, port: probe)
        return scan.main(["https://www.example.com", *extra])

    def test_all_good_exits_zero(self, monkeypatch, capsys):
        assert self.run_main(monkeypatch, FakeProbe()) == 0
        assert "PASSED" in capsys.readouterr().out

    def test_any_failure_exits_one_and_says_which(self, monkeypatch, capsys):
        probe = FakeProbe()
        probe.days = 3
        assert self.run_main(monkeypatch, probe) == 1
        output = capsys.readouterr().out
        assert "FAIL  certificate" in output and "FAILED: 1" in output

    @pytest.mark.parametrize(
        "address", ["http://www.example.com", "www.example.com", "https://x/page"]
    )
    def test_only_a_plain_https_address_is_accepted(self, address):
        with pytest.raises(SystemExit):
            scan.main([address])
