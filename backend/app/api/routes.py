"""Screening API. Sync path operations (blocking SQLAlchemy/LLM calls run in the threadpool)."""
import json
import re
import secrets
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import func

from app.api.deps import CurrentOrg, DbSession
from app.api.rate_limit import check_rate_limit
from app.models.tables import Candidate, InterviewStub, Job, Score, ScreeningRun, Tag
from app.schemas.io import (
    ApplicantOut,
    ApplyOut,
    CandidateDetail,
    JobCreate,
    JobListRow,
    JobOut,
    JobPatch,
    RankRow,
    RunCreate,
    RunDetail,
    RunOut,
    ScheduleOut,
    ScreenOut,
    UploadOut,
)
from app.services.parser import UnsupportedUpload, parse_upload
from app.services.pipeline import index_candidate, index_job, screen_job
from app.services.redact import redact
from app.services.runner import create_run, get_run

router = APIRouter(tags=["screening"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
_CHUNK = 1024 * 1024
_REPO_ROOT = Path(__file__).resolve().parents[3]
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


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


def _job_in_org(db, org, job_id: str) -> Job:
    job = db.query(Job).filter(Job.id == job_id, Job.org_id == org.id).first()
    if not job:
        raise HTTPException(404, "job not found")
    return job


def _candidate_in_org(db, org, candidate_id: str) -> Candidate:
    cand = db.get(Candidate, candidate_id)
    if not cand:
        raise HTTPException(404, "candidate not found")
    _job_in_org(db, org, cand.job_id)
    return cand


@router.post("/jobs", response_model=JobOut)
def create_job(body: JobCreate, db: DbSession, org: CurrentOrg) -> JobOut:
    job = Job(title=body.title, description=body.description, org_id=org.id)
    db.add(job)
    db.commit()
    db.refresh(job)
    index_job(db, job)
    return JobOut(id=job.id, title=job.title, status=job.status, apply_token=job.apply_token)


@router.get("/jobs", response_model=list[JobListRow])
def list_jobs(db: DbSession, org: CurrentOrg) -> list[JobListRow]:
    jobs = db.query(Job).filter(Job.org_id == org.id).order_by(Job.created_at.desc()).all()
    q = db.query(Candidate.job_id, func.count()).group_by(Candidate.job_id)
    ids = [j.id for j in jobs]
    if ids:
        q = q.filter(Candidate.job_id.in_(ids))
    counts = dict(q.all())
    return [JobListRow(id=j.id, title=j.title, status=j.status, apply_token=j.apply_token,
                       applicant_count=counts.get(j.id, 0)) for j in jobs]


@router.patch("/jobs/{job_id}", response_model=JobOut)
def update_job(job_id: str, body: JobPatch, db: DbSession, org: CurrentOrg) -> JobOut:
    if body.status not in ("open", "closed"):
        raise HTTPException(422, "status must be open or closed")
    job = _job_in_org(db, org, job_id)
    job.status = body.status
    db.commit()
    return JobOut(id=job.id, title=job.title, status=job.status, apply_token=job.apply_token)


@router.post("/jobs/{job_id}/rotate-link")
def rotate_link(job_id: str, db: DbSession, org: CurrentOrg) -> dict:
    job = _job_in_org(db, org, job_id)
    job.apply_token = secrets.token_urlsafe(24)
    db.commit()
    return {"apply_token": job.apply_token}


@router.post("/jobs/{job_id}/candidates:upload", response_model=UploadOut)
def upload_candidates(job_id: str, db: DbSession, org: CurrentOrg,
                      files: list[UploadFile] = File(...)) -> UploadOut:  # noqa: B008 — idiomatic FastAPI
    _job_in_org(db, org, job_id)
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


@router.get("/jobs/{job_id}/applicants", response_model=list[ApplicantOut])
def list_applicants(job_id: str, db: DbSession, org: CurrentOrg) -> list[ApplicantOut]:
    _job_in_org(db, org, job_id)
    out = []
    for cand in db.query(Candidate).filter(Candidate.job_id == job_id).all():
        s = db.query(Score).filter(Score.candidate_id == cand.id).first()
        tags = [t.tag for t in db.query(Tag).filter(Tag.candidate_id == cand.id).all()]
        out.append(ApplicantOut(candidate_id=cand.id, name=cand.name, email=cand.email,
                                phone=cand.phone, filename=_display_filename(cand.filename, cand.id),
                                overall=s.overall if s else None, tags=tags))
    return out


@router.post("/apply/{token}", response_model=ApplyOut)
def apply_for_job(token: str, request: Request, db: DbSession,
                  full_name: Annotated[str, Form()], email: Annotated[str, Form()],
                  phone: Annotated[str, Form()] = "",
                  cv: UploadFile = File(...)) -> ApplyOut:  # noqa: B008 — idiomatic FastAPI
    client = request.client.host if request.client else "unknown"
    if not check_rate_limit(f"apply:{client}"):
        raise HTTPException(429, "too many applications; try again in a minute")
    job = db.query(Job).filter(Job.apply_token == token).first()
    if not job:
        raise HTTPException(404, "application link not found")
    if job.status != "open":
        raise HTTPException(410, "applications for this job are closed")
    name = (full_name or "").strip()
    if not name:
        raise HTTPException(422, "full_name is required")
    if not _EMAIL_RE.match((email or "").strip()):
        raise HTTPException(422, "a valid email is required")
    suffix = Path(cv.filename or "").suffix.lower()
    if suffix != ".pdf":
        raise HTTPException(400, "CV must be a PDF file")
    data = _read_bounded(cv)
    try:
        text = parse_upload(cv.filename or "cv.pdf", data)
    except UnsupportedUpload as e:
        raise HTTPException(400, str(e))
    if not text.strip():
        raise HTTPException(400, "could not read any text from the PDF")
    cand = Candidate(job_id=job.id, name=name, email=email.strip(),
                     phone=(phone or "").strip(), raw_text=text, filename=cv.filename or "")
    db.add(cand)
    db.commit()
    db.refresh(cand)
    index_candidate(db, cand)
    return ApplyOut(applicant_id=cand.id)


@router.post("/jobs/{job_id}/screen", response_model=ScreenOut)
def screen(job_id: str, db: DbSession, org: CurrentOrg) -> ScreenOut:
    _job_in_org(db, org, job_id)
    return ScreenOut(ranking=screen_job(db, job_id))


@router.post("/jobs/{job_id}/runs", response_model=RunOut)
def create_screening_run(job_id: str, body: RunCreate, db: DbSession, org: CurrentOrg) -> RunOut:
    _job_in_org(db, org, job_id)
    if body.all:
        ids = [c.id for c in db.query(Candidate).filter(Candidate.job_id == job_id).all()]
    else:
        ids = list(body.candidate_ids)
        known = {c.id for c in db.query(Candidate).filter(Candidate.job_id == job_id).all()}
        unknown = [i for i in ids if i not in known]
        if unknown:
            raise HTTPException(422, f"unknown candidates for this job: {unknown}")
    run = create_run(db, job_id, ids)
    return RunOut(run_id=run.id, status=run.status, total=len(ids))


@router.get("/jobs/{job_id}/runs", response_model=list[RunDetail])
def list_runs(job_id: str, db: DbSession, org: CurrentOrg) -> list[RunDetail]:
    _job_in_org(db, org, job_id)
    runs = db.query(ScreeningRun).filter(ScreeningRun.job_id == job_id).order_by(ScreeningRun.created_at.desc()).all()
    return [RunDetail(run_id=r.id, job_id=r.job_id, status=r.status, total=len(r.candidate_ids),
                      done=len(r.done_ids), failed=len(r.failed_ids), error=r.error) for r in runs]


@router.get("/runs/{run_id}", response_model=RunDetail)
def run_detail(run_id: str, db: DbSession, org: CurrentOrg) -> RunDetail:
    run = db.get(ScreeningRun, run_id)
    if not run:
        raise HTTPException(404, "run not found")
    _job_in_org(db, org, run.job_id)
    return RunDetail(**get_run(db, run_id))


@router.get("/jobs/{job_id}/ranking", response_model=list[RankRow])
def ranking(job_id: str, db: DbSession, org: CurrentOrg) -> list[RankRow]:
    _job_in_org(db, org, job_id)
    rows = []
    for s in db.query(Score).filter(Score.job_id == job_id).order_by(Score.overall.desc()).all():
        cand = db.get(Candidate, s.candidate_id)
        tags = [t.tag for t in db.query(Tag).filter(Tag.job_id == job_id, Tag.candidate_id == s.candidate_id).all()]
        rows.append(RankRow(candidate_id=s.candidate_id, name=redact(cand.name if cand else "redacted"),
                            overall=s.overall, tags=tags))
    return rows


@router.get("/candidates/{candidate_id}", response_model=CandidateDetail)
def candidate_detail(candidate_id: str, db: DbSession, org: CurrentOrg) -> CandidateDetail:
    cand = _candidate_in_org(db, org, candidate_id)
    s = db.query(Score).filter(Score.candidate_id == candidate_id).first()
    tags = [t.tag for t in db.query(Tag).filter(Tag.candidate_id == candidate_id).all()]
    score = None
    if s:
        ev = [{"requirement_id": e.get("requirement_id", ""), "quote": redact(e.get("quote", ""), cand.name), "sub": e.get("sub", "")} for e in (s.evidence or [])]
        score = {"overall": s.overall, "subs": s.subs, "evidence": ev, "tags": tags}
    return CandidateDetail(candidate_id=cand.id, name=redact(cand.name, cand.name),
                           filename=_display_filename(cand.filename, cand.id), score=score)


@router.post("/candidates/{candidate_id}/schedule", response_model=ScheduleOut)
def schedule_stub(candidate_id: str, slot: str, db: DbSession, org: CurrentOrg) -> ScheduleOut:
    cand = _candidate_in_org(db, org, candidate_id)
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
