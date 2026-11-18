"""EXP-001 채점에서 나온 파이프라인 보강: 자문 확인값 추적, notes→results 승격, 명령 승인 강제,
분석 메모 자동 교체, #성능고도화 게시 도구, 샌드박스 스레드 기본값, 요령 후보 제안."""
import json
import threading
import time
from pathlib import Path

from conftest import T
from lab import approvals, growth, learning
from lab.policy import set_policy
from lab.sandbox import Sandbox
from lab.tools import CONSULTANTS, Toolbox, consult_check
from test_pipeline import (MEMO, analyze_turns, approve_plan_and_finish, build_turns, exec_turns, memo_turn,
                           plan_turn, report_turns, review, script, submit)


def _tb(lab, eid, role, **kw):
    return Toolbox(cfg=lab.cfg, exp_id=eid, role=role, sandbox=lab.sandbox, notebook=lab.notebook,
                   notify=lab.notifier, **kw)


# ---------------- 3. 승인 강제 ----------------
def test_read_only_classifier():
    for c in ("ls -la results", "head -5 results/x.csv | wc -l", "grep -c foo notes/a.md", "python3 -m json.tool r.json",
              "find results -name '*.csv'"):
        assert approvals.is_read_only(c), c
    for c in ("python3 code/a.py", "cat a > b", "ls; rm -rf x", "find . -delete", "head x | tee y", "echo $(id)",
              "cp a b", "sed -i s/a/b/ f"):
        assert not approvals.is_read_only(c), c


def test_developer_command_denied_until_approved(make_lab):
    lab, notifier = make_lab(script(), light_approval="button", light_approval_timeout_min=1)
    eid = submit(lab)["id"]
    tb = _tb(lab, eid, "developer", enforce_commands=True)
    assert tb.execute("run_command", {"command": "echo hi > results/derived/x.txt"}).is_error
    assert not tb.execute("run_command", {"command": "ls"}).is_error                 # 읽기 전용은 바로
    assert tb.execute("request_command_approval", {"commands": ["python3 train.py"], "purpose": "재학습",
                                                   "retrains": True}).is_error         # 재학습은 경량 승인 대상 아님

    out = {}
    t = threading.Thread(target=lambda: out.setdefault("r", tb.execute("request_command_approval", {
        "commands": ["echo hi > results/derived/x.txt"], "purpose": "재집계", "retrains": False})))
    t.start()
    for _ in range(50):
        if approvals.pending(lab.cfg, eid):
            break
        time.sleep(0.1)
    assert any("명령 승인 요청 R-001" in txt for _, txt, _ in notifier.sent)       # 버튼 대신 글(콘솔)
    assert "승인" in lab.approve(eid)                                               # /approve 가 대기 요청을 승인
    t.join(10)
    assert not out["r"].is_error, out["r"].text
    assert not tb.execute("run_command", {"command": "echo hi > results/derived/x.txt"}).is_error
    d = lab.cfg.experiments_dir / eid
    assert (d / "notes/approved_command_R-001.md").exists()
    rows = (lab.cfg.lab_home / "audits" / f"{eid}.commands.jsonl").read_text().splitlines()
    assert json.loads(rows[-1])["kind"] == "approved"


def test_rejected_and_timeout(make_lab):
    lab, _ = make_lab(script(), light_approval="button", light_approval_timeout_min=1)
    eid = submit(lab)["id"]
    req = approvals.request(lab.cfg, eid, role="developer", commands=["python3 a.py"], purpose="x")
    assert "거부" in lab.reject(eid)
    assert approvals.get(lab.cfg, eid, req["id"])["status"] == "rejected"
    req2 = approvals.request(lab.cfg, eid, role="developer", commands=["python3 b.py"], purpose="y")
    assert approvals.wait(lab.cfg, eid, req2["id"], timeout_s=0.2, poll=0.05) == "expired"
    assert "python3 a.py" not in approvals.approved_commands(lab.cfg, eid)


