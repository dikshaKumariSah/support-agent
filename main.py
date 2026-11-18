import uuid
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from agent import Conversation

app = FastAPI()

# Open conversations, kept in memory: {conversation_id: Conversation}.
# They are lost when the server restarts.
conversations: dict[str, Conversation] = {}

CHAT_PAGE = Path(__file__).parent / "static" / "index.html"


@app.get("/")
def home():
    return FileResponse(CHAT_PAGE)


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None


@app.post("/chat")
def chat(request: ChatRequest):
    if request.conversation_id is None:
        conversation_id = str(uuid.uuid4())
        conversations[conversation_id] = Conversation()
    elif request.conversation_id in conversations:
        conversation_id = request.conversation_id
    else:
        raise HTTPException(status_code=404, detail="Conversation not found")

    reply = conversations[conversation_id].send(request.message)
    return {"conversation_id": conversation_id, "reply": reply}


@app.get("/health")
def health():
    return {"status": "ok"}
