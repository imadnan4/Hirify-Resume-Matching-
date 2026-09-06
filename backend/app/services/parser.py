"""Parse PDF/TXT uploads. pdfplumber primary, pypdf fallback."""
import sys
from io import BytesIO
from pathlib import Path


class UnsupportedUpload(ValueError):
    pass


def parse_upload(filename: str, data: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".txt":
        return data.decode("utf-8", errors="replace")
    if suffix == ".pdf":
        try:
            import pdfplumber

            with pdfplumber.open(BytesIO(data)) as pdf:
                return "\n".join((p.extract_text() or "") for p in pdf.pages).strip()
        except Exception as e:  # noqa: BLE001 — pdfplumber raises varied parse errors; pypdf is the fallback
            print(f"parser: pdfplumber failed ({e}); trying pypdf", file=sys.stderr)
            from pypdf import PdfReader

            reader = PdfReader(BytesIO(data))
            return "\n".join((p.extract_text() or "") for p in reader.pages).strip()
    raise UnsupportedUpload(f"unsupported upload type: {suffix} (use .pdf or .txt)")
