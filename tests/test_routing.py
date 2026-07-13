SALES_PAYLOAD = {
    "sender": "buyer@example.com",
    "subject": "Need pricing",
    "body": "Can you share enterprise pricing for 1000 seats?",
}

TECH_PAYLOAD = {
    "sender": "dev@example.com",
    "subject": "App crash",
    "body": "Your dashboard shows an error and crashes every hour.",
}

BILLING_PAYLOAD = {
    "sender": "finance@example.com",
    "subject": "Charged twice",
    "body": "We were charged twice for invoice 8801. Please refund the duplicate.",
}


TERMINAL = {"completed", "pending_approval", "rejected", "error"}


def _run_and_fetch(client, poll, payload):
    result = client.post("/api/emails/analyze", json=payload).json()
    return poll(client, result["workflow_id"], TERMINAL)


def test_sales_request_routes_to_sales(client, poll):
    detail = _run_and_fetch(client, poll, SALES_PAYLOAD)
    assert detail["selected_specialist"] == "sales"


def test_technical_issue_routes_to_technical_support(client, poll):
    detail = _run_and_fetch(client, poll, TECH_PAYLOAD)
    assert detail["selected_specialist"] == "technical_support"


def test_billing_issue_routes_to_billing_support(client, poll):
    detail = _run_and_fetch(client, poll, BILLING_PAYLOAD)
    assert detail["selected_specialist"] == "billing_support"
