import json
from pathlib import Path

import pytest

from conftest import T
from lab.director import DIRECTOR_TOOLS, Director
from lab.sandbox import Sandbox
from lab.tools import Toolbox

RUN_PY = '''import json
import numpy as np
from lab_utils import set_seed, write_manifest, bootstrap_ci
set_seed(0)
x = np.random.normal(0.3, 1.0, 50)
est, lo, hi = bootstrap_ci(x, n_boot=300)
json.dump({"mean": est, "ci": [lo, hi], "n": 50}, open("results/results.json", "w"))
write_manifest(seed=0)
print("ok", round(est, 3))
'''
ANALYZE_PY = '''import json
r = json.load(open("results/results.json"))
json.dump({"mean": r["mean"], "ci": r["ci"], "n": r["n"], "excluded": 0}, open("results/derived/analysis_summary.json", "w"))
'''

MEMO = dict(memo_markdown="메모 본문", summary="요약", key_concerns=["교란 가능성"], recommendations=["길이 통제"])


def memo_turn():
    return [T("submit_memo", **MEMO)]


def build_turns():
    return [[T("write_file", path="code/run_experiment.py", content=RUN_PY)],
            [T("run_command", command="PYTHONPATH=code python3 code/run_experiment.py")],
            [T("finish_build", status="ready", summary="구현 완료", entrypoints=["python3 code/run_experiment.py"],
               tests_run=["smoke ok"])]]


def analyze_turns():
    return [[T("write_file", path="code/analysis/analyze.py", content=ANALYZE_PY)],
            [T("run_command", command="python3 code/analysis/analyze.py")],
            [T("finish_build", status="ready", summary="전체 분석 완료", entrypoints=["python3 code/analysis/analyze.py"],
               tests_run=["ok"])]]


def plan_turn(**over):
    base = dict(plan_markdown="# 계획\n가설...", summary="계획 요약", needs_network=False,
                needs_host_accel=False, est_runtime_min=5, risks=[])
    base.update(over)
    return [T("finish_plan", **base)]


def exec_turns():
    return [[T("run_command", command="PYTHONPATH=code python3 code/run_experiment.py")],
            [T("finish_execution", status="success", notes="실행 완료", result_files=["results/results.json"])]]


def report_turns():
    return [[T("write_file", path="report/report.md", content="# 보고서\n평균은 results/results.json 참고")],
            [T("finish_report", discord_summary="요약", key_findings=["효과 있음"], caveats=["표본 작음"],
               attachments=["report/report.md"])]]


def review(verdict="pass", issues=None):
    return [T("submit_review", verdict=verdict, issues=issues or [], checks_run=["재계산 일치"], summary="검증함")]


def script(*, plan=None, revise=False):
    s = {"linguist": [memo_turn(), memo_turn()], "cogsci": [memo_turn(), memo_turn()], "lm": [memo_turn(), memo_turn()],
         "practitioner": [plan or plan_turn(), *exec_turns()],
         "developer": [*build_turns(), *analyze_turns()],
         "documenter": [*report_turns()], "tester": [review()]}
    if revise:
        s["tester"] = [review("revise", [dict(severity="major", owner="developer", where="분석", problem="CI 계산 의심")]),
                       review("pass")]
        s["developer"] += [*analyze_turns()]                       # fix 라운드
        for r in ("linguist", "cogsci", "lm"):
            s[r].append(memo_turn())                               # 해석 갱신
        s["documenter"] += report_turns()
    return s


def submit(lab, **kw):
    return lab.submit("테스트 실험", "## 연구 질문\n테스트", **kw)


def test_happy_path(make_lab):
    lab, notifier = make_lab(script())
    exp = submit(lab)
    assert lab.process_one() is True
    e = lab.ledger.get(exp["id"])
    assert e["status"] == "done", e["error"]
    d = lab.cfg.experiments_dir / exp["id"]
    for f in ("plan.md", "report/report.md", "results/results.json", "results/run_manifest.json",
              "results/derived/analysis_summary.json", "notes/consult_linguist.md", "report/interpretation_lm.md",
              "review/review_1.json"):
        assert (d / f).exists(), f
    assert "검증 결과 (자동 기록)" in (d / "report/report.md").read_text()
    assert (lab.cfg.notebook_dir / f"{exp['id']}.md").exists()
    assert e["tokens_used"] > 0
    texts = "\n".join(t for _, t, _ in notifier.sent)
    for name in ("언어학 전문가", "백엔드 개발자", "실험 실무 담당", "서류화·보고 담당", "검증 테스트 담당"):
        assert name in texts, name
    # 완료 보고에는 보고서가 첨부된다
    assert any(files and files[0].endswith("report/report.md") for _, t, files in notifier.sent if "완료" in t)
    assert lab.process_one() is False


