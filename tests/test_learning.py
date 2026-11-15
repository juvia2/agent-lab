from lab import learning


def test_queue_roundtrip(tmp_path):
    p = learning.enqueue("linguist", "제목", "설명", None, base=tmp_path)
    items = learning.pending_items(base=tmp_path)
    assert [i[1]["role"] for i in items] == ["linguist"]
    learning.mark_sent(p, base=tmp_path)
    assert learning.pending_items(base=tmp_path) == []
    assert (tmp_path / "sent" / p.name).exists()


def test_grouped_reports_share_one_thread(tmp_path):
    head = learning.enqueue("director", "요약", "d", None, base=tmp_path, group="run1")
    rest = learning.enqueue("linguist", "02", "d", None, base=tmp_path, group="run1")
    solo = learning.enqueue("lm", "단독", "d", None, base=tmp_path)
    items = dict(learning.pending_items(base=tmp_path))
    assert learning.thread_for(items[head], base=tmp_path) is None      # 첫 보고는 채널에
    learning.remember_thread("run1", 42, base=tmp_path)
    assert learning.thread_for(items[rest], base=tmp_path) == 42        # 나머지는 그 스레드로
    assert learning.thread_for(items[solo], base=tmp_path) is None      # 묶음 없는 보고는 그대로 채널
    assert learning.pending_items(base=tmp_path)[0][0] == head           # 요약이 먼저 나간다


def test_literature_report_fits_embed():
    md = (learning.ROOT / "knowledge/literature/lm.md").read_text(encoding="utf-8")
    title, desc = learning.literature_report(md)
    assert "15편" in title
    assert len(desc) <= learning.MAX_DESC
    assert "15." in desc


def test_attachment_stays_inside_repo():
    assert learning.attachment({"file": "../../etc/passwd"}) is None
    assert learning.attachment({"file": "knowledge/literature/lm.md"}) is not None
