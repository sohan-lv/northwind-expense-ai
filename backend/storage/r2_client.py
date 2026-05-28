import logging

import boto3
from botocore.exceptions import ClientError

from backend.config import settings

logger = logging.getLogger(__name__)


def get_r2_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.R2_ENDPOINT_URL,
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        region_name="auto",
    )


def upload_file(file_bytes: bytes, key: str) -> str:
    client = get_r2_client()
    try:
        client.put_object(Bucket=settings.R2_BUCKET_NAME, Key=key, Body=file_bytes)
        return key
    except ClientError as e:
        raise RuntimeError(f"R2 upload failed for key '{key}': {e}") from e


def get_signed_url(key: str, expires_in: int = 3600) -> str:
    client = get_r2_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.R2_BUCKET_NAME, "Key": key},
        ExpiresIn=expires_in,
    )


def delete_file(key: str) -> bool:
    client = get_r2_client()
    try:
        client.delete_object(Bucket=settings.R2_BUCKET_NAME, Key=key)
        return True
    except Exception:
        return False


def test_connection() -> bool:
    client = get_r2_client()
    try:
        client.list_objects_v2(Bucket=settings.R2_BUCKET_NAME, MaxKeys=1)
        logger.info("R2 connection: OK")
        return True
    except Exception as e:
        logger.warning(f"R2 connection: FAILED — {e}")
        return False
