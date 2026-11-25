import json
import shutil
import subprocess
import types

import cloudflare_firewall as firewall
import pytest
from harden_common import HardeningError

V4 = ["173.245.48.0/20", "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22", "141.101.64.0/18"]
V6 = ["2400:cb00::/32", "2606:4700::/32", "2803:f800::/32"]
GOOD = {4: V4, 6: V6}


def listing(items):
    return "\n".join(items) + "\n"


class Page:
    def __init__(self, text):
        self.text = text

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self.text.encode()


def opener(pages):
    def open_address(address, timeout):
        return Page(pages[address])

    return open_address


@pytest.fixture
def commands(monkeypatch):
    """Records what would be run instead of running it; nft checks pass."""

    class Seen(list):
        dry_runs = []

    seen = Seen()
    seen.dry_runs = []

    def fake_run(command, *, dry_run=False, input_text=None, check=True):
        seen.append(list(command))
        seen.dry_runs.append(dry_run)
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(firewall, "run", fake_run)
    monkeypatch.setattr(firewall, "require_root", lambda: None)
    return seen


def arguments(tmp_path, dry_run=False):
    return types.SimpleNamespace(dry_run=dry_run, state_dir=str(tmp_path))


def use_list(monkeypatch, ranges=None, fail=False):
    def fetch():
        if fail:
            raise HardeningError("Cloudflare's address list could not be fetched.")
        return ranges or GOOD

    monkeypatch.setattr(firewall, "fetch_ranges", fetch)


class TestReadingTheList:
    def test_a_good_list_is_read(self):
        assert firewall.parse_ranges(listing(V4), 4) == sorted(V4)

    @pytest.mark.parametrize(
        "text", ["", "not-an-address\n" + listing(V4), "<html>blocked</html>", "1.2.3.4/33"]
    )
    def test_anything_that_is_not_an_address_list_is_refused(self, text):
        with pytest.raises(HardeningError):
            firewall.parse_ranges(text, 4)

    def test_a_short_list_is_refused_instead_of_locking_everyone_out(self):
        with pytest.raises(HardeningError):
            firewall.parse_ranges(listing(V4[:2]), 4)

    def test_the_other_address_version_is_refused(self):
        with pytest.raises(HardeningError):
            firewall.parse_ranges(listing(V6), 4)

    def test_both_lists_are_fetched_over_https(self):
        pages = {
            "https://www.cloudflare.com/ips-v4": listing(V4),
            "https://www.cloudflare.com/ips-v6": listing(V6),
        }
        assert firewall.fetch_ranges(opener(pages)) == {4: sorted(V4), 6: sorted(V6)}
        assert all(address.startswith("https://") for address in firewall.LIST_ADDRESSES.values())

    def test_a_network_failure_is_reported_in_plain_words(self):
        def broken(address, timeout):
            raise OSError("secret detail")

        with pytest.raises(HardeningError, match="could not be fetched") as caught:
            firewall.fetch_ranges(broken)
        assert "secret detail" not in str(caught.value)


class TestKeepingTheLastGoodList:
    def test_a_fresh_list_is_used_and_kept(self, tmp_path):
        ranges, fresh = firewall.choose_ranges(tmp_path, lambda: GOOD)
        assert fresh and ranges == GOOD

    def test_when_the_fetch_fails_the_last_good_list_is_used(self, tmp_path):
        firewall.save(tmp_path, "cloudflare-ranges.json", GOOD)

        def broken():
            raise HardeningError("Cloudflare's address list could not be fetched.")

        ranges, fresh = firewall.choose_ranges(tmp_path, broken)
        assert not fresh and ranges[4] == sorted(V4)

    def test_with_no_good_list_nothing_is_chosen(self, tmp_path):
        def broken():
            raise HardeningError("Cloudflare's address list could not be fetched.")

        with pytest.raises(HardeningError, match="nothing was changed"):
            firewall.choose_ranges(tmp_path, broken)

    def test_a_damaged_saved_list_counts_as_none(self, tmp_path):
        (tmp_path / "cloudflare-ranges.json").write_text(json.dumps({"v4": ["x"], "v6": []}))
        assert firewall.load_saved(tmp_path, "cloudflare-ranges.json") is None
        (tmp_path / "cloudflare-ranges.json").write_text("not json")
        assert firewall.load_saved(tmp_path, "cloudflare-ranges.json") is None


