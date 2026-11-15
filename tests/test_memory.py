"""연구실장 세컨드 브레인: 조사 달라도 검색, 출처·검증 상태 표시, 결정은 연구자만 확정, 디스코드 게시 정책 준수."""
import json

import pytest

from lab import memory
from lab.agents import director_system
from lab.director import DIRECTOR_TOOLS, Director


def _exp(lab, title, request, *, status, verdict=None, report=None, approved=False):
    eid = lab.submit(title, request)["id"]
    d = lab.cfg.experiments_dir / eid
    if report:
        (d / "report" / "report.md").write_text(report, encoding="utf-8")
    if verdict:
        (d / "review" / "review_1.json").write_text(json.dumps({"verdict": verdict}), encoding="utf-8")
    lab.ledger.update(eid, status=status, approved=int(approved))
    return eid


def test_search_survives_particles_and_labels_verification(make_lab):
    lab, _ = make_lab({})
    ok = _exp(lab, "관계절 처리", "목적격 관계절의 서프라이절을 비교한다", status="done", verdict="pass",
              report="주격 관계절이 더 낮은 서프라이절을 보였다 (b=0.42)", approved=True)
    bad = _exp(lab, "관계절 재현", "관계절 효과 재현", status="failed", verdict="revise",
               report="관계절 효과가 재현됐다고 썼으나 검증에서 지적됨")
    hits = memory.ResearchMemory(lab.cfg, lab.ledger).search("관계절에서 서프라이절은", k=12)
    by = {(h["exp_id"], h["source"].split("/")[-1]): h for h in hits}
    assert by[(ok, "report.md")]["status"] == "검증 통과" and by[(ok, "report.md")]["kind"] == memory.K_OBSERVED
    assert by[(ok, "report.md")]["sha"] and by[(ok, "report.md")]["source"] == f"experiments/{ok}/report/report.md"
    assert "검증 통과 아님" in by[(bad, "report.md")]["status"]          # 실패 실험도 검색되되 성공으로 표시되지 않음
    assert memory.ResearchMemory(lab.cfg, lab.ledger).search("전혀무관한질의어") == []


def test_unapproved_plan_is_ai_proposal(make_lab):
    lab, _ = make_lab({})
    eid = _exp(lab, "토크나이저", "토크나이저 경계 점검", status="awaiting_approval")
    (lab.cfg.experiments_dir / eid / "plan.md").write_text("토크나이저 경계를 형태소 단위로 맞춘다", encoding="utf-8")
    mem = memory.ResearchMemory(lab.cfg, lab.ledger)
    plan = next(h for h in mem.search("토크나이저 경계") if h["source"].endswith("plan.md"))
    assert plan["kind"] == memory.K_AI and "승인 전" in plan["status"]
    lab.ledger.update(eid, approved=1)
    plan = next(h for h in mem.search("토크나이저 경계") if h["source"].endswith("plan.md"))
    assert plan["kind"] == memory.K_DECISION


def test_read_source_stays_inside_roots(make_lab):
    lab, _ = make_lab({})
    eid = _exp(lab, "제목", "요청 본문", status="queued")
    mem = memory.ResearchMemory(lab.cfg, lab.ledger)
    text, exp_id = mem.read_source(f"experiments/{eid}/request.md")
    assert "요청 본문" in text and exp_id == eid and "sha256" in text
    for bad in (f"experiments/{eid}/../../ledger.db", "experiments/../../.env", "policies/ADHOC.json", "/etc/passwd"):
        with pytest.raises((PermissionError, FileNotFoundError)):
            mem.read_source(bad)


