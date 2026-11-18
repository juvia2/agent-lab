import dataclasses
import json

from lab import growth, memory, reading
from lab.agents import system_for
from lab.config import Config
from lab.policy import load_policy


def _cfg(tmp_path):
    cfg = dataclasses.replace(Config.from_env(), lab_home=tmp_path / "lab")
    cfg.ensure_dirs()
    return cfg


def _paper(store, pid, text):
    d = store.dir(pid) / "inputs"
    d.mkdir(parents=True, exist_ok=True)
    (d / "paper.pdf.txt").write_text(text, encoding="utf-8")


def test_session_roundtrip_and_paper_tools(tmp_path):
    cfg = _cfg(tmp_path)
    st = reading.ReadingStore(cfg)
    pid = st.new(note="구문 처리 관점으로 보고 싶어")
    assert pid == "P-001" and st.new() == "P-002"
    st.update(pid, thread_id=99, title="Garden paths in LMs", tags=["surprisal", "구문처리"])
    assert st.find_by_thread(99)["id"] == pid
    _paper(st, pid, "--- 1쪽 ---\nWe test garden-path sentences.\n\n--- 2쪽 ---\nSurprisal underestimates the reanalysis cost.")
    box = reading.ReadingBox(cfg, pid, "linguist")
    assert "reanalysis" in box.execute("search_paper", {"query": "reanalysis cost"}).text
    assert "1쪽" in box.execute("read_paper", {}).text
    empty = reading.ReadingBox(cfg, "P-002", "lm").execute("read_paper", {})
    assert empty.is_error                                   # 본문 없으면 지어내지 않게 오류로 알린다
    st.log(pid, "연구자", "왜 surprisal 이 과소추정해?")
    assert "과소추정" in st.history_text(pid)


def test_lens_stated_goes_to_every_agent_prompt(tmp_path):
    cfg = _cfg(tmp_path)
    box = reading.ReadingBox(cfg, "P-001", "cogsci")
    out = box.execute("record_research_lens", {"text": "구문 처리는 빈도보다 구조적 설명에 무게를 둔다",
                                               "category": "이론적입장", "stated": True, "evidence": "내 입장은 구조 쪽이야"})
    assert out.text.startswith("stated")
    for role in ("statistician", "developer"):              # 리딩에 안 들어온 역할도 메인 실험에서 같은 지향을 본다
        assert "구조적 설명에 무게" in system_for(role, cfg)
    assert "연구 지향" in growth.summary(cfg)


def test_lens_inferred_needs_confirmation(tmp_path):
    cfg = _cfg(tmp_path)
    box = reading.ReadingBox(cfg, "P-001", "lm")
    for _ in range(cfg.learn_threshold):
        box.execute("record_research_lens", {"text": "통계 검정력 질문을 자주 한다", "category": "방법론"})
    assert "통계 검정력" not in system_for("lm", cfg)       # 확인 전에는 지시로 들어가지 않는다
    assert box.footer().startswith("**학습 후보 확인 요청**")
    cid = growth.due(cfg)[0]["id"]
    growth.approve(cfg, cid)
    assert "통계 검정력" in system_for("lm", cfg)


def test_parse_select_and_answer():
    title, tags, tutors, note = reading.parse_select(
        "TITLE: Syntactic Surprisal\nTAGS: surprisal, 구문처리\nTUTORS: cogsci, developer, linguist, lm, tester\n"
        "인지·언어학 관점이 핵심이라 둘이 맡습니다.")
    assert title == "Syntactic Surprisal" and tags == ["surprisal", "구문처리"]
    assert tutors == ["cogsci", "linguist", "lm"]          # 튜터 풀 밖(developer) 제외, 최대 3명, 리드 먼저
    assert note.startswith("인지")
    assert reading.parse_select("엉뚱한 답")[2] == ["lm", "linguist"]
    assert reading.parse_answer("ANSWER: statistician, cogsci, lm", ["lm"]) == ["statistician", "cogsci"]
    assert reading.parse_answer("??", ["linguist"]) == ["linguist"]


def test_pdf_url_allowlist():
    assert reading.pdf_url("https://arxiv.org/abs/2401.01234v2") == "https://arxiv.org/pdf/2401.01234v2"
    assert reading.pdf_url("https://aclanthology.org/2024.acl-long.12/") == "https://aclanthology.org/2024.acl-long.12.pdf"
    assert reading.pdf_url("https://openreview.net/forum?id=abc123") == "https://openreview.net/pdf?id=abc123"
    assert reading.pdf_url("https://evil.example.com/paper.pdf") is None
    assert reading.find_url("이거 읽자 <https://arxiv.org/abs/2401.01234>") == "https://arxiv.org/abs/2401.01234"
    assert reading.CLOSE_WORDS.search("오늘은 여기까지 하고 정리해줘")


