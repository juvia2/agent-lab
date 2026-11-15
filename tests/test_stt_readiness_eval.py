from collections import Counter
import json
import subprocess
import sys
from types import SimpleNamespace
from pathlib import Path

from scripts.stt_readiness_eval import case_hash, cases, grade, run_case


def test_readiness_bank_covers_each_role_with_three_synthetic_cases():
    bank = cases()
    assert len(bank) == 30
    assert set(Counter(c["role"] for c in bank).values()) == {3}
    assert all(c["data"] for c in bank)
    assert len(next(c for c in bank if c["id"] == "statistician_recovery")["data"]["rows"]) == 6
    assert all("/Users/" not in c["question"] and "H 원문" not in str(c["data"]) for c in bank)
    for case in bank:
        row = {"answer": case["expected"], "case_hash": case_hash(case), "terminal": True,
               "turns": 2, "calls": [{"name": "read_file", "input": {"path": "case.json"}, "ok": True}]}
        assert "artifact.json was not written successfully" in grade(case, row)


def test_grader_requires_real_tool_evidence_and_case_version():
    case = next(c for c in cases() if c["id"] == "statistician_recovery")
    row = {"answer": case["expected"], "artifact": case["expected"],
           "case_hash": case_hash(case), "terminal": True, "turns": 4,
           "calls": [{"name": "read_file", "input": {"path": "case.json"}, "ok": True},
                     {"name": "run_command", "input": {"command": "python code/check.py"}, "ok": True},
                     {"name": "write_file", "input": {"path": "artifact.json"}, "ok": True}]}
    assert grade(case, row) == []
    assert "synthetic calculation was not run successfully" in grade(case, {**row, "calls": row["calls"][:1]})
    assert "artifact mismatch" in grade(case, {**row, "artifact": {}})
    assert "case version mismatch" in grade(case, {**row, "case_hash": "old"})


def test_case_runner_uses_isolated_read_and_calculation_tools():
    class ScriptedClient:
        def __init__(self, case):
            self.case = case
            self.messages = self
            self.n = 0
            self.calls = [("read_file", {"path": "case.json"})]
            if case["needs_run"]:
                self.calls.append(("run_command", {"command": "python code/check.py"}))
            self.calls += [("write_file", {"path": "artifact.json", "content": json.dumps(case["expected"])}),
                           ("submit_answer", {"answer": case["expected"]})]

        def create(self, **_):
            name, args = self.calls[self.n]
            self.n += 1
            block = SimpleNamespace(type="tool_use", id=str(self.n), name=name, input=args)
            return SimpleNamespace(content=[block], stop_reason="tool_use",
                                   usage=SimpleNamespace(input_tokens=1, output_tokens=1))

    for case in cases():
        row = run_case(ScriptedClient(case), case)
        assert grade(case, row) == [], case["id"]
        assert row["artifact"] == case["expected"]


def test_grade_rejects_missing_trials(tmp_path):
    case = cases()[0]
    row = {"id": case["id"], "trial": 1, "answer": case["expected"], "artifact": case["expected"],
           "case_hash": case_hash(case), "terminal": True, "turns": 2,
           "calls": [{"name": "read_file", "input": {"path": "case.json"}, "ok": True},
                     {"name": "write_file", "input": {"path": "artifact.json"}, "ok": True}]}
    path = tmp_path / "one.jsonl"
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    result = subprocess.run([sys.executable, str(Path(__file__).resolve().parent.parent / "scripts" / "stt_readiness_eval.py"),
                             "grade", "--results", str(path)], capture_output=True, text=True)
    assert result.returncode == 1
    assert "누락 시행: 89건" in result.stdout
