"""
Chat attachments on S3 (same bucket as profile pics, different prefix).
Stores only objects in S3; metadata goes to DynamoDB on the message row.
"""
from __future__ import annotations

import os
import re
import time
import secrets
import hashlib
from typing import Tuple

import boto3
from botocore.exceptions import ClientError

# Single PUT keeps requests and complexity low (good for small/medium files).
MAX_ATTACHMENT_BYTES = 15 * 1024 * 1024

# Conservative allow-list to reduce abuse and surprise costs.
EXT_TO_MIME = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".txt": "text/plain",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def _public_object_url(bucket: str, region: str, key: str, cache_bust: bool = True) -> str:
    base = f"https://{bucket}.s3.{region}.amazonaws.com/{key}"
    if cache_bust:
        return f"{base}?v={int(time.time())}"
    return base


def _safe_filename(name: str | None) -> str:
    base = os.path.basename(name or "file")
    base = re.sub(r"[^a-zA-Z0-9._-]+", "_", base).strip("._") or "file"
    return base[:160]


def _detect_magic_ext(raw: bytes) -> str | None:
    if raw.startswith(b"%PDF"):
        return ".pdf"
    if len(raw) >= 8 and raw[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if len(raw) >= 3 and raw[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if len(raw) >= 6 and raw[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    if len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return ".webp"
    if len(raw) >= 4 and raw[:4] == b"PK\x03\x04":
        return ".docx"
    if len(raw) >= 8 and raw[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return ".doc"
    return None


def _infer_ext_and_mime(
    original_filename: str | None, declared_mime: str | None, raw: bytes
) -> Tuple[str, str]:
    name = original_filename or ""
    ext = os.path.splitext(name)[1].lower()
    if ext not in EXT_TO_MIME:
        ext = ""

    magic_ext = _detect_magic_ext(raw)

    if not ext and magic_ext and magic_ext in EXT_TO_MIME:
        ext = magic_ext

    if not ext:
        raise ValueError(
            "Unsupported file type. Allowed: PDF, Word (.doc/.docx), images, plain text."
        )

    mime = EXT_TO_MIME[ext]

    if ext == ".txt":
        return ext, mime

    if ext == ".jpg" or ext == ".jpeg":
        if magic_ext not in (None, ".jpg"):
            raise ValueError("Not a valid JPEG image")
        ext = ".jpg"
        mime = EXT_TO_MIME[".jpg"]
        return ext, mime

    if ext == ".pdf" and magic_ext != ".pdf":
        raise ValueError("Not a valid PDF")
    if ext == ".png" and magic_ext != ".png":
        raise ValueError("Not a valid PNG")
    if ext == ".gif" and magic_ext != ".gif":
        raise ValueError("Not a valid GIF")
    if ext == ".webp" and magic_ext != ".webp":
        raise ValueError("Not a valid WebP image")
    if ext == ".docx" and magic_ext != ".docx":
        raise ValueError("Not a valid DOCX file")
    if ext == ".doc" and magic_ext != ".doc":
        raise ValueError("Not a valid DOC file")

    return ext, mime


def upload_chat_attachment(
    username: str, raw: bytes, original_filename: str | None, declared_mime: str | None
) -> tuple[str, str, str]:
    if len(raw) > MAX_ATTACHMENT_BYTES:
        raise ValueError(f"File too large (max {MAX_ATTACHMENT_BYTES // (1024 * 1024)} MB)")

    ext, content_type = _infer_ext_and_mime(original_filename, declared_mime, raw)
    safe = _safe_filename(original_filename)
    if not safe.lower().endswith(ext.lower()):
        root, _ = os.path.splitext(safe)
        safe = f"{root}{ext}"

    bucket = os.getenv("S3_BUCKET_NAME")
    if not bucket:
        raise RuntimeError("S3_BUCKET_NAME is not configured")

    region = os.getenv("AWS_DEFAULT_REGION", "ap-south-1")
    user_hash = hashlib.sha256(username.encode("utf-8")).hexdigest()[:16]
    token = secrets.token_hex(4)
    key = f"attachments/global/{user_hash}/{int(time.time() * 1000)}_{token}_{safe}"

    client = boto3.client("s3", region_name=region)
    try:
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=raw,
            ContentType=content_type,
            CacheControl="public, max-age=3600",
        )
    except ClientError as e:
        raise RuntimeError(f"S3 upload failed: {e}") from e

    url = _public_object_url(bucket, region, key, cache_bust=True)
    return url, safe, content_type
