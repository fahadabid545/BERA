"""Lets only Cloudflare reach the web ports (80 and 443) of this server.

It fetches Cloudflare's published address ranges, loads them into a firewall table of its own
(`inet bera_web`, nftables) and refreshes them on a timer. Nothing else is touched: SSH and every
other port are never restricted by this script, and other firewall rules are left alone.

If the fetch fails or looks wrong, the last good list is used. If there is no good list at all,
nothing is applied: the ports are never opened to everyone by this script, and a list that is
empty or invalid is never loaded.

    python cloudflare_firewall.py apply [--dry-run]    fetch, show the change, load it
    python cloudflare_firewall.py remove [--dry-run]   take the rules away again (the undo)
    python cloudflare_firewall.py status               what is loaded now

Exit status: 0 fresh list applied; 3 applied from the last good list because the fetch failed
(the timer shows as failed, so someone looks); 1 nothing applied.
"""

import argparse
import ipaddress
import json
import tempfile
import time
import urllib.request
from pathlib import Path

from harden_common import HardeningError, main_wrapper, require_root, run, show_change, write_file

LIST_ADDRESSES = {4: "https://www.cloudflare.com/ips-v4", 6: "https://www.cloudflare.com/ips-v6"}
# A short list means a broken page, not Cloudflare: refuse it rather than lock everyone out.
MINIMUM_RANGES = {4: 5, 6: 3}
FETCH_TIMEOUT_SECONDS = 20
WEB_PORTS = (80, 443)
TABLE = "bera_web"
DEFAULT_STATE_DIR = Path("/var/lib/bera-harden")
EXIT_FRESH, EXIT_NOTHING_APPLIED, EXIT_LAST_GOOD = 0, 1, 3


def parse_ranges(text, version):
    """The address ranges in `text`, one per line, checked. Raises on anything unexpected."""
    found = []
    for line in text.split():
        try:
            network = ipaddress.ip_network(line, strict=True)
        except ValueError:
            raise HardeningError(
                "The list from Cloudflare has an entry that is not an address range."
            ) from None
        if network.version != version:
            raise HardeningError("The list from Cloudflare mixes address versions.")
        found.append(str(network))
    if len(found) < MINIMUM_RANGES[version]:
        raise HardeningError("The list from Cloudflare is too short to be right.")
    return sorted(set(found))


def fetch_ranges(open_address=urllib.request.urlopen):
    """{4: [...], 6: [...]} straight from Cloudflare (https only)."""
    ranges = {}
    for version, address in LIST_ADDRESSES.items():
        try:
            with open_address(address, timeout=FETCH_TIMEOUT_SECONDS) as response:
                ranges[version] = parse_ranges(response.read().decode("ascii"), version)
        except HardeningError:
            raise
        except Exception:  # network, DNS, TLS, decoding: all mean "could not get the list"
            raise HardeningError("Cloudflare's address list could not be fetched.") from None
    return ranges


def _state_file(state_dir, name):
    return Path(state_dir) / name


def load_saved(state_dir, name):
    """A saved list, checked again, or None when missing or damaged."""
    try:
        saved = json.loads(_state_file(state_dir, name).read_text())
        return {
            4: parse_ranges("\n".join(saved["v4"]), 4),
            6: parse_ranges("\n".join(saved["v6"]), 6),
        }
    except (OSError, ValueError, KeyError, TypeError, HardeningError):
        return None


def save(state_dir, name, ranges):
    text = json.dumps({"v4": ranges[4], "v6": ranges[6], "saved_at": int(time.time())})
    Path(state_dir).mkdir(parents=True, exist_ok=True)
    write_file(_state_file(state_dir, name), text, mode=0o644, quiet=True)


def choose_ranges(state_dir, fetcher):
    """(ranges, fresh). The newest list if the fetch worked, else the last good one."""
    try:
        return fetcher(), True
    except HardeningError as problem:
        print(f"WARNING: {problem}")
        kept = load_saved(state_dir, "cloudflare-ranges.json")
        if kept is None:
            raise HardeningError(
                "There is no good list of Cloudflare's addresses to use, so nothing was changed."
            ) from None
        print("Using the last good list.")
        return kept, False


