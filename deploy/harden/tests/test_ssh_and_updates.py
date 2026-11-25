import types
from pathlib import Path

import automatic_updates as updates
import pytest
import ssh_hardening as ssh
from harden_common import HardeningError

KEY = (
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFakeFakeFakeFakeFakeFakeFakeFakeFake0000 fake@example.com"
)


def make_home(tmp_path, *, key=KEY, file_mode=0o600, home_mode=0o755):
    home = tmp_path / "home"
    (home / ".ssh").mkdir(parents=True)
    (home / ".ssh" / "authorized_keys").write_text(key + "\n")
    (home / ".ssh" / "authorized_keys").chmod(file_mode)
    (home / ".ssh").chmod(0o700)
    home.chmod(home_mode)
    return home


def lookup_for(home):
    def lookup(name):
        if name != "owner":
            raise KeyError(name)
        return types.SimpleNamespace(pw_dir=str(home))

    return lookup


class TestWhoMayBeLockedIn:
    def test_a_user_with_a_key_passes(self, tmp_path):
        ssh.check_user_can_sign_in_with_a_key("owner", lookup_for(make_home(tmp_path)))

    def test_root_is_refused(self, tmp_path):
        with pytest.raises(HardeningError, match="not root"):
            ssh.check_user_can_sign_in_with_a_key("root", lookup_for(make_home(tmp_path)))

    def test_an_unknown_user_is_refused(self, tmp_path):
        with pytest.raises(HardeningError, match="no user"):
            ssh.check_user_can_sign_in_with_a_key("ghost", lookup_for(make_home(tmp_path)))

    @pytest.mark.parametrize(
        "content", ["", "# only a comment", "ssh-ed25519 short", "password123"]
    )
    def test_a_file_without_a_real_key_is_refused(self, tmp_path, content):
        with pytest.raises(HardeningError, match="no SSH key"):
            ssh.check_user_can_sign_in_with_a_key(
                "owner", lookup_for(make_home(tmp_path, key=content))
            )

    def test_a_missing_key_file_is_refused(self, tmp_path):
        home = make_home(tmp_path)
        (home / ".ssh" / "authorized_keys").unlink()
        with pytest.raises(HardeningError, match="no readable"):
            ssh.check_user_can_sign_in_with_a_key("owner", lookup_for(home))

    @pytest.mark.parametrize("which", ["file", "home"])
    def test_rights_the_ssh_server_would_ignore_are_refused(self, tmp_path, which):
        home = make_home(
            tmp_path,
            file_mode=0o666 if which == "file" else 0o600,
            home_mode=0o777 if which == "home" else 0o755,
        )
        with pytest.raises(HardeningError, match="ignore the key"):
            ssh.check_user_can_sign_in_with_a_key("owner", lookup_for(home))


@pytest.fixture
def server(monkeypatch, tmp_path):
    """No real SSH server: records the commands and lets a test make `sshd -t` fail."""
    state = types.SimpleNamespace(commands=[], sshd_ok=True)

    def fake_run(command, *, dry_run=False, input_text=None, check=True):
        state.commands.append(command)
        ok = state.sshd_ok if command[:2] == ["sshd", "-t"] else True
        return types.SimpleNamespace(returncode=0 if ok else 1, stdout="", stderr="")

    monkeypatch.setattr(ssh, "run", fake_run)
    monkeypatch.setattr(ssh, "require_root", lambda: None)
    monkeypatch.setattr(ssh, "check_user_can_sign_in_with_a_key", lambda name, lookup=None: None)
    state.drop_in = tmp_path / "sshd_config.d" / "10-bera-hardening.conf"
    return state


def ssh_args(server, **changes):
    values = {
        "user": "owner",
        "dry_run": False,
        "i_have_a_second_session": True,
        "drop_in": server.drop_in,
    }
    return types.SimpleNamespace(**{**values, **changes})


