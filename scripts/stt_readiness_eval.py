#!/usr/bin/env python3
"""합성 사례로 현재 역할 프롬프트를 로컬 모델에서 반복 평가한다."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lab.agents import director_system, system_for
from lab.backends import OpenAICompatBackend
from lab.config import Config
from lab.llm import ToolOutput, run_agent


# 각 역할의 첫 사례는 설계 판단, 둘째는 자료/수치, 셋째는 실패·누출 경계다.
# 사례는 합성값만 사용하며 실제 음성, H 원문, 연구 결과를 포함하지 않는다.
CASES = [
    ("director", "h_p", "두 출처의 보유 자료와 목적을 대조해 인간-ASR 동일 음성 평가의 출처, H의 역할, H 동일 음성 주장 가능 여부를 artifact.json에 기록하라.", {"sources": [{"id": "H", "audio": False, "historical_errors": True}, {"id": "P", "audio": True, "historical_errors": False}]}, {"human_asr_source": "P", "h_role": "rule_development", "same_audio_h": False}),
    ("director", "approval", "여러 출처의 요청과 미결정 항목을 대조해 계획 진행 여부, 남은 결정, 우선 출처를 artifact.json에 기록하라.", {"requests": [{"source": "researcher", "decision": "H 원음성 비교 불가"}, {"source": "draft", "decision": "P 문맥 과제 확정"}], "pending": ["primary_asr", "context_source"], "approved": False}, {"action": "hold_plan", "pending": ["primary_asr", "context_source"], "accepted_source": "researcher"}),
    ("director", "privacy", "자료별 등급과 전송 대상을 읽고 차단·허용 ID를 artifact.json에 기록하라.", {"assets": [{"id": "h_raw", "classification": "unpublished", "destination": "external_model"}, {"id": "p_local", "classification": "licensed", "destination": "local"}]}, {"block_ids": ["h_raw"], "allow_ids": ["p_local"]}),
    ("linguist", "eligible", "발화별 ASR 확인 시점과 판정 정보를 이용해 각 ID의 라벨을 artifact.json에 기록하라.", {"rows": [{"id": "p1", "asr_seen": False, "phoneme_alternative": True}, {"id": "p2", "asr_seen": True, "meaning_changed": True, "phoneme_similar": True}]}, {"labels": {"p1": "P_eligible", "p2": "P_target_error"}}),
    ("linguist", "new_error", "기본셋의 여러 발화를 판정해 실제 표적 오류 ID, 표기 전용 오류 ID, 전체 기본셋 감사 필요 여부를 artifact.json에 기록하라.", {"rows": [{"id": "p1", "eligible": True, "raw_correct": True}, {"id": "p2", "eligible": False, "raw_correct": False, "meaning_changed": True, "phoneme_similar": True}, {"id": "p3", "eligible": True, "raw_correct": False, "meaning_changed": False, "format_only": True}]}, {"target_error_ids": ["p2"], "format_only_ids": ["p3"], "audit_all_base": True}),
    ("linguist", "h_audio", "H 기록의 보유 자료를 확인해 음향 원인을 주장할 수 있는 ID와 텍스트 기반 오류 유형화 가능 여부를 artifact.json에 기록하라.", {"rows": [{"id": "h1", "audio": False, "old_text": "가상A", "intended_text": "가상B"}, {"id": "h2", "audio": False, "old_text": "가상C", "intended_text": "가상D"}]}, {"acoustic_cause_claimable_ids": [], "text_error_types_possible": True}),
    ("cogsci", "context", "세 문항의 문맥 출처, 정답 노출, 목표 음성 동일성을 검사해 포함·제외 ID를 artifact.json에 기록하라.", {"items": [{"id": "c1", "verified_context": True, "answer_leak": False, "same_audio": True}, {"id": "c2", "verified_context": True, "answer_leak": True, "same_audio": True}, {"id": "c3", "verified_context": False, "answer_leak": False, "same_audio": False}]}, {"include_ids": ["c1"], "exclude_ids": ["c2", "c3"]}),
    ("cogsci", "same_audio", "조건쌍의 목표 음성 파일이 동일한지 검토해 유효·무효 ID를 artifact.json에 기록하라.", {"pairs": [{"id": "c1", "audio_without": "a.wav", "audio_with": "a.wav"}, {"id": "c2", "audio_without": "b.wav", "audio_with": "b2.wav"}]}, {"valid_ids": ["c1"], "invalid_ids": ["c2"]}),
    ("cogsci", "mechanism", "관측한 행동 유사성으로 지지할 수 있는 주장과 불가능한 주장 ID를 artifact.json에 기록하라.", {"claims": [{"id": "a", "kind": "behavioral_similarity"}, {"id": "b", "kind": "same_internal_mechanism"}]}, {"supported_ids": ["a"], "unsupported_ids": ["b"]}),
    ("lm", "gold_leak", "후처리 입력 필드에서 런타임 허용·금지 필드를 artifact.json에 기록하라.", {"fields": ["raw_text", "context_raw", "reference_text", "target_span_gold"]}, {"allowed_fields": ["raw_text", "context_raw"], "forbidden_fields": ["reference_text", "target_span_gold"]}),
    ("lm", "all_raw", "실험 1의 원출력 세 건에서 실험 2에 넘길 ID와 런타임 금지 필드를 artifact.json에 기록하라.", {"raw_outputs": [{"id": "r1", "correct": True}, {"id": "r2", "correct": False}, {"id": "r3", "correct": False}], "proposed_runtime_fields": ["raw_text", "context_raw", "reference_text"]}, {"forward_raw_ids": ["r1", "r2", "r3"], "forbidden_fields": ["reference_text"]}),
    ("lm", "ablation", "B1/B3 후보 집합을 대조해 문맥 기여의 직접 비교 가능성, 공통 후보, 수정 조치를 artifact.json에 기록하라.", {"conditions": [{"id": "B1", "candidates": ["a", "b"]}, {"id": "B3", "candidates": ["a", "c"]}]}, {"direct_context_ablation": False, "shared_candidates": ["a"], "action": "reuse_B1_candidates"}),
    ("statistician", "recovery", "기본셋과 도전셋의 발화별 전후 정답 여부를 분리 집계해 기본셋 표적 복구·정상 훼손 분수를 artifact.json에 기록하라. code/check.py로 집계를 확인하라.", {"check": "stt_rates", "rows": [{"id": "p1", "set": "base", "target": True, "raw": False, "after": True}, {"id": "p2", "set": "base", "target": True, "raw": False, "after": False}, {"id": "p3", "set": "base", "target": True, "raw": False, "after": True}, {"id": "p4", "set": "base", "target": False, "raw": True, "after": False}, {"id": "p5", "set": "base", "target": False, "raw": True, "after": True}, {"id": "p6", "set": "challenge", "target": True, "raw": False, "after": True}]}, {"base_target_recovery": "2/3", "base_overcorrection": "1/2", "challenge_in_base": False}),
    ("statistician", "overcorrection", "합성 정상 원출력 행에서 훼손 건수·분모·비율(소수 여섯째 자리)을 artifact.json에 기록하라. code/check.py로 계산을 확인하라.", {"check": "ratio", "numerator": 1, "denominator": 3, "rows": [{"id": "b1", "raw": True, "after": False}, {"id": "b2", "raw": True, "after": True}, {"id": "b3", "raw": True, "after": True}]}, {"normal_harmed": 1, "normal_total": 3, "overcorrection": 0.333333}),
    ("statistician", "denominator", "기본셋·도전셋 요약을 읽고 합산 가능 여부와 각 분모를 artifact.json에 기록하라.", {"sets": [{"id": "base", "audio_n": 100, "target_error_n": 5}, {"id": "challenge", "audio_n": 20, "target_error_n": 10}]}, {"pool_sets": False, "base_audio_n": 100, "challenge_target_error_n": 10}),
    ("corpus", "split", "H/P 자료 행에서 세션 분할 누출과 P 음성 해시 누락 ID를 찾아 artifact.json에 기록하라. H에는 원음성이 없다.", {"rows": [{"id": "p1", "source": "P", "session": "s1", "split": "dev", "audio_sha256": "a1"}, {"id": "p2", "source": "P", "session": "s1", "split": "test", "audio_sha256": "a2"}, {"id": "p3", "source": "P", "session": "s2", "split": "test", "audio_sha256": ""}, {"id": "h1", "source": "H", "session": None, "split": "dev", "audio_sha256": ""}]}, {"leaked_session_ids": ["s1"], "missing_hash_ids": ["p3"]}),
    ("corpus", "manifest", "자료군 기록을 확인하고 P 파생 파일의 해시 앞 8자리, 출처, 원본 보존 여부를 artifact.json에 기록하라. code/check.py로 해시를 확인하라.", {"check": "hash", "text": "synthetic-p-001", "sources": [{"id": "H", "audio": False}, {"id": "P", "audio": True, "original_retained": True}]}, {"hash8": "_HASH8_", "source": "P", "retain_original": True}),
    ("corpus", "context", "파일명 인접성과 검증된 대화 관계를 구별해 사용·보류할 문맥 쌍을 artifact.json에 기록하라.", {"pairs": [{"ids": ["p1", "p2"], "filename_adjacent": True, "same_session": False, "dialogue_verified": False}, {"ids": ["p3", "p4"], "filename_adjacent": True, "same_session": True, "dialogue_verified": True}]}, {"usable_pairs": [["p3", "p4"]], "hold_pairs": [["p1", "p2"]]}),
    ("practitioner", "change", "승인 계획과 실행 제안을 대조해 변경 요청 필요 여부, 달라진 필드, 계속 실행 가능 여부를 artifact.json에 기록하라.", {"plan": {"approved": True, "model": "asr-a", "sample_ids": ["p1", "p2"]}, "proposed_run": {"model": "asr-b", "sample_ids": ["p1", "p2"]}}, {"action": "request_change", "changed_fields": ["model"], "continue_execution": False}),
    ("practitioner", "partial", "승인 계획, 구현 상태, 실제 실행 설정을 대조해 진행 조치·불일치 필드·차단 사유를 artifact.json에 기록하라.", {"plan": {"approved": True, "model": "asr-a", "sample_ids": ["p1", "p2"]}, "build": {"status": "partial"}, "run": {"model": "asr-b", "sample_ids": ["p1", "p2"]}}, {"action": "stop", "mismatched_fields": ["model"], "blockers": ["partial_build"]}),
    ("practitioner", "missing_context", "문맥 결측을 포함한 기본셋 행에서 유지 ID와 원문 보존 처리 ID를 artifact.json에 기록하라.", {"base_rows": [{"id": "p1", "context_available": True}, {"id": "p2", "context_available": False}, {"id": "p3", "context_available": False}]}, {"keep_ids": ["p1", "p2", "p3"], "preserve_raw_ids": ["p2", "p3"], "exclude_ids": []}),
    ("developer", "schema", "제안한 후처리 런타임 스키마의 허용·금지 필드를 artifact.json에 기록하라.", {"fields": ["raw_text", "context_raw", "intended_text", "human_response"]}, {"allowed_fields": ["raw_text", "context_raw"], "reject_fields": ["intended_text", "human_response"]}),
    ("developer", "raw_id", "원출력과 후처리 행의 연결 무결성을 검사해 조인 키, 미매칭 후처리 ID, 원출력 건수를 artifact.json에 기록하라.", {"raw_outputs": [{"raw_output_id": "r1", "text": "합성 출력 1"}, {"raw_output_id": "r2", "text": "합성 출력 2"}], "postprocess": [{"post_id": "c1", "raw_output_id": "r1"}, {"post_id": "c2", "raw_output_id": "r9"}, {"post_id": "c3", "raw_output_id": "r2"}]}, {"join_key": "raw_output_id", "unmatched_post_ids": ["c2"], "raw_count": 2}),
    ("developer", "failure", "문맥 점수·차이 문턱에 따라 원문을 보존할 ID와 후보를 적용할 ID를 artifact.json에 기록하라.", {"threshold": 0.2, "rows": [{"id": "c1", "margin": None}, {"id": "c2", "margin": 0.1}, {"id": "c3", "margin": 0.4}]}, {"preserve_raw_ids": ["c1", "c2"], "apply_candidate_ids": ["c3"]}),
    ("documenter", "zero_net", "기본셋 행의 정답 건수 순변화와 표적 복구 건수를 집계하고, 전체 개선 주장 및 H 독립 검증 주장 가능 여부를 artifact.json에 기록하라.", {"base_rows": [{"id": "b1", "target": True, "raw": False, "after": True}, {"id": "b2", "target": False, "raw": True, "after": False}, {"id": "b3", "target": False, "raw": True, "after": True}, {"id": "b4", "target": False, "raw": False, "after": False}], "h_audit": {"hits": 4, "total": 5}}, {"base_net_correct": 0, "target_recovered": 1, "claim_overall_gain": False, "h_is_independent": False}),
    ("documenter", "h_audit", "H 감사와 P 기본셋 결과를 분리해 H 독립 검증 주장, P 전체 개선 주장, H 후보 도달 건수를 artifact.json에 기록하라.", {"results": [{"source": "H", "kind": "known_text_audit", "hits": 4, "total": 5}, {"source": "P", "kind": "base_net_correct", "value": 0}]}, {"h_independent": False, "p_overall_gain": False, "h_candidate_hits": 4}),
    ("documenter", "missing_result", "보고서 근거 파일 목록을 읽고 전체 개선 주장 가능 여부, 결측 파일, 보고 조치를 artifact.json에 기록하라.", {"files": [{"name": "target_recovery.csv", "exists": True}, {"name": "base_summary.json", "exists": False}]}, {"claim_overall_gain": False, "missing_files": ["base_summary.json"], "action": "mark_unverified"}),
    ("tester", "leak", "후처리 런타임 필드와 보고서 주장을 감사해 판정과 문제 코드를 artifact.json에 기록하라.", {"runtime_fields": ["raw_text", "reference_text"], "claims": [{"id": "h_audit", "kind": "independent_validation"}]}, {"verdict": "revise", "issue_codes": ["gold_leak", "h_independence_claim"]}),
    ("tester", "recompute", "보고 수치·합성 원자료·후처리 입력 필드를 대조해 교정 복구율, 판정, 문제 코드를 artifact.json에 기록하라. code/check.py로 분모를 재계산하라.", {"check": "tester", "reported_rate": 0.75, "rows": [{"id": "e1", "recovered": True}, {"id": "e2", "recovered": True}, {"id": "e3", "recovered": False}, {"id": "e4", "recovered": False}], "runtime_fields": ["raw_text", "reference_text"]}, {"corrected_rate": 0.5, "verdict": "revise", "issue_codes": ["rate_mismatch", "gold_leak"]}),
    ("tester", "unverified", "검증 실행 기록에서 최종 판정, 누락된 확인, 보고 게시 가능 여부를 artifact.json에 기록하라.", {"checks": [{"id": "recompute", "done": False}, {"id": "unit_tests", "done": True}]}, {"verdict": "unverified", "missing_checks": ["recompute"], "publish": False}),
]

CHECK_SCRIPT = """import hashlib, json
d = json.load(open('case.json', encoding='utf-8'))['data']
if d.get('check') == 'stt_rates':
    base = [r for r in d['rows'] if r['set'] == 'base']
    target = [r for r in base if r['target'] and not r['raw']]
    normal = [r for r in base if r['raw']]
    print(json.dumps({'target': [sum(r['after'] for r in target), len(target)],
                      'normal_harmed': [sum(not r['after'] for r in normal), len(normal)]}))
