"""Screening pipeline: retrieve top-k chunks per candidate -> LLM score -> rubric -> persist."""
from sqlalchemy.orm import Session

from app.models.tables import Candidate, Chunk, Job, Score, Tag
from app.services import embed as embed_mod
from app.services.chunker import chunk_cv, chunk_jd
from app.services.llm import score_with_llm
from app.services.redact import redact
from app.services.scoring import apply_rubric

TOP_K = 6


def index_job(db: Session, job: Job) -> None:
    reqs = chunk_jd(job.description)
    texts = [c["text"] for c in reqs]
    vecs = embed_mod.embed(texts)
    for c, v in zip(reqs, vecs):
        db.add(Chunk(job_id=job.id, candidate_id=f"job:{job.id}", requirement_id=c["requirement_id"],
                     section=c["section"], text=c["text"], embedding=v))
    db.commit()


def index_candidate(db: Session, cand: Candidate) -> None:
    parts = chunk_cv(cand.raw_text)
    vecs = embed_mod.embed([p["text"] for p in parts])
    for p, v in zip(parts, vecs):
        db.add(Chunk(job_id=cand.job_id, candidate_id=cand.id, requirement_id=p["requirement_id"],
                     section=p["section"], text=p["text"], embedding=v))
    db.commit()


def _topk(chunks: list[Chunk], job_vecs: list[list[float]], k: int = TOP_K) -> list[Chunk]:
    if not chunks or not all(c.embedding for c in chunks) or not job_vecs:
        return chunks[:k]
    qv = [sum(col) / len(job_vecs) for col in zip(*job_vecs)]
    scored = sorted(chunks, key=lambda c: -embed_mod.cosine(c.embedding, qv) if c.embedding else 0)
    return scored[:k]


def screen_job(db: Session, job_id: str) -> list[dict]:
    job = db.get(Job, job_id)
    # Batch-load once: job requirement chunks + all candidate chunks grouped in memory.
    job_chunks = db.query(Chunk).filter(
        Chunk.job_id == job_id, Chunk.candidate_id == f"job:{job_id}").all()
    reqs = [c.text for c in job_chunks] or [job.description]
    job_vecs = [c.embedding for c in job_chunks if c.embedding]
    by_cand: dict[str, list[Chunk]] = {}
    for c in db.query(Chunk).filter(
            Chunk.job_id == job_id, Chunk.candidate_id != f"job:{job_id}").all():
        by_cand.setdefault(c.candidate_id, []).append(c)
    ranking = []
    for cand in db.query(Candidate).filter(Candidate.job_id == job_id).all():
        ctx_chunks = _topk(by_cand.get(cand.id, []), job_vecs)
        ctx = redact("\n---\n".join(c.text for c in ctx_chunks) or cand.raw_text[:4000], cand.name)
        raw = score_with_llm(reqs, ctx)
        final = apply_rubric(raw)
        db.query(Score).filter(Score.job_id == job_id, Score.candidate_id == cand.id).delete()
        db.query(Tag).filter(Tag.job_id == job_id, Tag.candidate_id == cand.id).delete()
        db.add(Score(job_id=job_id, candidate_id=cand.id, overall=final["overall"],
                     subs=final["subs"], evidence=final["evidence"]))
        for t in final["tags"]:
            db.add(Tag(job_id=job_id, candidate_id=cand.id, tag=t))
        ranking.append({"candidate_id": cand.id, "overall": final["overall"], "tags": final["tags"]})
    db.commit()
    return sorted(ranking, key=lambda r: -r["overall"])
