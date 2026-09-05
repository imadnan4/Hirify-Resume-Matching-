"""Display-only PII redaction. Originals stay in DB."""
import re

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
PHONE = re.compile(r"\+?\d[\d\s().-]{7,}\d")


def redact(text: str, name: str = "") -> str:
    out = EMAIL.sub("[email]", text)
    out = PHONE.sub("[phone]", out)
    if name and len(name) > 2:
        out = out.replace(name, "[name]")
    return out
