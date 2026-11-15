import pytest
from fastapi.testclient import TestClient
from agent import Conversation
from main import app


@pytest.fixture
def conv():
    """A brand-new conversation for each test that asks for it."""
    return Conversation()


def talk(conv, messages):
    """Send customer messages to Riya one by one."""
    for message in messages:
        reply = conv.send(message)
        print("CUSTOMER:", message)
        print("AGENT:", reply)


# ---------- Tests that call Gemini ----------

def test_charge_matches_membership(conv):
    talk(conv, [
        "I see an unknown charge on my card",
        "1999 on 10 January 2026",
        "Asha Rao, 9800000001, asha@mail.com",
    ])
    assert "get_plans" in conv.tool_calls
    assert "create_ticket" not in conv.tool_calls


def test_charge_matches_nothing(conv):
    talk(conv, [
        "I see an unknown charge on my card",
        "4321 on 3 March 2026",
        "Asha Rao, 9800000001, asha@mail.com",
    ])
    assert "get_plans" in conv.tool_calls
    assert "create_ticket" not in conv.tool_calls


# ---------- Tests without Gemini ----------

def test_guard_blocks_charge_ticket_before_get_plans(conv):
    result = conv.create_ticket(
        concern="unknown_charge", problem="unknown charge", tried_for_this_concern="Nothing yet",
        reason="test", customer_mood="Calm", team="Billing",
    )
    assert result["created"] is False
    assert "create_ticket" not in conv.tool_calls


def test_get_plans_needs_verification(conv):
    assert conv.get_plans() == {"error": "Customer not verified"}


def test_get_plans_returns_purchases(conv):
    conv.verified_customer_id = 1
    result = conv.get_plans()
    laptop = {"product": "Laptop", "order_date": "2026-11-05", "amount": "54999.00"}
    assert laptop in result["purchases"]


def test_conversations_do_not_share_verification():
    asha = Conversation()
    stranger = Conversation()
    asha.verified_customer_id = 1
    assert stranger.verified_customer_id is None
    assert stranger.get_plans() == {"error": "Customer not verified"}


def test_chat_unknown_conversation_returns_404():
    client = TestClient(app)
    response = client.post("/chat", json={"message": "hi", "conversation_id": "does-not-exist"})
    assert response.status_code == 404


def test_home_serves_chat_page():
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Riya" in response.text
