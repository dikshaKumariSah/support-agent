import os
import uuid
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, text
from agent import Conversation

load_dotenv()
engine = create_engine(os.getenv("DATABASE_URL"))
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


@app.get("/customers")
def get_customers():
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT id, name, email FROM customers"))
        return [dict(row._mapping) for row in rows]


@app.get("/customers/{customer_id}/orders")
def get_orders(customer_id: int):
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, product, status, delay_reason FROM orders WHERE customer_id = :cid"),
            {"cid": customer_id},
        )
        return [dict(row._mapping) for row in rows]

@app.get("/verify")
def verify(name: str, phone: str, email: str | None = None, pincode: str | None = None):
    with engine.connect() as conn:
        if email:
            row = conn.execute(
                text("SELECT id, name, phone FROM customers WHERE email = :email"),
                {"email": email},
            ).first()
            if row is None:
                return {"verified": False, "reason": "email_not_found"}
            if row.phone != phone:
                return {"verified": False, "reason": "phone_mismatch"}
            if row.name != name:
                return {"verified": False, "reason": "name_mismatch"}
            return {"verified": True, "customer_id": row.id}

        if pincode:
            row = conn.execute(
                text("SELECT id FROM customers WHERE name = :name AND phone = :phone AND pincode = :pincode"),
                {"name": name, "phone": phone, "pincode": pincode},
            ).first()
            if row is None:
                return {"verified": False, "reason": "pincode_mismatch"}
            return {"verified": True, "customer_id": row.id}

    return {"verified": False, "reason": "need_email_or_pincode"}
