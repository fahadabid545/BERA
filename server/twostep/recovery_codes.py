"""One-time recovery codes. Shown once when made; only a keyed hash is stored."""

import secrets

from django.utils import timezone

from core.field_protection import lookup_hash
from platform_settings.service import get_setting

from .models import RecoveryCode

# No 0/O or 1/I, so a code copied by hand is not mistaken. 10 characters of 32 is 50 bits.
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 10
GROUP_LENGTH = 5
PURPOSE = "twostep.recovery_code"


def normalise(text):
    return "".join(character for character in text.upper() if character.isalnum())


def _hash(code):
    return lookup_hash(normalise(code), PURPOSE)


def _new_code():
    letters = "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))
    return f"{letters[:GROUP_LENGTH]}-{letters[GROUP_LENGTH:]}"


def replace_codes(person):
    """Throws away every old code and returns a fresh set, the only time they can be read."""
    RecoveryCode.objects.filter(user=person).delete()
    codes = set()
    while len(codes) < get_setting("two_step.recovery_code_count"):
        codes.add(_new_code())
    RecoveryCode.objects.bulk_create(
        [RecoveryCode(user=person, code_hash=_hash(code)) for code in codes]
    )
    return sorted(codes)


def use_code(person, code):
    """True once for a right, unused code. The update only matches an unused row, so two
    requests with the same code cannot both succeed."""
    used = RecoveryCode.objects.filter(
        user=person, code_hash=_hash(code), used_at__isnull=True
    ).update(used_at=timezone.now())
    return used == 1


def codes_left(person):
    return RecoveryCode.objects.filter(user=person, used_at__isnull=True).count()
