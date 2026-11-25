"""The nginx example must keep the rules the server's safety depends on."""

import re
from pathlib import Path

import pytest

FOLDER = Path(__file__).resolve().parents[2] / "nginx"
CONF = (FOLDER / "bera.example.conf").read_text()
GLOBAL = (FOLDER / "00-bera-global.conf").read_text()


def blocks():
    """The `server { ... }` blocks, split on their top-level braces."""
    found, depth, start = [], 0, None
    for index, char in enumerate(CONF):
        if char == "{":
            if depth == 0 and CONF[:index].rstrip().endswith("server"):
                start = CONF.rindex("server", 0, index)
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0 and start is not None:
                found.append(CONF[start : index + 1])
                start = None
    return found


def default_blocks():
    return [block for block in blocks() if "default_server" in block]


def test_an_unknown_name_or_the_ip_address_gets_no_answer_and_no_certificate():
    plain = next(b for b in default_blocks() if "listen 80 " in b)
    secure = next(b for b in default_blocks() if "listen 443 " in b)
    assert "return 444;" in plain
    assert "ssl_reject_handshake on;" in secure
    assert "ssl_certificate" not in secure.replace("ssl_reject_handshake", "")


@pytest.mark.parametrize("host", ["staging.example.com", "www.example.com"])
def test_each_site_demands_our_client_certificate_and_closes_otherwise(host):
    secure = next(b for b in blocks() if f"server_name {host};" in b and "listen 443" in b)
    assert "ssl_verify_client on;" in secure and "optional" not in secure
    assert re.search(r"ssl_client_certificate\s+\S+origin-pull-ca\.pem;", secure)
    assert "error_page 495 496 497 = @closed;" in secure and "return 444;" in secure


def test_staging_and_production_trust_different_authorities():
    paths = re.findall(r"ssl_client_certificate\s+(\S+);", CONF)
    assert len(paths) == 2 and len(set(paths)) == 2
    assert "staging" in paths[0] and "production" in paths[1]
    certificates = re.findall(r"ssl_certificate\s+(\S+);", CONF)
    assert len(set(certificates)) == len(certificates) == 2


def test_port_80_only_sends_known_names_to_https():
    for block in blocks():
        if "listen 80" in block and "default_server" not in block:
            assert "return 301 https://$host$request_uri;" in block
            assert "proxy_pass" not in block


def test_only_secure_sites_proxy_to_the_app():
    for block in blocks():
        if "proxy_pass" in block:
            assert "ssl_verify_client on;" in block


def test_the_proxy_adds_the_address_and_a_visitor_cannot_choose_it():
    assert CONF.count("proxy_add_x_forwarded_for") == 4
    assert "proxy_set_header X-Forwarded-For $http_x_forwarded_for" not in CONF


def test_strict_transport_security_is_sent_once():
    assert CONF.count("proxy_hide_header Strict-Transport-Security;") == 2
    assert (
        CONF.count(
            'add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;'
        )
        == 2
    )


def test_the_global_settings_hide_the_version_and_refuse_old_tls():
    assert "server_tokens off;" in GLOBAL
    assert "ssl_protocols TLSv1.2 TLSv1.3;" in GLOBAL
    assert "TLSv1 " not in GLOBAL and "TLSv1.1" not in GLOBAL
    assert "ssl_session_tickets off;" in GLOBAL


def test_the_example_ports_match_the_resource_table():
    assert "127.0.0.1:8001" in CONF and "127.0.0.1:8002" in CONF
