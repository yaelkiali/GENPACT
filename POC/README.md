# AI Metrics Service — יעל

## מבנה הקבצים

```
yael-service/
├── app/
│   ├── main.py       ← FastAPI — כל ה-endpoints
│   ├── models.py     ← Pydantic — מבנה קלט/פלט
│   ├── database.py   ← PostgreSQL + SQLAlchemy
│   ├── blob.py       ← Azurite (Azure Blob מדומה)
│   └── metrics.py    ← Prometheus מטריקות
├── tests/
│   └── test_api.py   ← Pytest — 7 בדיקות
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── .env
```

## הרצה

```bash
# שלב 1 — הרץ את כל ה-containers
docker compose up

# שלב 2 — פתחי בדפדפן
# http://localhost:8000/docs  ← Swagger (נסי את ה-endpoints!)
# http://localhost:8000/metrics ← Prometheus data (דודו יחבר לכאן)

# שלב 3 — שלחי בקשת דמה
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt": "מה זה FastAPI?", "model": "gpt-4"}'
```

## בדיקות (בלי Docker)

```bash
pip install -r requirements.txt
pytest tests/ -v
```

## Endpoints

| Method | Path       | תיאור                        |
|--------|------------|------------------------------|
| POST   | /chat      | שולח prompt → מקבל תשובה + מטריקות |
| GET    | /stats     | סיכום שימוש מה-DB             |
| GET    | /metrics   | Prometheus scraping (לדודו)   |
| GET    | /health    | בדיקת תקינות                  |
| GET    | /docs      | Swagger UI                   |

## מה דודו מוסיף

בקובץ docker-compose.yml יש הערות עם TODO —
דודו מוסיף שם את: otel-collector, tempo, loki, prometheus, grafana
