from app.config import get_settings


GENERAL_PAYLOAD = {
    "sender": "ask@example.com",
    "subject": "Weekend support hours",
    "body": "What are your weekend support hours?",
}


TERMINAL = {"completed", "pending_approval", "rejected", "error"}


def test_general_request_auto_completes(client, poll):
    response = client.post("/api/emails/analyze", json=GENERAL_PAYLOAD)
    workflow_id = response.json()["workflow_id"]
    detail = poll(client, workflow_id, TERMINAL)
    assert detail["status"] == "completed"
    assert detail["final_response"] is not None


def test_history_records_runs(client):
    client.post("/api/emails/analyze", json=GENERAL_PAYLOAD)
    response = client.get("/api/workflows")
    data = response.json()
    assert len(data) >= 1


def test_trace_events_are_available(client, poll):
    post = client.post("/api/emails/analyze", json=GENERAL_PAYLOAD).json()
    poll(client, post["workflow_id"], TERMINAL)
    detail = client.get(f"/api/workflows/{post['workflow_id']}").json()
    assert len(detail["trace"]) >= 1


def test_fake_mode_setting_enabled():
    settings = get_settings()
    assert settings.use_fake_model is True
