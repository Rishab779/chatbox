import os
import smtplib
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from io import BytesIO

from dotenv import load_dotenv

load_dotenv()

SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_EMAIL = os.getenv("SMTP_EMAIL")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

# Optional: full HTTPS URL to a banner image (e.g. hosted on S3). If unset, a small branded PNG is generated.
EMAIL_HEADER_IMAGE_URL = (os.getenv("EMAIL_HEADER_IMAGE_URL") or "").strip()


def _build_inline_banner_png() -> bytes:
    """Branded header image embedded in the email (no external hosting required)."""
    from PIL import Image, ImageDraw, ImageFont

    w, h = 600, 170
    img = Image.new("RGB", (w, h), "#0f3460")
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, w, 72], fill="#1a1a2e")
    draw.rectangle([0, 72, w, h], fill="#16213e")

    font_paths = [
        os.getenv("EMAIL_BANNER_FONT_PATH", "").strip(),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
    ]
    title_font = None
    sub_font = None
    for path in font_paths:
        if not path or not os.path.isfile(path):
            continue
        try:
            title_font = ImageFont.truetype(path, 34)
            sub_font = ImageFont.truetype(path, 16)
            break
        except OSError:
            continue
    if title_font is None:
        title_font = ImageFont.load_default()
        sub_font = ImageFont.load_default()

    draw.text((28, 20), "Chatbox", fill="#e94560", font=title_font)
    draw.text((28, 100), "Verify your email to finish signing up", fill="#c9d1d9", font=sub_font)

    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _otp_html(otp: str, username: str | None, header_img_src: str) -> str:
    name = (username or "").strip()
    greeting = f"Hi <strong>{name}</strong>," if name else "Hi there,"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Your verification code</title>
</head>
<body style="margin:0;padding:0;background-color:#f4f6f8;font-family:Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color:#f4f6f8;padding:24px 12px;">
    <tr>
      <td align="center">
        <table role="presentation" width="600" cellspacing="0" cellpadding="0" style="max-width:600px;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 4px 24px rgba(15,52,96,0.12);">
          <tr>
            <td style="padding:0;">
              <img src="{header_img_src}" width="600" alt="Chatbox" style="display:block;width:100%;max-width:600px;height:auto;border:0;" />
            </td>
          </tr>
          <tr>
            <td style="padding:32px 36px 8px 36px;color:#1a1a2e;font-size:16px;line-height:1.6;">
              {greeting}
              <p style="margin:16px 0 0 0;color:#3d4f5f;">
                Thanks for joining <strong style="color:#0f3460;">Chatbox</strong>. Use this one-time code to verify your email:
              </p>
            </td>
          </tr>
          <tr>
            <td align="center" style="padding:12px 36px 28px 36px;">
              <div style="display:inline-block;padding:18px 40px;background:linear-gradient(135deg,#16213e 0%,#0f3460 100%);border-radius:10px;letter-spacing:8px;font-size:28px;font-weight:700;color:#e94560;font-family:Consolas,Monaco,monospace;">
                {otp}
              </div>
            </td>
          </tr>
          <tr>
            <td style="padding:0 36px 28px 36px;color:#5c6b7a;font-size:14px;line-height:1.55;">
              This code expires when you complete verification. If you did not create an account, you can ignore this message.
            </td>
          </tr>
          <tr>
            <td style="padding:20px 36px;background:#f4f6f8;border-top:1px solid #e2e8f0;font-size:12px;color:#8899aa;text-align:center;">
              Sent by Chatbox · Do not share this code with anyone.
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _otp_plain(otp: str, username: str | None) -> str:
    name = (username or "").strip()
    hi = f"Hi {name}," if name else "Hi,"
    return (
        f"{hi}\n\n"
        f"Welcome to Chatbox. Your email verification code is:\n\n"
        f"  {otp}\n\n"
        f"Enter this code in the app to finish signing up.\n\n"
        f"If you did not request this, you can ignore this email.\n"
    )


def send_otp_email(to_email: str, otp: str, username: str | None = None):
    if not SMTP_EMAIL or not SMTP_PASSWORD:
        print(f"MOCK EMAIL (No credentials provided): OTP for {to_email} is {otp}")
        return

    use_external_banner = EMAIL_HEADER_IMAGE_URL.startswith("https://")
    header_src = EMAIL_HEADER_IMAGE_URL if use_external_banner else "cid:chatbox_header"

    html_body = _otp_html(otp, username, header_src)
    plain_body = _otp_plain(otp, username)

    msg = MIMEMultipart("related")
    msg["From"] = SMTP_EMAIL
    msg["To"] = to_email
    msg["Subject"] = "Your Chatbox verification code"

    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(plain_body, "plain", "utf-8"))
    alt.attach(MIMEText(html_body, "html", "utf-8"))
    msg.attach(alt)

    if not use_external_banner:
        try:
            png_bytes = _build_inline_banner_png()
            img = MIMEImage(png_bytes, _subtype="png")
            img.add_header("Content-ID", "<chatbox_header>")
            img.add_header("Content-Disposition", "inline", filename="chatbox_header.png")
            msg.attach(img)
        except Exception as e:
            print(f"Banner image skipped (Pillow/font issue): {e}")

    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_EMAIL, SMTP_PASSWORD)
        server.sendmail(SMTP_EMAIL, to_email, msg.as_string())
        server.quit()
        print(f"Successfully sent OTP email to {to_email}")
    except Exception as e:
        print(f"Failed to send email: {e}")
        raise e
