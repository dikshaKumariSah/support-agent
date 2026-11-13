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


response = client.models.generate_content(
    model="gemini-3.5-flash-lite",
    contents="I am verified customer 1. Where is my laptop and why is it late?",
    config=types.GenerateContentConfig(tools=[get_orders]),
)
print(response.text)