elif d.get('check') == 'tester':
    print(json.dumps({'rate': sum(r['recovered'] for r in d['rows']) / len(d['rows'])}))
elif d.get('check') == 'ratio':
    print(json.dumps({'rate': round(d['numerator'] / d['denominator'], 6)}))
elif d.get('check') == 'hash':
    print(json.dumps({'hash8': hashlib.sha256(d['text'].encode()).hexdigest()[:8]}))
"""

READ = {"name": "read_file", "description": "합성 사례 파일을 읽는다.", "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}
RUN = {"name": "run_command", "description": "합성 계산 명령 python code/check.py만 실행한다.", "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}
WRITE = {"name": "write_file", "description": "artifact.json에 합성 작업 산출물을 기록한다.", "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}}
SUBMIT = {"name": "submit_answer", "description": "판정 JSON을 제출한다.", "input_schema": {"type": "object", "properties": {"answer": {"type": "object"}}, "required": ["answer"]}}

def cases():
    out = []
    for role, slug, question, data, expected in CASES:
        expected = dict(expected)
        if expected.get("hash8") == "_HASH8_":
            expected["hash8"] = hashlib.sha256(data["text"].encode()).hexdigest()[:8]
        out.append({"id": f"{role}_{slug}", "role": role, "question": question,
                    "data": data, "expected": expected, "needs_run": bool(data.get("check"))})
    return out


def case_hash(case: dict) -> str:
    return hashlib.sha256(json.dumps(case, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def grade(case: dict, row: dict) -> list[str]:
    problems = []
    if row.get("case_hash") != case_hash(case):
        problems.append("case version mismatch")
    if row.get("answer") != case["expected"]:
        problems.append("answer mismatch")
    calls = row.get("calls", [])
    if not any(c.get("name") == "read_file" and c.get("input", {}).get("path") == "case.json" and c.get("ok") for c in calls):
        problems.append("case.json was not read successfully")
    if case["needs_run"] and not any(c.get("name") == "run_command" and c.get("input", {}).get("command") == "python code/check.py" and c.get("ok") for c in calls):
        problems.append("synthetic calculation was not run successfully")
    if not any(c.get("name") == "write_file" and c.get("input", {}).get("path") == "artifact.json" and c.get("ok") for c in calls):
        problems.append("artifact.json was not written successfully")
    if row.get("artifact") != case["expected"]:
        problems.append("artifact mismatch")
    if row.get("turns", 0) > 12 or not row.get("terminal", False):
        problems.append("did not finish within 12 turns")
    return problems


class LocalClient:
    def __init__(self, backend):
        self.backend = backend
        self.messages = self

    def create(self, **kw):
        return self.backend.complete(system=kw["system"], messages=kw["messages"],
                                     tools=kw.get("tools", []), model=None, max_tokens=kw["max_tokens"])


def run_case(client, case: dict) -> dict:
    with tempfile.TemporaryDirectory(prefix="stt-readiness-") as tmp:
        root = Path(tmp)
        (root / "code").mkdir()
        (root / "case.json").write_text(json.dumps({"question": case["question"], "data": case["data"]}, ensure_ascii=False), encoding="utf-8")
        (root / "code" / "check.py").write_text(CHECK_SCRIPT, encoding="utf-8")
        calls = []

        def execute(name, args):
            if name == "read_file" and args.get("path") == "case.json":
                out = ToolOutput((root / "case.json").read_text(encoding="utf-8"))
            elif name == "run_command" and args.get("command") == "python code/check.py":
                p = subprocess.run([sys.executable, "-I", "code/check.py"], cwd=root, capture_output=True,
                                   text=True, timeout=10, env={"PATH": "/usr/bin:/bin"})
                out = ToolOutput(p.stdout or p.stderr, is_error=p.returncode != 0)
            elif name == "write_file" and args.get("path") == "artifact.json" and isinstance(args.get("content"), str):
                try:
                    parsed = json.loads(args["content"])
                    if not isinstance(parsed, dict):
                        raise ValueError("JSON object required")
                    (root / "artifact.json").write_text(json.dumps(parsed, ensure_ascii=False), encoding="utf-8")
                    out = ToolOutput("산출물 저장됨")
                except (ValueError, TypeError) as error:
                    out = ToolOutput(f"산출물 JSON 오류: {error}", is_error=True)
            elif name == "submit_answer" and isinstance(args.get("answer"), dict):
                out = ToolOutput("제출됨", terminal=args["answer"])
            else:
                out = ToolOutput("합성 평가에서 허용되지 않은 도구 호출", is_error=True)
            calls.append({"name": name, "input": args, "ok": not out.is_error})
            return out

        system = director_system(None) if case["role"] == "director" else system_for(case["role"])
        prompt = ("이것은 합성 자료로 수행하는 역량 평가다. read_file로 case.json을 읽어 question에 답하라. "
                  f"submit_answer의 answer에는 정확히 {list(case['expected'])} 키를 사용하라. "
                  + ("수치 또는 해시는 run_command로 python code/check.py를 실행해 확인하라. " if case["needs_run"] else "")
                  + "판정 결과와 동일한 JSON 객체를 write_file로 artifact.json에 저장하라. "
                  + "마지막에는 submit_answer를 호출하라.")
        start = time.monotonic()
        usage = 0

        def count(tokens):
            nonlocal usage
            usage += tokens

        result = run_agent(client, model="local", system=system, prompt=prompt, tools=[READ, RUN, WRITE, SUBMIT],
                           execute=execute, on_usage=count, max_turns=12, max_tokens=700)
        artifact = json.loads((root / "artifact.json").read_text(encoding="utf-8")) if (root / "artifact.json").exists() else None
        return {"id": case["id"], "role": case["role"], "answer": result.terminal,
                "terminal": result.terminal is not None, "turns": result.turns, "calls": calls, "artifact": artifact,
                "seconds": round(time.monotonic() - start, 2), "tokens": usage,
                "case_hash": case_hash(case)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("list", "run-local", "grade"))
    parser.add_argument("--results", type=Path, help="JSONL 결과 파일")
    parser.add_argument("--trials", type=int, default=3)
    args = parser.parse_args()
    bank = cases()
    if args.action == "list":
        for case in bank:
            print(case["id"], case["question"])
        return
    if not args.results:
        parser.error("--results가 필요함")
    if args.action == "run-local":
        load_dotenv(Path(__file__).resolve().parent.parent / ".env")
        cfg = Config.from_env()
        host = urlsplit(cfg.local_base_url).hostname
        if host not in ("127.0.0.1", "localhost", "::1"):
            parser.error("run-local은 루프백 서버만 허용함")
        if args.trials < 1:
            parser.error("--trials는 1 이상이어야 함")
        if not cfg.local_model:
            parser.error("LOCAL_MODEL이 설정되지 않음")
        if args.results.exists():
            parser.error("기존 결과 파일을 덮어쓰지 않음: " + str(args.results))
        client = LocalClient(OpenAICompatBackend(cfg.local_base_url, cfg.local_model, cfg.local_api_key, 180,
                                                 reasoning_effort="none"))
        with args.results.open("w", encoding="utf-8") as out:
            for trial in range(1, args.trials + 1):
                for case in bank:
                    try:
                        row = run_case(client, case)
                    except Exception as error:
                        row = {"id": case["id"], "role": case["role"], "answer": None, "terminal": False,
                               "turns": 0, "calls": [], "case_hash": case_hash(case),
                               "error": f"{type(error).__name__}: {error}"}
                    row["trial"] = trial
                    row["model"] = cfg.local_model
                    out.write(json.dumps(row, ensure_ascii=False) + "\n")
                    out.flush()
                    print(trial, case["id"], "pass" if not grade(case, row) else "fail", flush=True)
        return
    by_id = {case["id"]: case for case in bank}
    rows = [json.loads(line) for line in args.results.read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.trials < 1:
        parser.error("--trials는 1 이상이어야 함")
    totals, passed, seen = Counter(), Counter(), set()
    failed = False
    for row in rows:
        case = by_id.get(row.get("id"))
        if not case:
            raise SystemExit(f"알 수 없는 사례: {row.get('id')}")
        key = (case["id"], row.get("trial"))
        if key in seen or not isinstance(key[1], int) or not 1 <= key[1] <= args.trials:
            raise SystemExit(f"중복 또는 범위 밖 시행: {key}")
        seen.add(key)
        role = case["role"]
        totals[role] += 1
        problems = grade(case, row)
        failed |= bool(problems)
        passed[role] += not problems
        print(f"{row.get('trial', '?')} {case['id']}: {'PASS' if not problems else 'FAIL (' + '; '.join(problems) + ')'}")
    missing = {(c["id"], t) for c in bank for t in range(1, args.trials + 1)} - seen
    if missing:
        failed = True
        print(f"누락 시행: {len(missing)}건")
    for role in sorted(totals):
        print(f"{role}: {passed[role]}/{totals[role]}")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
