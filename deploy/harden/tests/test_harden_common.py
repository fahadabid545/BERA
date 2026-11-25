import os
import subprocess

import harden_common as common
import pytest


def test_a_dry_run_prints_the_command_and_does_not_run_it(capsys):
    assert common.run(["definitely-not-a-program"], dry_run=True) is None
    assert "would run: definitely-not-a-program" in capsys.readouterr().out


def test_a_command_is_never_run_through_a_shell(tmp_path):
    marker = tmp_path / "created"
    result = common.run(["echo", f"hello; touch {marker}"])
    assert "hello;" in result.stdout and not marker.exists()


def test_write_file_shows_the_text_and_replaces_the_file_in_one_step(tmp_path, capsys):
    target = tmp_path / "one" / "file.conf"
    common.write_file(target, "setting yes\n", mode=0o640)
    assert target.read_text() == "setting yes\n"
    assert oct(os.stat(target).st_mode & 0o777) == "0o640"
    assert "setting yes" in capsys.readouterr().out
    assert [path.name for path in target.parent.iterdir()] == ["file.conf"]  # no leftovers


def test_write_file_dry_run_writes_nothing(tmp_path):
    common.write_file(tmp_path / "x", "text", dry_run=True)
    assert list(tmp_path.iterdir()) == []


def test_a_stopped_script_prints_one_line_and_returns_one(capsys):
    def stop():
        raise common.HardeningError("something is wrong")

    assert common.main_wrapper(stop) == 1
    assert "STOPPED: something is wrong" in capsys.readouterr().err


def test_a_real_run_without_root_is_refused(monkeypatch):
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    with pytest.raises(common.HardeningError, match="root"):
        common.require_root()


def test_run_failure_raises_for_a_failing_command():
    with pytest.raises(subprocess.CalledProcessError):
        common.run(["false"])
