"""Qwen via xkiro OpenAI-compatible gateway. Tools-first, JSON fallback, fixture mode.

No key (CI) -> deterministic fixture scorer so tests never need secrets.
"""
import json
import os
from pathlib import Path

SYSTEM = (Path(__file__).resolve().parents[3] / "prompts" / "screen_system.md").read_text() if (
    Path(__file__).resolve().parents[3] / "prompts" / "screen_system.md"
).exists() else "Score the candidate. Use the tool."

SCORE_TOOL = {
    "type": "function",
    "function": {
        "name": "score_candidate",
        "description": "Score candidate vs JD with evidence quotes",
        "parameters": {
            "type": "object",
            "properties": {
                "overall": {"type": "number", "minimum": 0, "maximum": 100},
                "skills_match": {"type": "number", "minimum": 0, "maximum": 100},
                "experience": {"type": "number", "minimum": 0, "maximum": 100},
                "project_impact": {"type": "number", "minimum": 0, "maximum": 100},
                "education": {"type": "number", "minimum": 0, "maximum": 100},
                "cv_clarity": {"type": "number", "minimum": 0, "maximum": 100},
                "tags": {"type": "array", "items": {"type": "string"}},
                "evidence": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "requirement_id": {"type": "string"},
                            "quote": {"type": "string"},
                            "sub": {"type": "string"},
                        },
                        "required": ["requirement_id", "quote"],
                    },
                },
            },
            "required": ["overall", "skills_match", "experience", "project_impact", "education", "cv_clarity", "evidence"],
        },
    },
}


def score_with_llm(jd_reqs: list[str], cv_context: str) -> dict:
    if not os.getenv("XKIRO_API_KEY"):
        return _fixture(jd_reqs, cv_context)
    from openai import OpenAI

    client = OpenAI(base_url=os.getenv("XKIRO_BASE_URL"), api_key=os.getenv("XKIRO_API_KEY"))
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"Requirements:\n{chr(10).join(jd_reqs)}\n\nCandidate context:\n{cv_context}\n\nScore 0-100 via score_candidate."},
    ]
    try:
        msg = client.chat.completions.create(
            model=os.getenv("QWEN_MODEL", "qwen/qwen3.8-max:free"),
            messages=messages, tools=[SCORE_TOOL], tool_choice="auto", temperature=0,
        ).choices[0].message
        if msg.tool_calls:
            return _validated(json.loads(msg.tool_calls[0].function.arguments), jd_reqs, cv_context)
    except Exception:
        pass
    try:
        txt = client.chat.completions.create(
            model=os.getenv("QWEN_MODEL", "qwen/qwen3.8-max:free"),
            messages=messages + [{"role": "system", "content": "Return ONLY the score_candidate JSON object."}],
            response_format={"type": "json_object"}, temperature=0,
        ).choices[0].message.content or "{}"
        return _validated(json.loads(txt), jd_reqs, cv_context)
    except Exception:
        return _fixture(jd_reqs, cv_context)


def _validated(raw: object, jd_reqs: list[str], cv_context: str) -> dict:
    """Gateway output is best-effort: malformed payloads fall back to the fixture."""
    if not isinstance(raw, dict):
        return _fixture(jd_reqs, cv_context)
    for key in ("overall", "skills_match", "experience", "project_impact", "education", "cv_clarity"):
        if not isinstance(raw.get(key), (int, float)) or isinstance(raw.get(key), bool):
            return _fixture(jd_reqs, cv_context)
    if not isinstance(raw.get("evidence", []), list):
        return _fixture(jd_reqs, cv_context)
    for item in raw.get("evidence", []):
        if not isinstance(item, dict) or not isinstance(item.get("quote"), str):
            return _fixture(jd_reqs, cv_context)
    tags = raw.get("tags", [])
    if not isinstance(tags, list) or any(not isinstance(t, str) for t in tags):
        return _fixture(jd_reqs, cv_context)
    return raw


def _fixture(jd_reqs: list[str], cv_context: str) -> dict:
    """Deterministic offline scorer: keyword overlap per requirement, quoted."""
    import re

    words = set(re.findall(r"[a-z]{3,}", cv_context.lower()))
    ev, hits = [], 0
    for i, req in enumerate(jd_reqs, 1):
        keys = set(re.findall(r"[a-z]{3,}", req.lower())) - {"with", "and", "the", "for", "yrs", "years"}
        if keys & words:
            hits += 1
            snippet = cv_context[:160].replace("\n", " ")
            ev.append({"requirement_id": f"REQ-{i}", "quote": snippet, "sub": "skills_match"})
    base = 100 * hits / max(len(jd_reqs), 1)
    return {
        "overall": round(base, 1), "skills_match": round(base, 1),
        "experience": round(max(0, base - 10), 1), "project_impact": round(max(0, base - 15), 1),
        "education": 50.0, "cv_clarity": 60.0, "tags": [], "evidence": ev,
    }
