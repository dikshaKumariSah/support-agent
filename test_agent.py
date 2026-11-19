from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from google.genai import errors
from sqlalchemy import create_engine, text
import agent
from agent import Conversation
from main import app


@pytest.fixture
def conv():
    """A brand-new conversation for each test that asks for it."""
    return Conversation()


def talk(conv, messages):
    """Send customer messages to Dhriti one by one."""
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


def test_guard_blocks_charge_ticket_when_get_plans_failed(conv):
    # get_plans is called, but fails because the customer isn't verified
    assert conv.get_plans() == {"error": "Customer not verified"}
    assert "get_plans" in conv.tool_calls
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


@pytest.mark.parametrize("name, email, pincode, expected", [
    ("  ASHA kumari  rao", "asha@mail.com", "", True),               # middle name, capitals, extra spaces
    ("Asha Rao", "Asha@Mail.COM", "", True),                         # email capitals
    ("Asha", "asha@mail.com", "", "full_name_needed"),               # first name only
    ("Usha Rao", "asha@mail.com", "", "name_mismatch"),              # wrong first name
    ("Asha Sharma", "asha@mail.com", "", "surname_mismatch"),        # other surname, no pincode yet
    ("Asha Sharma", "asha@mail.com", "560001", True),                # other surname, right pincode
    ("Asha Sharma", "asha@mail.com", "110001", "pincode_mismatch"),  # other surname, wrong pincode
])
def test_verify_customer_name_rules(conv, name, email, pincode, expected):
    conv.customer_messages = f"{name}, 9800000001, {email} {pincode}"  # what the customer typed
    result = conv.verify_customer(name=name, phone="9800000001", email=email, pincode=pincode)
    if expected is True:
        assert result == {"verified": True}
        assert conv.verified_customer_id == 1
    else:
        assert result["reason"] == expected
        assert conv.verified_customer_id is None


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
    assert "Dhriti" in response.text


# ---------- Membership cancellation (local database only) ----------

def membership(customer_id):
    """Read a membership's status and cancel reason straight from the database."""
    with agent.engine.connect() as conn:
        return conn.execute(
            text("SELECT status, cancel_reason FROM memberships WHERE customer_id = :cid"),
            {"cid": customer_id},
        ).first()


@pytest.fixture
def restore_memberships():
    """After the test, put Asha's and Ravi's memberships back to Active, even if the test failed."""
    yield
    with agent.engine.begin() as conn:
        conn.execute(text(
            "UPDATE memberships SET status = 'Active', cancel_reason = NULL WHERE customer_id IN (1, 2)"
        ))


def test_cancel_needs_verification(conv):
    result = conv.cancel_membership(reason_category="not_using", reason="I don't use it")
    assert result["reason"] == "not_verified"
    assert membership(1).status == "Active"


def test_cancel_never_signed_up_is_not_cancelled(conv):
    conv.verified_customer_id = 1
    result = conv.cancel_membership(reason_category="never_signed_up", reason="I never signed up")
    assert result["reason"] == "possible_fraud"
    assert membership(1).status == "Active"


def show_options_and_reply(conv):
    """What happens in a real chat before a cancel: Dhriti shows the options, then the customer answers."""
    conv.get_membership_options()
    conv.message_count += 1  # the customer's reply, e.g. "Yes, cancel it"


def test_cancel_refused_before_options_shown(conv):
    conv.verified_customer_id = 1
    result = conv.cancel_membership(reason_category="not_using", reason="I don't use it")
    assert result["reason"] == "explain_first"
    assert membership(1).status == "Active"


def test_cancel_refused_in_same_turn_as_options(conv):
    # Chat 4's bug: options and cancel in the same turn, with no customer answer in between.
    conv.verified_customer_id = 1
    conv.get_membership_options()
    result = conv.cancel_membership(reason_category="other", reason="Too expensive")
    assert result["reason"] == "wait_for_answer"
    assert membership(1).status == "Active"


def test_cancel_membership_success(conv, restore_memberships):
    conv.verified_customer_id = 1
    show_options_and_reply(conv)
    result = conv.cancel_membership(reason_category="not_using", reason="I don't shop here anymore")
    assert result == {"cancelled": True, "tier": "Silver", "benefits_until": "2027-01-10"}
    row = membership(1)
    assert row.status == "Cancelled"
    assert row.cancel_reason == "I don't shop here anymore"


def test_cancel_twice_finds_no_active_membership(conv, restore_memberships):
    conv.verified_customer_id = 1
    show_options_and_reply(conv)
    conv.cancel_membership(reason_category="other", reason="Too expensive")
    result = conv.cancel_membership(reason_category="other", reason="Too expensive")
    assert result["reason"] == "no_active_membership"


def test_cancel_database_error(conv, monkeypatch):
    real_engine = agent.engine
    conv.verified_customer_id = 1
    show_options_and_reply(conv)  # uses the real database, before we break it
    # Point the agent at a database address where nothing is running, so the UPDATE really fails.
    # monkeypatch puts the real engine back automatically after the test.
    monkeypatch.setattr(agent, "engine", create_engine("postgresql+psycopg://nobody:nothing@127.0.0.1:1/none?connect_timeout=2"))
    result = conv.cancel_membership(reason_category="not_using", reason="I don't use it")
    assert result["reason"] == "database_error"
    with real_engine.connect() as conn:  # check with the real database: nothing changed
        status = conn.execute(text("SELECT status FROM memberships WHERE customer_id = 1")).scalar()
    assert status == "Active"


def test_gold_membership_offers_silver(conv):
    conv.verified_customer_id = 2
    result = conv.get_membership_options()
    assert result["tier"] == "Gold"
    assert result["cheaper_option"]["tier"] == "Silver"
    assert result["cheaper_option"]["price"] == "₹1,999 a year"


# ---------- Retry when Gemini is busy (no real Gemini calls) ----------

def gemini_error(code):
    return errors.APIError(code, {"error": {"code": code, "message": "test", "status": "TEST"}})


class FakeChat:
    """Stands in for the Gemini chat: raises the given errors first, then answers."""

    def __init__(self, failures, conv=None, run_tool=False):
        self.failures = list(failures)
        self.calls = 0
        self.conv = conv
        self.run_tool = run_tool

    def send_message(self, message):
        self.calls += 1
        if self.failures:
            if self.run_tool:  # pretend a tool ran before the error
                self.conv.tool_calls.append("create_ticket")
            raise self.failures.pop(0)
        return SimpleNamespace(text="Hello from Dhriti")


def test_send_retries_once_when_gemini_is_busy(conv, monkeypatch):
    monkeypatch.setattr(agent.time, "sleep", lambda seconds: None)  # don't really wait
    conv.chat = FakeChat([gemini_error(503)])
    assert conv.send("hi") == "Hello from Dhriti"
    assert conv.chat.calls == 2
    assert conv.message_count == 1  # the message is counted once, not per attempt


def test_send_does_not_retry_after_a_tool_ran(conv, monkeypatch):
    monkeypatch.setattr(agent.time, "sleep", lambda seconds: None)
    conv.chat = FakeChat([gemini_error(429)], conv=conv, run_tool=True)
    with pytest.raises(errors.APIError):
        conv.send("hi")
    assert conv.chat.calls == 1  # no retry: it could repeat the tool (e.g. a second ticket)
