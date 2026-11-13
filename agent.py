import os
from dotenv import load_dotenv
from google import genai
from google.genai import types
from sqlalchemy import create_engine, text

load_dotenv()
engine = create_engine(os.getenv("DATABASE_URL"))
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# ---------- TOOLS ----------

verified_customer_id = None


def verify_customer(name: str, phone: str, email: str) -> dict:
    """Check the customer's name, phone and email. Must be done before any account lookup."""
    global verified_customer_id
    with engine.connect() as conn:
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
    verified_customer_id = row.id
    return {"verified": True}


def get_orders() -> list[dict]:
    """Get the verified customer's orders, with status, courier status and delay reason."""
    if verified_customer_id is None:
        return [{"error": "Customer not verified. Ask for name, phone and email first."}]
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT id, product, status, courier_status, delay_reason FROM orders WHERE customer_id = :cid"),
            {"cid": verified_customer_id},
        )
        return [dict(row._mapping) for row in rows]


# ---------- RULES ----------

RULES = """You are a customer support agent for an electronics store.
- Greet warmly and show empathy first.
- Explain courier and technical terms in simple words.
- Only use facts from your tools. Never invent order details. Don't add reassurances that aren't in the data.
- Never promise refunds, discounts or delivery dates.
- Do not offer a human or supervisor on your own.
- If the customer asks for a human, try to calm them and help. Only hand over if they still insist after you have tried twice.
- If the request is outside what you can do, say you will connect them to the right team.
- Always verify the customer's name, phone and email before looking up anything.
- If verification fails, politely ask again for the detail that didn't match."""

# ---------- CHAT ----------

chat = client.chats.create(
    model="gemini-3.5-flash-lite",
    config=types.GenerateContentConfig(
        tools=[verify_customer, get_orders], system_instruction=RULES),
)

print("Type 'quit' to stop.")
while True:
    message = input("You: ")
    if message == "quit":
        break
    response = chat.send_message(message)
    print("Agent:", response.text)
