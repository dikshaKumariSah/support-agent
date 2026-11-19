import os
import json
from dotenv import load_dotenv
from google import genai
from google.genai import types
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

load_dotenv()
engine = create_engine(os.getenv("DATABASE_URL"))
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# ---------- SHARED TEXT (same for every conversation) ----------

COURIER_GUIDE = {
    "Picked up": "The courier has collected the parcel from our store.",
    "In transit": "The parcel is moving between courier hubs.",
    "Held at facility": "The parcel is waiting at the courier's local hub.",
    "Out for delivery": "The parcel is with a delivery person.",
    "Delivered": "The courier has marked the parcel as delivered.",
}

MEMBERSHIP_GUIDE = {
    "Silver": {
        "price": "₹1,999 a year",
        "benefits": ["Free delivery on all orders", "Member-only prices",
                     "A protection plan for devices bought from us"],
    },
    "Gold": {
        "price": "₹13,999 a year",
        "benefits": ["Everything in Silver", "Free home repair visits",
                     "Priority customer support", "Longer warranty on new purchases"],
    },
}

AFTER_CANCELLING = ("Benefits stay until the renewal date, then end, including plans that came with the membership. "
                    "Separately bought plans are not affected. No refunds are promised.")

CANCEL_REASONS = {"not_using", "confused", "never_signed_up", "other"}

RULES = """You are Dhriti, a virtual assistant for ElectroMart, an electronics store.

Follow this call flow in order:
1. Understand the concern. If it's unclear or details are missing, ask one short question at a time. Don't guess.
2. Say the concern back in one sentence and ask the customer to confirm it.
3. Once confirmed, show empathy and say you'll try your best and check what you can do for them.
4. Verify the customer's name, phone and email before looking up anything. If a detail doesn't match, politely ask again for that detail only. If verify_customer returns full_name_needed, ask for their full name. If it returns surname_mismatch, ask if the account could be under another surname, and ask for their pincode.
5. After verification, thank them by first name, then solve the concern using your tools.
6. Ask: "Is there anything else I can help you with?"
7. If no, close with: "Thank you for contacting ElectroMart customer care. You were speaking with Dhriti, ElectroMart's virtual assistant. Have a great day ahead, and take care!"

Always:
- Follow steps 1 to 4 of the call flow for every concern, including cancellations and fraud: repeat the concern, ask them to confirm it, show empathy, then verify. Never skip these steps, even if the customer gives their details early.
- Don't use the customer's name until verify_customer returns verified: true, even if they already typed it.
- Use the customer's first name naturally after verification, not in every sentence.
- Keep a warm tone, even in short answers.
- Always say amounts in rupees, like ₹1,999. Never use $ or any other currency.
- Only use facts from your tools. Never invent details or add reassurances that aren't in the data.
- For courier statuses, use only the meaning from explain_courier_status.
- Never promise refunds, discounts or delivery dates.
- Do not offer a human on your own. If the customer asks for one, try to help twice; hand over only if they still insist.
- If the request is outside what you can do, call create_ticket for the right team. Only tell the customer it's passed on after the ticket is created. Tell them the team has the details, so they won't need to explain again.

- Unknown charge: Unknown charges are in scope. Never create a ticket for them before calling get_plans. Ask the amount and date first. If the customer only remembers roughly when (like "last year"), don't insist on an exact date. Call get_plans and compare with the membership last_payment_amount, plan price and purchase amount, and their payment, start or order dates. Customers often remember the price before tax, not the exact charge. Check everything in that period and find the closest amount near that date. Then ask only about the amount and date, like: "I found a charge of ₹1,999 on 10 January 2026. Was it this amount?" Don't say what the charge is for in this question. Explain what it was for only after the customer says yes. The membership and the plans are separate: a membership payment is the membership fee, so call it the membership (for example "your Silver membership"), never a protection plan. A plan with source "Membership" is included with the membership and has no charge of its own. If nothing matches, ask where they saw it. If they saw it only in an email or text message, say: it may be a scam, so don't click any links or pay anything. Forward the email to abuse@electromart.example. Check your card statement too. If the charge is there and you didn't make it, contact your bank and dispute it. Card statement and unauthorised: tell them to dispute it with their bank.

- Membership cancellation: Membership cancellations are in scope. While understanding the concern (step 1), ask why they want to cancel. Then repeat the concern, confirm, show empathy and verify. Then follow the reason:
  - Not using it: call get_membership_options and explain the benefits they are paying for, so they know what they would lose. If they have Gold, suggest moving to Silver instead of cancelling, with its price. If they want to move to Silver, create a ticket for the Membership team to change the tier.
  - Confused about the membership: call get_membership_options and explain the benefits, and what they keep after cancelling and until when (the renewal date).
  - Never signed up for it: it may be fraud. Don't cancel. Create a ticket for the Fraud team, with the customer's exact words as the problem (for example "I never signed up for this membership").
  - Before cancelling, ask exactly one yes/no question: "Just to confirm, do you want to cancel your <tier> membership?" Call cancel_membership only after a clear yes to that question, with the reason in their own words.
  - If an answer could mean either option (for example "yes" to a question with two choices), don't guess: ask which one they mean.
  - If cancel_membership returns database_error, tell them it couldn't be done right now and create a ticket for the Backend team.
  Only use benefits and prices from get_membership_options. Never promise refunds.
"""

