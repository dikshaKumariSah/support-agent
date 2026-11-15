import os
import json
from dotenv import load_dotenv
from google import genai
from google.genai import types
from sqlalchemy import create_engine, text

load_dotenv()
engine = create_engine(os.getenv("DATABASE_URL"))
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# ---------- TOOLS ----------

verified_customer_id = None
tool_calls = []
customer_messages = ""


def verify_customer(name: str, phone: str, email: str) -> dict:
    """Verify the customer. Only call this AFTER the customer has confirmed their concern and has typed their name, phone and email. Never call it with made-up details."""
    tool_calls.append("verify_customer")
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
    tool_calls.append("get_orders")
    if verified_customer_id is None:
        return [{"error": "Customer not verified. Ask for name, phone and email first."}]
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT id, product, status, courier_status, delay_reason FROM orders WHERE customer_id = :cid"),
            {"cid": verified_customer_id},
        )
        return [dict(row._mapping) for row in rows]


def get_plans() -> dict:
    """Get the verified customer's membership, plans and purchases with amounts and dates.
    Use for unknown charge questions. Only call after verification."""
    tool_calls.append("get_plans")
    print("[TOOL] get_plans called, verified id:", verified_customer_id)
    if verified_customer_id is None:
        return {"error": "Customer not verified"}
    with engine.connect() as conn:
        membership = conn.execute(
            text("SELECT tier, status, last_payment_date, last_payment_amount, renewal_date "
                 "FROM memberships WHERE customer_id = :cid"),
            {"cid": verified_customer_id}).mappings().all()
        plans = conn.execute(
            text("SELECT type, source, start_date, end_date, price "
                 "FROM plans WHERE customer_id = :cid"),
            {"cid": verified_customer_id}).mappings().all()
        purchases = conn.execute(
            text("SELECT product, order_date, amount "
                 "FROM orders WHERE customer_id = :cid"),
            {"cid": verified_customer_id}).mappings().all()
    print("[TOOL] get_plans found:", membership, plans, purchases)
    result = {"membership": [dict(m) for m in membership],
              "plans": [dict(p) for p in plans],
              "purchases": [dict(o) for o in purchases]}
    return json.loads(json.dumps(result, default=str))


COURIER_GUIDE = {
    "Picked up": "The courier has collected the parcel from our store.",
    "In transit": "The parcel is moving between courier hubs.",
    "Held at facility": "The parcel is waiting at the courier's local hub.",
    "Out for delivery": "The parcel is with a delivery person.",
    "Delivered": "The courier has marked the parcel as delivered.",
}


def explain_courier_status(status: str) -> str:
    """Get the approved plain-language meaning of a courier status. Always use this instead of explaining it yourself."""
    tool_calls.append("explain_courier_status")
    return COURIER_GUIDE.get(status, "No approved explanation. Do not guess; just repeat the status.")


def create_ticket(concern: str, problem: str, tried_for_this_concern: str, reason: str, customer_mood: str, team: str) -> dict:
    """Hand the conversation to a human team.
    Call this when the request is outside what you can do, or the customer still insists on a human after you tried twice.
    Never call this for an unknown charge if get_plans shows a matching amount. Explain that charge to the customer instead.

    Rules for the brief:
    - concern: "unknown_charge" if the customer asks about a charge they don't recognise. Otherwise "other".
    - problem: use the customer's own words. Don't add details they didn't say.
    - tried_for_this_concern: only what was tried for THIS concern. If nothing, write "Nothing yet".
    - customer_mood: only if the customer clearly showed it. Otherwise write "Calm"."""
    if concern == "unknown_charge" and "get_plans" not in tool_calls:
        tool_calls.append("create_ticket_blocked")
        return {"created": False, "error": "Call get_plans first and compare the charge before creating a ticket."}
    tool_calls.append("create_ticket")
    print(f"[TOOL] create_ticket called for team: {team}")
    brief = {
        "problem": problem,
        "tried": tried_for_this_concern,
        "reason": reason,
        "mood": customer_mood,
        "team": team,
    }
    with engine.begin() as conn:
        row = conn.execute(
            text("INSERT INTO tickets (customer_id, brief) VALUES (:cid, CAST(:brief AS JSONB)) RETURNING id"),
            {"cid": verified_customer_id, "brief": json.dumps(brief)},
        ).first()
    return {"created": True, "ticket_id": row.id}

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
- If the request is outside what you can do, call create_ticket for the right team. Only tell the customer it's passed on after the ticket is created. Tell them the team has the details, so they won't need to explain again.

- Unknown charge: Unknown charges are in scope. Never create a ticket for them before calling get_plans. Ask the amount and date first. If the customer only remembers roughly when (like "last year"), don't insist on an exact date. Call get_plans and compare with the membership last_payment_amount, plan price and purchase amount, and their payment, start or order dates. Customers often remember the price before tax, not the exact charge. Check everything in that period, find the closest amount near that date, then ask: "Was it this amount?" Only explain the charge after the customer confirms. If nothing matches, ask where they saw it. Email or text only: it may be a scam, so tell them not to click links or pay. Card statement and unauthorised: tell them to dispute it with their bank.
"""

# ---------- CHAT ----------

GREETING = "Thank you for contacting ElectroMart customer care. My name is Riya, your virtual assistant. How can I help you today?"

chat = client.chats.create(
    model="gemini-3.5-flash-lite",
    config=types.GenerateContentConfig(
        tools=[verify_customer, get_orders, get_plans,
               explain_courier_status, create_ticket],
        system_instruction=RULES +
        "\n- You have already greeted the customer. Don't greet again.",
    ),
)
if __name__ == "__main__":
    print("Agent:", GREETING)
    while True:
        message = input("You: ")
        customer_messages += " " + message
        response = chat.send_message(message)
        print("Agent:", response.text)
        if "Have a great day ahead" in response.text:
            break
