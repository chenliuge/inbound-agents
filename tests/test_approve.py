import pytest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.approve import approve_file


def make_pending(tmp_path, agent="01-industry", content="正文"):
    pending = tmp_path / "pending"
    pending.mkdir(exist_ok=True)
    f = pending / f"2026-04-18_{agent}.md"
    f.write_text(
        f'---\nagent: {agent}\nstatus: pending\nreviewer: ""\nreview_note: ""\n---\n\n{content}',
        encoding="utf-8",
    )
    return f


def test_approve_moves_to_approved(tmp_path):
    src = make_pending(tmp_path)
    dest = approve_file(str(src))
    assert dest.exists()
    assert dest.parent.name == "approved"
    assert not src.exists()

def test_approve_updates_status(tmp_path):
    src = make_pending(tmp_path)
    dest = approve_file(str(src))
    assert "status: approved" in dest.read_text()

def test_approve_adds_reviewer(tmp_path):
    src = make_pending(tmp_path)
    dest = approve_file(str(src), reviewer="Nick")
    assert 'reviewer: "Nick"' in dest.read_text()

def test_approve_adds_note(tmp_path):
    src = make_pending(tmp_path)
    dest = approve_file(str(src), note="内容不错")
    assert "内容不错" in dest.read_text()

def test_approve_archives_previous(tmp_path):
    approved = tmp_path / "approved"
    approved.mkdir()
    old = approved / "old-01-industry.md"
    old.write_text("old", encoding="utf-8")
    src = make_pending(tmp_path)
    approve_file(str(src))
    assert (tmp_path / "archived" / "old-01-industry.md").exists()
    assert not old.exists()

def test_approve_rejects_non_pending(tmp_path):
    f = tmp_path / "somefile.md"
    f.write_text("content")
    with pytest.raises(ValueError):
        approve_file(str(f))

def test_approve_rejects_missing_file():
    with pytest.raises(FileNotFoundError):
        approve_file("nonexistent/pending/file.md")
