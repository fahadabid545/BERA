"""Staging and production: Cloudflare R2 through its S3-compatible interface.

The bucket is private (no public address). R2 encrypts every object at rest, so nothing extra
is asked of it. Downloads use a short-lived signed address created after the app's own
permission check."""

from functools import lru_cache

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings

from .errors import StorageError, StoredFileMissing

NOT_FOUND_CODES = {"NoSuchKey", "404", "NotFound"}


@lru_cache(maxsize=1)
def make_client():
    return boto3.client(
        "s3",
        endpoint_url=f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        region_name="auto",
        # Retrying is the storage service's job (it waits and tells people); not the library's.
        config=Config(signature_version="s3v4", retries={"max_attempts": 1}),
    )


def save(key, data):
    try:
        make_client().put_object(Bucket=settings.R2_BUCKET, Key=key, Body=data)
    except (BotoCoreError, ClientError) as error:
        raise StorageError from error


def read(key):
    try:
        return make_client().get_object(Bucket=settings.R2_BUCKET, Key=key)["Body"].read()
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") in NOT_FOUND_CODES:
            raise StoredFileMissing from error
        raise StorageError from error
    except BotoCoreError as error:
        raise StorageError from error


def delete(key):
    try:
        make_client().delete_object(Bucket=settings.R2_BUCKET, Key=key)
    except (BotoCoreError, ClientError) as error:
        raise StorageError from error


def link_for(key, file_name, expires_seconds):
    """A signed address that works for `expires_seconds` and asks the browser to save the file
    under its (cleaned) name."""
    return make_client().generate_presigned_url(
        "get_object",
        Params={
            "Bucket": settings.R2_BUCKET,
            "Key": key,
            "ResponseContentDisposition": f'attachment; filename="{file_name}"',
        },
        ExpiresIn=expires_seconds,
    )
