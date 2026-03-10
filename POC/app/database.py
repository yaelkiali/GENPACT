# app/database.py
import os
import uuid
from datetime import datetime

from sqlalchemy import create_engine, Column, String, Integer, Float, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://user:password@localhost:5432/ai_metrics"
)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class AIRequest(Base):
    __tablename__ = "ai_requests"

    id            = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    timestamp     = Column(DateTime, default=datetime.utcnow, nullable=False)
    user_id       = Column(String, nullable=True)
    model         = Column(String, nullable=False)
    prompt_length = Column(Integer, nullable=False)
    tokens_input  = Column(Integer, nullable=False)
    tokens_output = Column(Integer, nullable=False)
    duration_ms   = Column(Float, nullable=False)
    status        = Column(String, nullable=False, default="success")
    blob_path     = Column(String, nullable=True)


def create_tables():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
