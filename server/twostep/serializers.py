from rest_framework import serializers

from core.validation import StrictSerializer

# Generous: a code is checked, not stored, and a wrong length is simply a wrong code.
MAX_CODE_LENGTH = 32
MAX_CHALLENGE_LENGTH = 1024
MAX_PASSWORD_LENGTH = 4096


class CodeSerializer(StrictSerializer):
    code = serializers.CharField(max_length=MAX_CODE_LENGTH)


class ChallengeSerializer(StrictSerializer):
    challenge = serializers.CharField(max_length=MAX_CHALLENGE_LENGTH)


class ChallengeCodeSerializer(ChallengeSerializer, CodeSerializer):
    pass


class TurnOffSerializer(CodeSerializer):
    password = serializers.CharField(max_length=MAX_PASSWORD_LENGTH, trim_whitespace=False)


class RequirementSerializer(StrictSerializer):
    required = serializers.BooleanField()
