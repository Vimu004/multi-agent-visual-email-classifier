TERMINAL = {"completed", "pending_approval", "rejected", "error"}

BILLING_PAYLOAD = {
    "sender": "finance@example.com",
    "subject": "Charged twice",
    "body": "We were charged twice for invoice 8801. Please refund the duplicate.",
    "mode": "agentic",
}


def test_agentic_mode_routes_without_specialist_or_approval(client, poll):
    result = client.post("/api/emails/analyze", json=BILLING_PAYLOAD).json()
    detail = poll(client, result["workflow_id"], TERMINAL)

    assert detail["status"] == "completed"
    assert detail["mode"] == "agentic"
    # Agentic mode never assigns a department agent or pauses for approval —
    # it only classifies and forwards.
    assert detail["selected_specialist"] is None
    assert detail["requires_human_approval"] is False
    assert "billing@northstar.example" in detail["final_response"]["body"]


def test_multiagentic_mode_still_default(client, poll):
    payload = {**BILLING_PAYLOAD, "mode": "multi_agentic"}
    del payload["mode"]
    result = client.post("/api/emails/analyze", json=payload).json()
    detail = poll(client, result["workflow_id"], TERMINAL)

    assert detail["mode"] == "multi_agentic"
    assert detail["selected_specialist"] == "billing_support"
    # Billing is a high-risk category in this demo, so it must still pause
    # for human approval rather than auto-completing.
    assert detail["status"] == "pending_approval"
