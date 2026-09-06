"""Chunking: JD by requirement bullets, CV by sections. ~400-600 tokens via chars."""
import re

REQ_RE = re.compile(r"^(?:REQ-\d+\s*[:\-–.]?\s*|[-*•]\s+|\d+[.)]\s+)(.+)", re.MULTILINE)
SECTION_RE = re.compile(r"^(experience|projects?|education|skills|summary|work history)[:\s]*$", re.MULTILINE | re.IGNORECASE)


def chunk_jd(description: str) -> list[dict]:
    lines = [ln.strip() for ln in description.splitlines() if ln.strip()]
    reqs = [m.group(1).strip() for ln in lines for m in [REQ_RE.match(ln)] if m]
    if not reqs:
        reqs = lines or [description.strip()]
    return [{"requirement_id": f"REQ-{i+1}", "section": "requirement", "text": t} for i, t in enumerate(reqs)]


def chunk_cv(text: str) -> list[dict]:
    parts = SECTION_RE.split(text)
    if len(parts) < 3:
        return _window(text, "body")
    out: list[dict] = []
    for i in range(1, len(parts), 2):
        out.extend(_window(parts[i + 1] if i + 1 < len(parts) else "", parts[i].lower()))
    return out or _window(text, "body")


def _window(text: str, section: str, size: int = 2200, overlap: int = 220) -> list[dict]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= size:
        return [{"requirement_id": "", "section": section, "text": text}]
    return [
        {"requirement_id": "", "section": section, "text": text[i : i + size]}
        for i in range(0, len(text), size - overlap)
    ]
