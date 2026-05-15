from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
import bcrypt
import random
import string
from server.database import create_user, get_user, verify_user, set_otp, update_profile_pic
from server.email_service import send_otp_email
from server.s3_profile import decode_base64_image_field, upload_profile_image

router = APIRouter(prefix="/auth", tags=["auth"])

class RegisterRequest(BaseModel):
    email: EmailStr
    username: str
    password: str
    profile_image_base64: str | None = Field(
        default=None,
        description="Optional base64 or data URL; uploaded to S3 after account creation.",
    )
    profile_image_content_type: str | None = Field(
        default=None,
        description="Optional MIME when image_base64 is raw base64 (not a data URL).",
    )

class VerifyRequest(BaseModel):
    username: str
    otp: str

class LoginRequest(BaseModel):
    username: str
    password: str

def generate_otp(length=6):
    return ''.join(random.choices(string.digits, k=length))

@router.post("/register")
async def register(req: RegisterRequest):
    user = get_user(req.username)
    if user:
        raise HTTPException(status_code=400, detail="Username already exists.")

    decoded_image: tuple[bytes, str] | None = None
    if req.profile_image_base64:
        try:
            decoded_image = decode_base64_image_field(
                req.profile_image_base64, req.profile_image_content_type
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    hashed_password = bcrypt.hashpw(req.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    otp = generate_otp()

    try:
        create_user(req.username, req.email, hashed_password, otp)
    except Exception:
        raise HTTPException(status_code=400, detail="Failed to create user (username may already exist).")

    profile_picture_warning: str | None = None
    if decoded_image is not None:
        raw, ctype = decoded_image
        try:
            url = upload_profile_image(req.username, raw, ctype)
            update_profile_pic(req.username, url)
        except RuntimeError as e:
            profile_picture_warning = str(e)

    try:
        send_otp_email(req.email, otp, req.username)
    except Exception:
        pass  # Allow failure gracefully if email fails

    body: dict = {"message": "Registration successful. Please verify OTP sent to email."}
    if profile_picture_warning:
        body["profile_picture_warning"] = profile_picture_warning
    return body

@router.post("/verify")
async def verify(req: VerifyRequest):
    user = get_user(req.username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    
    if user.get("is_verified"):
        return {"message": "User is already verified."}
        
    if user.get("otp") != req.otp:
        raise HTTPException(status_code=400, detail="Invalid OTP.")
        
    verify_user(req.username)
    return {"message": "Verification successful."}

@router.post("/login")
async def login(req: LoginRequest):
    user = get_user(req.username)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
        
    if not user.get("is_verified"):
        raise HTTPException(status_code=403, detail="User is not verified. Please register or verify OTP.")
        
    if not bcrypt.checkpw(req.password.encode('utf-8'), user.get("password_hash").encode('utf-8')):
        raise HTTPException(status_code=401, detail="Invalid username or password.")
        
    return {
        "message": "Login successful.",
        "username": user["username"],
        "profile_pic_url": user.get("profile_pic_url") or "",
    }
