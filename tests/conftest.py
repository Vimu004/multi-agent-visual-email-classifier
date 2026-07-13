import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("USE_FAKE_MODEL", "true")
os.environ.setdefault("DATABASE_URL", "sqlite:///test_email_agents.db")

from app.main import app  # noqa: E402
from app.database import init_db  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _setup_db():
    db_path = Path("test_email_agents.db")
    if db_path.exists():
        db_path.unlink()
    init_db()
    yield
    if db_path.exists():
        db_path.unlink()


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def poll():
    """Poll a workflow's detail endpoint until it reaches a terminal status.

    The analyze endpoint now runs the graph in the background and returns
    immediately, so tests wait for the background task to reach a terminal
    state instead of reading the result synchronously.
    """

    def _poll(client, workflow_id, statuses, timeout=20.0):
        deadline = time.time() + timeout
        detail = {}
        while time.time() < deadline:
            detail = client.get(f"/api/workflows/{workflow_id}").json()
            if detail.get("status") in statuses:
                return detail
            time.sleep(0.1)
        return detail

    return _poll


TERMINAL = {"completed", "pending_approval", "rejected", "error"}
