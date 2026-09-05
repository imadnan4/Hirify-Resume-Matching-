from fastapi.testclient import TestClient

from app.core.db import Base, engine
from app.main import app

Base.metadata.drop_all(bind=engine)
client = TestClient(app)


def test_flow_upload_screen_rank_detail():
    job = client.post("/jobs", json={"title": "Backend", "description": "REQ-1: 2+ yrs FastAPI\nREQ-2: Postgres"}).json()
    up = client.post(f"/jobs/{job['id']}/candidates:upload",
                     files=[("files", ("a.txt", b"Experience: Built FastAPI billing API for 3 yrs. Postgres daily.", "text/plain")),
                            ("files", ("b.txt", b"Experience: Junior designer, no backend.", "text/plain"))])
    assert len(up.json()["candidate_ids"]) == 2
    ranking = client.post(f"/jobs/{job['id']}/screen").json()["ranking"]
    assert ranking[0]["overall"] >= ranking[1]["overall"]
    rows = client.get(f"/jobs/{job['id']}/ranking").json()
    assert len(rows) == 2
    detail = client.get(f"/candidates/{ranking[0]['candidate_id']}").json()
    assert detail["score"]["evidence"]
    sched = client.post(f"/candidates/{ranking[0]['candidate_id']}/schedule", params={"slot": "2026-09-10T10:00Z"}).json()
    assert sched["ok"] is True
