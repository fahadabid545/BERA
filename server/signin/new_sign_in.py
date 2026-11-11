"""Tells a person when their account is signed in from a device or country not seen before."""

import pycountry
from django.utils import timezone

from companies.countries import OTHER_COUNTRY
from companies.country_detection import detect_country
from emailing.links import build_link
from emailing.rendering import format_moment
from emailing.service import send_email

from .devices import describe_device
from .models import KnownSignIn

UNKNOWN_PLACE = "an unknown location"


def place_name(country_code):
    country = (
        None if country_code == OTHER_COUNTRY else pycountry.countries.get(alpha_2=country_code)
    )
    return country.name if country else UNKNOWN_PLACE


def notify_if_new_sign_in(person, request):
    """Records the device and country, and emails the person if either is new.

    The very first sign-in is the baseline and sends nothing; there is nothing to compare it
    with. When the country cannot be told (it is then Other) nothing is flagged for the
    place, so a missing header never causes a flood of notices."""
    device = describe_device(request.headers.get("User-Agent", ""))
    country = detect_country(request)
    known = KnownSignIn.objects.filter(user=person)
    is_first = not known.exists()
    is_new = not is_first and (
        not known.filter(device=device).exists() or not known.filter(country=country).exists()
    )
    KnownSignIn.objects.get_or_create(user=person, device=device, country=country)
    if is_new:
        send_email(
            "new_sign_in",
            person.email,
            name=person.name,
            when=format_moment(timezone.now()),
            device=device,
            place=place_name(country),
            link=build_link("/forgot-password"),
        )
    return is_new
