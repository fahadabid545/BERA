"""Makes SSH key-only: no passwords, no root login. It never locks you out.

It refuses to change anything unless the named user can already sign in with a key (a real
key in their authorized_keys, with file rights the SSH server will accept), checks the new
settings with `sshd -t` before they are used, and only reloads the SSH server (open sessions
stay open). Keep a second SSH session open while you apply it, and test a new one before you
close the old one.

    python ssh_hardening.py apply --user NAME [--dry-run] --i-have-a-second-session
    python ssh_hardening.py undo [--dry-run]       remove our settings again
    python ssh_hardening.py check                  show the settings the server really uses

This script does not limit WHO may reach the SSH port. Do that in Hetzner's cloud firewall
(only the owner's address); see the README.
"""

import argparse
import pwd
import re
import stat
from pathlib import Path

from harden_common import HardeningError, main_wrapper, remove_file, require_root, run, write_file

DEFAULT_DROP_IN = Path("/etc/ssh/sshd_config.d/10-bera-hardening.conf")
# Read before the cloud image's own 50-cloud-init.conf: for most settings the first value wins.
SETTINGS = (
    ("PermitRootLogin", "no"),
    ("PasswordAuthentication", "no"),
    ("KbdInteractiveAuthentication", "no"),
    ("PubkeyAuthentication", "yes"),
    ("PermitEmptyPasswords", "no"),
    ("X11Forwarding", "no"),
    ("MaxAuthTries", "3"),
    ("LoginGraceTime", "30"),
)
KEY_LINE = re.compile(
    r"^(?:[^ ]+ )?(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp\d+|sk-ssh-ed25519@openssh\.com|"
    r"sk-ecdsa-sha2-nistp256@openssh\.com) [A-Za-z0-9+/=]{40,}"
)


def render():
    lines = [f"{name} {value}" for name, value in SETTINGS]
    return (
        "# Made by ssh_hardening.py (BERA-179). Remove with: ssh_hardening.py undo\n"
        + "\n".join(lines)
        + "\n"
    )


def _too_open(path):
    return bool(path.stat().st_mode & (stat.S_IWGRP | stat.S_IWOTH))


def check_user_can_sign_in_with_a_key(name, lookup=pwd.getpwnam):
    """Raises unless `name` is a normal user with a usable key. The SSH server ignores a key file
    that others can write, so that counts as no key."""
    if name == "root":
        raise HardeningError(
            "Name a normal user with a key, not root: root login is being turned off."
        )
    try:
        account = lookup(name)
    except KeyError:
        raise HardeningError(f"There is no user named {name}.") from None
    home = Path(account.pw_dir)
    keys = home / ".ssh" / "authorized_keys"
    try:
        has_key = any(KEY_LINE.match(line.strip()) for line in keys.read_text().splitlines())
        unsafe = _too_open(home) or _too_open(keys) or _too_open(keys.parent)
    except OSError:
        raise HardeningError(
            f"{name} has no readable authorized_keys file, so nothing was changed."
        ) from None
    if not has_key:
        raise HardeningError(f"{name} has no SSH key in authorized_keys, so nothing was changed.")
    if unsafe:
        raise HardeningError(
            f"The folders or file holding {name}'s keys can be changed by others; the SSH server "
            "would ignore the key. Fix the rights (chmod go-w) first. Nothing was changed."
        )


def reload_ssh_server():
    for service in ("ssh", "sshd"):
        if run(["systemctl", "reload", service], check=False).returncode == 0:
            return
    raise HardeningError("The SSH server could not be reloaded. Run the undo steps in the README.")


def apply(arguments):
    check_user_can_sign_in_with_a_key(arguments.user)
    text = render()
    if arguments.dry_run:
        write_file(arguments.drop_in, text, dry_run=True)
        print("Dry run: nothing was changed.")
        return 0
    if not arguments.i_have_a_second_session:
        raise HardeningError(
            "Open a second SSH session first, then repeat with --i-have-a-second-session."
        )
    require_root()
    previous = arguments.drop_in.read_text() if arguments.drop_in.exists() else None
    write_file(arguments.drop_in, text)
    if run(["sshd", "-t"], check=False).returncode != 0:
        _restore(arguments.drop_in, previous)
        raise HardeningError(
            "The SSH server did not accept the new settings; they were taken back."
        )
    reload_ssh_server()
    print("Done. Open a NEW SSH session now and check you can sign in before closing this one.")
    return 0


def _restore(path, previous):
    if previous is None:
        remove_file(path)
    else:
        write_file(path, previous, quiet=True)


def undo(arguments):
    if not arguments.dry_run:
        require_root()
    remove_file(arguments.drop_in, dry_run=arguments.dry_run)
    if not arguments.dry_run:
        run(["sshd", "-t"])
        reload_ssh_server()
    return 0


def check(arguments):
    result = run(["sshd", "-T"], check=False)
    wanted = {name.lower(): value for name, value in SETTINGS}
    actual = dict(line.split(" ", 1) for line in result.stdout.splitlines() if " " in line)
    wrong = [name for name, value in wanted.items() if actual.get(name) != value]
    for name, value in wanted.items():
        print(f"{name} = {actual.get(name, 'unknown')} (wanted {value})")
    return 1 if wrong else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("apply", "undo", "check"))
    parser.add_argument("--user", help="apply: the user who signs in with a key")
    parser.add_argument("--dry-run", action="store_true", help="show the change, change nothing")
    parser.add_argument("--i-have-a-second-session", action="store_true")
    parser.add_argument("--drop-in", type=Path, default=DEFAULT_DROP_IN)
    arguments = parser.parse_args(argv)
    if arguments.command == "apply" and not arguments.user:
        parser.error("apply needs --user")
    commands = {"apply": apply, "undo": undo, "check": check}
    return main_wrapper(lambda: commands[arguments.command](arguments)) or 0


if __name__ == "__main__":
    raise SystemExit(main())
