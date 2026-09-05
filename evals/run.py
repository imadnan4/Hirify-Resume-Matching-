"""Hirify backend eval harness. Reads data/eval/heldout, writes results.json + results.md."""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.llm import score_with_llm  # noqa: E402
from app.services.scoring import apply_rubric  # noqa: E402


def precision_at_k(ranked: list[str], relevant: set[str], k: int) -> float:
    top = ranked[:k]
    return sum(1 for c in top if c in relevant) / max(k, 1)


def dcg(ranked: list[str], grades: dict[str, float], k: int) -> float:
    return sum((2 ** grades.get(c, 0) - 1) / math.log2(i + 2) for i, c in enumerate(ranked[:k]))


def ndcg(ranked: list[str], grades: dict[str, float], k: int) -> float:
    ideal = sorted(grades, key=lambda c: -grades[c])
    denom = dcg(ideal, grades, k)
    return (dcg(ranked, grades, k) / denom) if denom else 0.0


def spearman(a: list[str], b: list[str]) -> float:
    rank_a = {c: i for i, c in enumerate(a)}
    rank_b = {c: i for i, c in enumerate(b)}
    common = [c for c in a if c in rank_b]
    n = len(common)
    if n < 2:
        return 0.0
    diff = sum((rank_a[c] - rank_b[c]) ** 2 for c in common)
    return 1 - 6 * diff / (n * (n * n - 1))


def main() -> None:
    held = ROOT / "data" / "eval" / "heldout"
    labels = json.loads((held / "labels.json").read_text())
    grades: dict[str, float] = labels["grades"]
    truth_rank = sorted(grades, key=lambda c: -grades[c])
    jd_reqs = (held / "job.txt").read_text().splitlines()

    scored = []
    uncited = 0
    for cv_file in sorted((held / "cvs").glob("*.txt")):
        cid = cv_file.stem
        raw = score_with_llm(jd_reqs, cv_file.read_text())
        final = apply_rubric(raw)
        scored.append((cid, final["overall"]))
        if not final["evidence"]:
            uncited += 1
    scored.sort(key=lambda kv: -kv[1])
    ranked = [c for c, _ in scored]
    relevant = {c for c, g in grades.items() if g >= 4}

    out = {
        "ranked": ranked,
        "scores": {c: s for c, s in scored},
        "precision@3": round(precision_at_k(ranked, relevant, 3), 3),
        "ndcg@5": round(ndcg(ranked, grades, 5), 3),
        "spearman": round(spearman(ranked, truth_rank), 3),
        "faithfulness": {"uncited_claims": uncited, "total": len(scored)},
        "pass_bar": {"ndcg@5_bar": 0.75, "zero_uncited": True},
        "pass": ndcg(ranked, grades, 5) >= 0.75 and uncited == 0,
    }
    (ROOT / "evals").mkdir(exist_ok=True)
    (ROOT / "evals" / "results.json").write_text(json.dumps(out, indent=1))
    (ROOT / "evals" / "results.md").write_text(
        "# Eval results\n\n"
        + "\n".join(f"- {k}: {v}" for k, v in out.items() if k in ("precision@3", "ndcg@5", "spearman"))
        + f"\n- uncited: {uncited}/{len(scored)}\n- PASS: {out['pass']}\n"
    )
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
