"""Job + Candidate + Chunk + Score/Tag/InterviewStub. Single source for table shapes."""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.db import Base


def _uid() -> str:
    return uuid.uuid4().hex[:12]


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_uid)
    title: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Candidate(Base):
    __tablename__ = "candidates"
    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_uid)
    job_id: Mapped[str] = mapped_column(String(12), ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200), default="redacted")
    raw_text: Mapped[str] = mapped_column(Text)
    filename: Mapped[str] = mapped_column(String(300), default="")


class Chunk(Base):
    __tablename__ = "chunks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(12), ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    # Mixed namespace: candidate row ids plus "job:<id>" requirement markers,
    # so no FK here by design; rows are rewritten on every screen run.
    candidate_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    requirement_id: Mapped[str] = mapped_column(String(32), default="")
    section: Mapped[str] = mapped_column(String(64), default="")
    text: Mapped[str] = mapped_column(Text)
    # 384-dim MiniLM embedding. pgvector VECTOR in prod migrations; JSON here for sqlite portability.
    embedding: Mapped[list] = mapped_column(JSON, default=list)


class Score(Base):
    __tablename__ = "scores"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(12), ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    candidate_id: Mapped[str] = mapped_column(String(12), ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    overall: Mapped[float] = mapped_column(Float)
    subs: Mapped[dict] = mapped_column(JSON().with_variant(JSONB, "postgresql"), default=dict)
    evidence: Mapped[list] = mapped_column(JSON().with_variant(JSONB, "postgresql"), default=list)


class Tag(Base):
    __tablename__ = "tags"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(12), ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    candidate_id: Mapped[str] = mapped_column(String(12), ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    tag: Mapped[str] = mapped_column(String(64), index=True)


class InterviewStub(Base):
    __tablename__ = "interviews_stub"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(12), ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    candidate_id: Mapped[str] = mapped_column(String(12), ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    slot: Mapped[str] = mapped_column(String(120))
