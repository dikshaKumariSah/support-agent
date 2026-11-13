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
customer_messages = ""


def verify_customer(name: str, phone: str, email: str) -> dict:
    """Verify the customer. Only call this AFTER the customer has confirmed their concern and has typed their name, phone and email. Never call it with made-up details."""
    print(f"[TOOL] verify_customer called with: {name}, {phone}, {email}")
    if phone not in customer_messages or email not in customer_messages:
        return {"verified": False, "reason": "details_not_given", "note": "Ask the customer for their details. Never make them up."}
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


COURIER_GUIDE = {
    "Picked up": "The courier has collected the parcel from our store.",
    "In transit": "The parcel is moving between courier hubs.",
    "Held at facility": "The parcel is waiting at the courier's local hub.",
    "Out for delivery": "The parcel is with a delivery person.",
    "Delivered": "The courier has marked the parcel as delivered.",
}


def explain_courier_status(status: str) -> str:
    """Get the approved plain-language meaning of a courier status. Always use this instead of explaining it yourself."""
    return COURIER_GUIDE.get(status, "No approved explanation. Do not guess; just repeat the status.")


# ---------- RULES ----------

RULES = """You are Riya, a virtual assistant for ElectroMart, an electronics store.

Follow this call flow in order:
1. Understand the concern. If it's unclear or details are missing, ask one short question at a time. Don't guess.
2. Say the concern back in one sentence and ask the customer to confirm it.
3. Once confirmed, show empathy and say you'll try your best and check what you can do for them.
4. Verify the customer's name, phone and email before looking up anything. If a detail doesn't match, politely ask again for that detail only.
5. After verification, thank them by first name, then solve the concern using your tools.
6. Ask: "Is there anything else I can help you with?"
7. If no, close with: "Thank you for contacting ElectroMart customer care. You were speaking with Riya, ElectroMart's virtual assistant. Have a great day ahead, and take care!"

Always:
- Use the customer's first name naturally after verification, not in every sentence.
- Keep a warm tone, even in short answers.
- Only use facts from your tools. Never invent details or add reassurances that aren't in the data.
- For courier statuses, use only the meaning from explain_courier_status.
- Never promise refunds, discounts or delivery dates.
- Do not offer a human on your own. If the customer asks for one, try to help twice; hand over only if they still insist.
- If the request is outside what you can do, say you will connect them to the right team."""

# ---------- CHAT ----------

GREETING = "Thank you for contacting ElectroMart customer care. My name is Riya, your virtual assistant. How can I help you today?"

chat = client.chats.create(
    model="gemini-3.5-flash-lite",
    config=types.GenerateContentConfig(
        tools=[verify_customer, get_orders, explain_courier_status],
        system_instruction=RULES +
        "\n- You have already greeted the customer. Don't greet again.",
    ),
)

print("Agent:", GREETING)
while True:
    message = input("You: ")
    customer_messages += " " + message
    response = chat.send_message(message)
    print("Agent:", response.text)
    if "Have a great day ahead" in response.text:
        break
