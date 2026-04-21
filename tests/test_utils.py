import time
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.utils import read_knowledge, read_approved, write_pending


# ── read_knowledge ────────────────────────────────────────────────

def test_read_knowledge_single_file(tmp_path):
    f = tmp_path / "A.md"
    f.write_text("hello", encoding="utf-8")
    assert read_knowledge(str(f)) == "hello"

def test_read_knowledge_directory_concatenates(tmp_path):
    (tmp_path / "A.md").write_text("aaa", encoding="utf-8")
    (tmp_path / "B.md").write_text("bbb", encoding="utf-8")
    result = read_knowledge(str(tmp_path))
    assert "aaa" in result and "bbb" in result

def test_read_knowledge_missing_returns_empty():
    assert read_knowledge("nonexistent/path/xyz") == ""


# ── read_approved ─────────────────────────────────────────────────

def test_read_approved_returns_most_recent(tmp_path):
    (tmp_path / "approved").mkdir()
    (tmp_path / "approved" / "old.md").write_text("old", encoding="utf-8")
    time.sleep(0.05)
    (tmp_path / "approved" / "new.md").write_text("new", encoding="utf-8")
    assert read_approved(str(tmp_path)) == "new"

def test_read_approved_empty_dir_returns_empty(tmp_path):
    (tmp_path / "approved").mkdir()
    assert read_approved(str(tmp_path)) == ""

def test_read_approved_no_dir_returns_empty(tmp_path):
    assert read_approved(str(tmp_path)) == ""


# ── write_pending ─────────────────────────────────────────────────

def test_write_pending_creates_file(tmp_path):
    p = write_pending(str(tmp_path), "内容", "01-industry", ["行业情报"])
    assert p.exists()

def test_write_pending_frontmatter(tmp_path):
    p = write_pending(str(tmp_path), "内容", "01-industry", ["行业情报"])
    text = p.read_text()
    assert "agent: 01-industry" in text
    assert "status: pending" in text
    assert "行业情报" in text

def test_write_pending_content_present(tmp_path):
    p = write_pending(str(tmp_path), "正文内容", "01-industry", [])
    assert "正文内容" in p.read_text()

def test_write_pending_no_overwrite(tmp_path):
    p1 = write_pending(str(tmp_path), "内容1", "01-industry", [])
    p2 = write_pending(str(tmp_path), "内容2", "01-industry", [])
    assert p1 != p2

def test_write_pending_output_type(tmp_path):
    p = write_pending(str(tmp_path), "内容", "03-sales", [], output_type="sales-support")
    assert "output_type: sales-support" in p.read_text()
