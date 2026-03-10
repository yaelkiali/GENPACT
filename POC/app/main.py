# app/main.py
import random
import time
import uuid
from datetime import datetime, date

from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, extract
from starlette.responses import Response

from app.models import ChatRequest, ChatResponse, StatsResponse, HealthResponse
from app.database import get_db, create_tables, AIRequest
from app.blob import ensure_container, save_request_to_blob
from app.metrics import (
    REQUESTS_TOTAL, REQUEST_DURATION, TOKENS_TOTAL, get_metrics_response
)

app = FastAPI(
    title="AI Metrics API",
    description="מדמה קריאות למודלי AI ועוקב אחרי מטריקות שימוש",
    version="0.1.0",
)


# ── Startup ───────────────────────────────────────────────────
@app.on_event("startup")
def startup():
    create_tables()
    ensure_container()


# ── POST /chat ────────────────────────────────────────────────
@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, db: Session = Depends(get_db)):
    """
    מדמה קריאה למודל AI.
    שומר מטריקות ב-DB ואת הבקשה ב-Azure Blob.
    """
    request_id = str(uuid.uuid4())
    start = time.time()

    # ── דמיית עיבוד ──────────────────────────────────────────
    tokens_input  = max(1, len(req.prompt.split()) * 2)
    tokens_output = random.randint(50, min(req.max_tokens, 500))
    time.sleep(random.uniform(0.1, 0.5))          # דמיית latency
    duration_ms   = (time.time() - start) * 1000

    response_text = _fake_response(req.model, req.prompt)

    # ── שמירה ל-DB ────────────────────────────────────────────
    record = AIRequest(
        id            = request_id,
        user_id       = req.user_id,
        model         = req.model,
        prompt_length = len(req.prompt),
        tokens_input  = tokens_input,
        tokens_output = tokens_output,
        duration_ms   = duration_ms,
        status        = "success",
    )
    db.add(record)

    # ── שמירה ל-Azure Blob ────────────────────────────────────
    try:
        blob_path = save_request_to_blob(request_id, {
            "request_id":   request_id,
            "prompt":       req.prompt,
            "model":        req.model,
            "tokens_input": tokens_input,
            "tokens_output":tokens_output,
            "duration_ms":  duration_ms,
            "timestamp":    datetime.utcnow().isoformat(),
        })
        record.blob_path = blob_path
    except Exception:
        pass  # blob לא קריטי — לא נפיל את הבקשה

    db.commit()

    # ── Prometheus מטריקות ────────────────────────────────────
    REQUESTS_TOTAL.labels(model=req.model, status="success").inc()
    REQUEST_DURATION.labels(model=req.model).observe(duration_ms / 1000)
    TOKENS_TOTAL.labels(model=req.model, direction="input").inc(tokens_input)
    TOKENS_TOTAL.labels(model=req.model, direction="output").inc(tokens_output)

    return ChatResponse(
        request_id    = request_id,
        response_text = response_text,
        model         = req.model,
        tokens_input  = tokens_input,
        tokens_output = tokens_output,
        duration_ms   = round(duration_ms, 2),
        timestamp     = datetime.utcnow(),
    )


# ── GET /stats ────────────────────────────────────────────────
@app.get("/stats", response_model=StatsResponse)
def get_stats(db: Session = Depends(get_db)):
    """סיכום שימוש מה-DB — מה Grafana יציג."""
    today = date.today()

    total_requests  = db.query(func.count(AIRequest.id)).scalar() or 0
    total_tokens_in = db.query(func.sum(AIRequest.tokens_input)).scalar() or 0
    total_tokens_out= db.query(func.sum(AIRequest.tokens_output)).scalar() or 0
    avg_duration    = db.query(func.avg(AIRequest.duration_ms)).scalar() or 0.0

    by_model = dict(
        db.query(AIRequest.model, func.count(AIRequest.id))
          .group_by(AIRequest.model).all()
    )

    requests_today = db.query(func.count(AIRequest.id)).filter(
        func.date(AIRequest.timestamp) == today
    ).scalar() or 0

    requests_month = db.query(func.count(AIRequest.id)).filter(
        extract("month", AIRequest.timestamp) == today.month,
        extract("year",  AIRequest.timestamp) == today.year,
    ).scalar() or 0

    return StatsResponse(
        total_requests       = total_requests,
        total_tokens_input   = total_tokens_in,
        total_tokens_output  = total_tokens_out,
        avg_duration_ms      = round(avg_duration, 2),
        requests_by_model    = by_model,
        requests_today       = requests_today,
        requests_this_month  = requests_month,
    )


# ── GET /metrics ──────────────────────────────────────────────
@app.get("/metrics")
def metrics():
    """Prometheus סורק את זה — דודו יחבר לכאן מ-Grafana."""
    data, content_type = get_metrics_response()
    return Response(data, media_type=content_type)


# ── GET /health ───────────────────────────────────────────────
@app.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db)):
    db_ok = True
    blob_ok = True
    try:
        db.execute("SELECT 1")
    except Exception:
        db_ok = False
    return HealthResponse(
        status       = "ok" if db_ok else "degraded",
        db           = db_ok,
        blob_storage = blob_ok,
    )


# ── Helper ────────────────────────────────────────────────────
def _fake_response(model: str, prompt: str) -> str:
    templates = [
        f"[{model}] עיבדתי את הבקשה '{prompt[:40]}...' בהצלחה.",
        f"[{model}] ניתוח הושלם. הנה התובנות שלי.",
        f"[{model}] קיבלתי את ההנחיה ומחזיר תשובה מדומה לצורך בדיקה.",
    ]
    return random.choice(templates)
