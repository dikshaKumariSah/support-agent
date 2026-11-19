# Dhriti – ElectroMart Support Agent

A customer-support AI agent for **ElectroMart**, a made-up electronics store.
Dhriti chats with customers, verifies who they are, looks up their data in PostgreSQL through tools, and hands over to a human team only when she can't help.

Built with **Python, FastAPI, PostgreSQL and Google Gemini (function calling)**.

**Live demo:** https://support-agent-zhok.onrender.com/
It runs on Render's free plan, which sleeps after 15 idle minutes, so the first visit can take up to a minute to load.

> ElectroMart, its customers and its policies are fictional. No real company or customer data is used.

---

## What Dhriti can do

- **Follow a support call flow**: understand the concern → confirm it → show empathy → verify the customer → solve it with tools → "anything else?" → close.
- **Verify customers** by name, phone and email before showing any account data.
- **Explain order status** using approved, plain-language courier explanations.
- **Investigate unknown charges**: compare the amount and date with the customer's membership, plans and purchases, confirm the closest match ("Was it this amount?"), and only then explain it. If nothing matches, ask where the charge was seen and give scam or bank-dispute advice.
- **Handle membership cancellations** (Silver ₹1,999/yr, Gold ₹13,999/yr) like a call centre: ask the reason first, explain the benefits the customer would lose, suggest moving from Gold to Silver instead of cancelling, and explain what they keep after cancelling. A "never signed up" case is treated as possible fraud and handed to a human instead of being cancelled.
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
                                               explain_courier_status / create_ticket /
                                               get_membership_options / cancel_membership
                                                          │
                                                          ▼
                                                     PostgreSQL
```

Gemini decides **which** tool to call. The tools themselves are normal Python methods that run SQL and return data.

## Design decisions

- **One `Conversation` object per chat.** It holds the verified customer, the customer's messages, the tool calls and its own Gemini chat. The tools are methods, so a tool can only see its own conversation's data. Two customers chatting at the same time never share state.
- **Random conversation IDs (`uuid4`).** Nobody can guess another customer's conversation.
- **No public data endpoints.** Customer data is only reachable through Dhriti's tools, after verification.
- **Rules enforced in code, not only in the prompt.**
  - Every data tool checks `verified_customer_id` first and refuses if the customer isn't verified.
  - `verify_customer` checks that the phone and email were really typed by the customer, so the model can't make them up.
  - `create_ticket` refuses an `unknown_charge` ticket until `get_plans` has actually returned the customer's data (a failed call doesn't count).
  - `cancel_membership` only works for a verified customer with a reason, never cancels a "never signed up" case, and reports database errors so a ticket can be created.
  - `cancel_membership` also refuses until `get_membership_options` has shown the benefits **and** the customer has sent a message after that, so Dhriti can't show the benefits and cancel in the same turn. Before cancelling she asks one clear question: "Just to confirm, do you want to cancel your <tier> membership?"
- **SQL placeholders (`:cid`)** everywhere, never values pasted into SQL text, to prevent SQL injection.
- **Dates and Decimals are converted to text** (`json.dumps(..., default=str)`) before being sent to Gemini.
- **One retry when Gemini is busy.** If Gemini answers 429 (rate limit) or 503 (busy), the message is sent once more after 5 seconds, but only if no tool ran yet, so a retry can never repeat a tool like `create_ticket`.
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
agent.py         Dhriti: RULES, Conversation class and its tools, command-line chat
main.py          FastAPI app: /, /health, /chat
static/index.html  Chat page (plain HTML + JavaScript)
schema.sql       Database tables
seed.sql         Sample data (made-up)
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

4. **Add the sample data** (made-up customers Asha Rao with a Silver membership, plans, a Laptop order and a service booking, and Ravi Rao with a Gold membership). The tests use this data.
   ```bash
   psql -d support_agent -f seed.sql
   ```

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
| POST | `/chat` | Talk to Dhriti |

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

26 tests:

| Test | Calls Gemini? |
|---|---|
| Charge of 1999 matches the membership; no ticket | Yes |
| Charge of 4321 matches nothing; no ticket | Yes |
| Guard blocks an unknown-charge ticket before `get_plans` | No |
| Guard still blocks it when `get_plans` failed (customer not verified) | No |
| `get_plans` refuses an unverified customer | No |
| `get_plans` returns purchases | No |
| Name rules for `verify_customer` (7 cases: middle name, capitals and spaces, email capitals, first name only, wrong first name, other surname with and without pincode) | No |
| Cancellation refused for an unverified customer | No |
| "Never signed up" is not cancelled (possible fraud) | No |
| Cancellation saves status `Cancelled` and the reason | No |
| Cancelling twice finds no active membership | No |
| A database failure returns `database_error` | No |
| Cancellation refused before the benefits were shown | No |
| Cancellation refused in the same turn as the benefits (no customer answer yet) | No |
| `send` retries once when Gemini is busy (503) | No |
| `send` does not retry if a tool already ran | No |
| Gold members are offered Silver as a cheaper option | No |
| Two conversations don't share verification | No |
| `/chat` with an unknown ID returns 404 | No |
| `GET /` serves the chat page | No |

The two Gemini tests use real API calls, so their results can vary from run to run.

## Known limitations

- Conversations are kept in memory: they are lost when the server restarts, and old ones are never cleaned up.
- The live demo is on Render's free plan: it sleeps after 15 idle minutes, so the first visit can take up to a minute.
- Demo visitors can really cancel the sample memberships, and they stay cancelled until the data is reset. The cancellation tests write only to a local database and restore it afterwards.

## Roadmap

- [x] Unknown-charge matching against purchases
- [x] pytest tests
- [x] `POST /chat` with per-conversation state
- [x] README
- [x] Simple chat page
- [x] Docker and deployment with a live link
