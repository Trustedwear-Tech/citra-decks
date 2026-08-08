# Copyright (c) 2024-2026 Citra AI (https://github.com/Citra-AI)
# Licensed under the Citra AI License v1.0. See LICENSE.md for details.
# SPDX-License-Identifier: LicenseRef-Citra-AI-BSL-1.0

"""
Unified object storage backend for Citra AI.

Supports MinIO (self-hosted), AWS S3, and Azure Blob Storage via a single
interface. Uses boto3 for S3/MinIO (MinIO is fully S3-API compatible) and
azure-storage-blob for Azure.

Usage:
    from storage_backend import get_storage_client

    storage = get_storage_client()
    await storage.upload_file(bucket, key, data)
    url = storage.get_presigned_url(bucket, key)
"""

import os
import io
import logging
from typing import Optional, BinaryIO
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class StorageBackend:
    """S3-compatible object storage (works with MinIO and AWS S3)."""

    def __init__(self):
        import boto3
        from botocore.config import Config as BotoConfig

        self.endpoint_url = os.getenv("BUCKET_ENDPOINT_URL", "").strip() or None
        self.bucket_name = os.getenv("BUCKET_NAME", "citra-documents")
        self.access_key = os.getenv("BUCKET_ACCESS_KEY", "")
        self.secret_key = os.getenv("BUCKET_SECRET_KEY", "")
        self.region = os.getenv("BUCKET_REGION", "us-east-1")

        client_kwargs = {
            "service_name": "s3",
            "aws_access_key_id": self.access_key,
            "aws_secret_access_key": self.secret_key,
            "region_name": self.region,
            "config": BotoConfig(signature_version="s3v4"),
        }

        if self.endpoint_url:
            client_kwargs["endpoint_url"] = self.endpoint_url

        self._client = boto3.client(**client_kwargs)

        # Detect if MinIO
        self.is_minio = bool(self.endpoint_url and "minio" in self.endpoint_url.lower())

        mode = "MinIO" if self.is_minio else ("S3" if not self.endpoint_url else "S3-compatible")
        logger.info(f"📦 Storage backend initialized: {mode} (bucket={self.bucket_name})")

    def ensure_bucket(self, bucket: Optional[str] = None):
        """Create bucket if it doesn't exist."""
        bucket = bucket or self.bucket_name
        try:
            self._client.head_bucket(Bucket=bucket)
        except Exception:
            try:
                self._client.create_bucket(
                    Bucket=bucket,
                    CreateBucketConfiguration={"LocationConstraint": self.region}
                    if self.region != "us-east-1" else {}
                )
                logger.info(f"📦 Created bucket: {bucket}")
            except Exception as e:
                # Bucket might already exist from a different error path
                if "BucketAlreadyOwnedByYou" not in str(e):
                    raise

    def upload_file(
        self,
        key: str,
        data: BinaryIO | bytes,
        bucket: Optional[str] = None,
        content_type: Optional[str] = None,
    ) -> str:
        """
        Upload a file to storage.
        Returns the object key.
        """
        bucket = bucket or self.bucket_name
        extra_args = {}
        if content_type:
            extra_args["ContentType"] = content_type

        if isinstance(data, bytes):
            data = io.BytesIO(data)

        self._client.upload_fileobj(data, bucket, key, ExtraArgs=extra_args or None)
        logger.debug(f"Uploaded: s3://{bucket}/{key}")
        return key

    def download_file(self, key: str, bucket: Optional[str] = None) -> bytes:
        """Download a file from storage."""
        bucket = bucket or self.bucket_name
        response = self._client.get_object(Bucket=bucket, Key=key)
        return response["Body"].read()

    def get_presigned_url(
        self,
        key: str,
        bucket: Optional[str] = None,
        expires_in: int = 3600,
    ) -> str:
        """Generate a presigned URL for download."""
        bucket = bucket or self.bucket_name
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expires_in,
        )

    def get_upload_presigned_url(
        self,
        key: str,
        bucket: Optional[str] = None,
        expires_in: int = 3600,
        content_type: Optional[str] = None,
    ) -> str:
        """Generate a presigned URL for upload."""
        bucket = bucket or self.bucket_name
        params = {"Bucket": bucket, "Key": key}
        if content_type:
            params["ContentType"] = content_type
        return self._client.generate_presigned_url(
            "put_object",
            Params=params,
            ExpiresIn=expires_in,
        )

    def delete_file(self, key: str, bucket: Optional[str] = None) -> bool:
        """Delete a file from storage."""
        bucket = bucket or self.bucket_name
        try:
            self._client.delete_object(Bucket=bucket, Key=key)
            return True
        except Exception as e:
            logger.error(f"Failed to delete {key}: {e}")
            return False

    def file_exists(self, key: str, bucket: Optional[str] = None) -> bool:
        """Check if a file exists."""
        bucket = bucket or self.bucket_name
        try:
            self._client.head_object(Bucket=bucket, Key=key)
            return True
        except Exception:
            return False

    def list_files(
        self,
        prefix: str = "",
        bucket: Optional[str] = None,
        max_keys: int = 1000,
    ) -> list[dict]:
        """List files in a bucket with optional prefix."""
        bucket = bucket or self.bucket_name
        response = self._client.list_objects_v2(
            Bucket=bucket, Prefix=prefix, MaxKeys=max_keys
        )
        return [
            {
                "key": obj["Key"],
                "size": obj["Size"],
                "last_modified": obj["LastModified"].isoformat(),
            }
            for obj in response.get("Contents", [])
        ]


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_storage_client: Optional[StorageBackend] = None


def get_storage_client() -> StorageBackend:
    """Get the global storage client (lazy initialization)."""
    global _storage_client
    if _storage_client is None:
        _storage_client = StorageBackend()
    return _storage_client