def test_decision_needs_researcher_and_keeps_history(make_lab):
    lab, _ = make_lab({})
    mem = memory.ResearchMemory(lab.cfg, lab.ledger)
    d = memory.propose_decision(lab.cfg, "주 지표는 CER 로 한다", basis="연구자: 띄어쓰기 변동을 피하려고")
    hit = mem.search("주 지표는 무엇")[0]
    assert hit["kind"] == memory.K_AI and "확인 전" in hit["status"]       # 확정 전에는 연구자 결정이 아님
    assert "확정" in memory.approve_decision(lab.cfg, d["id"])
    assert mem.search("주 지표")[0]["kind"] == memory.K_DECISION
    assert "할 수 없습니다" in memory.approve_decision(lab.cfg, d["id"])
    memory.retire_decision(lab.cfg, d["id"])
    hit = mem.search("주 지표")[0]
    assert "폐기됨" in hit["status"]                                        # 지우지 않고 이력으로 남김
    rej = memory.propose_decision(lab.cfg, "주 지표는 WER 로 한다")
    memory.reject_decision(lab.cfg, rej["id"])
    assert all(rej["id"] not in h["source"] for h in mem.search("주 지표"))
    assert rej["id"] in memory.decisions_summary(lab.cfg)


def test_director_memory_tools_respect_discord_policy(make_lab):
    lab, _ = make_lab({})
    eid = _exp(lab, "비공개 실험", "미공개 자극 목록 설계", status="done", verdict="pass", report="미공개 자극 결과")
    memory.propose_decision(lab.cfg, "미공개 자극은 외부 모델에 보내지 않는다")
    director = Director(lab)
    local = director._tool("search_research_memory", {"query": "미공개 자극"}, None, None, None)
    assert eid in local.text and "decisions.json" in local.text
    out = director._tool("search_research_memory", {"query": "미공개 자극"}, None, None, 1)   # 디스코드 대화, 정책 파일 없음
    assert eid not in out.text and "decisions.json" not in out.text
    blocked = director._tool("read_source", {"source": f"experiments/{eid}/report/report.md"}, None, None, 1)
    assert blocked.is_error
    pol = lab.cfg.lab_home / "policies"
    pol.mkdir(exist_ok=True)
    (pol / f"{eid}.json").write_text('{"classification":"public","external_backends":[],"discord_publish":true}')
    assert eid in director._tool("search_research_memory", {"query": "미공개 자극"}, None, None, 1).text
    rec = director._tool("record_decision_proposal", {"text": "필러는 24문항", "exp_id": eid}, None, None, 1)
    assert "D-002" in rec.text and "/memory approve" in rec.text


def test_director_prompt_and_no_confirm_tool(make_lab):
    lab, _ = make_lab({})
    s = director_system(None, lab.cfg)
    assert "search_research_memory" in s and "지금 지시가 과거 기록보다 우선" in s
    names = {t["name"] for t in DIRECTOR_TOOLS}
    assert {"search_research_memory", "read_source", "record_decision_proposal"} <= names
    assert not any("approve" in n or "confirm" in n for n in names)


def test_conversation_long_term_recall(tmp_path):
    """최근 2시간 창 밖의 예전 대화도 관련 있으면 꺼낸다. 창 안의 것은 중복으로 꺼내지 않는다."""
    import time
    from types import SimpleNamespace as NS
    cfg = NS(memory_dir=tmp_path)
    memory.log_exchange(cfg, channel="의뢰", who="Cognitive Scientist",
                        request="읽기시간이 surprisal에 비례한다는 가설의 한계", answer="스필오버 효과로 선형성이 깨진다")
    memory.log_exchange(cfg, channel="의뢰", who="Linguist", request="관계절 핵명사 후행", answer="한국어는 핵이 뒤에 온다")
    (tmp_path / "conversations.jsonl").open("a").write("깨진 줄\n")
    hits = memory.recall_exchanges(cfg, "surprisal 가설 한계 다시 정리해줘", before_ts=time.time() + 1)
    assert [h["who"] for h in hits] == ["Cognitive Scientist"]
    assert "스필오버" in memory.format_exchanges(hits)
    assert memory.recall_exchanges(cfg, "surprisal 가설 한계", before_ts=0) == []
    assert memory.recall_exchanges(cfg, "", before_ts=time.time() + 1) == []
