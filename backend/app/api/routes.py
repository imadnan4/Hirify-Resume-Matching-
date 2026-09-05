"""REST surface consumed by the frontend agent. See /docs/BACKEND_API.md for examples."""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.db import get_db, init_db
from app.models.tables import Candidate, InterviewStub, Job, Score, Tag
from app.schemas.io import CandidateDetail, JobCreate, JobOut, RankRow, ScoreOut
from app.services.parser import UnsupportedUpload, parse_upload
from app.services.pipeline import index_candidate, index_job, screen_job
from app.services.redact import redact

router = APIRouter()


@router.post("/jobs", response_model=JobOut)
def create_job(body: JobCreate, db: Session = Depends(get_db)):
    init_db()
    job = Job(title=body.title, description=body.description)
    db.add(job)
    db.commit()
    db.refresh(job)
    index_job(db, job)
    return {"id": job.id, "title": job.title}


@router.post("/jobs/{job_id}/candidates:upload")
async def upload_candidates(job_id: str, files: list[UploadFile] = File(...), db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "job not found")
    ids = []
    for f in files:
        data = await f.read()
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
    return {"candidate_ids": ids}


@router.post("/jobs/{job_id}/screen")
def screen(job_id: str, db: Session = Depends(get_db)):
    if not db.get(Job, job_id):
        raise HTTPException(404, "job not found")
    return {"ranking": screen_job(db, job_id)}


@router.get("/jobs/{job_id}/ranking", response_model=list[RankRow])
def ranking(job_id: str, db: Session = Depends(get_db)):
    rows = []
    for s in db.query(Score).filter(Score.job_id == job_id).order_by(Score.overall.desc()).all():
        cand = db.get(Candidate, s.candidate_id)
        tags = [t.tag for t in db.query(Tag).filter(Tag.job_id == job_id, Tag.candidate_id == s.candidate_id).all()]
        rows.append({"candidate_id": s.candidate_id, "name": redact(cand.name if cand else "redacted"), "overall": s.overall, "tags": tags})
    return rows


@router.get("/candidates/{candidate_id}", response_model=CandidateDetail)
def candidate_detail(candidate_id: str, db: Session = Depends(get_db)):
    cand = db.get(Candidate, candidate_id)
    if not cand:
        raise HTTPException(404, "candidate not found")
    s = db.query(Score).filter(Score.candidate_id == candidate_id).first()
    tags = [t.tag for t in db.query(Tag).filter(Tag.candidate_id == candidate_id).all()]
    score = None
    if s:
        ev = [{"requirement_id": e.get("requirement_id", ""), "quote": redact(e.get("quote", ""), cand.name), "sub": e.get("sub", "")} for e in (s.evidence or [])]
        score = {"overall": s.overall, "subs": s.subs, "evidence": ev, "tags": tags}
    return {"candidate_id": cand.id, "name": redact(cand.name, cand.name), "filename": cand.filename, "score": score}


@router.post("/candidates/{candidate_id}/schedule")
def schedule_stub(candidate_id: str, slot: str, db: Session = Depends(get_db)):
    cand = db.get(Candidate, candidate_id)
    if not cand:
        raise HTTPException(404, "candidate not found")
    row = InterviewStub(job_id=cand.job_id, candidate_id=candidate_id, slot=slot)
    db.add(row)
    db.commit()
    return {"ok": True, "slot": slot}


@router.get("/eval")
def eval_latest(db: Session = Depends(get_db)):
    from pathlib import Path
    import json

    for p in [Path("evals/results.json"), Path("backend/evals-results.json")]:
        if p.exists():
            return json.loads(p.read_text())
    return {"detail": "no eval run yet; run python evals/run.py"}
