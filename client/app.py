import json
import os
import queue
import sys
import time
import base64
import hashlib

import requests
import streamlit as st

# Ensure Python can find the 'client' and 'server' modules when run from root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from client.session_handler import init_session, clear_session
from client.websocket_client import init_websocket, start_background_listener

st.set_page_config(page_title="Realtime Chatbox", layout="centered")

init_session()

# Initialize auth states
if "auth_mode" not in st.session_state:
    st.session_state.auth_mode = "Login"
if "registration_email" not in st.session_state:
    st.session_state.registration_email = None
if "registration_username" not in st.session_state:
    st.session_state.registration_username = None

API_BASE = os.getenv("CHATBOX_API_BASE", "http://127.0.0.1:8000").rstrip("/")
AUTH_URL = f"{API_BASE}/auth"


def _avatar_for_message(role: str, profile_pic_url: str | None) -> str:
    url = (profile_pic_url or "").strip()
    if url:
        return url
    return "🧑‍💻" if role == st.session_state.username else "💬"


def _render_message_body(msg: dict) -> None:
    role = msg["role"]
    att_url = (msg.get("attachment_url") or "").strip()
    content = (msg.get("content") or "").strip()
    mime = (msg.get("attachment_mime") or "").lower()

    if att_url:
        st.markdown(f"**{role}**")
        fname = msg.get("attachment_filename") or "file"
        if mime.startswith("image/"):
            st.image(att_url)
        else:
            st.markdown(f"📄 [{fname}]({att_url})")
        if mime == "application/pdf":
            h = hashlib.md5(att_url.encode("utf-8")).hexdigest()[:16]
            summaries = st.session_state.pdf_summaries
            with st.expander("📝 AI summary (Groq — free tier)", expanded=False):
                if att_url in summaries:
                    st.markdown(summaries[att_url])
                if st.button("Generate summary", key=f"pdf_sum_btn_{h}"):
                    with st.spinner("Reading PDF and calling the model…"):
                        try:
                            sr = requests.post(
                                f"{API_BASE}/summarize/pdf",
                                json={
                                    "username": st.session_state.username,
                                    "pdf_url": att_url,
                                },
                                timeout=120,
                            )
                        except requests.RequestException as e:
                            st.error(str(e))
                        else:
                            if sr.status_code == 200:
                                summaries[att_url] = sr.json().get("summary", "")
                                st.rerun()
                            else:
                                try:
                                    detail = sr.json().get("detail", sr.text)
                                except Exception:
                                    detail = sr.text or "Summary failed."
                                st.error(detail)
        if content:
            st.markdown(content)
    else:
        st.markdown(f"**{role}**: {content}")


def _post_attachment_and_broadcast(
    file_bytes: bytes,
    filename: str,
    content_type: str | None,
    caption: str,
) -> None:
    u = st.session_state.username
    files = {"file": (filename, file_bytes, content_type or "application/octet-stream")}
    r = requests.post(f"{API_BASE}/users/{u}/attachments", files=files)
    if r.status_code != 200:
        try:
            detail = r.json().get("detail", r.text)
        except Exception:
            detail = r.text or "Upload failed."
        st.error(detail)
        return
    out = r.json()
    url = out["url"]
    fname = out["filename"]
    mime = out["mime"]
    cap = (caption or "").strip()

    entry = {
        "role": u,
        "content": cap,
        "profile_pic_url": st.session_state.profile_pic_url or "",
        "attachment_url": url,
        "attachment_filename": fname,
        "attachment_mime": mime,
    }
    st.session_state.messages.append(entry)

    payload = {
        "type": "chat",
        "sender": u,
        "content": cap,
        "attachment_url": url,
        "attachment_filename": fname,
        "attachment_mime": mime,
        "sender_profile_pic_url": st.session_state.profile_pic_url or "",
    }
    try:
        st.session_state.ws.send(json.dumps(payload))
    except Exception as e:
        st.session_state.messages.pop()
        st.error(f"Failed to send message: {e}")
        return
    st.rerun()


