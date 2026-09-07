"""Public apply intake + org-scoped jobs (API seam). TDD slice 1."""
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
        yield c
    app.dependency_overrides.clear()


def _pdf_bytes(text="Experience: Built FastAPI billing API for 3 yrs. Postgres daily."):
    from io import BytesIO

    from reportlab.pdfgen import canvas

    buf = BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(50, 750, text[:100])
    c.save()
    return buf.getvalue()


def _job(client, title="Backend"):
    return client.post("/jobs", json={
        "title": title,
        "description": "REQ-1: 2+ yrs FastAPI\nREQ-2: Postgres",
    }).json()


def test_job_carries_shareable_apply_token(client):
    job = _job(client)
    assert job["apply_token"] and len(job["apply_token"]) >= 16
    assert job["status"] == "open"


def test_jobs_list_reports_applicant_counts(client):
    job = _job(client)
    rows = client.get("/jobs").json()
    assert any(r["id"] == job["id"] and r["applicant_count"] == 0 for r in rows)
    client.post(f"/apply/{job['apply_token']}", data={
        "full_name": "Ada", "email": "ada@example.com",
    }, files=[("cv", ("ada.pdf", _pdf_bytes(), "application/pdf"))])
    rows = client.get("/jobs").json()
    assert any(r["id"] == job["id"] and r["applicant_count"] == 1 for r in rows)


def test_apply_happy_path_with_optional_phone(client):
    job = _job(client)
    r = client.post(f"/apply/{job['apply_token']}", data={
        "full_name": "Ada Lovelace", "email": "ada@example.com", "phone": "+92-300-1234567",
    }, files=[("cv", ("ada.pdf", _pdf_bytes(), "application/pdf"))])
    assert r.status_code == 200, r.text
    applicant_id = r.json()["applicant_id"]
    rows = client.get(f"/jobs/{job['id']}/applicants").json()
    assert any(a["candidate_id"] == applicant_id and a["email"] == "ada@example.com"
               and a["phone"] == "+92-300-1234567" for a in rows)


def test_apply_rejects_unknown_token(client):
    r = client.post("/apply/nope-not-a-token", data={
        "full_name": "X", "email": "x@example.com",
    }, files=[("cv", ("x.pdf", _pdf_bytes(), "application/pdf"))])
    assert r.status_code == 404


def test_apply_rejects_non_pdf(client):
    job = _job(client)
    r = client.post(f"/apply/{job['apply_token']}", data={
        "full_name": "X", "email": "x@example.com",
    }, files=[("cv", ("x.txt", b"plain text cv", "text/plain"))])
    assert r.status_code == 400


def test_apply_requires_name_and_email(client):
    job = _job(client)
    r = client.post(f"/apply/{job['apply_token']}", data={"full_name": "", "email": "not-an-email"},
                    files=[("cv", ("x.pdf", _pdf_bytes(), "application/pdf"))])
    assert r.status_code == 422


def test_closed_job_refuses_applications(client):
    job = _job(client)
    assert client.patch(f"/jobs/{job['id']}", json={"status": "closed"}).status_code == 200
    r = client.post(f"/apply/{job['apply_token']}", data={
        "full_name": "Late", "email": "late@example.com",
    }, files=[("cv", ("late.pdf", _pdf_bytes(), "application/pdf"))])
    assert r.status_code == 410


def test_rotate_link_invalidates_old_token(client):
    job = _job(client)
    old = job["apply_token"]
    new = client.post(f"/jobs/{job['id']}/rotate-link").json()["apply_token"]
    assert new != old
    payload = {"full_name": "X", "email": "x@example.com"}
    files = [("cv", ("x.pdf", _pdf_bytes(), "application/pdf"))]
    assert client.post(f"/apply/{old}", data=payload, files=files).status_code == 404
    assert client.post(f"/apply/{new}", data=payload, files=files).status_code == 200


def test_public_job_lookup_for_apply_page(client):
    job = _job(client)
    body = client.get(f"/apply/{job['apply_token']}/job").json()
    assert body["title"] == "Backend" and "REQ-1" in body["description"]
    assert body["status"] == "open"
    assert "apply_token" not in body
    assert client.get("/apply/nope-not-a-token/job").status_code == 404


def test_org_isolation_between_workspaces(client):
    from app.models.tables import Organization

    job = _job(client)
    client.post(f"/apply/{job['apply_token']}", data={
        "full_name": "Ada", "email": "ada@example.com",
    }, files=[("cv", ("ada.pdf", _pdf_bytes(), "application/pdf"))])

    other = Organization(id="otherorg1234", name="Other")
    app.dependency_overrides[get_current_org] = lambda: other
    try:
        assert client.get("/jobs").json() == []
        assert client.get(f"/jobs/{job['id']}/applicants").status_code == 404
    finally:
        del app.dependency_overrides[get_current_org]


def test_apply_rate_limit(client, monkeypatch):
    monkeypatch.setenv("APPLY_RATE_LIMIT_PER_MIN", "2")
    job = _job(client)
    payload = {"full_name": "X", "email": "x@example.com"}

    def files():
        return [("cv", ("x.pdf", _pdf_bytes(), "application/pdf"))]

    assert client.post(f"/apply/{job['apply_token']}", data=payload, files=files()).status_code == 200
    assert client.post(f"/apply/{job['apply_token']}", data=payload, files=files()).status_code == 200
    assert client.post(f"/apply/{job['apply_token']}", data=payload, files=files()).status_code == 429
