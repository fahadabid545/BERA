"""The throttle classes for views. Add them to a view's `throttle_classes` (see `limited`).

    class LoginView(APIView):
        throttle_classes = limited(LoginThrottle)

Every other view is covered by OtherRequestsThrottle through the project default.
"""

import hashlib

from rest_framework.throttling import BaseThrottle

from . import rate_limits
from .client_address import client_address


def address_subject(request):
    return f"address:{client_address(request)}"


def account_subject(request):
    """The signed-in person, or the address when nobody is signed in."""
    user = request.user
    if user and user.is_authenticated:
        return f"user:{user.user_id}"
    return address_subject(request)


class RuleThrottle(BaseThrottle):
    rule = None
    retry_after = 0

    def subject(self, request):
        raise NotImplementedError

    def cost(self, request):
        return 1

    def allow_request(self, request, view):
        self.retry_after = rate_limits.hit(self.rule, self.subject(request), self.cost(request))
        return self.retry_after == 0

    def wait(self):
        return self.retry_after


class LoginThrottle(RuleThrottle):
    rule = rate_limits.LOGIN
    subject = staticmethod(address_subject)


class RefreshThrottle(RuleThrottle):
    rule = rate_limits.REFRESH
    subject = staticmethod(address_subject)


class SignUpThrottle(RuleThrottle):
    rule = rate_limits.SIGN_UP
    subject = staticmethod(address_subject)


class ContactThrottle(RuleThrottle):
    rule = rate_limits.CONTACT
    subject = staticmethod(address_subject)


class PasswordResetThrottle(RuleThrottle):
    """Per email, so one person's inbox cannot be flooded from many addresses."""

    rule = rate_limits.PASSWORD_RESET

    def subject(self, request):
        email = request.data.get("email") if hasattr(request.data, "get") else None
        if not isinstance(email, str) or not email.strip():
            return address_subject(request)
        return "email:" + hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()


class InviteThrottle(RuleThrottle):
    rule = rate_limits.INVITES

    def subject(self, request):
        return f"company:{request.user.company_id}"


class UploadThrottle(RuleThrottle):
    """Counts files, not requests: a batch of 40 files uses 40 of the company's allowance."""

    rule = rate_limits.UPLOADS

    def subject(self, request):
        return f"company:{request.user.company_id}"

    def cost(self, request):
        return max(1, sum(len(files) for _, files in request.FILES.lists()))


class DownloadThrottle(RuleThrottle):
    rule = rate_limits.DOWNLOADS

    def subject(self, request):
        return f"user:{request.user.user_id}"


class OtherRequestsThrottle(RuleThrottle):
    rule = rate_limits.OTHER_REQUESTS
    subject = staticmethod(account_subject)


def limited(*throttles):
    """A view's throttles: the ones named plus the general limit every request has."""
    return [*throttles, OtherRequestsThrottle]
