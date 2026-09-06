"""Seed + held-out generator. Real PDFs via reportlab, hand-check after.

Tiers are hand-graded 1-5 against the role JDs: 5 exceeds all REQs, 1 knock-out.
Held-out CVs are distinct people from seed (unseen), graded against backend.txt.
"""
import json
from pathlib import Path

from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[2]

JDS = {
    "backend.txt": "Backend Engineer (FastAPI)\nREQ-1: 2+ yrs FastAPI\nREQ-2: Postgres in production\nREQ-3: Docker + CI",
    "frontend.txt": "Frontend Engineer (React)\nREQ-1: 2+ yrs React\nREQ-2: Tailwind in production\nREQ-3: REST API integration",
    "data.txt": "Junior Data Analyst\nREQ-1: Python pandas\nREQ-2: SQL queries\nREQ-3: statistics basics",
}

SEED_CVS = {
    "be_staff": "Experience:\nStaff backend engineer, 7 yrs FastAPI at Acme. Postgres in production, query tuning. Docker, GitHub Actions CI.\nEducation:\nMSc CS",
    "be_mid": "Experience:\nBackend engineer, 3 yrs FastAPI at Beta. Postgres daily. Docker compose, CI pipelines.\nEducation:\nBSc CS",
    "be_junior": "Experience:\n1 yr FastAPI at a startup. Postgres basics, learning Docker.\nEducation:\nBSc CS",
    "be_nearmiss": "Experience:\nFlask developer 4 yrs, weekend FastAPI side project. MySQL, no Docker.\nEducation:\nBSc CS",
    "be_koyears": "Experience:\n3 months FastAPI bootcamp graduate. SQLite only.\nEducation:\nBSc CS",
    "be_designer": "Experience:\nSenior product designer, Figma, design systems. No backend.\nEducation:\nBA Design",
    "fe_senior": "Experience:\nSenior frontend engineer, 5 yrs React at Acme. Tailwind in production, design tokens. REST API integration daily.\nEducation:\nBSc CS",
    "fe_mid": "Experience:\nFrontend engineer, 3 yrs React. Tailwind on two launches. REST API integration.\nEducation:\nBSc CS",
    "fe_junior": "Experience:\n1 yr React internship. Tailwind basics, fetched REST endpoints.\nEducation:\nBSc CS",
    "fe_crossover": "Experience:\nBackend engineer 4 yrs, built one React dashboard. Bootstrap, not Tailwind. REST API design.\nEducation:\nBSc CS",
    "fe_ko": "Experience:\nPrint designer, InDesign. No React.\nEducation:\nBA Design",
    "da_senior": "Experience:\nData analyst, 4 yrs Python pandas at Acme. Complex SQL queries, window functions. A/B testing statistics.\nEducation:\nMSc Statistics",
    "da_intern": "Experience:\n6 month data internship. Python pandas notebooks. SQL queries on Postgres. Statistics coursework.\nEducation:\nBSc Math",
    "da_junior": "Experience:\n1 yr reporting analyst. Python pandas monthly reports. Basic SQL queries.\nEducation:\nBSc Economics",
    "da_excel": "Experience:\nExcel power user 5 yrs, pivot tables. No Python, no SQL.\nEducation:\nBBA",
    "da_ko": "Experience:\nTruck driver, logistics. No Python.\nEducation:\nHigh school",
}

HELDOUT_CVS = {
    "ho_staff": ("Experience:\nPrincipal engineer, 8 yrs FastAPI at Globex. Postgres in production at scale. Docker, CI ownership.\nEducation:\nMSc CS", 5),
    "ho_mid": ("Experience:\nBackend engineer, 4 yrs FastAPI. Postgres in production. Docker, CI.\nEducation:\nBSc CS", 4),
    "ho_mid2": ("Experience:\nBackend engineer, 3 yrs FastAPI at Initech. Postgres daily, Docker.\nEducation:\nBSc CS", 4),
    "ho_junior": ("Experience:\n1 yr FastAPI developer. Postgres basics. Learning Docker and CI.\nEducation:\nBSc CS", 3),
    "ho_junior2": ("Experience:\nFastAPI freelancer 1 yr. Postgres on side projects.\nEducation:\nBSc CS", 3),
    "ho_near": ("Experience:\nDjango developer 5 yrs, small FastAPI service. Postgres daily, no Docker.\nEducation:\nBSc CS", 2),
    "ho_near2": ("Experience:\nNode.js backend 3 yrs. Started learning FastAPI. MongoDB.\nEducation:\nBSc CS", 2),
    "ho_ko": ("Experience:\nQA tester manual, 2 yrs. No FastAPI, no Postgres.\nEducation:\nBSc CS", 1),
    "ho_wrong": ("Experience:\nPastry chef 6 yrs. No software.\nEducation:\nCulinary diploma", 1),
}


def _pdf(path: Path, text: str) -> None:
    c = canvas.Canvas(str(path))
    y = 750
    for line in text.splitlines():
        c.drawString(50, y, line[:100])
        y -= 16
    c.save()


def main() -> None:
    seed = ROOT / "data" / "seed"
    hocvs = ROOT / "data" / "eval" / "heldout" / "cvs"
    seed.mkdir(parents=True, exist_ok=True)
    hocvs.mkdir(parents=True, exist_ok=True)
    for stale in list(seed.glob("*.txt")) + list(hocvs.glob("*.txt")):
        stale.unlink()
    for pdf in seed.glob("*.pdf"):
        if not pdf.with_suffix(".txt").exists():
            pdf.unlink()
    (ROOT / "data" / "eval" / "heldout" / "job.txt").write_text(JDS["backend.txt"])
    for name, jd in JDS.items():
        (seed / name).write_text(jd)
    for slug, text in SEED_CVS.items():
        (seed / f"{slug}.txt").write_text(text)
        _pdf(seed / f"{slug}.pdf", text)
    grades = {}
    for slug, (text, grade) in HELDOUT_CVS.items():
        (hocvs / f"{slug}.txt").write_text(text)
        grades[slug] = grade
    (ROOT / "data" / "eval" / "heldout" / "labels.json").write_text(json.dumps({"grades": grades}, indent=1))
    print(f"seed ({len(SEED_CVS)} CVs, {len(JDS)} JDs) + heldout ({len(grades)} CVs) written")


if __name__ == "__main__":
    main()
