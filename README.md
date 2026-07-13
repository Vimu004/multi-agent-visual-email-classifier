# Multi-Agent Email Assistant POC

A locally runnable FastAPI + LangGraph demonstration that classifies incoming emails, routes them through a supervisor-controlled network of specialist agents, pauses for human approval, and stores every step in SQLite with a simple observability timeline.

## Highlights
- FastAPI backend with LangGraph typed state and conditional routing
- Supervisor agent fans out to spam, sales, technical, billing, account-access, and general specialists
- Response + reviewer agents enforce policy and trigger a human-in-the-loop pause using persisted state
- Local JSON knowledge base per category (no external vector DB)
- SQLite persistence for workflows and trace events
- Dashboard, architecture page, history list, and workflow detail pages built with vanilla HTML/CSS/JS
- Fake-mode fallback when Azure GPT-5.4 Nano is unavailable

## Architecture Overview
1. API receives an email and writes an initial workflow row to SQLite.
2. LangGraph state flows through Intake → Classification → Supervisor → Specialist → Response → Reviewer.
3. The supervisor selects a single specialist per run; knowledge snippets are injected per category.
4. The approval gate enforces mandatory review rules (low confidence, sensitive actions, refunds, account changes, high-risk notes, reviewer escalation, or missing policy coverage).
5. When approval is needed, the workflow pauses, the state JSON is stored, and the dashboard shows editable draft + Approve/Reject actions.
6. Approvals and rejections resume LangGraph via dedicated graphs before finalizing.
7. Every node writes a trace event with timestamps and summaries for the UI timeline.

## Agents Implemented
- Classification Agent
- Supervisor Agent
- Spam Specialist
- Sales Specialist
- Technical Support Specialist
- Billing Support Specialist
- Account Access Specialist
- General Enquiry Specialist
- Response Agent
- Reviewer Agent
- Human Approval Gate (UI-driven)

## Local Setup
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

### `.env` values
```
AZURE_AI_PROJECT_ENDPOINT=
AZURE_AI_API_KEY=
AZURE_AI_MODEL_DEPLOYMENT_NAME=gpt-5.4-nano
USE_FAKE_MODEL=true
DATABASE_URL=sqlite:///email_agents.db
```

### Azure GPT-5.4 Nano
1. Deploy GPT-5.4 Nano inside Azure AI Foundry.
2. Copy the project endpoint and API key.
3. Set `AZURE_AI_MODEL_DEPLOYMENT_NAME` to the deployment name (e.g., `gpt-5.4-nano`).
4. Set `USE_FAKE_MODEL=false` to route calls through Azure. The UI badge will switch to “Azure GPT-5.4 Nano”.

### Fake Mode
Set `USE_FAKE_MODEL=true` to run deterministic keyword-based outputs for demos without Azure connectivity. The dashboard highlights “Local Demo Mode”.

## Run the Server
```bash
uvicorn app.main:app --reload
```

Open:
```
Dashboard:     http://localhost:8000
Architecture:  http://localhost:8000/architecture
History:       http://localhost:8000/history
Swagger:       http://localhost:8000/docs
```

## API Example
```http
POST /api/emails/analyze
Content-Type: application/json

{
  "sender": "customer@example.com",
  "subject": "Cannot access my account after changing my phone",
  "body": "Hi, I changed my mobile phone yesterday and now the verification code is going to my old number."
}
```
- Auto-complete response ⇒ status `completed` with `final_response`.
- Sensitive response ⇒ status `pending_approval`, draft response, and approval reason.

Approval endpoints:
```http
POST /api/reviews/{workflow_id}/approve
{
  "edited_response": {
    "subject": "Re: Account access",
    "body": "We will verify your identity before updating the phone number."
  }
}

POST /api/reviews/{workflow_id}/reject
{
  "reason": "Escalated to security"
}
```

## Data + Observability
- `workflows` table stores the email, LangGraph state JSON, approval metadata, and final response.
- `trace_events` table stores each agent run (name, status, duration, summaries).
- Dashboard timeline and history widgets read directly from these tables via the API.

## Tests
```bash
pytest
```
Covers routing, approval gating, persistence, trace recording, and fake-mode behavior using a temporary SQLite database.

## Known Limitations
- No authentication or multi-user approval controls.
- Azure GPT calls are synchronous per node; batching/streaming is out of scope.
- Fake mode uses simple keyword heuristics and should not be used for evaluation.
- UI polling is minimal; real-time streaming of graph state would require websockets or events.
