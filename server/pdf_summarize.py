"""
Summarize chat PDF attachments using Groq's free OpenAI-compatible API.
Requires GROQ_API_KEY (https://console.groq.com/). PDFs must be our public S3 URLs.
"""
from __future__ import annotations

import io
import os
import re

import requests
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from pypdf import PdfReader

from server.database import get_user

router = APIRouter(tags=["summarize"])

MAX_PDF_BYTES = 15 * 1024 * 1024
MAX_CHARS_FOR_LLM = 48_000
GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_GROQ_MODEL = "llama-3.1-8b-instant"


class SummarizePdfRequest(BaseModel):
    username: str = Field(..., min_length=1)
    pdf_url: str = Field(..., min_length=8, description="Public HTTPS URL of a PDF in this project's S3 bucket")


def _is_allowed_chat_pdf_url(url: str) -> bool:
    url = (url or "").strip()
    if not url.startswith("https://"):
        return False
    bucket = os.getenv("S3_BUCKET_NAME", "")
    if not bucket:
        return False
    normalized = url.replace(".s3.dualstack.", ".s3.")
    if f"{bucket}.s3" not in normalized:
        return False
    return "/attachments/" in url


def _fetch_pdf_bytes(url: str) -> bytes:
    try:
        r = requests.get(url, timeout=90)
        r.raise_for_status()
    except requests.RequestException as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not download PDF: {e}",
        ) from e
    data = r.content
    if len(data) > MAX_PDF_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="PDF is too large to summarize.",
        )
    if not data.startswith(b"%PDF"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Downloaded file is not a PDF.",
        )
    return data


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid or encrypted PDF: {e}",
        ) from e

    parts: list[str] = []
    for page in reader.pages:
        try:
            t = page.extract_text() or ""
        except Exception:
            t = ""
        parts.append(t)
    text = "\n".join(parts)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def _call_groq_summarize(document_text: str) -> str:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Summaries are not configured. Set GROQ_API_KEY (free tier: https://console.groq.com/).",
        )
    model = os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL).strip() or DEFAULT_GROQ_MODEL
    clipped = document_text[:MAX_CHARS_FOR_LLM]
    if len(document_text) > MAX_CHARS_FOR_LLM:
        clipped += "\n\n[... document truncated for summarization ...]"

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You summarize PDF documents for a chat app. "
                    "Reply with clear markdown: short overview, then 3–7 bullet key points. "
                    "If the text is unreadable or empty, say so briefly."
                ),
            },
            {
                "role": "user",
                "content": f"Summarize the following PDF text:\n\n{clipped}",
            },
        ],
        "temperature": 0.25,
        "max_tokens": 1200,
    }
    try:
        r = requests.post(
            GROQ_CHAT_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=120,
        )
    except requests.RequestException as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM request failed: {e}",
        ) from e

    if r.status_code != 200:
        try:
            err = r.json().get("error", {}).get("message", r.text)
        except Exception:
            err = r.text
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM error ({r.status_code}): {err}",
        )

    try:
        data = r.json()
        return (data["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError) as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unexpected response from LLM.",
        ) from e


@router.post("/summarize/pdf")
def summarize_pdf(req: SummarizePdfRequest):
    if not _is_allowed_chat_pdf_url(req.pdf_url):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="URL is not an allowed chat attachment from this deployment.",
        )

    user = get_user(req.username)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    raw = _fetch_pdf_bytes(req.pdf_url)
    text = _extract_pdf_text(raw)
    if not text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No extractable text in this PDF (it may be scanned images only).",
        )

    summary = _call_groq_summarize(text)
    if not summary:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Model returned an empty summary.",
        )

    return {"summary": summary, "model": os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL)}
