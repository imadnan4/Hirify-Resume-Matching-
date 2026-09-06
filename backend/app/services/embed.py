"""embed() seam. Local MiniLM when installed, else deterministic hash fallback (384-dim).

Keeps RAG + tests runnable without torch. Set EMBEDDING_BACKEND=hash in CI.
"""
import hashlib
import math
import sys

from app.core.config import settings

DIM = 384
_model = None


def embed(texts: list[str]) -> list[list[float]]:
    if settings.EMBEDDING_BACKEND != "hash":
        try:
            return _minilm(texts)
        except ImportError:
            pass  # package absent: hash fallback is the documented CI/dev path
        except OSError as e:
            # model weights/cache unavailable: degraded but operable
            print(f"embed: MiniLM unavailable ({e}); falling back to hash vectors", file=sys.stderr)
    return [_hash_vec(t) for t in texts]


def _minilm(texts: list[str]) -> list[list[float]]:
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer("all-MiniLM-L6-v2")
    vecs = _model.encode(texts, normalize_embeddings=True)
    return [list(map(float, v)) for v in vecs]


def _hash_vec(text: str) -> list[float]:
    vals = [int(hashlib.sha256(f"{i}:{text}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF for i in range(DIM)]
    norm = math.sqrt(sum(v * v for v in vals)) or 1.0
    return [v / norm for v in vals]


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))
