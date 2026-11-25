"""The list of every cookie and browser storage key (`docs/cookies.json`) must stay true.

The website shows no cookie notice because it uses no non-essential cookies. If this test fails,
something was added that the list does not know. Update the list, and if the new cookie is not
essential (analytics, tracking, advertising) a cookie notice (BERA-176) is then required before
release: that is new work with wording from the owner."""

import json
import re
from pathlib import Path
from types import SimpleNamespace

from django.conf import settings
from django.http import HttpResponse

from signin.cookies import set_session_cookies
from signin.kinds import KINDS

ROOT = Path(settings.BASE_DIR).parent
LIST = json.loads((ROOT / "docs" / "cookies.json").read_text())
REMINDER = (
    " Update docs/cookies.json. If it is not essential, a cookie notice (BERA-176) is required "
    "before release."
)
TRACKING = re.compile(
    r"analytics|gtag|google-tag|gtm|segment|mixpanel|amplitude|hotjar|plausible|posthog|matomo|"
    r"fullstory|heap|clarity|sentry-replay|facebook-pixel|fbq|tiktok-pixel|adsense|doubleclick|"
    r"intercom|hubspot|drift|crisp|clickstream|tracking|vercel/analytics|vercel/speed-insights",
    re.IGNORECASE,
)
OUR_CODE = "our code"


def our_names(storage):
    return {
        item["name"] for item in LIST if item["set_by"] == OUR_CODE and item["storage"] == storage
    }


def test_every_entry_says_what_it_is_for_and_who_sets_it():
    for item in LIST:
        assert item["storage"] in ("cookie", "localStorage", "sessionStorage"), item
        assert item["set_by"] in (OUR_CODE, "outside our code"), item
        assert item["purpose"].strip(), item
        assert isinstance(item["essential"], bool), item
    assert len({item["name"] for item in LIST}) == len(LIST)


def test_nothing_we_set_is_non_essential():
    extra = [item["name"] for item in LIST if item["set_by"] == OUR_CODE and not item["essential"]]
    assert not extra, f"{extra} is not essential." + REMINDER


def test_the_cookies_the_server_sets_are_all_on_the_list():
    issued = SimpleNamespace(
        access_token="fake", refresh_token="fake", access_seconds=60, refresh_seconds=600
    )
    set_by_server = set()
    for kind in KINDS:
        response = HttpResponse()
        set_session_cookies(response, kind, issued)
        set_by_server |= set(response.cookies)
    unknown = set_by_server - our_names("cookie")
    assert not unknown, f"The server sets {sorted(unknown)}, which is not on the list." + REMINDER
    assert our_names("cookie") <= set_by_server, "A cookie on the list is no longer set."


def test_cookies_are_set_in_one_place_only():
    allowed = Path(settings.BASE_DIR) / "signin" / "cookies.py"
    for file in Path(settings.BASE_DIR).rglob("*.py"):
        parts = set(file.parts)
        if parts & {".venv", "tests", "migrations", "node_modules"} or file == allowed:
            continue
        assert ".set_cookie(" not in file.read_text(), (
            f"{file.relative_to(ROOT)} sets a cookie outside signin/cookies.py." + REMINDER
        )


def test_django_sets_no_cookie_of_its_own():
    assert "django.contrib.sessions" not in settings.INSTALLED_APPS
    assert "django.middleware.csrf.CsrfViewMiddleware" not in settings.MIDDLEWARE
    assert not any("session" in name.lower() for name in settings.MIDDLEWARE)


def test_no_analytics_or_tracking_library_is_a_dependency():
    names = []
    package = json.loads((ROOT / "web" / "package.json").read_text())
    names += list(package.get("dependencies", {})) + list(package.get("devDependencies", {}))
    for requirements in (ROOT / "server").glob("requirements*.txt"):
        for line in requirements.read_text().splitlines():
            name = re.split(r"[<>=!~\[; ]", line.strip(), maxsplit=1)[0]
            if name and not name.startswith("#"):
                names.append(name)
    found = [name for name in names if TRACKING.search(name)]
    assert not found, f"{found} looks like analytics or tracking." + REMINDER
