from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from server.connection_manager import ConnectionManager
from server.auth import router as auth_router
from server.users import router as users_router
from server.attachments import router as attachments_router
from server.pdf_summarize import router as summarize_router
from server.database import save_message, get_recent_messages, get_profile_pic_url
import os
import json

app = FastAPI(title="Realtime Chat Server")
manager = ConnectionManager()

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(attachments_router)
app.include_router(summarize_router)


@app.get("/")
async def root():
    """
    **Health check endpoint.**
    
    *Note: The main chat functionality uses WebSockets at `/ws/{username}`. 
    WebSocket endpoints do not appear in this Swagger UI because Swagger 
    is built exclusively for HTTP REST APIs, not persistent WebSocket connections.*
    """
    return {"status": "online", "message": "Realtime Chat Server is running."}

@app.get("/messages/history/{username}")
async def messages_history(username: str):
    history = get_recent_messages(username, limit=30)
    formatted = [
        {
            "role": msg["sender"],
            "content": msg["content"],
            "profile_pic_url": msg.get("profile_pic_url", ""),
            "attachment_url": msg.get("attachment_url") or "",
            "attachment_filename": msg.get("attachment_filename") or "",
            "attachment_mime": msg.get("attachment_mime") or "",
        }
        for msg in history
    ]
    return {"messages": formatted}

@app.websocket("/ws/{username}")
async def websocket_endpoint(websocket: WebSocket, username: str):
    await manager.connect(websocket, username)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                payload = json.loads(data)
                sender = payload.get("sender", username)
                if payload.get("type") == "chat":
                    bucket = os.getenv("S3_BUCKET_NAME", "")
                    att_url = payload.get("attachment_url") or ""
                    if att_url and bucket and f"{bucket}.s3" not in att_url.replace(
                        ".s3.dualstack", ".s3"
                    ):
                        att_url = ""
                    if not att_url:
                        payload.pop("attachment_url", None)
                        payload.pop("attachment_filename", None)
                        payload.pop("attachment_mime", None)
                    save_message(
                        sender,
                        payload.get("content", ""),
                        attachment_url=att_url or None,
                        attachment_filename=payload.get("attachment_filename"),
                        attachment_mime=payload.get("attachment_mime"),
                    )
                pic = get_profile_pic_url(sender)
                payload["sender_profile_pic_url"] = pic
                # Broadcast the message to everyone EXCEPT the sender
                # This ensures the sender's own UI isn't duplicated
                await manager.broadcast(payload, exclude_user=username)
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        manager.disconnect(username)
    except Exception:
        manager.disconnect(username)
