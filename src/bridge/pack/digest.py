"""Pack digest: SHA-256 over the raw bytes of every file in the pack tree.

The digest covers file paths and contents only. Certification, price and listing data live
outside the tree (signed side documents), so they can change without changing the digest.
Non-canonical input is rejected, never normalised: a CR byte in a text file, a symlink,
or a path that is not plain relative POSIX makes the pack invalid.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

TEXT_SUFFIXES = {".yaml", ".yml", ".json", ".md", ".txt", ".py", ".sh", ".toml"}
MAX_FILES = 2000


class DigestError(ValueError):
    pass


def _files(root: Path) -> list[Path]:
    out = []
    for p in sorted(root.rglob("*")):
        if p.is_symlink():
            raise DigestError(f"symlink not allowed: {p.relative_to(root).as_posix()}")
        if p.is_file():
            out.append(p)
    if len(out) > MAX_FILES:
        raise DigestError(f"too many files ({len(out)} > {MAX_FILES})")
    return out


def tree_digest(root: Path) -> str:
    """Return `sha256:<hex>` for the pack tree at `root`."""
    root = Path(root)
    if not root.is_dir():
        raise DigestError(f"not a directory: {root}")
    entries = []
    for p in _files(root):
        rel = p.relative_to(root).as_posix()
        if rel.startswith("/") or ".." in rel.split("/") or "\\" in rel or "\x00" in rel:
            raise DigestError(f"bad path: {rel!r}")
        data = p.read_bytes()
        if p.suffix.lower() in TEXT_SUFFIXES and b"\r" in data:
            raise DigestError(f"CR byte in text file (use LF only): {rel}")
        entries.append((rel.encode("utf-8"), hashlib.sha256(data).digest()))
    entries.sort()
    h = hashlib.sha256()
    for rel, file_hash in entries:
        h.update(len(rel).to_bytes(4, "big") + rel + file_hash)
    return "sha256:" + h.hexdigest()
