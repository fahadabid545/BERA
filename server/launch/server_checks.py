"""Items 9 and 15: the server's own protection, and the library and secret checks. The
protection is read from the running server (firewall, web server, SSH); a program that cannot be
run counts as a failure, never as a pass."""

import sys

from .context import Context
from .results import item, not_ok, ok

SSH_WANTED = {"passwordauthentication": "no", "permitrootlogin": "no"}


def _ran(result):
    code, _ = result
    return code == 0


def _firewall(context):
    return _ran(context.run(["nft", "list", "table", "inet", "bera_web"], folder=None))


def _origin_pulls(context):
    code, text = context.run(["nginx", "-T"], folder=None)
    return code == 0 and "ssl_verify_client on" in text


def _ssh_settings(context):
    code, text = context.run(["sshd", "-T"], folder=None)
    if code != 0:
        return None
    return dict(line.split(" ", 1) for line in text.splitlines() if " " in line)


def _secrets(context):
    return context.remembered_run(
        "secrets", [sys.executable, str(context.project_folder / "scripts" / "scan_secrets.py")]
    )


def _libraries(context):
    return context.remembered_run(
        "libraries",
        [sys.executable, str(context.project_folder / "scripts" / "check_vulnerabilities.py")],
    )


def _separation(context):
    return context.run(
        [
            sys.executable,
            str(context.project_folder / "scripts" / "check_environments.py"),
            str(context.staging_env_file),
            str(context.production_env_file),
        ],
        folder=context.project_folder,
    )


def server_protection(context: Context):
    parts = []
    checks = (
        ("Only Cloudflare may reach the web ports (the firewall table is loaded).", _firewall),
        ("Authenticated origin pulls are on in the web server.", _origin_pulls),
    )
    for words, check in checks:
        parts.append(ok(words) if check(context) else not_ok(f"Not confirmed: {words}"))
    settings_in_use = _ssh_settings(context)
    if settings_in_use is None:
        parts.append(not_ok("Could not read the SSH settings in use (run this as root)."))
    else:
        wrong = [name for name, want in SSH_WANTED.items() if settings_in_use.get(name) != want]
        parts.append(ok("SSH is key-only.") if not wrong else not_ok("SSH is not key-only."))
    parts.append(
        ok("Staging and production share nothing.")
        if _ran(_separation(context))
        else not_ok("Staging and production are not separate, or the check could not run.")
    )
    parts.append(
        ok("The secret scan is clean.")
        if _ran(_secrets(context))
        else not_ok("The secret scan found something, or could not run.")
    )
    parts.append(
        ok("The library check is clean.")
        if _ran(_libraries(context))
        else not_ok("The library check found a problem, or could not run.")
    )
    return item(9, "Server protection, separation, secrets and libraries", parts)


def security_review(context: Context):
    document = context.project_folder / "docs" / "security" / "pre-launch-review.md"
    parts = [
        ok("The written pre-launch review exists.")
        if document.is_file()
        else not_ok("docs/security/pre-launch-review.md is missing."),
        ok("No open high or critical library finding.")
        if _ran(_libraries(context))
        else not_ok("There is an open high finding, or the library check could not run."),
    ]
    return item(15, "Pre-launch security review has no open high findings", parts)
