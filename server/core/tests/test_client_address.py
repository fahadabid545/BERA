import pytest
from django.test import RequestFactory

from core.client_address import UNKNOWN, client_address


def address_of(settings, proxies, remote="203.0.113.9", forwarded=None):
    settings.TRUSTED_PROXY_COUNT = proxies
    extra = {"REMOTE_ADDR": remote}
    if forwarded is not None:
        extra["HTTP_X_FORWARDED_FOR"] = forwarded
    return client_address(RequestFactory().get("/", **extra))


def test_without_proxies_the_connection_address_is_used_and_the_header_is_ignored(settings):
    assert address_of(settings, 0, forwarded="198.51.100.1") == "203.0.113.9"


def test_with_one_proxy_the_address_that_proxy_saw_is_used(settings):
    assert address_of(settings, 1, remote="10.0.0.2", forwarded="198.51.100.1") == "198.51.100.1"


def test_entries_a_visitor_wrote_themselves_are_ignored(settings):
    forged = "1.1.1.1, 2.2.2.2, 198.51.100.1"  # the visitor wrote the first two
    assert address_of(settings, 1, remote="10.0.0.2", forwarded=forged) == "198.51.100.1"


def test_with_two_proxies_the_second_from_the_end_is_the_visitor(settings):
    forwarded = "1.1.1.1, 198.51.100.1, 10.0.0.3"
    assert address_of(settings, 2, remote="10.0.0.2", forwarded=forwarded) == "198.51.100.1"


@pytest.mark.parametrize("forwarded", [None, "", "  ,  "])
def test_a_missing_header_falls_back_to_the_connection_address(settings, forwarded):
    assert address_of(settings, 1, forwarded=forwarded) == "203.0.113.9"


def test_fewer_entries_than_proxies_means_the_header_cannot_be_trusted(settings):
    assert address_of(settings, 2, forwarded="198.51.100.1") == "203.0.113.9"


@pytest.mark.parametrize("junk", ["not-an-address", "999.1.1.1", "' OR 1=1 --", "<script>"])
def test_junk_is_one_unknown_source_never_an_error(settings, junk):
    assert address_of(settings, 1, forwarded=junk) == UNKNOWN


def test_one_ipv6_network_counts_as_one_source(settings):
    first = address_of(settings, 0, remote="2001:db8:1:2:aaaa:bbbb:cccc:dddd")
    second = address_of(settings, 0, remote="2001:db8:1:2:1111:2222:3333:4444")
    other = address_of(settings, 0, remote="2001:db8:1:3::1")
    assert first == second == "2001:db8:1:2::/64"
    assert other != first


class TestCameThroughOurProxy:
    @pytest.mark.parametrize(
        ("proxies", "forwarded", "expected"),
        [
            (0, "198.51.100.7", False),
            (1, None, False),
            (1, "198.51.100.7", True),
            (2, "198.51.100.7", False),
            (2, "203.0.113.1, 198.51.100.7", True),
        ],
    )
    def test_it_needs_as_many_forwarding_entries_as_there_are_proxies(
        self, settings, proxies, forwarded, expected
    ):
        from django.test import RequestFactory

        from core.client_address import came_through_our_proxy

        settings.TRUSTED_PROXY_COUNT = proxies
        extra = {"HTTP_X_FORWARDED_FOR": forwarded} if forwarded else {}
        assert came_through_our_proxy(RequestFactory().get("/", **extra)) is expected