class TestTheRules:
    def ruleset(self):
        return firewall.render_ruleset({4: sorted(V4), 6: sorted(V6)})

    def test_only_the_web_ports_are_limited_and_ssh_is_never_mentioned(self):
        text = self.ruleset()
        assert "tcp dport { 80, 443 }" in text
        for port in ("22", "2222", "3000", "5432"):
            assert f"dport {{ {port}" not in text and f" {port}," not in text
        assert text.count("drop") == 1 and "reject" not in text

    def test_the_drop_comes_after_the_cloudflare_accepts(self):
        lines = [line.strip() for line in self.ruleset().splitlines()]
        drop = next(i for i, line in enumerate(lines) if line.endswith("drop"))
        accepts = [i for i, line in enumerate(lines) if "@cloudflare" in line and "accept" in line]
        assert len(accepts) == 2 and max(accepts) < drop

    def test_the_whole_table_is_replaced_in_one_load(self):
        lines = self.ruleset().splitlines()
        assert lines[0] == f"table inet {firewall.TABLE} {{}}"  # exists, so the delete cannot fail
        assert lines[1] == f"delete table inet {firewall.TABLE}"

    def test_every_range_is_in_a_set(self):
        text = self.ruleset()
        assert all(item in text for item in V4 + V6)

    def test_the_firewall_program_accepts_the_syntax(self):
        if not shutil.which("nft"):
            pytest.skip("nft is not installed")
        result = subprocess.run(
            ["nft", "--check", "--file", "-"], input=self.ruleset(), text=True, capture_output=True
        )
        if "not permitted" in result.stderr.lower():
            pytest.skip("not allowed to talk to the firewall here")
        assert result.returncode == 0, result.stderr

    def test_the_change_is_described(self):
        old = {4: sorted(V4), 6: sorted(V6)}
        new = {4: sorted([*V4[1:], "104.16.0.0/13"]), 6: sorted(V6)}
        text = firewall.describe_change(new, old)
        assert "+ 104.16.0.0/13" in text and f"- {V4[0]}" in text
        assert firewall.describe_change(old, old) == "The list is unchanged."
        assert "First time" in firewall.describe_change(old, None)


class TestApplying:
    def test_a_dry_run_changes_and_saves_nothing(self, tmp_path, commands, monkeypatch, capsys):
        use_list(monkeypatch)
        assert firewall.apply(arguments(tmp_path, dry_run=True)) == 0
        assert not [c for c in commands if "--file" in c and "--check" not in c]
        assert list(tmp_path.iterdir()) == []
        assert "tcp dport { 80, 443 }" in capsys.readouterr().out

    def test_the_change_is_printed_before_it_is_loaded(
        self, tmp_path, commands, monkeypatch, capsys
    ):
        use_list(monkeypatch)
        assert firewall.apply(arguments(tmp_path)) == 0
        assert any(c[:2] == ["nft", "--file"] for c in commands)
        assert "will accept only these Cloudflare ranges" in capsys.readouterr().out

    def test_a_successful_apply_saves_the_list_for_later(self, tmp_path, commands, monkeypatch):
        use_list(monkeypatch)
        firewall.apply(arguments(tmp_path))
        assert firewall.load_saved(tmp_path, "cloudflare-ranges.json")[4] == sorted(V4)

    def test_a_failed_fetch_applies_the_last_good_list_and_says_so_by_status(
        self, tmp_path, commands, monkeypatch
    ):
        use_list(monkeypatch)
        firewall.apply(arguments(tmp_path))
        commands.clear()
        use_list(monkeypatch, fail=True)
        assert firewall.apply(arguments(tmp_path)) == firewall.EXIT_LAST_GOOD
        assert any(c[:2] == ["nft", "--file"] for c in commands)  # reloaded after a restart

    def test_with_no_good_list_nothing_is_loaded_and_the_ports_are_not_opened(
        self, tmp_path, commands, monkeypatch
    ):
        use_list(monkeypatch, fail=True)
        with pytest.raises(HardeningError):
            firewall.apply(arguments(tmp_path))
        assert not [c for c in commands if c[:2] == ["nft", "--file"]]
        assert not [c for c in commands if "delete" in c]

    def test_the_firewall_refusing_the_table_stops_before_loading(self, tmp_path, monkeypatch):
        use_list(monkeypatch)
        loaded = []

        def refusing(command, *, dry_run=False, input_text=None, check=True):
            loaded.append(command)
            return types.SimpleNamespace(returncode=1 if "--check" in command else 0, stdout="")

        monkeypatch.setattr(firewall, "run", refusing)
        monkeypatch.setattr(firewall, "require_root", lambda: None)
        with pytest.raises(HardeningError, match="refused"):
            firewall.apply(arguments(tmp_path))
        assert not [c for c in loaded if c[:2] == ["nft", "--file"]]


class TestUndo:
    def test_undo_removes_only_our_table(self, commands):
        firewall.remove(types.SimpleNamespace(dry_run=False))
        assert commands == [["nft", "delete", "table", "inet", firewall.TABLE]]

    def test_an_undo_dry_run_only_prints(self, commands):
        firewall.remove(types.SimpleNamespace(dry_run=True))
        assert commands == [["nft", "delete", "table", "inet", firewall.TABLE]]
        assert commands.dry_runs == [True]  # the real runner prints it and does not run it