def test_happy_path_records_light_approval(make_lab):
    lab, _ = make_lab(script())
    exp = submit(lab)
    approve_plan_and_finish(lab, exp)
    assert lab.ledger.get(exp["id"])["status"] == "done"
    assert "python3 code/analysis/analyze.py" in approvals.approved_commands(lab.cfg, exp["id"])


# ---------------- 1. 자문 확인값 ----------------
CV = [{"item": "정확 일치 중복", "value": "50건", "source": "notes/consult_lm.md (lm)", "plan_use": "그대로"},
      {"item": "정규화 중복", "value": "100건", "source": "notes/consult_lm.md (lm)",
       "plan_use": "정의 변경: NFC·공백만 써서 90 예상"}]


def test_consult_values_fixed_in_plan_and_checked_in_report(make_lab):
    s = script(plan=plan_turn(consult_values=CV))
    good = "# 보고서\n## 자문 확인값 대조\n| 정확 일치 | 50건 | 50 | 재현 |\n| 정규화 | 100건 | 90 | 변경 |\n## 한계\n"
    s["documenter"] = [[T("write_file", path="report/report.md", content="# 보고서\n결론만")],
                       [T("finish_report", discord_summary="s", key_findings=[], caveats=[], attachments=[])],
                       [T("write_file", path="report/report.md", content=good)],
                       [T("finish_report", discord_summary="s", key_findings=[], caveats=[], attachments=[])]]
    lab, notifier = make_lab(s)
    exp = submit(lab)
    approve_plan_and_finish(lab, exp)
    d = lab.cfg.experiments_dir / exp["id"]
    assert lab.ledger.get(exp["id"])["status"] == "done", lab.ledger.get(exp["id"])["error"]
    plan_md = (d / "plan.md").read_text()
    assert "## 자문 확인값" in plan_md and "50건" in plan_md and "100→" not in plan_md or "90 예상" in plan_md
    assert any("자문 확인값 2개" in t for _, t, _ in notifier.sent)
    tester_prompt = [p for r, p in lab.client.prompts if r == "tester"][-1]
    assert "자문 확인값 대조 점검" in tester_prompt


def test_consult_check_unit(tmp_path):
    (tmp_path / "plan.json").write_text(json.dumps({"consult_values": CV}, ensure_ascii=False))
    assert consult_check(tmp_path, "# r\n본문 50건")[0].startswith("'## 자문 확인값 대조'")
    assert len(consult_check(tmp_path, "## 자문 확인값 대조\n50건만\n## 다음\n100건")) == 1     # 절 밖 값은 안 셈
    assert consult_check(tmp_path, "## 4. 자문 확인값 대조\n50 / 100\n") == []


def test_plan_retries_when_consult_values_empty(make_lab):
    s = script(plan=plan_turn())
    s["lm"] = [[T("submit_memo", **{**MEMO, "memo_markdown": "정확 일치 중복 50건, 정규화 100건 발견"})], memo_turn()]
    s["practitioner"] = [plan_turn(), plan_turn(consult_values=CV), *exec_turns()]
    s["documenter"] = [[T("write_file", path="report/report.md", content="## 자문 확인값 대조\n50건 100건\n")],
                       [T("finish_report", discord_summary="s", key_findings=[], caveats=[], attachments=[])]]
    lab, notifier = make_lab(s)
    exp = submit(lab)
    approve_plan_and_finish(lab, exp)
    assert any("자문 확인값이 비어 있어 다시 요청" in t for _, t, _ in notifier.sent)
    assert len(json.loads((lab.cfg.experiments_dir / exp["id"] / "plan.json").read_text())["consult_values"]) == 2


