from lab import learning


def test_queue_roundtrip(tmp_path):
    p = learning.enqueue("linguist", "제목", "설명", None, base=tmp_path)
    items = learning.pending_items(base=tmp_path)
    assert [i[1]["role"] for i in items] == ["linguist"]
    learning.mark_sent(p, base=tmp_path)
    assert learning.pending_items(base=tmp_path) == []
    assert (tmp_path / "sent" / p.name).exists()


def test_literature_report_fits_embed():
    md = (learning.ROOT / "knowledge/literature/lm.md").read_text(encoding="utf-8")
    title, desc = learning.literature_report(md)
    assert "15편" in title
    assert len(desc) <= learning.MAX_DESC
    assert "15." in desc


def test_attachment_stays_inside_repo():
    assert learning.attachment({"file": "../../etc/passwd"}) is None
    assert learning.attachment({"file": "knowledge/literature/lm.md"}) is not None