if not st.session_state.username:
    st.title("Welcome to Chatbox")

    if st.session_state.auth_mode == "OTP":
        st.subheader("Verify your Email")
        if st.session_state.get("registration_pic_warning"):
            st.warning(st.session_state.registration_pic_warning)
            st.session_state.registration_pic_warning = None
        st.info(f"An OTP has been sent to {st.session_state.registration_email}")
        otp = st.text_input("Enter 6-digit OTP:")
        if st.button("Verify"):
            res = requests.post(
                f"{AUTH_URL}/verify",
                json={"username": st.session_state.registration_username, "otp": otp},
            )
            if res.status_code == 200:
                st.success("Verification successful! You can now login.")
                st.session_state.auth_mode = "Login"
                st.rerun()
            else:
                st.error(res.json().get("detail", "Invalid OTP"))
        if st.button("Back to Login"):
            st.session_state.auth_mode = "Login"
            st.rerun()

    else:
        tab1, tab2 = st.tabs(["Login", "Register"])

        with tab1:
            st.subheader("Login")
            login_username = st.text_input("Username", key="login_user")
            login_password = st.text_input("Password", type="password", key="login_pass")
            if st.button("Login"):
                if login_username and login_password:
                    res = requests.post(
                        f"{AUTH_URL}/login",
                        json={"username": login_username, "password": login_password},
                    )
                    if res.status_code == 200:
                        data = res.json()
                        st.session_state.username = data["username"]
                        st.session_state.profile_pic_url = data.get("profile_pic_url", "")

                        try:
                            history_res = requests.get(
                                f"{API_BASE}/messages/history/{login_username}"
                            )
                            if history_res.status_code == 200:
                                st.session_state.messages = history_res.json().get(
                                    "messages", []
                                )
                        except Exception as e:
                            st.error(f"Failed to load history: {e}")

                        st.rerun()
                    else:
                        st.error(res.json().get("detail", "Login failed."))
                else:
                    st.warning("Please enter username and password.")

        with tab2:
            st.subheader("Register")
            reg_email = st.text_input("Email", key="reg_email")
            reg_username = st.text_input("Username", key="reg_user")
            reg_password = st.text_input("Password", type="password", key="reg_pass")
            reg_pic = st.file_uploader(
                "Upload profile picture (optional)",
                type=["png", "jpg", "jpeg", "webp", "gif"],
                key="reg_profile_pic",
            )
            if st.button("Register"):
                if reg_email and reg_username and reg_password:
                    payload = {
                        "email": reg_email,
                        "username": reg_username,
                        "password": reg_password,
                    }
                    if reg_pic is not None:
                        b64 = base64.b64encode(reg_pic.getvalue()).decode("ascii")
                        payload["profile_image_base64"] = b64
                        payload["profile_image_content_type"] = reg_pic.type or None
                    res = requests.post(f"{AUTH_URL}/register", json=payload)
                    if res.status_code == 200:
                        data = res.json()
                        if data.get("profile_picture_warning"):
                            st.session_state.registration_pic_warning = data[
                                "profile_picture_warning"
                            ]
                        st.session_state.registration_email = reg_email
                        st.session_state.registration_username = reg_username
                        st.session_state.auth_mode = "OTP"
                        st.rerun()
                    else:
                        st.error(res.json().get("detail", "Registration failed."))
                else:
                    st.warning("Please fill all fields.")
    st.stop()

# --- Chat (logged in) ---

col1, col2 = st.columns([0.8, 0.2])
with col1:
    st.title(f"Chatbox - {st.session_state.username}")
with col2:
    if st.button("Logout"):
        clear_session()
        st.session_state.auth_mode = "Login"
        st.rerun()

if st.session_state.ws is None:
    try:
        st.session_state.ws = init_websocket(st.session_state.username)
    except Exception as e:
        st.error(f"Failed to connect to server: {e}")
        st.stop()

