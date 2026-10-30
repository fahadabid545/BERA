import json
import subprocess
from datetime import date

import pytest

import check_vulnerabilities as check
from check_vulnerabilities import DEVELOPMENT, PRODUCTION, Finding, evaluate

TODAY = date(2026, 11, 1)
LATER = date(2027, 1, 31)


def accept(package, scope=PRODUCTION, ecosystem="npm", reason="Looked at it.", review_by=LATER):
    return {
        "ecosystem": ecosystem,
        "package": package,
        "scope": scope,
        "reason": reason,
        "review_by": review_by,
    }


def finding(package, severity="high", scope=PRODUCTION, ecosystem="npm"):
    return Finding(ecosystem, package, severity, scope)


def test_a_serious_production_finding_fails():
    failures, _, _ = evaluate({finding("left-pad", "critical")}, [], TODAY)
    assert failures == [
        "left-pad (npm, critical, production) has a known weakness. Fix it or accept it in writing."
    ]


@pytest.mark.parametrize("severity", ["low", "moderate"])
def test_a_minor_production_finding_only_warns(severity):
    failures, warnings, _ = evaluate({finding("left-pad", severity)}, [], TODAY)
    assert failures == [] and len(warnings) == 1


@pytest.mark.parametrize("severity", ["moderate", "high", "critical"])
def test_development_tool_findings_only_warn(severity):
    failures, warnings, _ = evaluate({finding("vitest", severity, DEVELOPMENT)}, [], TODAY)
    assert failures == [] and len(warnings) == 1


def test_a_written_acceptance_lets_a_serious_finding_pass():
    failures, warnings, accepted = evaluate({finding("postcss")}, [accept("postcss")], TODAY)
    assert (failures, warnings) == ([], [])
    assert accepted == ["postcss (npm, high, production) accepted until 2027-01-31."]


def test_an_acceptance_for_development_does_not_cover_production():
    failures, _, _ = evaluate({finding("vite")}, [accept("vite", DEVELOPMENT)], TODAY)
    assert len(failures) == 1


def test_an_acceptance_past_its_review_date_fails_even_without_the_finding():
    failures, _, _ = evaluate(set(), [accept("postcss", review_by=date(2026, 10, 31))], TODAY)
    assert failures == ["npm:postcss was due for review on 2026-10-31. Look again."]


@pytest.mark.parametrize("reason", ["", "   "])
def test_an_acceptance_needs_a_written_reason(reason):
    failures, _, _ = evaluate({finding("postcss")}, [accept("postcss", reason=reason)], TODAY)
    assert "npm:postcss is accepted without a written reason." in failures
    assert len(failures) == 2  # and the finding itself still counts


def test_an_acceptance_needs_a_review_date():
    failures, _, _ = evaluate(set(), [accept("postcss", review_by=None)], TODAY)
    assert failures == ["npm:postcss is accepted without a review date."]


def test_an_acceptance_that_is_no_longer_needed_is_pointed_out():
    _, warnings, _ = evaluate(set(), [accept("postcss")], TODAY)
    assert warnings == ["The acceptance for postcss (npm) is no longer needed. Remove it."]


def test_findings_only_in_the_full_audit_belong_to_development_tools():
    production = {finding("next", "moderate")}
    everything = {
        finding("next", "moderate", DEVELOPMENT),
        finding("vitest", "critical", DEVELOPMENT),
    }
    result = check.split_scopes(production, everything)
    assert {(f.package, f.scope) for f in result} == {("next", PRODUCTION), ("vitest", DEVELOPMENT)}


def test_the_projects_acceptances_are_complete_and_dated_in_the_future():
    entries = check.load_acceptances()
    assert entries
    for entry in entries:
        assert entry["reason"].strip() and isinstance(entry["review_by"], date), entry["package"]
        assert entry["scope"] in {PRODUCTION, DEVELOPMENT}
    # Only the development tools named in the decision, plus the temporary Next.js one.
    assert {e["package"] for e in entries if e["scope"] == PRODUCTION} == {"postcss", "next"}


@pytest.mark.network
class TestAKnownBadLibraryMakesTheCheckFail:
    """These use the real advisory databases (they need network access)."""

    @pytest.fixture
    def clean_web(self, tmp_path):
        directory = tmp_path / "clean-web"
        directory.mkdir()
        (directory / "package.json").write_text(json.dumps({"name": "clean", "version": "1.0.0"}))
        subprocess.run(
            ["npm", "install", "--package-lock-only"],
            cwd=directory,
            check=True,
            capture_output=True,
        )
        return directory

    @pytest.fixture
    def empty_python(self, tmp_path):
        path = tmp_path / "requirements.txt"
        path.write_text("")
        return path

    def run_check(self, requirements, web, tmp_path, capsys):
        nothing_accepted = tmp_path / "accepted.toml"
        nothing_accepted.write_text("")
        code = check.main(
            [
                "--server-requirements",
                str(requirements),
                "--server-dev-requirements",
                str(requirements),
                "--web-directory",
                str(web),
                "--accepted",
                str(nothing_accepted),
            ]
        )
        return code, capsys.readouterr().out

    def test_an_old_python_library(self, tmp_path, clean_web, capsys):
        bad = tmp_path / "bad-requirements.txt"
        bad.write_text("django==3.2.0\n")
        code, output = self.run_check(bad, clean_web, tmp_path, capsys)
        assert code == 1
        assert "FAILED: django (python, high, production)" in output

    def test_an_old_npm_library(self, tmp_path, empty_python, capsys):
        web = tmp_path / "bad-web"
        web.mkdir()
        (web / "package.json").write_text(
            json.dumps({"name": "bad", "version": "1.0.0", "dependencies": {"lodash": "4.17.15"}})
        )
        subprocess.run(
            ["npm", "install", "--package-lock-only"], cwd=web, check=True, capture_output=True
        )
        code, output = self.run_check(empty_python, web, tmp_path, capsys)
        assert code == 1
        assert "FAILED: lodash (npm" in output

    def test_a_clean_setup_passes(self, tmp_path, clean_web, empty_python, capsys):
        code, output = self.run_check(empty_python, clean_web, tmp_path, capsys)
        assert code == 0 and "0 failure(s)" in output

    def test_an_audit_that_cannot_run_fails_instead_of_passing(
        self, tmp_path, empty_python, capsys
    ):
        code, output = self.run_check(empty_python, tmp_path / "does-not-exist", tmp_path, capsys)
        assert code == 1 and "could not run" in output
