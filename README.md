# Riya – ElectroMart Support Agent

A customer-support AI agent for **ElectroMart**, a made-up electronics store.
Riya chats with customers, verifies who they are, looks up their data in PostgreSQL through tools, and hands over to a human team only when she can't help.

Built with **Python, FastAPI, PostgreSQL and Google Gemini (function calling)**.

> ElectroMart, its customers and its policies are fictional. No real company or customer data is used.

---

## What Riya can do

- **Follow a support call flow**: understand the concern → confirm it → show empathy → verify the customer → solve it with tools → "anything else?" → close.
- **Verify customers** by name, phone and email before showing any account data.
- **Explain order status** using approved, plain-language courier explanations.
- **Investigate unknown charges**: compare the amount and date with the customer's membership, plans and purchases, confirm the closest match ("Was it this amount?"), and only then explain it. If nothing matches, ask where the charge was seen and give scam or bank-dispute advice.
- **Create handover tickets** with a short brief, so the customer doesn't have to repeat themselves to a human.

## How it works

```
Client ──POST /chat──▶ FastAPI (main.py)
                          │  finds or creates a Conversation by conversation_id
                          ▼
                    Conversation (agent.py)
                          │  sends the message to Gemini with RULES + tools
                          ▼
                       Gemini ──calls tools──▶ verify_customer / get_orders / get_plans /
                                               explain_courier_status / create_ticket
                                                          │
                                                          ▼
                                                     PostgreSQL
```

Gemini decides **which** tool to call. The tools themselves are normal Python methods that run SQL and return data.

## Design decisions

- **One `Conversation` object per chat.** It holds the verified customer, the customer's messages, the tool calls and its own Gemini chat. The tools are methods, so a tool can only see its own conversation's data. Two customers chatting at the same time never share state.
- **Random conversation IDs (`uuid4`).** Nobody can guess another customer's conversation.
- **Rules enforced in code, not only in the prompt.**
  - Every data tool checks `verified_customer_id` first and refuses if the customer isn't verified.
  - `verify_customer` checks that the phone and email were really typed by the customer, so the model can't make them up.
  - `create_ticket` refuses an `unknown_charge` ticket until `get_plans` has been called.
- **SQL placeholders (`:cid`)** everywhere, never values pasted into SQL text, to prevent SQL injection.
- **Dates and Decimals are converted to text** (`json.dumps(..., default=str)`) before being sent to Gemini.
- **Tests check behaviour, not wording.** The model's wording changes on every run, so tests check which tools were called.

## Tech stack

| Part | Tool |
|---|---|
| Language | Python 3.14 |
| API | FastAPI + Uvicorn |
| Database | PostgreSQL, SQLAlchemy, psycopg 3 |
| AI model | Google Gemini `gemini-3.5-flash-lite` (via `google-genai`) |
| Tests | pytest, FastAPI `TestClient` |

## Project structure

```
agent.py         Riya: RULES, Conversation class and its tools, command-line chat
main.py          FastAPI app: /, /health, /customers, /customers/{id}/orders, /verify, /chat
static/index.html  Chat page (plain HTML + JavaScript)
schema.sql       Database tables
test_agent.py    pytest tests
requirements.txt Python packages
```

## Setup

1. **Create a virtual environment and install packages**
   ```bash
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Create the database and tables**
   ```bash
   createdb support_agent
   psql -d support_agent -f schema.sql
   ```

3. **Create a `.env` file** in the project folder (it is git-ignored):
   ```
   DATABASE_URL=postgresql+psycopg://<user>:<password>@localhost:5432/support_agent
   GEMINI_API_KEY=<your Gemini API key>
   ```
   A free-tier key from Google AI Studio is enough.

4. **Add sample data.** The tests expect a sample customer, Asha Rao (customer id 1), with a Plus membership paid on 10 January 2026 (1999.00) and a Laptop order (54999.00).

## Run

**API server**
```bash
uvicorn main:app --reload
```
Chat page: http://localhost:8000/
Interactive API docs: http://localhost:8000/docs

**Command-line chat**
```bash
python agent.py
```

## API

| Method | Path | What it does |
|---|---|---|
| GET | `/` | Chat page |
| GET | `/health` | Health check |
| GET | `/customers` | List customers |
| GET | `/customers/{customer_id}/orders` | A customer's orders |
| GET | `/verify` | Check name + phone + email (or pincode) |
| POST | `/chat` | Talk to Riya |

**`POST /chat`**

Start a conversation (no `conversation_id`):
```json
{ "message": "I see an unknown charge on my card" }
```
Response:
```json
{ "conversation_id": "00c0e0f9-084b-4e4b-8ddb-d0d11ee3175b", "reply": "Could you please tell me the amount and date of the charge?" }
```
Send the same `conversation_id` with every next message. An unknown ID returns **404**. A missing `message` returns **422**.

## Tests

```bash
pytest -v
```

8 tests:

| Test | Calls Gemini? |
|---|---|
| Charge of 1999 matches the membership; no ticket | Yes |
| Charge of 4321 matches nothing; no ticket | Yes |
| Guard blocks an unknown-charge ticket before `get_plans` | No |
| `get_plans` refuses an unverified customer | No |
| `get_plans` returns purchases | No |
| Two conversations don't share verification | No |
| `/chat` with an unknown ID returns 404 | No |
| `GET /` serves the chat page | No |

The two Gemini tests use real API calls, so their results can vary from run to run.

## Known limitations

- Conversations are kept in memory: they are lost when the server restarts, and old ones are never cleaned up.
- There is no seed script for sample data yet.

## Roadmap

- [x] Unknown-charge matching against purchases
- [x] pytest tests
- [x] `POST /chat` with per-conversation state
- [x] README
- [x] Simple chat page
- [ ] Docker and deployment with a live link
