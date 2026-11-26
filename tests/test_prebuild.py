"""구현 전 선행 단계: 계획이 정한 전문가 산출물(명세·코퍼스·분석 명세)이 순서대로 나와야 개발자가 구현을 시작한다."""
import json

import pytest

from conftest import T
from lab.pipeline import Lab
from lab.protocol import check_prebuild, code_sha256
from lab.tools import Toolbox, tool_schemas
from test_pipeline import approve_plan_and_finish, memo_turn, plan_turn, script, submit

STEPS = [dict(role="corpus", task="코퍼스 생성", outputs=["results/corpus/"]),
         dict(role="statistician", task="분석 명세", outputs=["results/spec/stats.md"])]


def step(path, status="ready", write=True):
    turns = [[T("write_file", path=path, content="내용")]] if write else []
    return turns + [[T("finish_build", status=status, summary="선행 산출물", entrypoints=[], tests_run=["확인"])]]


def prebuild_script(corpus=None, stats=None):
    s = script(plan=plan_turn(prebuild=STEPS))
    s["corpus"] = [memo_turn(), *(corpus if corpus is not None else step("results/corpus/a.txt")), memo_turn()]
    s["statistician"] = [memo_turn(), *(stats if stats is not None else step("results/spec/stats.md")), memo_turn()]
    return s


def build_roles(lab):
    return [r for r, p in lab.client.prompts if "지금 단계: prebuild" in p or "지금 단계: build" in p]


def test_steps_run_in_order_before_developer(make_lab):
    lab, _ = make_lab(prebuild_script())
    exp = submit(lab)
    approve_plan_and_finish(lab, exp)
    e = lab.ledger.get(exp["id"])
    assert e["status"] == "done", e["error"]
    order = list(dict.fromkeys(build_roles(lab)))
    assert order == ["corpus", "statistician", "developer"]
    assert "results/corpus/" in (lab.cfg.experiments_dir / exp["id"] / "plan.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("corpus,why", [(step("", write=False), "results/corpus/"),
                                        (step("results/corpus/a.txt", "partial"), "미완료")])
def test_missing_or_partial_step_stops_before_next(make_lab, corpus, why):
    lab, _ = make_lab(prebuild_script(corpus=corpus))
    exp = submit(lab)
    approve_plan_and_finish(lab, exp)
    e = lab.ledger.get(exp["id"])
    assert (e["status"], e["phase"]) == ("failed", "build") and why in e["error"]
    assert "developer" not in build_roles(lab) and "statistician" not in build_roles(lab)


def test_resume_skips_finished_steps(make_lab):
    lab, _ = make_lab(prebuild_script(stats=step("", "partial", write=False) + step("results/spec/stats.md")))
    exp = submit(lab)
    approve_plan_and_finish(lab, exp)
    assert lab.ledger.get(exp["id"])["status"] == "failed"
    n = build_roles(lab).count("corpus")
    lab.resume(exp["id"])
    lab.process_one()
    assert lab.ledger.get(exp["id"])["status"] == "done", lab.ledger.get(exp["id"])["error"]
    assert build_roles(lab).count("corpus") == n


def test_developer_changing_frozen_output_stops(make_lab):
    s = prebuild_script()
    s["developer"].insert(0, [T("run_command", command="echo x > results/corpus/a.txt")])
    lab, _ = make_lab(s)
    exp = submit(lab)
    approve_plan_and_finish(lab, exp)
    e = lab.ledger.get(exp["id"])
    assert (e["status"], e["phase"]) == ("failed", "build") and "results/corpus/a.txt" in e["error"]


def test_later_step_changing_earlier_output_stops(make_lab):
    lab, _ = make_lab(prebuild_script(stats=[[T("run_command", command="echo x > results/corpus/a.txt")],
                                             *step("results/spec/stats.md")]))
    exp = submit(lab)
    approve_plan_and_finish(lab, exp)
    e = lab.ledger.get(exp["id"])
    assert e["status"] == "failed" and "results/corpus/a.txt" in e["error"]
    assert "developer" not in build_roles(lab)


@pytest.mark.parametrize("bad", [[dict(role="developer", task="x", outputs=["results/a"])],
                                 [dict(role="corpus", task="x", outputs=[])],
                                 [dict(role="corpus", task="", outputs=["results/a"])],
                                 [dict(role="corpus", task="x", outputs=["plan.md"])],
                                 [dict(role="corpus", task="x", outputs=["results/../plan.md"])],
                                 [dict(role="corpus", task="x", outputs=["results/"])], ["corpus"], "corpus"])
def test_invalid_prebuild_rejected(bad):
    with pytest.raises(ValueError):
        check_prebuild(bad)


def test_consultants_write_only_declared_outputs(make_lab):
    lab, _ = make_lab(script())
    tb = Toolbox(cfg=lab.cfg, exp_id="EXP-001", role="corpus", sandbox=None, notebook=None, notify=None,
                 extra_write=("results/corpus/",))
    assert tb._writable("results/corpus/a.txt")
    assert not tb._writable("results/corpus/../code/a.py") and not tb._writable("notes/../plan.md")
    assert not tb._writable("results/code/x.py")


def test_memo_stage_does_not_offer_finish_build(make_lab):
    lab, _ = make_lab(script())
    seen = {}
    from lab import pipeline
    real = pipeline.run_agent

    def spy(*a, **kw):
        seen.setdefault(kw["prompt"].count("consult(자문)") and "consult", [t["name"] for t in kw["tools"]])
        return real(*a, **kw)
    pipeline.run_agent = spy
    try:
        submit(lab)
        lab.process_one()
    finally:
        pipeline.run_agent = real
    assert "submit_memo" in seen["consult"] and "finish_build" not in seen["consult"]


def test_results_code_is_protected_code(make_lab, tmp_path):
    lab, _ = make_lab(script())
    tb = Toolbox(cfg=lab.cfg, exp_id="EXP-001", role="developer", sandbox=None, notebook=None, notify=None)
    assert tb._writable("results/code/run_experiment.py")
    (tmp_path / "code").mkdir()
    before = code_sha256(tmp_path)
    (tmp_path / "results/code").mkdir(parents=True)
    (tmp_path / "results/code/a.py").write_text("x")
    assert code_sha256(tmp_path) != before


def test_execution_changing_results_code_stops(make_lab):
    s = script()
    s["developer"].insert(0, [T("write_file", path="results/code/a.py", content="x=1")])
    s["practitioner"].insert(1, [T("write_file", path="results/code/a.py", content="x=2")])
    lab, _ = make_lab(s)
    exp = submit(lab)
    approve_plan_and_finish(lab, exp)
    e = lab.ledger.get(exp["id"])
    assert e["status"] == "failed" and "results/code/a.py" in e["error"]
