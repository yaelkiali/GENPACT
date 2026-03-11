# AI Metrics Service — POC

A FastAPI service that simulates AI model calls, tracks usage metrics, and ships full observability telemetry (traces, logs, metrics) to a local monitoring stack.

## Architecture

```
┌─────────────┐     OTLP gRPC      ┌────────────────────┐
│  FastAPI    │ ─────────────────► │   OTel Collector   │
│  (port 8000)│                    └────────┬───────────┘
└──────┬──────┘                             │
       │ /metrics                   ┌───────┴────────┐
       ▼                            │                │
┌─────────────┐               traces│           logs │
│ Prometheus  │◄──scrape──────┐     ▼                ▼
│  (port 9090)│               │  ┌──────┐       ┌──────┐
└──────┬──────┘               │  │Tempo │       │ Loki │
       │                      │  │:3200 │       │:3100 │
       └──────────────┐       └──┤:4317 │       │      │
                      ▼          └──────┘       └──────┘
                 ┌──────────┐        │               │
                 │ Grafana  │◄───────┴───────────────┘
                 │  :3000   │  queries datasources
                 └──────────┘
```

## Project Structure

```
POC/
├── app/
│   ├── main.py         ← FastAPI endpoints + OTel instrumentation
│   ├── otel.py         ← TracerProvider + LoggerProvider setup
│   ├── models.py       ← Pydantic request/response models
│   ├── database.py     ← PostgreSQL + SQLAlchemy
│   ├── blob.py         ← Azurite (local Azure Blob emulator)
│   └── metrics.py      ← Prometheus counters and histograms
├── observability/
│   ├── otel-collector/
│   │   └── config.yaml       ← OTLP receivers, Tempo + Loki exporters
│   ├── tempo/
│   │   └── tempo.yaml        ← Trace storage (local filesystem)
│   ├── loki/
│   │   └── loki-config.yaml  ← Log storage (local filesystem)
│   ├── prometheus/
│   │   └── prometheus.yml    ← Scrape configs
│   └── grafana/
│       ├── provisioning/
│       │   ├── datasources/  ← Auto-provisioned Prometheus, Loki, Tempo
│       │   └── dashboards/   ← Dashboard provider config
│       └── dashboards/
│           └── ai-overview.json  ← AI Metrics Overview dashboard
├── tests/
│   └── test_api.py
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

## Prerequisites

- Docker Desktop (with Compose v2)
- At least 4 GB RAM available for Docker

## Deploy

```bash
# Clone / navigate to the POC folder
cd POC

# Start all services (first run pulls images — takes a few minutes)
docker compose up -d

# Verify all containers are running
docker compose ps
```

All 7 services should show `running`:

| Container | Purpose | Port |
|---|---|---|
| `api` | FastAPI app | 8000 |
| `postgres` | Request storage | 5432 |
| `azurite` | Azure Blob emulator | 10000 |
| `otel-collector` | Telemetry pipeline | 4317, 4318 |
| `tempo` | Trace storage | 3200 |
| `loki` | Log storage | 3100 |
| `prometheus` | Metrics storage | 9090 |
| `grafana` | Dashboards | 3000 |

## Usage

### Send a request

Open Swagger UI at **http://localhost:8000/docs** and use `POST /chat`, or use PowerShell:

```powershell
Invoke-RestMethod -Uri http://localhost:8000/chat `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"prompt": "What is FastAPI?", "model": "gpt-4", "user_id": "user1"}'
```

Or curl (Linux/macOS/Git Bash):

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is FastAPI?", "model": "gpt-4", "user_id": "user1"}'
```

### API Endpoints

---

#### `POST /chat`

Simulates an AI model call. Saves the request to PostgreSQL and Azure Blob Storage, emits a trace with child spans, and logs structured events to Loki.

