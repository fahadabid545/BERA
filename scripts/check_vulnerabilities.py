"""Checks the server and web libraries for known weaknesses.

    python scripts/check_vulnerabilities.py

Production libraries: a high or critical finding fails the check, unless it is accepted in
`security/accepted-vulnerabilities.toml` with a written reason and a review date.
Development tools: findings are shown as warnings only.
An acceptance past its review date fails the check, so accepted risks get looked at again.
Needs network access to the advisory databases; an audit that cannot run also fails.
"""

import argparse
import json
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ACCEPTED_FILE = ROOT / "security" / "accepted-vulnerabilities.toml"
SERIOUS = {"high", "critical"}
PRODUCTION, DEVELOPMENT = "production", "development"


class AuditError(Exception):
    """An audit could not be completed; never treated as "no findings"."""


@dataclass(frozen=True)
class Finding:
    ecosystem: str
    package: str
    severity: str  # python advisories carry none, so they count as "high"
    scope: str
    advisories: tuple = ()


def run_json(command, cwd):
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise AuditError(
            f"{' '.join(command[:3])} gave no readable result: {result.stderr[-300:]}"
        ) from error


def python_findings(requirements_file, scope):
    report = run_json(
        [
            sys.executable,
            "-m",
            "pip_audit",
            "-r",
            str(requirements_file),
            "--format",
            "json",
            "--progress-spinner",
            "off",
        ],
        ROOT,
    )
    return {
        Finding("python", item["name"], "high", scope, tuple(vuln["id"] for vuln in item["vulns"]))
        for item in report.get("dependencies", [])
        if item.get("vulns")
    }


def npm_findings(web_directory, scope):
    command = ["npm", "audit", "--json"] + (["--omit=dev"] if scope == PRODUCTION else [])
    report = run_json(command, web_directory)
    if "vulnerabilities" not in report:
        raise AuditError(f"npm audit failed: {str(report.get('error', report))[:300]}")
    return {
        Finding("npm", name, item["severity"], scope)
        for name, item in report["vulnerabilities"].items()
    }


def split_scopes(production, everything):
    """Findings only present in the full audit belong to development tools."""
    production_packages = {(f.ecosystem, f.package) for f in production}
    development = {
        Finding(f.ecosystem, f.package, f.severity, DEVELOPMENT, f.advisories)
        for f in everything
        if (f.ecosystem, f.package) not in production_packages
    }
    return set(production) | development


def load_acceptances(path=ACCEPTED_FILE):
    return tomllib.loads(path.read_text(encoding="utf-8")).get("accepted", [])


def evaluate(findings, acceptances, today):
    """(failures, warnings, accepted) as lists of plain sentences."""
    failures, warnings, accepted = [], [], []
    usable = {}
    for entry in acceptances:
        name = f"{entry.get('ecosystem')}:{entry.get('package')}"
        if not str(entry.get("reason", "")).strip():
            failures.append(f"{name} is accepted without a written reason.")
        elif not isinstance(entry.get("review_by"), date):
            failures.append(f"{name} is accepted without a review date.")
        elif entry["review_by"] < today:
            failures.append(f"{name} was due for review on {entry['review_by']}. Look again.")
        else:
            usable[(entry["ecosystem"], entry["package"], entry.get("scope"))] = entry

    seen = set()
    for finding in sorted(findings, key=lambda f: (f.scope, f.ecosystem, f.package)):
        key = (finding.ecosystem, finding.package, finding.scope)
        label = f"{finding.package} ({finding.ecosystem}, {finding.severity}, {finding.scope})"
        if key in usable:
            seen.add(key)
            accepted.append(f"{label} accepted until {usable[key]['review_by']}.")
        elif finding.scope == PRODUCTION and finding.severity in SERIOUS:
            failures.append(f"{label} has a known weakness. Fix it or accept it in writing.")
        else:
            warnings.append(f"{label} has a known weakness.")
    for key in sorted(set(usable) - seen):
        warnings.append(f"The acceptance for {key[1]} ({key[0]}) is no longer needed. Remove it.")
    return failures, warnings, accepted


def collect(server_requirements, server_dev_requirements, web_directory):
    python = split_scopes(
        python_findings(server_requirements, PRODUCTION),
        python_findings(server_dev_requirements, DEVELOPMENT),
    )
    npm = split_scopes(
        npm_findings(web_directory, PRODUCTION), npm_findings(web_directory, DEVELOPMENT)
    )
    return python | npm


def main(arguments=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--server-requirements", default=ROOT / "server" / "requirements.txt")
    parser.add_argument(
        "--server-dev-requirements", default=ROOT / "server" / "requirements-dev.txt"
    )
    parser.add_argument("--web-directory", default=ROOT / "web")
    parser.add_argument("--accepted", default=ACCEPTED_FILE, type=Path)
    options = parser.parse_args(arguments)
    try:
        findings = collect(
            options.server_requirements, options.server_dev_requirements, options.web_directory
        )
    except (AuditError, OSError) as error:
        print(f"FAILED: the check could not run: {error}")
        return 1
    failures, warnings, accepted = evaluate(
        findings, load_acceptances(options.accepted), date.today()
    )
    for line in accepted:
        print(f"accepted: {line}")
    for line in warnings:
        print(f"warning: {line}")
    for line in failures:
        print(f"FAILED: {line}")
    print(f"{len(failures)} failure(s), {len(warnings)} warning(s), {len(accepted)} accepted.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
