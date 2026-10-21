"""Long notes: a note of any realistic length is kept whole, and stored as short passages a helper can pick from.

A person may paste a whole meeting log, a project brief or a diary month. It is saved as ONE note (a "document") that
the manager shows and edits as one piece. Underneath, it is cut at paragraph and heading boundaries into passages of at
most CHUNK characters, so a helper that asks about one thing is handed the few passages that matter, not the whole text.
Putting the passages back together with blank lines gives the note as it was written.
"""
from __future__ import annotations

import re

MAX_DOC = 80_000  # characters in one note
CHUNK = 1200  # characters in one passage
SHORT = 1500  # a note up to this length stays a single record
MAX_PARTS = 120


def _cut(p: str) -> int:
    for sep in (". ", "\n", "; ", ", ", " "):
        at = p.rfind(sep, CHUNK // 2, CHUNK)
        if at > 0:
            return at + len(sep.rstrip()) if sep != " " else at
    return CHUNK


def split_document(text: str) -> list[str]:
    text = text.replace("\r\n", "\n").strip()
    pieces: list[str] = []
    for para in (p.strip() for p in re.split(r"\n\s*\n", text)):
        while len(para) > CHUNK:
            at = _cut(para)
            pieces.append(para[:at].strip())
            para = para[at:].strip()
        if para:
            pieces.append(para)
    chunks: list[str] = []
    cur = ""
    for piece in pieces:
        heading = piece.startswith("#")
        if cur and (len(cur) + 2 + len(piece) > CHUNK or (heading and len(cur) > 300)):
            chunks.append(cur)
            cur = piece
        else:
            cur = cur + "\n\n" + piece if cur else piece
    if cur:
        chunks.append(cur)
    return chunks


def join_document(parts: list[str]) -> str:
    return "\n\n".join(parts)


def guess_title(text: str) -> str:
    for line in text.strip().splitlines():
        line = line.strip().lstrip("#").strip()
        if line:
            return line[:80]
    return "Untitled note"
