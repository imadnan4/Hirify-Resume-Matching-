from app.services.chunker import chunk_cv, chunk_jd
from app.services.parser import parse_upload
from app.services.scoring import apply_rubric


def test_chunk_jd_by_requirement():
    chunks = chunk_jd("Title\nREQ-1: 2+ yrs FastAPI\nREQ-2: Postgres")
    assert [c["requirement_id"] for c in chunks] == ["REQ-1", "REQ-2"]
    assert chunks[0]["text"] == "2+ yrs FastAPI"


def test_chunk_cv_sections():
    chunks = chunk_cv("Experience:\nBuilt APIs for 3 yrs\nEducation:\nBSc CS")
    assert {c["section"] for c in chunks} >= {"experience", "education"}


def test_parse_txt():
    assert parse_upload("cv.txt", b"hello") == "hello"


def test_ko_cap():
    out = apply_rubric({"skills_match": 90, "experience": 90, "project_impact": 90,
                        "education": 90, "cv_clarity": 90,
                        "tags": ["below_min_years"], "evidence": [{"quote": "x", "requirement_id": "REQ-1"}]})
    assert out["overall"] <= 40
    assert out["evidence"]
