"""Pydantic I/O. Mirrors docs/BACKEND_API.md examples."""
from typing import Annotated

from pydantic import BaseModel, Field

ScoreValue = Annotated[float, Field(ge=0, le=100)]


class JobCreate(BaseModel):
    title: str
    description: str


class JobOut(BaseModel):
    id: str
    title: str


class EvidenceItem(BaseModel):
    requirement_id: str
    quote: str
    sub: str = ""


class ScoreOut(BaseModel):
    overall: ScoreValue
    subs: dict[str, ScoreValue] = Field(default_factory=dict)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class RankRow(BaseModel):
    candidate_id: str
    name: str
    overall: float
    tags: list[str] = Field(default_factory=list)


class CandidateDetail(BaseModel):
    candidate_id: str
    name: str
    filename: str = ""
    score: ScoreOut | None = None
