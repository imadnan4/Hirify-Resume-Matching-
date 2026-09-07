"""Screening runs: select N, queue, progress, resume (API + worker seams). TDD slice 2."""
import pytest
from app.api.deps import get_current_org
from app.api.rate_limit import reset_rate_limits
from app.core.db import Base, get_db
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBEDDING_BACKEND", "hash")
    monkeypatch.setenv("APPLY_RATE_LIMIT_PER_MIN", "1000")
    reset_rate_limits()
    url = f"sqlite:///{tmp_path}/t.db"
    eng = create_engine(url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=eng)
    TestingSession = sessionmaker(bind=eng, autoflush=False, autocommit=False)

    def override_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as c:
        c.db_session_factory = TestingSession  # type: ignore[attr-defined]
        yield c
    app.dependency_overrides.clear()


def _pdf():
    from io import BytesIO

    from reportlab.pdfgen import canvas

    buf = BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(50, 750, "Experience: Built FastAPI billing API for 3 yrs. Postgres daily.")
    c.save()
    return buf.getvalue()


def _setup(client, n=3):
    job = client.post("/jobs", json={
        "title": "Backend", "description": "REQ-1: 2+ yrs FastAPI\nREQ-2: Postgres",
    }).json()
    ids = []
    for i in range(n):
        r = client.post(f"/apply/{job['apply_token']}", data={
            "full_name": f"Cand {i}", "email": f"c{i}@example.com",
        }, files=[("cv", (f"c{i}.pdf", _pdf(), "application/pdf"))])
        ids.append(r.json()["applicant_id"])
    return job, ids


def test_create_run_with_selected_ids(client):
    job, ids = _setup(client)
    r = client.post(f"/jobs/{job['id']}/runs", json={"candidate_ids": ids[:2]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "queued" and body["total"] == 2


def test_create_run_all_snapshots_applicants(client):
    job, _ = _setup(client, n=3)
    body = client.post(f"/jobs/{job['id']}/runs", json={"all": True}).json()
    assert body["total"] == 3


def test_create_run_rejects_foreign_ids(client):
    job, _ = _setup(client, n=1)
    r = client.post(f"/jobs/{job['id']}/runs", json={"candidate_ids": ["deadbeef1234"]})
    assert r.status_code == 422


def test_drain_scores_everything_with_progress(client):
    from app.services.runner import drain_runs

    job, _ = _setup(client, n=3)
    run_id = client.post(f"/jobs/{job['id']}/runs", json={"all": True}).json()["run_id"]
    assert drain_runs(session_factory=client.db_session_factory) >= 1
    detail = client.get(f"/runs/{run_id}").json()
    assert detail["status"] == "done"
    assert detail["done"] == 3 and detail["failed"] == 0
    rows = client.get(f"/jobs/{job['id']}/ranking").json()
    assert len(rows) == 3


def test_drain_resumes_crashed_run(client):
    from app.models.tables import ScreeningRun
    from app.services.runner import drain_runs

    job, _ = _setup(client, n=3)
    run_id = client.post(f"/jobs/{job['id']}/runs", json={"all": True}).json()["run_id"]
    # Simulate a worker crash: stuck in running with no progress recorded.
    db = client.db_session_factory()
    try:
        row = db.get(ScreeningRun, run_id)
        row.status = "running"
        db.commit()
    finally:
        db.close()
    assert drain_runs(session_factory=client.db_session_factory) >= 1
    detail = client.get(f"/runs/{run_id}").json()
    assert detail["status"] == "done" and detail["done"] == 3


def test_failed_candidate_counted_not_lost(client, monkeypatch):
    import app.services.runner as runner_mod
    from app.services.runner import create_run, get_run

    job, ids = _setup(client, n=2)

    def boom(reqs, ctx):
        raise RuntimeError("gateway down")

    monkeypatch.setattr(runner_mod, "score_with_llm", boom)
    db = client.db_session_factory()
    try:
        run = create_run(db, job["id"], ids)
        from app.services.runner import _process_run

        _process_run(db, run, max_workers=1)
        assert sorted(run.failed_ids) == sorted(ids)
        assert get_run(db, run.id)["done"] == 0
        assert get_run(db, run.id)["status"] == "done"
    finally:
        db.close()


def test_runs_are_org_scoped(client):
    from app.models.tables import Organization

    job, _ = _setup(client, n=1)
    run_id = client.post(f"/jobs/{job['id']}/runs", json={"all": True}).json()["run_id"]
    app.dependency_overrides[get_current_org] = lambda: Organization(id="otherorg1234", name="Other")
    try:
        assert client.get(f"/jobs/{job['id']}/runs").status_code == 404
        assert client.get(f"/runs/{run_id}").status_code == 404
    finally:
        del app.dependency_overrides[get_current_org]
