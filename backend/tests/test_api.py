import pytest
from app.core.db import Base, get_db
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBEDDING_BACKEND", "hash")
    url = f"sqlite:///{tmp_path}/t.db"
    eng = create_engine(url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=eng)
    TestingSession = sessionmaker(bind=eng, autoflush=False, autocommit=False)

    def override():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_flow_upload_screen_rank_detail(client):
    job = client.post("/jobs", json={"title": "Backend", "description": "REQ-1: 2+ yrs FastAPI\nREQ-2: Postgres"}).json()
    up = client.post(f"/jobs/{job['id']}/candidates:upload",
                     files=[("files", ("a.txt", b"Experience: Built FastAPI billing API for 3 yrs. Postgres daily.", "text/plain")),
                            ("files", ("b.txt", b"Experience: Junior designer, no backend.", "text/plain"))])
    first_id, second_id = up.json()["candidate_ids"]
    ranking = client.post(f"/jobs/{job['id']}/screen").json()["ranking"]
    assert ranking[0]["candidate_id"] == first_id
    assert ranking[0]["overall"] >= ranking[1]["overall"]
    assert ranking[1]["candidate_id"] == second_id
    rows = client.get(f"/jobs/{job['id']}/ranking").json()
    assert len(rows) == 2
    detail = client.get(f"/candidates/{first_id}").json()
    assert detail["score"]["evidence"]
    assert detail["filename"].startswith("cv-")
    sched = client.post(f"/candidates/{first_id}/schedule", params={"slot": "2026-09-10T10:00Z"}).json()
    assert sched["ok"] is True


def test_upload_rejects_oversize(client):
    job = client.post("/jobs", json={"title": "Backend", "description": "REQ-1: FastAPI"}).json()
    big = b"x" * (10 * 1024 * 1024 + 1)
    r = client.post(f"/jobs/{job['id']}/candidates:upload", files=[("files", ("big.txt", big, "text/plain"))])
    assert r.status_code == 413
