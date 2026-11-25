"""Installs security updates by themselves (unattended-upgrades), and shows if one is waiting.

Only the operating system's security updates are installed automatically. The server restarts
by itself, at a quiet hour, only when an update needs it (a new kernel): the services start again
on their own, so expect a short break then. Use --no-auto-reboot to restart by hand instead; the
`check` command tells when a restart is waiting.

    python automatic_updates.py apply [--reboot-time HH:MM | --no-auto-reboot] [--dry-run]
    python automatic_updates.py undo [--dry-run]
    python automatic_updates.py check
"""

import argparse
import re
from pathlib import Path

from harden_common import HardeningError, main_wrapper, remove_file, require_root, run, write_file

APT_DIR = Path("/etc/apt/apt.conf.d")
SWITCH_FILE = "20auto-upgrades"
RULES_FILE = "52bera-unattended-upgrades"
# Backups run 02:30 and the weekly restore test 04:30 (UTC); a restart after both.
DEFAULT_REBOOT_TIME = "05:30"
REBOOT_NEEDED_FLAG = Path("/var/run/reboot-required")
UPGRADE_LOG = Path("/var/log/unattended-upgrades/unattended-upgrades.log")


def render_switch():
    return 'APT::Periodic::Update-Package-Lists "1";\nAPT::Periodic::Unattended-Upgrade "1";\n'


def render_rules(reboot_time):
    reboot = (
        'Unattended-Upgrade::Automatic-Reboot "false";\n'
        if reboot_time is None
        else 'Unattended-Upgrade::Automatic-Reboot "true";\n'
        f'Unattended-Upgrade::Automatic-Reboot-Time "{reboot_time}";\n'
    )
    return f"""// Made by automatic_updates.py (BERA-179). Remove with: automatic_updates.py undo
// Security updates only (the first line is for Ubuntu, the second for Debian).
Unattended-Upgrade::Allowed-Origins {{
    "${{distro_id}}:${{distro_codename}}-security";
    "origin=Debian,codename=${{distro_codename}}-security,label=Debian-Security";
}};
Unattended-Upgrade::Remove-Unused-Dependencies "true";
{reboot}"""


def check_installed():
    if run(["dpkg", "-s", "unattended-upgrades"], check=False).returncode != 0:
        raise HardeningError("Install the package first: apt install unattended-upgrades")


def apply(arguments):
    if arguments.no_auto_reboot:
        reboot_time = None
    else:
        reboot_time = arguments.reboot_time
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", reboot_time):
            raise HardeningError("The restart time must look like 05:30 (24 hours).")
    if not arguments.dry_run:
        require_root()
        check_installed()
    write_file(arguments.apt_dir / SWITCH_FILE, render_switch(), dry_run=arguments.dry_run)
    write_file(arguments.apt_dir / RULES_FILE, render_rules(reboot_time), dry_run=arguments.dry_run)
    return 0


def undo(arguments):
    if not arguments.dry_run:
        require_root()
    remove_file(arguments.apt_dir / RULES_FILE, dry_run=arguments.dry_run)
    print(
        "Left in place: 20auto-upgrades (the daily package list refresh). "
        "Set it to 0 to stop updates."
    )
    return 0


def check(arguments):
    """1 when a restart is waiting or the switch is off."""
    switch = arguments.apt_dir / SWITCH_FILE
    on = switch.exists() and 'Unattended-Upgrade "1"' in switch.read_text()
    waiting = REBOOT_NEEDED_FLAG.exists()
    print(f"Automatic security updates: {'on' if on else 'OFF'}")
    print(f"Restart waiting: {'YES, restart the server soon' if waiting else 'no'}")
    print(f"Log: {UPGRADE_LOG}")
    return 0 if on and not waiting else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("apply", "undo", "check"))
    parser.add_argument("--dry-run", action="store_true", help="show the change, change nothing")
    parser.add_argument("--reboot-time", default=DEFAULT_REBOOT_TIME)
    parser.add_argument("--no-auto-reboot", action="store_true")
    parser.add_argument("--apt-dir", type=Path, default=APT_DIR)
    arguments = parser.parse_args(argv)
    commands = {"apply": apply, "undo": undo, "check": check}
    return main_wrapper(lambda: commands[arguments.command](arguments)) or 0


if __name__ == "__main__":
    raise SystemExit(main())