**Request body:**
```json
{
  "prompt": "What is FastAPI?",
  "model": "gpt-4",
  "user_id": "user1",
  "max_tokens": 500
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `prompt` | string | Yes | The input text (min length: 1) |
| `model` | string | No | One of: `gpt-4`, `gpt-3.5`, `claude-3`, `gemini-pro`. Default: `gpt-4` |
| `user_id` | string | No | Identifier for the caller |
| `max_tokens` | integer | No | Max output tokens (1–4096). Default: 500 |

**Response:**
```json
{
  "request_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "response_text": "[gpt-4] Processed your request successfully.",
  "model": "gpt-4",
  "tokens_input": 10,
  "tokens_output": 237,
  "duration_ms": 312.5,
  "timestamp": "2026-03-11T12:00:00"
}
```

**What it produces (observability):**
- OTel trace with spans: `ai.model.inference`, `db.save_request`, `blob.save_request`
- Log line: `chat request received trace_id=... request_id=... model=... user_id=...`
- Log line: `chat completed trace_id=... request_id=... duration_ms=... tokens_in=... tokens_out=...`
- Prometheus counters: `ai_requests_total`, `ai_tokens_total`, `ai_request_duration_seconds`

---

#### `GET /stats`

Returns aggregated usage statistics from the PostgreSQL database.

**Response:**
```json
{
  "total_requests": 42,
  "total_tokens_input": 1540,
  "total_tokens_output": 8320,
  "avg_duration_ms": 287.4,
  "requests_by_model": {
    "gpt-4": 20,
    "claude-3": 12,
    "gpt-3.5": 10
  },
  "requests_today": 8,
  "requests_this_month": 42
}
```

---

#### `GET /metrics`

Prometheus scrape endpoint. Returns plain-text metrics in Prometheus exposition format. Prometheus scrapes this every 10 seconds automatically.

**Available metrics:**

| Metric | Type | Labels | Description |
|---|---|---|---|
| `ai_requests_total` | Counter | `model`, `status` | Total requests processed |
| `ai_tokens_total` | Counter | `model`, `direction` | Total tokens (direction: `input` / `output`) |
| `ai_request_duration_seconds` | Histogram | `model` | End-to-end request duration |

---

#### `GET /health`

Health check for liveness/readiness probes.

**Response:**
```json
{
  "status": "ok",
  "db": true,
  "blob_storage": true
}
```

`status` is `"ok"` when DB is reachable, `"degraded"` otherwise.

---

#### `GET /docs`

Swagger UI — interactive documentation auto-generated by FastAPI from the Pydantic models. Use this to explore and test all endpoints directly in the browser without needing curl or Postman.

#### `GET /redoc`

ReDoc UI — alternative read-only documentation view.

#### `GET /openapi.json`

Raw OpenAPI 3.0 schema in JSON format.

## Observability

### Grafana — http://localhost:3000
Login: `admin` / `admin`

**AI Metrics Overview** dashboard (auto-provisioned) shows:
- Total requests, input tokens, output tokens, avg latency (stat panels)
- Request rate by model (req/min)
- Token throughput by direction (input/output)
- Latency percentiles — p50, p95, p99
- Requests by model (pie chart)
- Token usage per model (input + output time series)

### Explore raw telemetry

**Traces** — Grafana → Explore → Tempo:
```
{resource.service.name="ai-metrics-api"}
```
Each trace covers one `POST /chat` call with three child spans:
- `ai.model.inference` — attributes: `ai.tokens_input`, `ai.tokens_output`, `ai.duration_ms`
- `db.save_request` — SQLAlchemy DB write
- `blob.save_request` — Azure Blob upload

**Logs** — Grafana → Explore → Loki:
```
{service_name="ai-metrics-api"}
```

**Metrics** — Grafana → Explore → Prometheus:
```
ai_requests_total
ai_tokens_total
ai_request_duration_seconds
```

### Prometheus — http://localhost:9090

Prometheus scrapes three targets:
- `api:8000/metrics` — application metrics
- `otel-collector:8888` — collector internal metrics
- `tempo:3200/metrics` — Tempo internal metrics

## What telemetry is emitted per request

Each `POST /chat` produces:

| Signal | What | Where |
|---|---|---|
| Trace | Full request span + 3 child spans | Tempo via OTel Collector |
| Log | `chat request received trace_id=... request_id=... model=... user_id=...` | Loki via OTel Collector |
| Log | `chat completed trace_id=... request_id=... duration_ms=... tokens_in=... tokens_out=...` | Loki via OTel Collector |
| Metric | `ai_requests_total{model, status}` counter | Prometheus |
| Metric | `ai_tokens_total{model, direction}` counter | Prometheus |
| Metric | `ai_request_duration_seconds{model}` histogram | Prometheus |

## Teardown

```bash
# Stop containers (keeps volumes / data)
docker compose down

# Stop and delete all data volumes
docker compose down -v
```
