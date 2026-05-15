from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

import bcrypt

from server.database import get_user, update_profile_pic
from server.s3_profile import decode_base64_image_field, upload_profile_image

router = APIRouter(tags=["users"])


class ProfilePictureRequest(BaseModel):
    password: str
    image_base64: str = Field(..., description="Base64 string or data:image/...;base64,...")
    content_type: str | None = Field(
        default=None,
        description="Optional MIME type when image_base64 is raw base64 (not a data URL)",
    )


@router.post("/users/{username}/profile-picture")
async def set_profile_picture(username: str, body: ProfilePictureRequest):
    user = get_user(username)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    if not bcrypt.checkpw(
        body.password.encode("utf-8"),
        user.get("password_hash", "").encode("utf-8"),
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid password.",
        )

    try:
        raw, ctype = decode_base64_image_field(body.image_base64, body.content_type)
        url = upload_profile_image(username, raw, ctype)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        ) from e

    update_profile_pic(username, url)
    return {"message": "Profile picture updated.", "profile_pic_url": url}
