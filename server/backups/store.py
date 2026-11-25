"""Where backup files are kept: a private Cloudflare R2 bucket used for nothing else, with its
own access key (never the key of the CV bucket). Development and tests use a local folder."""

import re
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import boto3
from boto3.s3.transfer import TransferConfig
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings

from .errors import BackupFailure

NAME_PATTERN = re.compile(r"^bera-backup-\d{8}T\d{6}Z\.dump\.enc$")
PART_SIZE = 8 * 1024 * 1024  # R2 needs at least 5 MiB per part


def object_name(moment: datetime):
    return f"bera-backup-{moment.strftime('%Y%m%dT%H%M%SZ')}.dump.enc"


@dataclass(frozen=True)
class StoredBackup:
    name: str
    modified: datetime
    size: int


class LocalStore:
    def __init__(self, folder):
        self.folder = Path(folder)

    def save(self, name, source):
        self.folder.mkdir(parents=True, exist_ok=True)
        self.folder.chmod(0o700)
        partial = self.folder / f"{name}.partial"
        try:
            with partial.open("wb") as target:
                while chunk := source.read(1024 * 1024):
                    target.write(chunk)
            partial.chmod(0o600)
            partial.rename(self.folder / name)
        finally:
            partial.unlink(missing_ok=True)

    def size(self, name):
        return (self.folder / name).stat().st_size

    def open(self, name):
        return (self.folder / name).open("rb")

    def list(self):
        return (
            [
                StoredBackup(
                    path.name,
                    datetime.fromtimestamp(path.stat().st_mtime).astimezone(),
                    path.stat().st_size,
                )
                for path in self.folder.glob("bera-backup-*")
                if NAME_PATTERN.match(path.name)
            ]
            if self.folder.exists()
            else []
        )

    def delete(self, name):
        (self.folder / name).unlink(missing_ok=True)


@lru_cache(maxsize=1)
def _r2_client():
    return boto3.client(
        "s3",
        endpoint_url=f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=settings.BACKUP_R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.BACKUP_R2_SECRET_ACCESS_KEY,
        region_name="auto",
        config=Config(signature_version="s3v4", retries={"max_attempts": 3}),
    )


class R2Store:
    def __init__(self, client, bucket):
        self.client = client
        self.bucket = bucket

    def _guard(self, kind, call):
        try:
            return call()
        except (BotoCoreError, ClientError):
            raise BackupFailure(kind) from None

    def save(self, name, source):
        transfer = TransferConfig(
            multipart_threshold=PART_SIZE,
            multipart_chunksize=PART_SIZE,
            max_concurrency=1,
            use_threads=False,
        )
        self._guard(
            "upload",
            lambda: self.client.upload_fileobj(source, self.bucket, name, Config=transfer),
        )

    def size(self, name):
        return self._guard(
            "storage",
            lambda: self.client.head_object(Bucket=self.bucket, Key=name)["ContentLength"],
        )

    def open(self, name):
        return self._guard(
            "download", lambda: self.client.get_object(Bucket=self.bucket, Key=name)["Body"]
        )

    def list(self):
        def collect():
            found = []
            for page in self.client.get_paginator("list_objects_v2").paginate(Bucket=self.bucket):
                found += [
                    StoredBackup(item["Key"], item["LastModified"], item["Size"])
                    for item in page.get("Contents", [])
                    if NAME_PATTERN.match(item["Key"])
                ]
            return found

        return self._guard("storage", collect)

    def delete(self, name):
        self._guard("pruning", lambda: self.client.delete_object(Bucket=self.bucket, Key=name))


def get_store():
    if settings.BACKUP_R2_BUCKET:
        return R2Store(_r2_client(), settings.BACKUP_R2_BUCKET)
    if settings.APP_ENV == "development":
        return LocalStore(settings.BACKUP_LOCAL_FOLDER)
    raise BackupFailure("configuration")