def render_ruleset(ranges, ports=WEB_PORTS):
    """The whole table. Loaded in one step, so there is never a moment with half of it."""
    port_text = ", ".join(str(port) for port in ports)
    v4 = ", ".join(ranges[4])
    v6 = ", ".join(ranges[6])
    return f"""table inet {TABLE} {{}}
delete table inet {TABLE}
table inet {TABLE} {{
    set cloudflare_v4 {{
        type ipv4_addr
        flags interval
        elements = {{ {v4} }}
    }}
    set cloudflare_v6 {{
        type ipv6_addr
        flags interval
        elements = {{ {v6} }}
    }}
    chain web_ports {{
        type filter hook input priority -10; policy accept;
        iif "lo" accept
        tcp dport {{ {port_text} }} ip saddr @cloudflare_v4 accept
        tcp dport {{ {port_text} }} ip6 saddr @cloudflare_v6 accept
        tcp dport {{ {port_text} }} drop
    }}
}}
"""


def describe_change(new, old):
    if old is None:
        return f"First time: {len(new[4])} IPv4 and {len(new[6])} IPv6 ranges will be allowed."
    lines = []
    for version in (4, 6):
        added = sorted(set(new[version]) - set(old[version]))
        removed = sorted(set(old[version]) - set(new[version]))
        lines += [f"+ {item}" for item in added] + [f"- {item}" for item in removed]
    return "\n".join(lines) or "The list is unchanged."


def apply(arguments):
    ranges, fresh = choose_ranges(arguments.state_dir, fetch_ranges)
    show_change(
        f"ports {', '.join(map(str, WEB_PORTS))} will accept only these Cloudflare ranges; "
        "SSH and all other ports are not touched",
        describe_change(ranges, load_saved(arguments.state_dir, "applied-ranges.json")),
    )
    ruleset = render_ruleset(ranges)
    with tempfile.NamedTemporaryFile("w", suffix=".nft", delete=False) as handle:
        handle.write(ruleset)
    try:
        # A syntax check changes nothing, so it runs in dry-run mode too (without root it may be
        # refused; that is only reported there).
        checked = run(["nft", "--check", "--file", handle.name], check=False)
        if arguments.dry_run:
            show_change("the table that would be loaded", ruleset)
            if checked.returncode != 0:
                print("Note: nft could not check the table here (are you root?).")
            return EXIT_FRESH if fresh else EXIT_LAST_GOOD
        require_root()
        if checked.returncode != 0:
            raise HardeningError("The firewall refused the new table; nothing was changed.")
        run(["nft", "--file", handle.name])
    finally:
        Path(handle.name).unlink(missing_ok=True)
    if fresh:
        save(arguments.state_dir, "cloudflare-ranges.json", ranges)
    save(arguments.state_dir, "applied-ranges.json", ranges)
    print("Loaded.")
    return EXIT_FRESH if fresh else EXIT_LAST_GOOD


def remove(arguments):
    if not arguments.dry_run:
        require_root()
    run(["nft", "delete", "table", "inet", TABLE], dry_run=arguments.dry_run, check=False)
    return 0


def status(arguments):
    result = run(["nft", "list", "table", "inet", TABLE], check=False)
    print(result.stdout if result.returncode == 0 else "No Cloudflare-only rules are loaded.")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("apply", "remove", "status"))
    parser.add_argument("--dry-run", action="store_true", help="show the change, change nothing")
    parser.add_argument("--state-dir", default=str(DEFAULT_STATE_DIR))
    arguments = parser.parse_args(argv)
    commands = {"apply": apply, "remove": remove, "status": status}
    return main_wrapper(lambda: commands[arguments.command](arguments)) or 0


if __name__ == "__main__":
    raise SystemExit(main())
