# tests/test_api.py
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from unittest.mock import patch

from app.main import app
from app.database import Base, get_db

# In-memory SQLite — no Docker required for tests
engine = create_engine(
    "sqlite:///./test.db",
    connect_args={"check_same_thread": False}
)
TestingSession = sessionmaker(bind=engine)
Base.metadata.create_all(bind=engine)


def override_get_db():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db

# Mock blob storage so tests don't require Azurite
with patch("app.main.save_request_to_blob", return_value="test/path.json"), \
     patch("app.main.ensure_container"):
    client = TestClient(app)


# ── Tests ─────────────────────────────────────────────────────

def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_chat_returns_200():
    with patch("app.main.save_request_to_blob", return_value="p"), \
         patch("app.main.ensure_container"):
        r = client.post("/chat", json={"prompt": "What is FastAPI?", "model": "gpt-4"})
    assert r.status_code == 200


def test_chat_has_required_fields():
    with patch("app.main.save_request_to_blob", return_value="p"), \
         patch("app.main.ensure_container"):
        r = client.post("/chat", json={"prompt": "Hello", "model": "claude-3"})
    data = r.json()
    assert "request_id" in data
    assert "tokens_input" in data
    assert "tokens_output" in data
    assert data["tokens_input"] > 0
    assert data["duration_ms"] > 0


def test_chat_invalid_model():
    """Pydantic rejects an invalid model — expects 422."""
    r = client.post("/chat", json={"prompt": "Hello", "model": "gpt-999"})
    assert r.status_code == 422


def test_chat_empty_prompt():
    """Pydantic rejects an empty prompt — expects 422."""
    r = client.post("/chat", json={"prompt": "", "model": "gpt-4"})
    assert r.status_code == 422


def test_stats_updates_after_request():
    """Stats should increment after a request."""
    with patch("app.main.save_request_to_blob", return_value="p"), \
         patch("app.main.ensure_container"):
        before = client.get("/stats").json()["total_requests"]
        client.post("/chat", json={"prompt": "Test prompt", "model": "gpt-4"})
        after = client.get("/stats").json()["total_requests"]
    assert after == before + 1


def test_metrics_endpoint():
    """Prometheus endpoint returns metric data."""
    r = client.get("/metrics")
    assert r.status_code == 200
    assert b"ai_requests_total" in r.content
