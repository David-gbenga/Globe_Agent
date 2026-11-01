"""BM25 over the markdown policies, chunked by `##` section.

Fifteen documents do not need a vector database. This is deliberate and is
not what we are assessing — you should not need to touch this file.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
_TOKEN = re.compile(r"[a-z0-9£]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


@dataclass
class Chunk:
    doc_id: str
    section: str
    text: str


def _chunk_document(path: Path) -> list[Chunk]:
    doc_id = path.stem
    raw = path.read_text(encoding="utf-8")
    parts = re.split(r"^## ", raw, flags=re.MULTILINE)
    chunks: list[Chunk] = []
    header = parts[0].strip()
    if header:
        chunks.append(Chunk(doc_id, "preamble", header))
    for part in parts[1:]:
        lines = part.splitlines()
        section = lines[0].strip() if lines else ""
        body = "\n".join(lines[1:]).strip()
        if body:
            chunks.append(Chunk(doc_id, section, f"## {section}\n{body}"))
    return chunks


@lru_cache(maxsize=1)
def _index() -> tuple[list[Chunk], list[Counter], dict[str, float], float]:
    chunks: list[Chunk] = []
    for path in sorted(DOCS_DIR.glob("*.md")):
        chunks.extend(_chunk_document(path))
    tfs = [Counter(tokenize(c.text)) for c in chunks]
    n = len(chunks)
    df: Counter = Counter()
    for tf in tfs:
        df.update(tf.keys())
    idf = {term: math.log(1 + (n - d + 0.5) / (d + 0.5)) for term, d in df.items()}
    avgdl = sum(sum(tf.values()) for tf in tfs) / max(n, 1)
    return chunks, tfs, idf, avgdl


def search(query: str, k: int = 4) -> list[Chunk]:
    chunks, tfs, idf, avgdl = _index()
    q = tokenize(query)
    k1, b = 1.5, 0.75
    scored = []
    for chunk, tf in zip(chunks, tfs):
        dl = sum(tf.values()) or 1
        score = 0.0
        for term in q:
            f = tf.get(term, 0)
            if not f:
                continue
            score += idf.get(term, 0.0) * (f * (k1 + 1)) / (f + k1 * (1 - b + b * dl / avgdl))
        if score > 0:
            scored.append((score, chunk))
    scored.sort(key=lambda x: -x[0])
    return [c for _, c in scored[:k]]
