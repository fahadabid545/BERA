from core import rate_limits
from core.throttles import RuleThrottle


class ApiKeyThrottle(RuleThrottle):
    """Each key has its own allowance, so one busy key never slows another."""

    rule = rate_limits.API_KEY

    def subject(self, request):
        return f"api-key:{request.user.key_id}"
