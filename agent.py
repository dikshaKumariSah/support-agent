import os
from dotenv import load_dotenv
from google import genai
from google.genai import types
from sqlalchemy import create_engine, text

load_dotenv()
engine = create_engine(os.getenv("DATABASE_URL"))
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


def get_orders(customer_id: int) -> list[dict]:
    """Get all orders for a verified customer, with status, courier status and delay reason."""
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT id, product, status, courier_status, delay_reason FROM orders WHERE customer_id = :cid"),
            {"cid": customer_id},
        )
        return [dict(row._mapping) for row in rows]


RULES = """You are a customer support agent for an electronics store.
- Greet warmly and show empathy first.
- Explain courier and technical terms in simple words.
- Only use facts from your tools. Never invent order details. Don't add reassurances that aren't in the data.
- Never promise refunds, discounts or delivery dates.
- Do not offer a human or supervisor on your own.
- If the customer asks for a human, try to calm them and help. Only hand over if they still insist after you have tried twice.
- If the request is outside what you can do, say you will connect them to the right team."""

chat = client.chats.create(
    model="gemini-3.5-flash-lite",
    config=types.GenerateContentConfig(
        tools=[get_orders], system_instruction=RULES),
)

print("Type 'quit' to stop.")
while True:
    message = input("You: ")
    if message == "quit":
        break
    response = chat.send_message(message)
    print("Agent:", response.text)
