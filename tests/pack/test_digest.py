import os

import pytest

from bridge.pack.digest import DigestError, tree_digest


def make(tmp_path, files):
    for name, data in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    return tmp_path


def test_same_tree_same_digest(tmp_path):
    a = make(tmp_path / "a", {"pack.yaml": b"id: x\n", "prompts/p.md": b"hi\n"})
    b = make(tmp_path / "b", {"prompts/p.md": b"hi\n", "pack.yaml": b"id: x\n"})
    assert tree_digest(a) == tree_digest(b)
    assert tree_digest(a).startswith("sha256:")


def test_content_change_changes_digest(tmp_path):
    a = make(tmp_path / "a", {"pack.yaml": b"id: x\n"})
    before = tree_digest(a)
    (a / "pack.yaml").write_bytes(b"id: y\n")
    assert tree_digest(a) != before


def test_rename_changes_digest(tmp_path):
    a = make(tmp_path / "a", {"one.md": b"same\n"})
    b = make(tmp_path / "b", {"two.md": b"same\n"})
    assert tree_digest(a) != tree_digest(b)


def test_path_and_content_cannot_be_confused(tmp_path):
    a = make(tmp_path / "a", {"ab": b"c"})
    b = make(tmp_path / "b", {"a": b"bc"})
    assert tree_digest(a) != tree_digest(b)


def test_crlf_text_file_rejected(tmp_path):
    a = make(tmp_path, {"workflow.yaml": b"name: x\r\n"})
    with pytest.raises(DigestError, match="CR byte"):
        tree_digest(a)


def test_cr_allowed_in_binary_file(tmp_path):
    a = make(tmp_path, {"logo.bin": b"\r\x00\x01"})
    assert tree_digest(a).startswith("sha256:")


def test_symlink_rejected(tmp_path):
    a = make(tmp_path / "a", {"real.md": b"x\n"})
    try:
        os.symlink(a / "real.md", a / "link.md")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not permitted on this system")
    with pytest.raises(DigestError, match="symlink"):
        tree_digest(a)


def test_missing_dir_rejected(tmp_path):
    with pytest.raises(DigestError, match="not a directory"):
        tree_digest(tmp_path / "nope")
