import os
from dotenv import load_dotenv
from fastapi import FastAPI
from sqlalchemy import create_engine, text

load_dotenv()
engine = create_engine(os.getenv("DATABASE_URL"))
app = FastAPI()


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