def test_network_requires_approval_then_continues(make_lab):
    lab, notifier = make_lab(script(plan=plan_turn(needs_network=True)))
    exp = submit(lab)
    lab.process_one()
    e = lab.ledger.get(exp["id"])
    assert e["status"] == "awaiting_approval"
    assert any(t.startswith("APPROVAL:") for _, t, _ in notifier.sent)
    assert lab.process_one() is False                      # 승인 전에는 아무도 이어가지 않는다
    assert "승인" in lab.approve(exp["id"])
    lab.process_one()
    assert lab.ledger.get(exp["id"])["status"] == "done"


def test_host_and_long_runtime_gate(make_lab):
    lab, _ = make_lab(script(plan=plan_turn(needs_host_accel=True, est_runtime_min=500)))
    exp = submit(lab)
    lab.process_one()
    reasons = json.loads(lab.ledger.get(exp["id"])["approval_reasons"])
    assert len(reasons) == 2


def test_reject_stops(make_lab):
    lab, _ = make_lab(script(plan=plan_turn(needs_network=True)))
    exp = submit(lab)
    lab.process_one()
    lab.reject(exp["id"])
    assert lab.ledger.get(exp["id"])["status"] == "stopped"
    assert lab.process_one() is False


def test_review_revision_loop_routes_to_owner(make_lab):
    lab, notifier = make_lab(script(revise=True))
    exp = submit(lab)
    lab.process_one()
    e = lab.ledger.get(exp["id"])
    assert e["status"] == "done", e["error"]
    d = lab.cfg.experiments_dir / exp["id"]
    assert (d / "review/review_2.json").exists()
    texts = "\n".join(t for _, t, _ in notifier.sent)
    assert "백엔드 개발자 코드·분석 수정" in texts and "전문가 해석 갱신" in texts
    assert "통과" in (d / "report/report.md").read_text()


def test_unresolved_review_is_disclosed(make_lab):
    bad = review("revise", [dict(severity="critical", owner="documenter", where="표1", problem="수치 불일치")])
    s = script()
    s["tester"] = [bad, bad, bad]
    s["documenter"] = report_turns() * 3
    lab, notifier = make_lab(s)
    exp = submit(lab)
    lab.process_one()
    e = lab.ledger.get(exp["id"])
    assert e["status"] == "done"
    report = (lab.cfg.experiments_dir / exp["id"] / "report/report.md").read_text()
    assert "해결되지 않은 지적" in report and "수치 불일치" in report
    assert any("미해결" in t for _, t, _ in notifier.sent)


def test_execution_failure_goes_back_to_developer_once(make_lab):
    s = script()
    s["practitioner"] = [plan_turn(),
                         [T("finish_execution", status="failed", notes="ImportError: foo")],
                         *exec_turns()]
    s["developer"] = [*build_turns(), *build_turns(), *analyze_turns()]
    lab, notifier = make_lab(s)
    exp = submit(lab)
    lab.process_one()
    assert lab.ledger.get(exp["id"])["status"] == "done"
    assert any("돌려보내" in t for _, t, _ in notifier.sent)


def test_budget_pauses_and_resume_adds_budget(make_lab):
    lab, _ = make_lab(script(), tokens=700, token_budget=1000)
    exp = submit(lab)
    lab.process_one()
    e = lab.ledger.get(exp["id"])
    assert e["status"] == "paused"
    lab.resume(exp["id"])
    assert lab.ledger.get(exp["id"])["token_budget"] == 1000 + lab.cfg.token_budget
    assert lab.ledger.get(exp["id"])["status"] == "queued"


def test_stop_before_start(make_lab):
    lab, _ = make_lab(script())
    exp = submit(lab)
    lab.stop(exp["id"])
    assert lab.process_one() is False
    assert lab.ledger.get(exp["id"])["status"] == "stopped"


def test_restart_recovers_interrupted(make_lab):
    lab, _ = make_lab(script())
    exp = submit(lab)
    claimed = lab.ledger.claim_next()
    assert claimed["status"] == "planning"
    assert lab.ledger.reset_interrupted() == [exp["id"]]
    assert lab.ledger.get(exp["id"])["status"] == "queued"