def test_close_note_is_searchable_by_director_memory(tmp_path):
    cfg = _cfg(tmp_path)
    st = reading.ReadingStore(cfg)
    pid = st.new()
    st.update(pid, title="Garden paths", tags=["surprisal"], tutors=["linguist"])
    path = st.close(pid, "## 한 줄 요약\n정원길 문장에서 서프라이절이 재분석 비용을 과소추정한다.")
    assert path.name == "P-001.md" and st.get(pid)["status"] == "closed"
    hits = memory.ResearchMemory(cfg).search("재분석 비용 과소추정")
    assert hits and hits[0]["kind"] == memory.K_READING and hits[0]["source"] == "reading/P-001.md"
    assert "Garden paths" in reading.trend_text(cfg) and "surprisal(1)" in reading.trend_text(cfg)


def test_reading_policy_file(tmp_path):
    cfg = _cfg(tmp_path)
    assert not load_policy(cfg, "READING").allows_discord   # 정책 파일 없으면 닫힘(기본값 유지)
    (cfg.lab_home / "policies").mkdir(parents=True, exist_ok=True)
    (cfg.lab_home / "policies" / "READING.json").write_text(json.dumps(
        {"classification": "public", "external_backends": ["claude"], "discord_publish": True}))
    assert load_policy(cfg, "READING").allows_discord


def test_paper_folder_zip_and_local_path(tmp_path):
    import zipfile
    src = tmp_path / "papers" / "garden"
    (src / "sub").mkdir(parents=True)
    (src / "main.tex").write_text("\\title{Garden}", encoding="utf-8")
    (src / "sub" / "refs.bib").write_text("@article{x}", encoding="utf-8")
    (src / "run.py").write_text("print(1)", encoding="utf-8")       # 논문 파일이 아니면 받지 않는다
    zp = tmp_path / "garden.zip"
    with zipfile.ZipFile(zp, "w") as z:
        z.write(src / "main.tex", "garden/main.tex")
        z.write(src / "run.py", "garden/run.py")
        z.writestr("../../escape.txt", "x")                         # 상위 폴더 탈출 시도 → 평평하게 저장
    dest = tmp_path / "in"
    dest.mkdir()
    assert sorted(reading.extract_zip(zp, dest)) == ["escape.txt", "main.tex"]
    assert not (tmp_path / "escape.txt").exists()
    roots = ((tmp_path / "papers").resolve(),)
    found = reading.find_local_path(f"이 폴더 읽어줘 {src}", roots)
    assert found == src.resolve()
    assert reading.find_local_path(f"{tmp_path / 'in'}", roots) is None      # 허용 폴더 밖
    dest2 = tmp_path / "in2"
    dest2.mkdir()
    assert sorted(reading.copy_folder(found, dest2)) == ["main.tex", "refs.bib"]


def test_every_agent_writes_own_report(make_lab):
    from conftest import T
    script = {r: [[T("search_paper", query="reanalysis")],
                  [("text", f"## 요약 (3줄)\n{r} 관점 요약.\n## 견해\n" + "근거 있는 견해. " * 30)]]
              for r in reading.REPORTERS if r not in reading.NO_TOOL_ROLES}
    for r in reading.NO_TOOL_ROLES:                                  # 도구 없이 본문만 받아 쓴다
        script[r] = [[("text", "## 요약 (3줄)\n본문만 보고 씀.\n## 견해\n" + "실행 관점 견해. " * 30)]]
    lab, _ = make_lab(script)
    cfg = lab.cfg
    st = reading.ReadingStore(cfg)
    pid = st.new(note="공부용")
    st.update(pid, title="Garden paths")
    _paper(st, pid, "--- 1쪽 ---\nSurprisal underestimates the reanalysis cost.")
    from lab.agents import director_system, system_for
    assert reading.missing_reports(cfg, pid) == list(reading.REPORTERS)
    for r in reading.REPORTERS:
        base = director_system(None, cfg) if r == "director" else system_for(r, cfg)
        reading.write_report(cfg, lab.client, r, pid, system_base=base, model="m", name=r, label=r)
    assert reading.missing_reports(cfg, pid) == []
    md = (reading.report_dir(cfg, pid) / "tester.md").read_text(encoding="utf-8")
    assert md.startswith("# Garden paths · 리딩 리포트 · tester")
    prev = reading.report_preview(md)
    assert prev.startswith("## 요약") and "## 견해" in prev
    assert "[리딩 리포트]" in st.history_text(pid, limit=40)          # 이후 질문·리딩 노트가 리포트를 맥락으로 쓴다


