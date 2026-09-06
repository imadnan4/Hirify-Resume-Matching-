"""Rubric math. Weights from config/rubric.yaml; KO tags cap overall at 40."""
from pathlib import Path

import yaml

RUBRIC_PATH = Path(__file__).resolve().parents[3] / "config" / "rubric.yaml"

SUBS = ["skills_match", "experience", "project_impact", "education", "cv_clarity"]

_DEFAULTS = {"skills_match": 35, "experience": 30, "project_impact": 20, "education": 5,
             "cv_clarity": 10, "ko_cap": 40,
             "knockouts": ["missing_work_auth", "below_min_years", "missing_required_credential"]}


def load_rubric() -> dict:
    if RUBRIC_PATH.exists():
        loaded = yaml.safe_load(RUBRIC_PATH.read_text())
        if isinstance(loaded, dict):
            return {**_DEFAULTS, **loaded}
    return dict(_DEFAULTS)


def apply_rubric(raw: dict) -> dict:
    r = load_rubric()
    subs = {k: max(0.0, min(100.0, float(raw.get(k, 0.0)))) for k in SUBS}
    total_w = sum(r.get(k, 0) for k in SUBS) or 100
    overall = sum(subs[k] * r.get(k, 0) / total_w for k in SUBS)
    tags = list(raw.get("tags", []))
    if any(t in r.get("knockouts", []) for t in tags):
        overall = min(overall, float(r.get("ko_cap", 40)))
    evidence = [e for e in raw.get("evidence", []) if e.get("quote")]
    return {"overall": round(overall, 1), "subs": subs, "tags": tags, "evidence": evidence}