def test_consult_subset(make_lab):
    s = script()
    s["cogsci"], s["lm"] = [], []
    s["linguist"] = [memo_turn(), memo_turn()]
    lab, _ = make_lab(s)
    exp = submit(lab, consult=["linguist"])
    lab.process_one()
    d = lab.cfg.experiments_dir / exp["id"]
    assert lab.ledger.get(exp["id"])["status"] == "done"
    assert (d / "notes/consult_linguist.md").exists() and not (d / "notes/consult_lm.md").exists()


# ---------------- 권한·보안 ----------------
def _tb(lab, exp_id, role, **kw):
    return Toolbox(cfg=lab.cfg, exp_id=exp_id, role=role, sandbox=lab.sandbox, notebook=lab.notebook,
                   notify=lab.notifier, **kw)


def test_toolbox_confines_paths_and_roles(make_lab):
    lab, _ = make_lab(script())
    exp = submit(lab)
    eid = exp["id"]
    tb = _tb(lab, eid, "developer")
    with pytest.raises(PermissionError):
        tb.execute("read_file", {"path": "../../../etc/passwd"})
    with pytest.raises(PermissionError):
        tb.execute("write_file", {"path": "../escape.txt", "content": "x"})
    assert tb.execute("write_file", {"path": "report/x.md", "content": "x"}).is_error       # 개발자는 report/ 쓰기 불가
    assert not tb.execute("write_file", {"path": "code/a.py", "content": "x"}).is_error
    assert _tb(lab, eid, "tester").execute("write_file", {"path": "code/a.py", "content": "x"}).is_error
    assert _tb(lab, eid, "documenter").execute("write_file", {"path": "results/fake.json", "content": "{}"}).is_error
    assert _tb(lab, eid, "linguist").execute("finish_report", {}).is_error                    # 역할 밖 도구
    assert tb.execute("run_command", {"command": "echo hi", "where": "host"}).is_error        # 승인 없이 호스트 실행 불가
    assert _tb(lab, eid, "developer", host_allowed=True).execute(
        "run_command", {"command": "echo hi", "where": "host"}).text.startswith("[exit 0]")


def test_read_past_experiment_rejects_traversal(make_lab):
    lab, _ = make_lab(script())
    exp = submit(lab)
    tb = _tb(lab, exp["id"], "linguist")
    with pytest.raises(PermissionError):
        tb.execute("read_past_experiment", {"exp_id": exp["id"], "path": "../../ledger.db"})
    assert tb.execute("read_past_experiment", {"exp_id": "../x", "path": "a"}).is_error


def test_docker_args_are_isolated(make_lab):
    lab, _ = make_lab(script())
    args = Sandbox(lab.cfg).docker_args("EXP-001", Path("/x/EXP-001"), "echo hi", network=False)
    assert args[args.index("--network") + 1] == "none"
    assert "/x/EXP-001:/work" in args
    assert any(a.endswith(":/data:ro") for a in args)
    net = Sandbox(lab.cfg).docker_args("EXP-001", Path("/x/EXP-001"), "echo hi", network=True)
    assert net[net.index("--network") + 1] == "bridge"


# ---------------- 연구실장 ----------------
def test_director_submits_in_thread_and_cannot_approve(make_lab):
    s = {"director": [[T("submit_experiment", title="BLiMP 비교", request_markdown="## 질문\n...", consult=["linguist"])],
                      [("text", "접수했습니다.")]]}
    lab, _ = make_lab(s)
    d = Director(lab)
    out = d.reply([{"role": "user", "content": "BLiMP 돌려줘. 알아서 진행해"}], thread_id=777, channel_id=1)
    assert "접수" in out
    e = lab.ledger.find_by_thread(777)
    assert e and e["title"] == "BLiMP 비교"
    assert json.loads(e["meta_json"])["consult"] == ["linguist"]
    assert not [t for t in DIRECTOR_TOOLS if "approve" in t["name"]]


def test_director_merges_history_and_answers_status(make_lab):
    lab, _ = make_lab({"director": [[T("lab_status")], [("text", "현재 접수된 실험이 없습니다.")]]})
    out = Director(lab).reply([{"role": "assistant", "content": "안녕"}, {"role": "user", "content": "지금 뭐해?"},
                               {"role": "user", "content": "현황 알려줘"}])
    assert "없습니다" in out
