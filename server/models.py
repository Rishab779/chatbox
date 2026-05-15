from pydantic import BaseModel


class ChatMessage(BaseModel):
    type: str
    sender: str
    content: str
    sender_profile_pic_url: str = ""
