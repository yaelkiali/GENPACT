# app/main.py
import logging
import os
import random
import time
import uuid
from datetime import datetime, date

from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, extract
from starlette.responses import Response
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

from app.models import ChatRequest, ChatResponse, ErrorResponse, StatsResponse, HealthResponse
from app.database import get_db, create_tables, AIRequest, engine
from app.blob import ensure_container, save_request_to_blob
from app.metrics import (
    REQUESTS_TOTAL, REQUEST_DURATION, TOKENS_TOTAL, get_metrics_response
)
from app.otel import setup_telemetry

logger = logging.getLogger(__name__)

# ── OTel bootstrap (runs at import time so instrumentation wraps uvicorn) ──
setup_telemetry()

app = FastAPI(
    title="AI Metrics API",
    description="Simulates AI model calls and tracks usage metrics",
    version="0.1.0",
)

# Instrument FastAPI (adds span per request, propagates context)
FastAPIInstrumentor.instrument_app(app)

# Instrument SQLAlchemy (adds span per DB statement)
SQLAlchemyInstrumentor().instrument(engine=engine)

tracer = trace.get_tracer(__name__)


# ── Startup ───────────────────────────────────────────────────
@app.on_event("startup")
def startup():
    create_tables()
    ensure_container()
    logger.info("Application started. OTel exporting to %s",
                os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"))


# ── POST /chat ────────────────────────────────────────────────
@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, db: Session = Depends(get_db)):
    """
    Simulates an AI model call.
    Persists metrics to DB and the request payload to Azure Blob.
    """
    request_id = str(uuid.uuid4())
    start = time.time()

    current_span = trace.get_current_span()
    current_span.set_attributes({
        "ai.request_id": request_id,
        "ai.model": req.model,
        "ai.user_id": req.user_id or "",
        "ai.prompt_length": len(req.prompt),
        "ai.max_tokens": req.max_tokens,
    })
    span_ctx = current_span.get_span_context()
    trace_id_hex = format(span_ctx.trace_id, "032x") if span_ctx.trace_id else "0" * 32
    logger.info("chat request received trace_id=%s request_id=%s model=%s user_id=%s",
                trace_id_hex, request_id, req.model, req.user_id)

    # ── Simulate processing ────────────────────────────────────
    with tracer.start_as_current_span("ai.model.inference") as span:
        tokens_input  = max(1, len(req.prompt.split()) * 2)
        tokens_output = random.randint(50, min(req.max_tokens, 500))
        time.sleep(random.uniform(0.1, 0.5))          # Simulate latency
        duration_ms   = (time.time() - start) * 1000
        response_text = _fake_response(req.model, req.prompt)
        span.set_attributes({
            "ai.tokens_input": tokens_input,
            "ai.tokens_output": tokens_output,
            "ai.duration_ms": round(duration_ms, 2),
        })

    # ── Persist to DB ────────────────────────────────────────────
    with tracer.start_as_current_span("db.save_request") as span:
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
        span.set_attribute("db.request_id", request_id)

        # ── Persist to Azure Blob ──────────────────────────────────
        with tracer.start_as_current_span("blob.save_request") as span:
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
                span.set_attribute("blob.path", blob_path)
                logger.info("blob saved request_id=%s path=%s", request_id, blob_path)
            except Exception as exc:
                span.record_exception(exc)
                span.set_attribute("blob.error", str(exc))
                logger.warning("blob save failed request_id=%s error=%s", request_id, exc)

        db.commit()

    # ── Prometheus metrics ──────────────────────────────────────
    REQUESTS_TOTAL.labels(model=req.model, status="success").inc()
    REQUEST_DURATION.labels(model=req.model).observe(duration_ms / 1000)
    TOKENS_TOTAL.labels(model=req.model, direction="input").inc(tokens_input)
    TOKENS_TOTAL.labels(model=req.model, direction="output").inc(tokens_output)

    logger.info("chat completed trace_id=%s request_id=%s duration_ms=%.2f tokens_in=%d tokens_out=%d",
                trace_id_hex, request_id, duration_ms, tokens_input, tokens_output)

    return ChatResponse(
        request_id    = request_id,
        response_text = response_text,
        model         = req.model,
        tokens_input  = tokens_input,
        tokens_output = tokens_output,
        duration_ms   = round(duration_ms, 2),
        timestamp     = datetime.utcnow(),
    )


# ── POST /chat/unstable — simulates random failures ──────────
@app.post("/chat/unstable")
def chat_unstable(req: ChatRequest):
    """
    Simulates an unreliable AI model endpoint.
    Randomly returns 200, 400, or 500 (~50% failure rate).
    Used for observability and dashboard demos.
    """
    request_id = str(uuid.uuid4())
    start = time.time()

    current_span = trace.get_current_span()
    current_span.set_attributes({
        "ai.request_id": request_id,
        "ai.model": req.model,
        "ai.endpoint": "unstable",
    })

    # Simulate variable processing time
    time.sleep(random.uniform(0.05, 0.8))
    duration_ms = (time.time() - start) * 1000

    # 50% success, 25% client error (400), 25% server error (500)
    roll = random.random()
    if roll < 0.50:
        status, status_code = "success", 200
    elif roll < 0.75:
        status, status_code = "client_error", 400
    else:
        status, status_code = "server_error", 500

    # Record Prometheus metrics regardless of outcome
    REQUESTS_TOTAL.labels(model=req.model, status=status).inc()
    REQUEST_DURATION.labels(model=req.model).observe(duration_ms / 1000)

    current_span.set_attributes({
        "ai.status": status,
        "ai.status_code": status_code,
        "ai.duration_ms": round(duration_ms, 2),
    })

    if status_code != 200:
        error_messages = {
            400: [
                "Invalid prompt format — content policy violation detected.",
                "Token limit exceeded for the requested model.",
                "Malformed request — missing required context field.",
            ],
            500: [
                "Model inference timeout — GPU cluster overloaded.",
                "Internal model error — unexpected null tensor output.",
                "Service degraded — upstream dependency unreachable.",
            ],
        }
        message = random.choice(error_messages[status_code])
        logger.warning("unstable endpoint failure request_id=%s status=%d msg=%s",
                        request_id, status_code, message)
        raise HTTPException(
            status_code=status_code,
            detail={
                "request_id": request_id,
                "error_type": status,
                "message": message,
                "model": req.model,
                "duration_ms": round(duration_ms, 2),
            },
        )

    tokens_in = max(1, len(req.prompt.split()) * 2)
    tokens_out = random.randint(50, min(req.max_tokens, 500))
    TOKENS_TOTAL.labels(model=req.model, direction="input").inc(tokens_in)
    TOKENS_TOTAL.labels(model=req.model, direction="output").inc(tokens_out)

    logger.info("unstable endpoint success request_id=%s duration_ms=%.2f",
                request_id, duration_ms)

    return ChatResponse(
        request_id=request_id,
        response_text=_fake_response(req.model, req.prompt),
        model=req.model,
        tokens_input=tokens_in,
        tokens_output=tokens_out,
        duration_ms=round(duration_ms, 2),
        timestamp=datetime.utcnow(),
    )


# ── GET /stats ────────────────────────────────────────────────
@app.get("/stats", response_model=StatsResponse)
def get_stats(db: Session = Depends(get_db)):
    """Usage summary from DB — data source for Grafana dashboards."""
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
    """Prometheus scrape target — consumed by Grafana."""
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
        f"[{model}] Successfully processed request '{prompt[:40]}...'.",
        f"[{model}] Analysis complete. Here are my insights.",
        f"[{model}] Prompt received — returning a simulated response for testing.",
    ]
    return random.choice(templates)