with st.sidebar.expander("Profile settings", expanded=False):
    st.caption("Update your profile picture (stored on S3). Re-enter your password to confirm.")
    settings_pic = st.file_uploader(
        "New profile picture",
        type=["png", "jpg", "jpeg", "webp", "gif"],
        key="settings_profile_pic",
    )
    settings_password = st.text_input("Current password", type="password", key="settings_pw")
    if st.button("Save profile picture", key="settings_save_pic"):
        if not settings_password:
            st.warning("Password is required.")
        elif settings_pic is None:
            st.warning("Choose an image file.")
        else:
            b64 = base64.b64encode(settings_pic.getvalue()).decode("ascii")
            body = {
                "password": settings_password,
                "image_base64": b64,
                "content_type": settings_pic.type or None,
            }
            u = st.session_state.username
            try:
                r = requests.post(f"{API_BASE}/users/{u}/profile-picture", json=body)
                if r.status_code == 200:
                    url = r.json().get("profile_pic_url", "")
                    st.session_state.profile_pic_url = url
                    st.success("Profile picture updated.")
                    st.rerun()
                else:
                    st.error(r.json().get("detail", "Update failed."))
            except Exception as ex:
                st.error(str(ex))

start_background_listener(st.session_state.ws, st.session_state.message_queue, st)

for msg in st.session_state.messages:
    is_user = msg["role"] == st.session_state.username
    role_type = "user" if is_user else "assistant"
    pic = msg.get("profile_pic_url") or ""
    avatar = _avatar_for_message(msg["role"], pic)

    with st.chat_message(role_type, avatar=avatar):
        _render_message_body(msg)

# Camera must NOT live inside st.popover: browsers often block getUserMedia there,
# and camera requires a secure context (HTTPS or localhost) — not plain http:// to EC2.
with st.expander("📷 Take a photo", expanded=False):
    st.caption(
        "Allow camera when the browser prompts. If you never see a prompt: use **HTTPS** "
        "(or localhost), or take a screenshot and upload it via ➕ instead."
    )
    cam_main = st.camera_input("Camera", key="attach_cam_main", label_visibility="collapsed")
    attach_caption_cam = st.text_input("Caption (optional)", key="attach_caption_cam")
    if st.button("Send this photo", key="attach_send_cam_btn"):
        if cam_main is None:
            st.warning("Take a photo first (wait for the preview to appear).")
        else:
            _post_attachment_and_broadcast(
                cam_main.getvalue(),
                "camera.jpg",
                "image/jpeg",
                attach_caption_cam,
            )

attach_col, chat_col = st.columns([0.09, 0.91])
with attach_col:
    with st.popover("➕", help="Send a file from this device"):
        attach_caption = st.text_input("Caption (optional)", key="attach_caption_pop")
        up = st.file_uploader(
            "Choose file",
            type=["pdf", "png", "jpg", "jpeg", "gif", "webp", "txt", "doc", "docx"],
            key="attach_file_pop",
        )
        if st.button("Send attachment", key="attach_send_btn"):
            if up is None:
                st.warning("Choose a file first.")
            else:
                _post_attachment_and_broadcast(
                    up.getvalue(),
                    up.name,
                    up.type,
                    attach_caption,
                )

with chat_col:
    prompt = st.chat_input("Type your message here...")
if prompt:
    st.session_state.messages.append(
        {
            "role": st.session_state.username,
            "content": prompt,
            "profile_pic_url": st.session_state.profile_pic_url or "",
            "attachment_url": "",
            "attachment_filename": "",
            "attachment_mime": "",
        }
    )

    payload = {
        "type": "chat",
        "sender": st.session_state.username,
        "content": prompt,
        "sender_profile_pic_url": st.session_state.profile_pic_url or "",
        "attachment_url": "",
        "attachment_filename": "",
        "attachment_mime": "",
    }
    try:
        st.session_state.ws.send(json.dumps(payload))
    except Exception as e:
        st.session_state.messages.pop()
        st.error(f"Failed to send message: {e}")
    else:
        st.rerun()

while True:
    try:
        data = st.session_state.message_queue.get(timeout=0.1)
        if "error" in data:
            st.error(data["error"])
            st.session_state.ws = None
            break
        else:
            if data.get("type") != "chat" or "sender" not in data:
                continue
            pic = data.get("sender_profile_pic_url") or data.get("profile_pic_url") or ""
            st.session_state.messages.append(
                {
                    "role": data["sender"],
                    "content": data.get("content", ""),
                    "profile_pic_url": pic,
                    "attachment_url": data.get("attachment_url") or "",
                    "attachment_filename": data.get("attachment_filename") or "",
                    "attachment_mime": data.get("attachment_mime") or "",
                }
            )
            st.rerun()
    except queue.Empty:
        time.sleep(0.1)
        continue
