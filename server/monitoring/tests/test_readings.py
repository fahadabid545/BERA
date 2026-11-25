import pytest

from monitoring import readings


class TestTheReadings:
    def test_memory_uses_what_is_available_not_what_is_free(self, tmp_path):
        info = tmp_path / "meminfo"
        info.write_text("MemTotal: 1000 kB\nMemFree: 50 kB\nMemAvailable: 300 kB\nCached: 600 kB\n")
        assert readings.memory_used_percent(info) == 70.0  # "free" would say 95

    @pytest.mark.parametrize(
        "content", ["", "MemTotal: 1000 kB\n", "MemTotal: x kB\nMemAvailable: 1 kB"]
    )
    def test_an_unreadable_file_gives_no_reading(self, tmp_path, content):
        info = tmp_path / "meminfo"
        info.write_text(content)
        assert readings.memory_used_percent(info) is None
        assert readings.memory_used_percent(tmp_path / "missing") is None

    def test_the_disk_reading_is_the_fullest_place(self, monkeypatch):
        usage = {"/a": (100, 90), "/b": (100, 40)}  # total, free
        monkeypatch.setattr(
            readings.shutil,
            "disk_usage",
            lambda path: type("U", (), {"total": usage[path][0], "free": usage[path][1]})(),
        )
        assert readings.disk_used_percent(["/a", "/b"]) == 60.0

    def test_a_place_that_cannot_be_read_gives_no_reading(self):
        assert readings.disk_used_percent(["/definitely/not/here"]) is None
