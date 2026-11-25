"""Items 10 to 14: the volume test, AI, email and names, the public side, and the private beta."""

from django.conf import settings
from django.utils import timezone

from ai import control
from ai.models import AiModel, PromptVersion
from announcements.models import Announcement
from platform_settings.service import get_setting

from .results import item, not_ok, ok, owner

MARKER_FILES_NOT_REAL_EMAIL = ("DevInboxBackend", "filebased", "locmem", "console", "dummy")
UNREAL_ADDRESS_ENDINGS = (".test", ".example", ".invalid", ".localhost")
UNREAL_DOMAINS = ("example.com", "example.org", "example.net")
SHARING_IMAGE = ("web", "public", "og-cover.png")


def volume_test(_context):
    return item(
        10,
        "Volume test",
        [
            owner(
                "The volume test (BERA-182) ran on the real server with a fake AI and with the "
                "real AI, and the targets and results are filled in."
            )
        ],
    )


def ai_ready(_context):
    parts = []
    if (settings.OPENAI_API_KEY or "").strip():
        parts.append(ok("An OpenAI key is set."))
    else:
        parts.append(not_ok("No OpenAI key is set."))
    if AiModel.objects.filter(enabled=True).exists():
        parts.append(ok("A model is enabled."))
    else:
        parts.append(not_ok("No AI model is enabled."))
    missing = [
        kind
        for kind in (PromptVersion.READING, PromptVersion.SCORING)
        if not PromptVersion.objects.filter(kind=kind).exists()
    ]
    parts += [not_ok(f"There is no {kind} prompt.") for kind in missing]
    if control.is_paused():
        parts.append(not_ok("AI work is paused."))
    if get_setting("ai.monthly_spend_alert_usd") is None:
        parts.append(not_ok("The monthly AI spend limit (ai.monthly_spend_alert_usd) is not set."))
    parts.append(
        owner(
            "The AI kill switch was tried once on the real server: paused, a CV waited, "
            "resumed, the CV was scored."
        )
    )
    return item(11, "Real AI key, models, prompts, kill switch and cost limit", parts)


def _looks_real(address):
    address = (address or "").strip().lower()
    domain = address.rpartition("@")[2]
    return bool(
        "@" in address
        and "." in domain
        and not domain.endswith(UNREAL_ADDRESS_ENDINGS)
        and domain not in UNREAL_DOMAINS
    )


def email_and_names(_context):
    parts = []
    if _looks_real(get_setting("general.support_email")):
        parts.append(ok("The support email looks real."))
    else:
        parts.append(not_ok("general.support_email is not a real address."))
    if any(word in settings.EMAIL_BACKEND for word in MARKER_FILES_NOT_REAL_EMAIL):
        parts.append(not_ok("Email is not set up to send for real."))
    parts.append(
        owner(
            "The app name setting is the real product name, a contact form test message "
            "arrives at the support address, and the sign-up, verification, reset and invite "
            "emails arrive in a real inbox."
        )
    )
    return item(12, "Support email, app name and real email delivery", parts)


def public_side(context):
    parts = []
    now = timezone.now()
    if Announcement.objects.filter(ends_at__gt=now).exists():
        parts.append(ok("An announcement is ready."))
    else:
        parts.append(not_ok("No announcement is ready (none that has not ended)."))
    if context.project_folder.joinpath(*SHARING_IMAGE).is_file():
        parts.append(ok("The sharing preview image exists."))
    else:
        parts.append(not_ok("web/public/og-cover.png is missing."))
    if str(settings.WEB_BASE_URL).startswith("https://"):
        parts.append(ok("The public address is https."))
    else:
        parts.append(not_ok("WEB_BASE_URL is not an https address."))
    return item(13, "Announcement, sharing image and public address", parts)


def private_beta(_context):
    return item(
        14,
        "Private beta",
        [
            owner(
                "The private beta (BERA-183) is done and no New feedback is left that blocks "
                "the launch."
            )
        ],
    )
