from fastapi import APIRouter, File, HTTPException, UploadFile, status

from server.database import get_user
from server.s3_attachments import upload_chat_attachment

router = APIRouter(tags=["attachments"])


@router.post("/users/{username}/attachments")
async def upload_chat_file(
    username: str,
    file: UploadFile = File(...),
):
    """Multipart upload for logged-in chat users (username must exist)."""
    user = get_user(username)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    raw = await file.read()
    try:
        url, fname, mime = upload_chat_attachment(
            username, raw, file.filename, file.content_type
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        ) from e

    return {"url": url, "filename": fname, "mime": mime}
