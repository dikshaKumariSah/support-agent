import pytest
import agent


@pytest.fixture(autouse=True)
def fresh_agent():
    """Give every test a clean start: no old tool calls, messages, login or chat history."""
    agent.tool_calls.clear()
    agent.customer_messages = ""
    agent.verified_customer_id = None
    agent.chat = agent.new_chat()


def talk(messages):
    """Send customer messages to Riya one by one, like test_charge.py did."""
    for message in messages:
        agent.customer_messages += " " + message
        reply = agent.chat.send_message(message)
        print("CUSTOMER:", message)
        print("AGENT:", reply.text)


# ---------- Tests that call Gemini ----------

def test_charge_matches_membership():
    talk([
        "I see an unknown charge on my card",
        "1999 on 10 January 2026",
        "Asha Rao, 9800000001, asha@mail.com",
    ])
    assert "get_plans" in agent.tool_calls
    assert "create_ticket" not in agent.tool_calls


def test_charge_matches_nothing():
    talk([
        "I see an unknown charge on my card",
        "4321 on 3 March 2026",
        "Asha Rao, 9800000001, asha@mail.com",
    ])
    assert "get_plans" in agent.tool_calls
    assert "create_ticket" not in agent.tool_calls


# ---------- Tests without Gemini ----------

def test_guard_blocks_charge_ticket_before_get_plans():
    result = agent.create_ticket(
        concern="unknown_charge", problem="unknown charge", tried_for_this_concern="Nothing yet",
        reason="test", customer_mood="Calm", team="Billing",
    )
    assert result["created"] is False
    assert "create_ticket" not in agent.tool_calls


def test_get_plans_needs_verification():
    assert agent.get_plans() == {"error": "Customer not verified"}


def test_get_plans_returns_purchases():
    agent.verified_customer_id = 1
    result = agent.get_plans()
    laptop = {"product": "Laptop", "order_date": "2026-11-05", "amount": "54999.00"}
    assert laptop in result["purchases"]
