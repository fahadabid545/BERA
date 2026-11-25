import logging

import pytest

from monitoring import heartbeat

ADDRESS = "https://hc-ping.example.test/fake-check-0001"  # nosecret: fake


class Answer:
    def __init__(self, status=200):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def requests_sent(monkeypatch):
    sent = []

    def fake_open(request, timeout):
        sent.append((request, timeout))
        return Answer()

    monkeypatch.setattr(heartbeat.urllib.request, "urlopen", fake_open)
    return sent


def test_the_ping_is_a_plain_get_with_no_data(requests_sent):
    assert heartbeat.ping(ADDRESS) is True
    request, timeout = requests_sent[0]
    assert request.get_method() == "GET" and request.data is None
    assert request.full_url == ADDRESS and "?" not in request.full_url
    assert set(request.headers) == {"User-agent"} and timeout == heartbeat.TIMEOUT_SECONDS


def test_no_address_means_nothing_is_sent(requests_sent):
    assert heartbeat.ping("") is True and requests_sent == []


def test_an_address_that_is_not_https_is_refused_without_a_request(requests_sent, caplog):
    with caplog.at_level(logging.ERROR):
        assert heartbeat.ping("http://hc-ping.example.test/fake-check-0001") is False
    assert requests_sent == [] and "fake-check-0001" not in caplog.text


def test_a_failure_is_reported_without_the_secret_address(monkeypatch, caplog):
    def broken(request, timeout):
        raise OSError(f"could not reach {request.full_url}")

    monkeypatch.setattr(heartbeat.urllib.request, "urlopen", broken)
    with caplog.at_level(logging.ERROR):
        assert heartbeat.ping(ADDRESS) is False
    assert "OSError" in caplog.text and "fake-check-0001" not in caplog.text


def test_a_service_error_answer_is_a_failure(monkeypatch):
    monkeypatch.setattr(heartbeat.urllib.request, "urlopen", lambda r, timeout: Answer(500))
    assert heartbeat.ping(ADDRESS) is False
