import re
from pathlib import Path

from companies.countries import COUNTRY_CODES, OTHER_COUNTRY

WEB_LIST = Path(__file__).resolve().parents[3] / "web" / "src" / "lib" / "countries.ts"


def test_the_list_has_every_country_once():
    assert len(COUNTRY_CODES) == len(set(COUNTRY_CODES)) == 249
    assert all(re.fullmatch(r"[A-Z]{2}", code) for code in COUNTRY_CODES)
    assert OTHER_COUNTRY == "ZZ" and OTHER_COUNTRY not in COUNTRY_CODES


def test_the_web_app_offers_exactly_the_countries_the_server_accepts():
    text = WEB_LIST.read_text(encoding="utf-8")
    listed = re.search(r"COUNTRY_CODES = \[(.*?)\] as const", text, re.DOTALL).group(1)
    assert tuple(re.findall(r'"([A-Z]{2})"', listed)) == COUNTRY_CODES
    assert f'OTHER_COUNTRY = "{OTHER_COUNTRY}"' in text