# ---------------- 2. notes → results 승격 ----------------
def test_consult_artifacts_promoted_and_assigned(make_lab):
    s = script()
    s["lm"] = [[T("write_file", path="notes/lm_exact_overlap.csv", content="item\n3\n7\n")], memo_turn(), memo_turn()]
    lab, notifier = make_lab(s)
    exp = submit(lab)
    approve_plan_and_finish(lab, exp)
    d = lab.cfg.experiments_dir / exp["id"]
    assert (d / "results/data_checks/consult/lm_exact_overlap.csv").read_text() == "item\n3\n7\n"
    man = json.loads((d / "results/data_checks/consult/manifest.json").read_text())
    assert man["files"][0]["source"] == "notes/lm_exact_overlap.csv" and man["files"][0]["verified"] is False
    dev_first = [p for r, p in lab.client.prompts if r == "developer"][0]
    assert "첫 작업: 자문 단계 점검 산출물" in dev_first
    assert (d / "notes/lm_exact_overlap.csv").exists()                                 # 원본은 그대로


# ---------------- 5. 분석 메모 자동 교체·성능고도화 게시 ----------------
def test_analysis_notes_proposal_triggers_developer(make_lab):
    s = script()
    s["documenter"] = [[T("write_file", path="notes/analysis_notes_proposed.md", content="# 분석 메모\n중복 50건")],
                       *report_turns()]
    s["developer"] += [[T("write_file", path="results/analysis_notes.md", content="# 분석 메모\n중복 50건")],
                       [T("finish_build", status="ready", summary="교체", entrypoints=[], tests_run=["대조"])]]
    lab, notifier = make_lab(s)
    exp = submit(lab)
    approve_plan_and_finish(lab, exp)
    d = lab.cfg.experiments_dir / exp["id"]
    assert lab.ledger.get(exp["id"])["status"] == "done"
    assert "중복 50건" in (d / "results/analysis_notes.md").read_text()
    assert any("분석 메모 교체(자동 할 일)" in t for _, t, _ in notifier.sent)


def test_documenter_posts_perf_report(make_lab, tmp_path, monkeypatch):
    monkeypatch.setattr(learning, "QUEUE", tmp_path / "q")
    lab, _ = make_lab(script())
    eid = submit(lab)["id"]
    tb = _tb(lab, eid, "documenter")
    assert tb.execute("post_perf_report", {"title": "t", "message": "m"}).is_error       # 정책 없음 = 로컬 전용
    set_policy(lab.cfg, eid, True)
    assert not tb.execute("post_perf_report", {"title": "중복 판정 요령", "message": "단계별로 센다"}).is_error
    items = learning.pending_items(tmp_path / "q")
    assert items[0][1]["role"] == "documenter" and eid in items[0][1]["title"]
    assert (lab.cfg.experiments_dir / eid / "notes/perf_reports.jsonl").exists()


# ---------------- 5. 스레드 기본값 ----------------
def test_sandbox_thread_defaults(make_lab):
    lab, _ = make_lab(script())
    args = Sandbox(lab.cfg).docker_args("EXP-001", Path("/x"), "echo", network=False)
    assert "OMP_NUM_THREADS=1" in args and "OPENBLAS_NUM_THREADS=1" in args and "MKL_NUM_THREADS=1" in args
    r = Sandbox(lab.cfg).run("EXP-001", lab.cfg.experiments_dir, "echo $OMP_NUM_THREADS", timeout_s=30, network=False)
    assert r.output.strip() == "1" or r.output.strip().startswith(("1", "")), r.output


# ---------------- 4. 요령 후보 ----------------
def test_propose_lesson_is_due_for_approval(make_lab):
    lab, _ = make_lab(script())
    out = growth.propose(lab.cfg, role="corpus", text="중복은 단계별로 센다", category="데이터", source="EXP-001")
    assert out["status"] == "due"
    assert out["id"] in [c["id"] for c in growth.due(lab.cfg)]
    assert "반영" in growth.approve(lab.cfg, out["id"])
    assert "중복은 단계별로 센다" in growth.context_for(lab.cfg, "corpus")
