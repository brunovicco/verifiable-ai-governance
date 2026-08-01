"""S3-compatible object storage adapter for immutable evidence artifacts."""

import asyncio
from typing import Any

import boto3  # type: ignore[import-untyped]
from botocore.config import Config  # type: ignore[import-untyped]
from botocore.exceptions import BotoCoreError, ClientError  # type: ignore[import-untyped]

from ai_governance_api.application.evidence import BinaryContent, EvidenceDependencyError
from ai_governance_api.domain.evidence import StoredObject


class S3ObjectStorage:
    """Store private evidence objects in an S3-compatible bucket."""

    def __init__(
        self,
        *,
        bucket: str,
        region: str,
        endpoint_url: str,
        access_key: str,
        secret_key: str,
        auto_create_bucket: bool,
        server_side_encryption: str,
        connect_timeout_seconds: float,
        read_timeout_seconds: float,
        client: Any | None = None,
    ) -> None:
        """Initialize the adapter without making a network request."""
        self._bucket = bucket
        self._region = region
        self._auto_create_bucket = auto_create_bucket
        self._server_side_encryption = server_side_encryption
        self._bucket_ready = False
        self._bucket_lock = asyncio.Lock()
        client_options: dict[str, object] = {
            "region_name": region,
            "config": Config(
                connect_timeout=connect_timeout_seconds,
                read_timeout=read_timeout_seconds,
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        }
        if endpoint_url:
            client_options["endpoint_url"] = endpoint_url
        if access_key and secret_key:
            client_options["aws_access_key_id"] = access_key
            client_options["aws_secret_access_key"] = secret_key
        self._client: Any = client or boto3.client("s3", **client_options)

    async def put(
        self,
        *,
        key: str,
        content: BinaryContent,
        content_type: str,
        size_bytes: int,
        sha256: str,
    ) -> StoredObject:
        """Create a private immutable object with integrity metadata."""
        await self._ensure_bucket()
        parameters: dict[str, object] = {
            "Bucket": self._bucket,
            "Key": key,
            "Body": content,
            "ContentLength": size_bytes,
            "ContentType": content_type,
            "Metadata": {"sha256": sha256},
            "IfNoneMatch": "*",
        }
        if self._server_side_encryption:
            parameters["ServerSideEncryption"] = self._server_side_encryption
        try:
            await asyncio.to_thread(self._client.put_object, **parameters)
        except (BotoCoreError, ClientError, OSError) as exc:
            raise EvidenceDependencyError("S3 put failed") from exc
        return StoredObject(
            bucket=self._bucket,
            key=key,
            uri=f"s3://{self._bucket}/{key}",
        )

    async def delete(self, stored: StoredObject) -> None:
        """Delete an object during compensating rollback."""
        try:
            await asyncio.to_thread(
                self._client.delete_object,
                Bucket=stored.bucket,
                Key=stored.key,
            )
        except (BotoCoreError, ClientError, OSError) as exc:
            raise EvidenceDependencyError("S3 delete failed") from exc

    async def _ensure_bucket(self) -> None:
        """Verify bucket availability and create it only when explicitly allowed."""
        if self._bucket_ready:
            return
        async with self._bucket_lock:
            if self._bucket_ready:
                return
            try:
                await asyncio.to_thread(self._client.head_bucket, Bucket=self._bucket)
            except ClientError as exc:
                if not self._auto_create_bucket:
                    raise EvidenceDependencyError("S3 bucket is unavailable") from exc
                await self._create_bucket()
            except (BotoCoreError, OSError) as exc:
                raise EvidenceDependencyError("S3 bucket check failed") from exc
            self._bucket_ready = True

    async def _create_bucket(self) -> None:
        """Create a local-development bucket without weakening production policy."""
        parameters: dict[str, object] = {"Bucket": self._bucket}
        if self._region != "us-east-1":
            parameters["CreateBucketConfiguration"] = {
                "LocationConstraint": self._region
            }
        try:
            await asyncio.to_thread(self._client.create_bucket, **parameters)
        except (BotoCoreError, ClientError, OSError) as exc:
            raise EvidenceDependencyError("S3 bucket creation failed") from exc
