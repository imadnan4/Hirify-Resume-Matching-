"""Seed + held-out generator. Real PDFs via reportlab, hand-check after."""
from pathlib import Path

from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[2]


CVS = {
    "backend": [
        ("senior_fastapi", "Experience:\nBuilt FastAPI billing API for 5 yrs at Acme. Postgres daily, Docker, CI.\nEducation:\nBSc CS"),
        ("junior_fastapi", "Experience:\n6 months FastAPI internship, Postgres basics.\nEducation:\nBSc CS"),
        ("designer_ko", "Experience:\nSenior product designer, Figma, no backend.\nEducation:\nBA Design"),
    ],
}

JDS = {
    "backend.txt": "Backend Engineer (FastAPI)\nREQ-1: 2+ yrs FastAPI\nREQ-2: Postgres in production\nREQ-3: Docker + CI",
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
    held = ROOT / "data" / "eval" / "heldout" / "cvs"
    seed.mkdir(parents=True, exist_ok=True)
    held.mkdir(parents=True, exist_ok=True)
    for name, jd in JDS.items():
        (ROOT / "data" / "eval" / "heldout" / "job.txt").parent.mkdir(parents=True, exist_ok=True)
        (ROOT / "data" / "eval" / "heldout" / "job.txt").write_text(jd)
        (seed / name).write_text(jd)
    for role, cvs in CVS.items():
        for slug, text in cvs:
            (seed / f"{role}_{slug}.txt").write_text(text)
            (held / f"{slug}.txt").write_text(text)
            _pdf(seed / f"{role}_{slug}.pdf", text)
    import json

    (ROOT / "data" / "eval" / "heldout" / "labels.json").write_text(json.dumps(
        {"grades": {"senior_fastapi": 5, "junior_fastapi": 3, "designer_ko": 1}}, indent=1))
    print("seed + heldout written")


if __name__ == "__main__":
    main()
