"""
Upload profile images to S3. Public URLs assume a bucket policy allows s3:GetObject.
"""
import base64
import binascii
import hashlib
import os
import re
import time
from typing import Tuple

import boto3
from botocore.exceptions import ClientError

ALLOWED_CONTENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}

JPEG_MAGIC = b"\xff\xd8\xff"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
WEBP_MAGIC = b"RIFF"
GIF_MAGIC = (b"GIF87a", b"GIF89a")

MAX_IMAGE_BYTES = 2 * 1024 * 1024


def _s3_key_prefix_for_user(username: str) -> str:
    digest = hashlib.sha256(username.encode("utf-8")).hexdigest()[:32]
    return f"profiles/{digest}"


def _public_object_url(bucket: str, region: str, key: str, cache_bust: bool = True) -> str:
    base = f"https://{bucket}.s3.{region}.amazonaws.com/{key}"
    if cache_bust:
        return f"{base}?v={int(time.time())}"
    return base


def _detect_content_type(raw: bytes) -> str | None:
    if len(raw) >= 3 and raw[:3] == JPEG_MAGIC[:3]:
        return "image/jpeg"
    if len(raw) >= 8 and raw[:8] == PNG_MAGIC:
        return "image/png"
    if len(raw) >= 12 and raw[:4] == WEBP_MAGIC and raw[8:12] == b"WEBP":
        return "image/webp"
    if len(raw) >= 6:
        for g in GIF_MAGIC:
            if raw.startswith(g):
                return "image/gif"
    return None


def decode_base64_image_field(data: str, declared_type: str | None) -> Tuple[bytes, str]:
    """
    Accept raw base64 or a data URL. Returns (bytes, content_type).
    """
    s = (data or "").strip()
    if not s:
        raise ValueError("Empty image data")

    content_type_from_url: str | None = None
    if s.startswith("data:"):
        m = re.match(r"^data:([^;]+);base64,(.+)$", s, re.DOTALL | re.IGNORECASE)
        if not m:
            raise ValueError("Invalid data URL")
        content_type_from_url = m.group(1).strip().lower().split(";")[0].strip()
        s = m.group(2)

    s = re.sub(r"\s+", "", s)
    try:
        raw = base64.b64decode(s, validate=True)
    except binascii.Error as e:
        raise ValueError("Invalid base64 encoding") from e

    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError(f"Image too large (max {MAX_IMAGE_BYTES // (1024 * 1024)}MB)")

    detected = _detect_content_type(raw)
    if content_type_from_url and content_type_from_url in ALLOWED_CONTENT_TYPES:
        final_type = content_type_from_url
    elif declared_type and declared_type.lower().split(";")[0].strip() in ALLOWED_CONTENT_TYPES:
        final_type = declared_type.lower().split(";")[0].strip()
    elif detected:
        final_type = detected
    else:
        raise ValueError("Unsupported or corrupt image type")

    if detected and detected != final_type:
        raise ValueError("Image bytes do not match declared content type")

    return raw, final_type


def upload_profile_image(username: str, raw: bytes, content_type: str) -> str:
    bucket = os.getenv("S3_BUCKET_NAME")
    if not bucket:
        raise RuntimeError("S3_BUCKET_NAME is not configured")

    region = os.getenv("AWS_DEFAULT_REGION", "ap-south-1")
    ext = ALLOWED_CONTENT_TYPES[content_type]
    prefix = _s3_key_prefix_for_user(username)
    key = f"{prefix}/avatar{ext}"

    client = boto3.client("s3", region_name=region)
    try:
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=raw,
            ContentType=content_type,
            CacheControl="public, max-age=86400",
        )
    except ClientError as e:
        raise RuntimeError(f"S3 upload failed: {e}") from e

    return _public_object_url(bucket, region, key, cache_bust=True)
