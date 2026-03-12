# app/models.py
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field


# ── Request ───────────────────────────────────────────────────
class ChatRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    model: Literal["gpt-4", "gpt-3.5", "claude-3", "gemini-pro"] = "gpt-4"
    user_id: Optional[str] = None
    max_tokens: int = Field(default=500, ge=1, le=4096)


# ── Response ──────────────────────────────────────────────────
class ChatResponse(BaseModel):
    request_id: str
    response_text: str
    model: str
    tokens_input: int
    tokens_output: int
    duration_ms: float
    timestamp: datetime


class StatsResponse(BaseModel):
    total_requests: int
    total_tokens_input: int
    total_tokens_output: int
    avg_duration_ms: float
    requests_by_model: dict
    requests_today: int
    requests_this_month: int


class ErrorResponse(BaseModel):
    request_id: str
    status_code: int
    error_type: str
    message: str
    model: str
    duration_ms: float
    timestamp: datetime


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    db: bool
    blob_storage: bool
