"""A short, readable description of the browser and system a request came from.

Used to tell a new device from a known one, and to say which one signed in. Version numbers
are left out on purpose: a browser update must not look like a new device.
"""

import re

UNKNOWN_DEVICE = "an unknown device"
MAX_LENGTH = 100

# Order matters: Edge, Opera and Chrome all say "Chrome", and Chrome also says "Safari".
BROWSERS = (
    ("Edge", re.compile(r"Edg(e|A|iOS)?/")),
    ("Opera", re.compile(r"OPR/|Opera")),
    ("Firefox", re.compile(r"Firefox/|FxiOS/")),
    ("Chrome", re.compile(r"Chrome/|CriOS/")),
    ("Safari", re.compile(r"Safari/")),
)
# iPhone and iPad user agents also say "like Mac OS X", and Android ones say "Linux".
SYSTEMS = (
    ("iPhone", re.compile(r"iPhone")),
    ("iPad", re.compile(r"iPad")),
    ("Android", re.compile(r"Android")),
    ("Windows", re.compile(r"Windows")),
    ("Mac", re.compile(r"Macintosh|Mac OS X")),
    ("Linux", re.compile(r"Linux|X11")),
)


def _first_match(options, text):
    return next((name for name, pattern in options if pattern.search(text)), None)


def describe_device(user_agent):
    text = (user_agent or "")[:500]
    browser, system = _first_match(BROWSERS, text), _first_match(SYSTEMS, text)
    if browser and system:
        return f"{browser} on {system}"
    return browser or system or UNKNOWN_DEVICE
