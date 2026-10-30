from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    throttle_classes,
)
from rest_framework.response import Response

from core.field_protection import normalize_email
from core.permissions import PublicAccess
from core.throttles import (
    PasswordResetThrottle,
    SignUpThrottle,
    VerificationResendThrottle,
    limited,
)

from .country_detection import detect_country
from .password_reset import FORGOT_MESSAGE, reset_password, send_reset_link
from .serializers import (
    ForgotPasswordSerializer,
    ResendVerificationSerializer,
    ResetPasswordSerializer,
    SignUpSerializer,
    VerifyEmailSerializer,
)
from .signup import NEUTRAL_MESSAGE, sign_up
from .verification import RESEND_MESSAGE, resend_verification, verify_email


@api_view(["POST"])
@authentication_classes([])
@permission_classes([PublicAccess])  # a visitor has no account yet
@throttle_classes(limited(SignUpThrottle))
def sign_up_company(request):
    serializer = SignUpSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    values = serializer.validated_data
    values.pop("accept_terms")
    sign_up(**values)
    return Response({"status": "ok", "message": NEUTRAL_MESSAGE})


@api_view(["GET"])
@authentication_classes([])
@permission_classes([PublicAccess])  # shown on the sign-up form before there is an account
def suggested_country(request):
    return Response({"country": detect_country(request)})


@api_view(["POST"])
@authentication_classes([])  # the link decides whose email is verified, not who is signed in
@permission_classes([PublicAccess])  # the secret in the link is the credential
def verify_company_email(request):
    serializer = VerifyEmailSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    verify_email(serializer.validated_data["token"])
    return Response({"status": "verified"})


@api_view(["POST"])
@authentication_classes([])
@permission_classes([PublicAccess])  # the person cannot sign in until the email is verified
@throttle_classes(limited(VerificationResendThrottle))
def resend_company_verification(request):
    serializer = ResendVerificationSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    resend_verification(normalize_email(serializer.validated_data["email"]))
    return Response({"status": "ok", "message": RESEND_MESSAGE})


@api_view(["POST"])
@authentication_classes([])
@permission_classes([PublicAccess])  # a person who forgot their password cannot sign in
@throttle_classes(limited(PasswordResetThrottle))
def forgot_company_password(request):
    serializer = ForgotPasswordSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    send_reset_link(normalize_email(serializer.validated_data["email"]))
    return Response({"status": "ok", "message": FORGOT_MESSAGE})


@api_view(["POST"])
@authentication_classes([])
@permission_classes([PublicAccess])  # the single-use secret in the link is the credential
def reset_company_password(request):
    serializer = ResetPasswordSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    values = serializer.validated_data
    reset_password(values["token"], values["password"])
    return Response({"status": "ok"})
