from app.core.db import Base
from app.models.tables import (
    Candidate,
    Chunk,
    InterviewStub,
    Job,
    Score,
    Tag,
)

__all__ = ["Base", "Candidate", "Chunk", "InterviewStub", "Job", "Score", "Tag"]
