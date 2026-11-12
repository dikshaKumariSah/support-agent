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
