ACCOUNT_PAYLOAD = {
    "sender": "customer@example.com",
    "subject": "Cannot access my account after changing my phone",
    "body": "Hi, I changed my mobile phone yesterday and now the verification code is going to my old number. I cannot log in. Can someone update the number for me?",
}


TERMINAL = {"completed", "pending_approval", "rejected", "error"}


def _submit_account_request(client, poll):
    response = client.post("/api/emails/analyze", json=ACCOUNT_PAYLOAD).json()
    detail = poll(client, response["workflow_id"], TERMINAL)
    assert detail["status"] == "pending_approval"
    return response["workflow_id"]


def test_account_access_flow_requires_approval(client, poll):
    workflow_id = _submit_account_request(client, poll)
    detail = client.get(f"/api/workflows/{workflow_id}").json()
    assert detail["requires_human_approval"] is True


def test_approval_completes_workflow(client, poll):
    workflow_id = _submit_account_request(client, poll)
    client.post(
        f"/api/reviews/{workflow_id}/approve",
        json={
            "edited_response": {
                "subject": "Re: Account access",
                "body": "We will verify your identity before updating the phone number.",
            }
        },
    )
    detail = client.get(f"/api/workflows/{workflow_id}").json()
    assert detail["status"] == "completed"
    assert detail["human_decision"] == "approved"
    assert detail["final_response"].get("body")


def test_rejection_marks_workflow(client, poll):
    workflow_id = _submit_account_request(client, poll)
    reason = "Escalated to security"
    client.post(f"/api/reviews/{workflow_id}/reject", json={"reason": reason})
    detail = client.get(f"/api/workflows/{workflow_id}").json()
    assert detail["status"] == "rejected"
    assert detail["human_decision"] == "rejected"
    assert detail["approval_reason"] == reason
