"""Screening API. Sync path operations (blocking SQLAlchemy/LLM calls run in the threadpool)."""
import json
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.api.deps import DbSession
from app.models.tables import Candidate, InterviewStub, Job, Score, Tag
from app.schemas.io import (
    CandidateDetail,
    JobCreate,
    JobOut,
    RankRow,
    ScheduleOut,
    ScreenOut,
    UploadOut,
)
from app.services.parser import UnsupportedUpload, parse_upload
from app.services.pipeline import index_candidate, index_job, screen_job
from app.services.redact import redact

router = APIRouter(tags=["screening"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
_CHUNK = 1024 * 1024
_REPO_ROOT = Path(__file__).resolve().parents[3]


def _read_bounded(f: UploadFile, limit: int = MAX_UPLOAD_BYTES) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        piece = f.file.read(_CHUNK)
        if not piece:
            break
        total += len(piece)
        if total > limit:
            raise HTTPException(413, f"{f.filename or 'upload'} exceeds {limit // (1024*1024)}MB")
        chunks.append(piece)
    return b"".join(chunks)


def _display_filename(filename: str, candidate_id: str) -> str:
    suffix = Path(filename or "").suffix or ".txt"
    return f"cv-{candidate_id[:6]}{suffix}"


@router.post("/jobs", response_model=JobOut)
def create_job(body: JobCreate, db: DbSession) -> JobOut:
    job = Job(title=body.title, description=body.description)
    db.add(job)
    db.commit()
    db.refresh(job)
    index_job(db, job)
    return JobOut(id=job.id, title=job.title)


@router.post("/jobs/{job_id}/candidates:upload", response_model=UploadOut)
def upload_candidates(
    job_id: str, db: DbSession, files: list[UploadFile] = File(...)  # noqa: B008 — idiomatic FastAPI
) -> UploadOut:
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "job not found")
    ids = []
    for f in files:
        data = _read_bounded(f)
        try:
            text = parse_upload(f.filename or "cv.txt", data)
        except UnsupportedUpload as e:
            raise HTTPException(400, str(e))
        cand = Candidate(job_id=job_id, raw_text=text, filename=f.filename or "")
        db.add(cand)
        db.commit()
        db.refresh(cand)
        index_candidate(db, cand)
        ids.append(cand.id)
    return UploadOut(candidate_ids=ids)


@router.post("/jobs/{job_id}/screen", response_model=ScreenOut)
def screen(job_id: str, db: DbSession) -> ScreenOut:
    if not db.get(Job, job_id):
        raise HTTPException(404, "job not found")
    return ScreenOut(ranking=screen_job(db, job_id))


@router.get("/jobs/{job_id}/ranking", response_model=list[RankRow])
def ranking(job_id: str, db: DbSession) -> list[RankRow]:
    rows = []
    for s in db.query(Score).filter(Score.job_id == job_id).order_by(Score.overall.desc()).all():
        cand = db.get(Candidate, s.candidate_id)
        tags = [t.tag for t in db.query(Tag).filter(Tag.job_id == job_id, Tag.candidate_id == s.candidate_id).all()]
        rows.append(RankRow(candidate_id=s.candidate_id, name=redact(cand.name if cand else "redacted"),
                            overall=s.overall, tags=tags))
    return rows


@router.get("/candidates/{candidate_id}", response_model=CandidateDetail)
def candidate_detail(candidate_id: str, db: DbSession) -> CandidateDetail:
    cand = db.get(Candidate, candidate_id)
    if not cand:
        raise HTTPException(404, "candidate not found")
    s = db.query(Score).filter(Score.candidate_id == candidate_id).first()
    tags = [t.tag for t in db.query(Tag).filter(Tag.candidate_id == candidate_id).all()]
    score = None
    if s:
        ev = [{"requirement_id": e.get("requirement_id", ""), "quote": redact(e.get("quote", ""), cand.name), "sub": e.get("sub", "")} for e in (s.evidence or [])]
        score = {"overall": s.overall, "subs": s.subs, "evidence": ev, "tags": tags}
    return CandidateDetail(candidate_id=cand.id, name=redact(cand.name, cand.name),
                           filename=_display_filename(cand.filename, cand.id), score=score)


@router.post("/candidates/{candidate_id}/schedule", response_model=ScheduleOut)
def schedule_stub(candidate_id: str, slot: str, db: DbSession) -> ScheduleOut:
    cand = db.get(Candidate, candidate_id)
    if not cand:
        raise HTTPException(404, "candidate not found")
    row = InterviewStub(job_id=cand.job_id, candidate_id=candidate_id, slot=slot)
    db.add(row)
    db.commit()
    return ScheduleOut(ok=True, slot=slot)


@router.get("/eval")
def eval_latest() -> dict:
    path = _REPO_ROOT / "evals" / "results.json"
    if path.exists():
        return json.loads(path.read_text())
    return {"detail": "no eval run yet; run python evals/run.py"}
