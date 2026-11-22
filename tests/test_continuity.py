"""협업 끊김 해결안: /amend 추가 과업, 정지 사유·자동 복구, 단계 계약 되돌림, 알림 3종 + 하루 요약, 감시자."""
import json
import time
from types import SimpleNamespace

import pytest

from conftest import T
from lab import watch
from lab.backends import BackendUnavailable, Router
from lab.config import load_routes
from lab.llm import BudgetExceeded
from lab.notify import ConsoleNotifier
from lab.policy import DataPolicy
from test_backends import Fake
from test_pipeline import memo_turn, review, submit


def test_amend_on_done_experiment_runs_dev_stat_qa_and_restores(make_lab):
    out = "results/derived/amend/A-01"
    lab, notifier = make_lab({
        "developer": [[T("write_file", path=f"{out}/summary.md", content="4단 재계산 표")],
                      [T("finish_build", status="ready", summary="재계산 저장", entrypoints=[], tests_run=["확인"])]],
        "statistician": [memo_turn()],
        "tester": [review()]})
    eid = submit(lab)["id"]
    lab.ledger.update(eid, status="done", phase="report")
    assert "A-01" in lab.amend(eid, "4단 재계산 표를 저장", by="Linguist")
    assert lab.ledger.get(eid)["phase"] == "amend"
    lab.process_one()
    e = lab.ledger.get(eid)
    assert (e["status"], e["phase"]) == ("done", "report")                     # 추가 과업 전 상태로 돌아온다
    d = lab.cfg.experiments_dir / eid / out
    assert (d / "summary.md").exists() and (d / "stat_review.md").exists() and (d / "review.json").exists()
    assert "판정: 통과" in (d / "amend.md").read_text(encoding="utf-8")
    assert json.loads(e["meta_json"])["amends"][0]["status"] == "done"
    assert any("추가 과업 A-01 완료" in t for _, t, _ in notifier.sent)


def test_amend_while_running_waits(make_lab):
    lab, _ = make_lab({})
    eid = submit(lab)["id"]
    lab.ledger.update(eid, status="running", phase="build")
    assert "끝나면" in lab.amend(eid, "표 추가")
    assert lab.ledger.get(eid)["phase"] == "build"
    assert "비어" in lab.amend(eid, "  ")


def test_contract_bounces_once_to_producer_then_halts(make_lab):
    lab, notifier = make_lab({})
    eid = submit(lab)["id"]
    lab.ledger.update(eid, status="analyzing", phase="interpret")
    bad = lab._contract(lab.ledger.get(eid))
    assert bad[0] == "analyze" and "analysis_summary.json" in bad[1]
    assert lab._bounce(lab.ledger.get(eid), *bad) is True
    e = lab.ledger.get(eid)
    assert e["phase"] == "analyze"
    assert "되돌아온 문제" in lab._header(e, "analyze")                          # 만든 쪽 프롬프트 맨 앞에 붙는다
    lab._advance(eid, "interpret")
    assert "되돌아온 문제" not in lab._header(lab.ledger.get(eid), "interpret")
    assert lab._bounce(lab.ledger.get(eid), *bad) is False                     # 두 번째는 되돌리지 않고 멈춘다
    assert lab.ledger.get(eid)["status"] == "failed"


def test_budget_auto_increases_up_to_cap(make_lab):
    lab, _ = make_lab({}, token_budget=1000, token_budget_max=2500)
    eid = submit(lab)["id"]
    cb = lab._usage_cb(eid)
    cb(1500)
    assert lab.ledger.get(eid)["token_budget"] == 2000
    cb(600)
    assert lab.ledger.get(eid)["token_budget"] == 2500
    with pytest.raises(BudgetExceeded):
        cb(500)


def test_first_stop_goes_to_watchdog_second_asks_researcher(make_lab):
    lab, notifier = make_lab({}, watchdog_min=30)
    eid = submit(lab)["id"]
    lab.ledger.update(eid, phase="build")
    lab._halt(eid, "refusal", "구현 보고 없음")
    assert not any("결정 필요" in t for _, t, _ in notifier.sent)
    assert any("연구실장이 재개" in t for _, t, _ in notifier.sent)
    assert watch.watchdog_tick(lab) == []                                     # 30분이 안 지났다
    assert watch.watchdog_tick(lab, now=time.time() + 3600) == [eid]
    assert lab.ledger.get(eid)["status"] == "queued"
    lab._halt(eid, "refusal", "또 보고 없음")
    assert any(t.startswith(f"**결정 필요** {eid} (모델 거절") for _, t, _ in notifier.sent)
    assert watch.watchdog_tick(lab, now=time.time() + 7200) == []             # 같은 단계는 한 번만


def test_watchdog_ignores_legacy_and_budget_stops(make_lab):
    lab, _ = make_lab({})
    old, budget = submit(lab)["id"], submit(lab)["id"]
    lab.ledger.update(old, status="paused", error="모델 백엔드 없음")          # stop_kind 없는 예전 정지(EXP-002 같은 것)
    lab._halt(budget, "budget", "한도", status="paused")
    assert watch.watchdog_tick(lab, now=time.time() + 3600) == []


def test_digest_collects_and_flushes_once_a_day(tmp_path):
    cfg = SimpleNamespace(lab_home=tmp_path, digest_hour=21)
    watch.digest_add(cfg, "EXP-001", "자문 메모 도착", "linguist")
    watch.digest_add(cfg, "EXP-001", "계획 확정")
    n = ConsoleNotifier()
    at20 = time.mktime(time.strptime("2026-11-22 20:00", "%Y-%m-%d %H:%M"))
    assert watch.digest_flush(cfg, n, now=at20) is False                      # 아직 요약 시각 전
    assert watch.digest_flush(cfg, n, now=at20 + 3600) is True
    assert "하루 요약" in n.sent[0][1] and "계획 확정" in n.sent[0][1] and n.sent[0][0] is None
    watch.digest_add(cfg, "EXP-001", "늦은 알림")
    assert watch.digest_flush(cfg, n, now=at20 + 7200) is False               # 하루 한 번, 남은 것은 다음 날로
    assert "늦은" in (tmp_path / "digest" / "pending.jsonl").read_text(encoding="utf-8")


def test_router_uses_fallback_route_after_role_routes_fail():
    dead, spare = Fake("hermes", BackendUnavailable("시간 초과", 1800)), Fake("codex", None)
    r = Router(SimpleNamespace(routes={"practitioner": [("hermes", None)], "fallback": [("hermes", None), ("codex", None)]}),
               {"hermes": dead, "codex": spare})
    resp = r.create(system="[ROLE:practitioner] x", messages=[{"role": "user", "content": "a"}], tools=[],
                    data_policy=DataPolicy("public", frozenset({"hermes", "codex"})))
    assert resp.backend == "codex" and dead.calls == 1                       # 실패한 경로를 예비로 다시 부르지 않는다


def test_fallback_route_cannot_hold_hermes(monkeypatch):
    monkeypatch.setenv("ROUTE_FALLBACK", "hermes")
    with pytest.raises(ValueError):
        load_routes()
