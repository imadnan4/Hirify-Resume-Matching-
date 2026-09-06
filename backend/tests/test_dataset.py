"""Dataset contract (data seam): full seed + held-out layout from the grilled plan."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "data" / "seed"
HELD = ROOT / "data" / "eval" / "heldout"

JOBS = {"backend": "be_", "frontend": "fe_", "data": "da_"}


def test_seed_has_three_job_descriptions():
    for role in JOBS:
        assert (SEED / f"{role}.txt").exists(), f"missing seed JD for {role}"


def test_seed_has_five_plus_cvs_per_role():
    import json

    labels = json.loads((HELD / "labels.json").read_text())
    for role, prefix in JOBS.items():
        cvs = sorted(SEED.glob(f"{prefix}*.txt"))
        assert len(cvs) >= 5, f"{role}: only {len(cvs)} seed CVs"
        assert {c.stem for c in cvs} != set(labels["grades"]), "seed must differ from held-out"


def test_heldout_has_graded_unseen_cvs():
    import json

    cvs = sorted((HELD / "cvs").glob("*.txt"))
    assert 8 <= len(cvs) <= 10, f"held-out needs 8-10 CVs, has {len(cvs)}"
    assert (HELD / "job.txt").exists()
    labels = json.loads((HELD / "labels.json").read_text())
    assert {c.stem for c in cvs} == set(labels["grades"]), "every held-out CV needs a hand grade"
    assert len(set(labels["grades"].values())) >= 3, "grades must span at least 3 tiers"