GREETING = "Thank you for contacting ElectroMart customer care. My name is Dhriti, your virtual assistant. How can I help you today?"


# ---------- ONE CONVERSATION ----------

class Conversation:
    """Everything that belongs to one customer's chat: who is verified, what they typed, which tools ran, and the Gemini chat."""

    def __init__(self):
        self.verified_customer_id = None
        self.customer_messages = ""
        self.tool_calls = []
        self.plans_checked = False  # True only after get_plans really returned the customer's data
        self.message_count = 0  # how many messages the customer has sent
        self.options_shown_at = None  # message_count when get_membership_options last returned data
        self.chat = client.chats.create(
            model="gemini-3.5-flash-lite",
            config=types.GenerateContentConfig(
                tools=[self.verify_customer, self.get_orders, self.get_plans,
                       self.explain_courier_status, self.create_ticket,
                       self.get_membership_options, self.cancel_membership],
                system_instruction=RULES +
                "\n- You have already greeted the customer. Don't greet again.",
            ),
        )

    def send(self, message: str) -> str:
        """Pass one customer message to Dhriti and return her reply."""
        self.customer_messages += " " + message
        self.message_count += 1
        return self.chat.send_message(message).text

    # ----- tools Gemini can call -----

    def verify_customer(self, name: str, phone: str, email: str, pincode: str = "") -> dict:
        """Verify the customer with their full name, phone and email. Only call this AFTER the customer has confirmed their concern and has typed these details. Never call it with made-up details.
        pincode: only if the customer typed it. Otherwise leave it empty."""
        self.tool_calls.append("verify_customer")
        print(f"[TOOL] verify_customer called with: {name}, {phone}, {email}, {pincode}")
        typed = self.customer_messages.lower()
        if phone not in typed or email.lower() not in typed or (pincode and pincode not in typed):
            return {"verified": False, "reason": "details_not_given", "note": "Ask the customer for their details. Never make them up."}
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT id, name, phone, pincode FROM customers WHERE LOWER(email) = LOWER(:email)"),
                {"email": email},
            ).first()
        if row is None:
            return {"verified": False, "reason": "email_not_found"}
        if row.phone != phone:
            return {"verified": False, "reason": "phone_mismatch"}

        # Compare names word by word, ignoring capitals and extra spaces.
        given = name.lower().split()
        profile = row.name.lower().split()
        if len(given) < 2:
            return {"verified": False, "reason": "full_name_needed"}
        if given[0] != profile[0]:
            return {"verified": False, "reason": "name_mismatch"}
        if not all(part in given for part in profile):
            # First name matches but the surname doesn't: maybe a maiden or married name.
            if not pincode:
                return {"verified": False, "reason": "surname_mismatch",
                        "note": "Ask if the account could be under another surname, and ask for their pincode."}
            if pincode != row.pincode:
                return {"verified": False, "reason": "pincode_mismatch"}
        self.verified_customer_id = row.id
        return {"verified": True}

    def get_orders(self) -> list[dict]:
        """Get the verified customer's orders, with status, courier status and delay reason."""
        self.tool_calls.append("get_orders")
        if self.verified_customer_id is None:
            return [{"error": "Customer not verified. Ask for name, phone and email first."}]
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT id, product, status, courier_status, delay_reason FROM orders WHERE customer_id = :cid"),
                {"cid": self.verified_customer_id},
            )
            return [dict(row._mapping) for row in rows]

    def get_plans(self) -> dict:
        """Get the verified customer's membership, plans and purchases with amounts and dates.
        Use for unknown charge questions. Only call after verification."""
        self.tool_calls.append("get_plans")
        print("[TOOL] get_plans called, verified id:", self.verified_customer_id)
        if self.verified_customer_id is None:
            return {"error": "Customer not verified"}
        with engine.connect() as conn:
            membership = conn.execute(
                text("SELECT tier, status, last_payment_date, last_payment_amount, renewal_date "
                     "FROM memberships WHERE customer_id = :cid"),
                {"cid": self.verified_customer_id}).mappings().all()
            plans = conn.execute(
                text("SELECT type, source, start_date, end_date, price "
                     "FROM plans WHERE customer_id = :cid"),
                {"cid": self.verified_customer_id}).mappings().all()
            purchases = conn.execute(
                text("SELECT product, order_date, amount "
                     "FROM orders WHERE customer_id = :cid"),
                {"cid": self.verified_customer_id}).mappings().all()
        print("[TOOL] get_plans found:", membership, plans, purchases)
        result = {"membership": [dict(m) for m in membership],
                  "plans": [dict(p) for p in plans],
                  "purchases": [dict(o) for o in purchases]}
        self.plans_checked = True
        return json.loads(json.dumps(result, default=str))

    def explain_courier_status(self, status: str) -> str:
        """Get the approved plain-language meaning of a courier status. Always use this instead of explaining it yourself."""
        self.tool_calls.append("explain_courier_status")
        return COURIER_GUIDE.get(status, "No approved explanation. Do not guess; just repeat the status.")

    def get_membership_options(self) -> dict:
        """Get the verified customer's membership: tier, price, benefits, renewal date, what they keep after cancelling, and a cheaper tier they could move to. Use it to explain the membership before any cancellation."""
        self.tool_calls.append("get_membership_options")
        if self.verified_customer_id is None:
            return {"error": "Customer not verified"}
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT tier, status, renewal_date FROM memberships WHERE customer_id = :cid"),
                {"cid": self.verified_customer_id},
            ).first()
        if row is None:
            return {"membership": None}
        guide = MEMBERSHIP_GUIDE.get(row.tier, {})
        result = {
            "tier": row.tier,
            "status": row.status,
            "renewal_date": str(row.renewal_date),
            "price": guide.get("price"),
            "benefits": guide.get("benefits", []),
            "after_cancelling": AFTER_CANCELLING,
        }
        if row.tier == "Gold":
            result["cheaper_option"] = {"tier": "Silver", **MEMBERSHIP_GUIDE["Silver"]}
        self.options_shown_at = self.message_count
        return result

    def cancel_membership(self, reason_category: str, reason: str) -> dict:
        """Cancel the verified customer's active membership. Only call this after you asked the reason, explained the benefits from get_membership_options, asked "Just to confirm, do you want to cancel your <tier> membership?", and the customer clearly said yes.
        reason_category: "not_using", "confused", "never_signed_up" or "other".
        reason: the customer's reason in their own words."""
        self.tool_calls.append("cancel_membership")
        if self.verified_customer_id is None:
            return {"cancelled": False, "reason": "not_verified", "note": "Verify the customer first."}
        if reason_category not in CANCEL_REASONS:
            return {"cancelled": False, "reason": "unknown_category"}
        if reason_category == "never_signed_up":
            return {"cancelled": False, "reason": "possible_fraud",
                    "note": "Don't cancel. Create a ticket for the Fraud team."}
        if not reason.strip():
            return {"cancelled": False, "reason": "reason_needed", "note": "Ask the customer why they want to cancel."}
        # The customer must have seen the benefits AND answered after that.
        if self.options_shown_at is None:
            return {"cancelled": False, "reason": "explain_first",
                    "note": "Call get_membership_options and explain the benefits first."}
        if self.message_count <= self.options_shown_at:
            return {"cancelled": False, "reason": "wait_for_answer",
                    "note": "Explain the benefits, ask the confirmation question, and wait for the customer's answer."}
        try:
            with engine.begin() as conn:
                row = conn.execute(
                    text("UPDATE memberships SET status = 'Cancelled', cancel_reason = :reason "
                         "WHERE customer_id = :cid AND status = 'Active' RETURNING tier, renewal_date"),
                    {"reason": reason, "cid": self.verified_customer_id},
                ).first()
        except SQLAlchemyError as error:
            print(f"[TOOL] cancel_membership database error: {type(error).__name__}")
            return {"cancelled": False, "reason": "database_error",
                    "note": "Create a ticket for the Backend team."}
        if row is None:
            return {"cancelled": False, "reason": "no_active_membership"}
        print(f"[TOOL] cancel_membership cancelled {row.tier} for customer {self.verified_customer_id}")
        return {"cancelled": True, "tier": row.tier, "benefits_until": str(row.renewal_date)}

    def create_ticket(self, concern: str, problem: str, tried_for_this_concern: str, reason: str, customer_mood: str, team: str) -> dict:
        """Hand the conversation to a human team.
        Call this when the request is outside what you can do, or the customer still insists on a human after you tried twice.
        Never call this for an unknown charge if get_plans shows a matching amount. Explain that charge to the customer instead.

        Rules for the brief:
        - concern: "unknown_charge" if the customer asks about a charge they don't recognise. Otherwise "other".
        - problem: use the customer's own words. Don't add details they didn't say.
        - tried_for_this_concern: only what was tried for THIS concern. If nothing, write "Nothing yet".
        - customer_mood: only if the customer clearly showed it. Otherwise write "Calm"."""
        if concern == "unknown_charge" and not self.plans_checked:
            self.tool_calls.append("create_ticket_blocked")
            return {"created": False, "error": "Verify the customer, get their data with get_plans and compare the charge before creating a ticket."}
        self.tool_calls.append("create_ticket")
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
                {"cid": self.verified_customer_id, "brief": json.dumps(brief)},
            ).first()
        return {"created": True, "ticket_id": row.id}


# ---------- COMMAND-LINE CHAT ----------

if __name__ == "__main__":
    conversation = Conversation()
    print("Agent:", GREETING)
    while True:
        reply = conversation.send(input("You: "))
        print("Agent:", reply)
        if "Have a great day ahead" in reply:
            break