def test_short_report_is_failure(make_lab):
    lab, _ = make_lab({"lm": [[("text", "짧음")]]})
    st = reading.ReadingStore(lab.cfg)
    pid = st.new()
    _paper(st, pid, "본문")
    import pytest
    from lab.agents import system_for
    with pytest.raises(RuntimeError):
        reading.write_report(lab.cfg, lab.client, "lm", pid, system_base=system_for("lm", lab.cfg), model="m")
    assert "lm" in reading.missing_reports(lab.cfg, pid)               # 실패한 리포트는 retry 대상으로 남는다


def test_local_path_with_spaces_and_trailing_words(tmp_path):
    d = tmp_path / "docs" / "에이전트 실험자료" / "garden paper"
    d.mkdir(parents=True)
    roots = ((tmp_path / "docs").resolve(),)
    assert reading.find_local_path(f"{d} 이 폴더 읽어줘", roots) == d.resolve()
    assert reading.find_local_path(f"이거 `{d}`", roots) == d.resolve()


def test_review_trigger_words():
    assert reading.wants_review("이 논문에 대한 내 분석 첨언해줘", False, "https://velog.io/@a/b")
    assert reading.wants_review("", False, "https://velog.io/@a/post")          # 논문 PDF 가 아닌 글 링크는 첨언
    assert not reading.wants_review("이 논문 같이 봐줘", True, None)           # PDF + 평범한 말은 리딩 세션
    assert not reading.wants_review("읽자", False, "https://arxiv.org/abs/2401.01234")
    assert reading.wants_review("나의 분석 어때?", True, None)                 # 내 글 파일을 붙이고 첨언 요청


def test_html_to_text_and_paper_links():
    raw = ("<html><head><title>[논문 Deep Dive] 제목</title><script>x=1</script></head><body><nav>메뉴</nav>"
           "<article><h2>1. 논문 정보</h2><p>원문: <a>https://aclanthology.org/2026.cl-2.7/</a></p>"
           "<table><tr><td>영어</td><td>0.74</td></tr></table></article></body></html>")
    title, text = reading.html_to_text(raw)
    assert title == "[논문 Deep Dive] 제목"
    assert "## 1. 논문 정보" in text and "메뉴" not in text and "x=1" not in text and "0.74" in text
    assert reading.paper_links(text) == ["https://aclanthology.org/2026.cl-2.7/"]
    assert reading.fetch_page("http://127.0.0.1:8765/", __import__("pathlib").Path("/tmp/x.md")) is None   # 내부망 차단


def test_review_session_writes_selected_reviews(make_lab):
    from conftest import T
    body = "## 한 줄 평\n좋은 분석.\n## 사실관계 점검\n" + "원문과 대조함. " * 30
    lab, _ = make_lab({"tester": [[T("search_paper", query="Pearson")], [("text", body)]],
                       "practitioner": [[("text", body)]]})
    cfg = lab.cfg
    st = reading.ReadingStore(cfg)
    pid = st.new(note="내 분석 첨언해줘")
    title, tags, who, _ = reading.parse_review_select("TITLE: 내 글\nTAGS: LLM\nREVIEWERS: tester, practitioner, nobody\n안내")
    assert who == ["tester", "practitioner"]
    assert reading.parse_review_select("REVIEWERS: ALL")[2] == list(reading.REPORTERS)
    assert reading.parse_review_select("TITLE: x")[2] == list(reading.REPORTERS)        # 지정 없으면 전원
    assert reading.ALL_WORDS.search("다들 각자 해석해줘")
    st.update(pid, kind="review", reviewers=who, title=title)
    d = st.dir(pid) / "inputs"
    d.mkdir(parents=True, exist_ok=True)
    (d / "article.md").write_text("# 내 글\n상관 0.701 은 일치도가 아니다.", encoding="utf-8")
    (d / "source_1.pdf.txt").write_text("--- 3쪽 ---\nMean Pearson r 0.701", encoding="utf-8")
    from lab.agents import system_for
    assert reading.missing_reports(cfg, pid) == ["tester", "practitioner"]
    for r in who:
        reading.write_report(cfg, lab.client, r, pid, system_base=system_for(r, cfg), model="m", mode="review")
    assert reading.missing_reports(cfg, pid) == []
    md = (reading.report_dir(cfg, pid, "review") / "tester.md").read_text(encoding="utf-8")
    assert "첨언" in md.splitlines()[0]
    assert reading.report_preview(md).startswith("## 한 줄 평")
