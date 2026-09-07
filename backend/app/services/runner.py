"""Background screening runs. HTTP never waits: runs queue, a worker drains them.

Crash-safe: progress (done_ids) commits per candidate; a run stuck in running
is reclaimed on the next drain. LLM fan-out is bounded by SCREEN_CONCURRENCY;
only the model call runs on worker threads, all DB writes stay on one session.
"""
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.models.tables import Candidate, ScreeningRun
from app.services.llm import score_with_llm
from app.services.pipeline import load_screening_context, persist_score, topk_chunks
from app.services.redact import redact
from app.services.scoring import apply_rubric


def _concurrency() -> int:
    try:
        return max(1, int(os.getenv("SCREEN_CONCURRENCY", "4")))
    except ValueError:
        return 4


def create_run(db: Session, job_id: str, candidate_ids: list[str]) -> ScreeningRun:
    run = ScreeningRun(job_id=job_id, candidate_ids=list(candidate_ids))
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def get_run(db: Session, run_id: str) -> dict:
    run = db.get(ScreeningRun, run_id)
    return {
        "run_id": run.id,
        "job_id": run.job_id,
        "status": run.status,
        "total": len(run.candidate_ids),
        "done": len(run.done_ids),
        "failed": len(run.failed_ids),
        "error": run.error,
    }


def _process_run(db: Session, run: ScreeningRun, max_workers: int | None = None) -> None:
    run.status = "running"
    db.commit()
    reqs, job_vecs, by_cand = load_screening_context(db, run.job_id)
    cands = {c.id: c for c in db.query(Candidate).filter(Candidate.id.in_(run.candidate_ids)).all()}
    pending = [cid for cid in run.candidate_ids if cid not in set(run.done_ids) | set(run.failed_ids)]
    contexts = {}
    for cid in pending:
        cand = cands.get(cid)
        if cand is None:
            continue
        chunks = by_cand.get(cid, [])
        ctx = redact("\n---\n".join(c.text for c in topk_chunks(chunks, job_vecs)) or cand.raw_text[:4000], cand.name)
        contexts[cid] = (cand, ctx)
    workers = max_workers or _concurrency()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(score_with_llm, reqs, ctx): cid for cid, (_, ctx) in contexts.items()}
        for fut in as_completed(futures):
            cid = futures[fut]
            try:
                final = apply_rubric(fut.result())
                persist_score(db, run.job_id, cid, final)
                run.done_ids = [*run.done_ids, cid]
            except Exception as e:  # noqa: BLE001 — one bad candidate must not kill the run
                run.failed_ids = [*run.failed_ids, cid]
                run.error = str(e)[:500]
            db.commit()
    # Candidates that vanished mid-run count as failed, never silently dropped.
    for cid in pending:
        if cid not in set(run.done_ids) | set(run.failed_ids):
            run.failed_ids = [*run.failed_ids, cid]
    run.status = "done"
    db.commit()


def drain_runs(session_factory=SessionLocal, max_workers: int | None = None) -> int:
    """Process every queued or crash-stuck run once. Returns runs handled."""
    db: Session = session_factory()
    try:
        runs = db.query(ScreeningRun).filter(ScreeningRun.status.in_(["queued", "running"])).all()
        for run in runs:
            _process_run(db, run, max_workers=max_workers)
        return len(runs)
    finally:
        db.close()