class TestApplyingSsh:
    def test_the_settings_turn_off_passwords_and_root(self):
        text = ssh.render()
        assert "PasswordAuthentication no" in text and "PermitRootLogin no" in text
        assert "KbdInteractiveAuthentication no" in text and "PubkeyAuthentication yes" in text

    def test_it_does_not_limit_who_may_reach_the_port(self):
        text = ssh.render().lower()
        assert "allowusers" not in text and "listenaddress" not in text and "match" not in text

    def test_a_dry_run_writes_and_reloads_nothing(self, server, capsys):
        assert ssh.apply(ssh_args(server, dry_run=True)) == 0
        assert not server.drop_in.exists() and server.commands == []
        assert "PasswordAuthentication no" in capsys.readouterr().out

    def test_without_the_second_session_flag_nothing_changes(self, server):
        with pytest.raises(HardeningError, match="second SSH session"):
            ssh.apply(ssh_args(server, i_have_a_second_session=False))
        assert not server.drop_in.exists()

    def test_apply_checks_the_settings_then_reloads_and_never_restarts(self, server):
        ssh.apply(ssh_args(server))
        assert server.drop_in.exists()
        assert server.commands[0] == ["sshd", "-t"]
        assert ["systemctl", "reload", "ssh"] in server.commands
        assert not [c for c in server.commands if "restart" in c]

    def test_settings_the_server_does_not_accept_are_taken_back(self, server):
        server.sshd_ok = False
        with pytest.raises(HardeningError, match="taken back"):
            ssh.apply(ssh_args(server))
        assert not server.drop_in.exists()
        assert not [c for c in server.commands if c[:2] == ["systemctl", "reload"]]

    def test_earlier_settings_come_back_when_the_new_ones_are_refused(self, server):
        server.drop_in.parent.mkdir(parents=True)
        server.drop_in.write_text("# earlier\n")
        server.sshd_ok = False
        with pytest.raises(HardeningError):
            ssh.apply(ssh_args(server))
        assert server.drop_in.read_text() == "# earlier\n"

    def test_undo_removes_our_file_and_reloads(self, server):
        ssh.apply(ssh_args(server))
        server.commands.clear()
        ssh.undo(ssh_args(server))
        assert not server.drop_in.exists()
        assert ["systemctl", "reload", "ssh"] in server.commands

    def test_an_undo_dry_run_keeps_the_file(self, server):
        ssh.apply(ssh_args(server))
        ssh.undo(ssh_args(server, dry_run=True))
        assert server.drop_in.exists()


class TestAutomaticUpdates:
    def args(self, tmp_path, **changes):
        values = {
            "dry_run": False,
            "reboot_time": "05:30",
            "no_auto_reboot": False,
            "apt_dir": tmp_path,
        }
        return types.SimpleNamespace(**{**values, **changes})

    @pytest.fixture(autouse=True)
    def installed(self, monkeypatch):
        monkeypatch.setattr(updates, "require_root", lambda: None)
        monkeypatch.setattr(updates, "check_installed", lambda: None)

    def test_only_security_updates_are_installed(self):
        text = updates.render_rules("05:30")
        assert "-security" in text and "-updates" not in text

    def test_it_restarts_at_the_chosen_hour_when_needed(self, tmp_path):
        updates.apply(self.args(tmp_path, reboot_time="03:15"))
        rules = (tmp_path / updates.RULES_FILE).read_text()
        assert 'Automatic-Reboot "true"' in rules and 'Reboot-Time "03:15"' in rules
        assert 'Unattended-Upgrade "1"' in (tmp_path / updates.SWITCH_FILE).read_text()

    def test_the_restart_can_be_switched_off(self, tmp_path):
        updates.apply(self.args(tmp_path, no_auto_reboot=True))
        rules = (tmp_path / updates.RULES_FILE).read_text()
        assert 'Automatic-Reboot "false"' in rules and "Reboot-Time" not in rules

    @pytest.mark.parametrize("bad", ["5:30", "25:00", "05:60", "noon", ""])
    def test_a_wrong_time_is_refused(self, tmp_path, bad):
        with pytest.raises(HardeningError):
            updates.apply(self.args(tmp_path, reboot_time=bad))
        assert list(tmp_path.iterdir()) == []

    def test_a_dry_run_writes_nothing(self, tmp_path, capsys):
        updates.apply(self.args(tmp_path, dry_run=True))
        assert list(tmp_path.iterdir()) == []
        assert "Allowed-Origins" in capsys.readouterr().out

    def test_undo_removes_our_rules(self, tmp_path):
        updates.apply(self.args(tmp_path))
        updates.undo(self.args(tmp_path))
        assert not (tmp_path / updates.RULES_FILE).exists()

    def test_check_reports_a_waiting_restart_and_a_switched_off_setting(
        self, tmp_path, monkeypatch
    ):
        updates.apply(self.args(tmp_path))
        flag = tmp_path / "reboot-required"
        monkeypatch.setattr(updates, "REBOOT_NEEDED_FLAG", flag)
        assert updates.check(self.args(tmp_path)) == 0
        flag.write_text("")
        assert updates.check(self.args(tmp_path)) == 1
        flag.unlink()
        (tmp_path / updates.SWITCH_FILE).write_text('APT::Periodic::Unattended-Upgrade "0";')
        assert updates.check(self.args(tmp_path)) == 1

    def test_the_package_must_be_installed_first(self, monkeypatch):
        monkeypatch.undo()
        monkeypatch.setattr(
            updates, "run", lambda *a, **k: types.SimpleNamespace(returncode=1, stdout="")
        )
        with pytest.raises(HardeningError, match="apt install"):
            updates.check_installed()


def test_the_scripts_are_next_to_their_units():
    folder = Path(__file__).resolve().parents[1]
    service = (folder / "systemd" / "bera-cloudflare-firewall.service").read_text()
    assert "cloudflare_firewall.py apply" in service and "Before=nginx.service" in service
    assert (folder / "cloudflare_firewall.py").exists()
    timer = (folder / "systemd" / "bera-cloudflare-firewall.timer").read_text()
    assert "Persistent=true" in timer and "OnCalendar" in timer
