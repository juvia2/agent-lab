"""에이전트에게 주는 도구들. 모든 파일 접근은 실험 폴더 안으로 제한된다."""
from __future__ import annotations

import posixpath
import re
import time
import json
from pathlib import Path

from . import approvals
from .llm import ToolOutput
from .protocol import check_protocol, code_sha256, sha256

CONSULTANTS = ("linguist", "cogsci", "lm", "statistician", "corpus")   # 자문·해석 전문가 5인
ROLES = CONSULTANTS + ("practitioner", "developer", "documenter", "tester")

# ---- 역할별 쓰기 허용 위치 (실험 폴더 기준) ----
WRITE_PREFIXES = {
    **{r: ("notes/", "results/derived/") for r in CONSULTANTS},
    "practitioner": ("results/", "notes/"),
    # results/data_checks/: 자문·해석 단계 점검 산출물을 옮겨 검증하는 곳, results/analysis_notes.md: 분석 메모 교체(보고서 단계 자동 할 일)
    "developer": ("code/", "results/code/", "results/derived/", "results/data_checks/", "results/analysis_notes.md", "notes/"),
    "documenter": ("report/", "notes/"),
    "tester": ("review/",),
}

_PATH = {"type": "string", "description": "실험 폴더 기준 상대경로"}

SCHEMAS: dict[str, dict] = {
    "list_files": {
        "name": "list_files", "description": "실험 폴더의 파일 목록을 본다.",
        "input_schema": {"type": "object", "properties": {"path": {**_PATH, "default": "."}}}},
    "read_file": {
        "name": "read_file", "description": "실험 폴더 안의 텍스트 파일을 읽는다.",
        "input_schema": {"type": "object", "properties": {"path": _PATH, "max_chars": {"type": "integer", "default": 12000}},
                         "required": ["path"]}},
    "write_file": {
        "name": "write_file", "description": "실험 폴더 안에 파일을 쓴다(역할별로 쓸 수 있는 폴더가 제한됨).",
        "input_schema": {"type": "object", "properties": {"path": _PATH, "content": {"type": "string"}},
                         "required": ["path", "content"]}},
    "run_command": {
        "name": "run_command",
        "description": "샌드박스에서 셸 명령을 실행한다. 작업 디렉터리는 실험 폴더(/work), 공유 데이터는 /data(읽기 전용). "
                       "긴 작업은 timeout_min 을 늘린다. 출력은 마지막 부분만 돌려주고 전체 로그는 logs/ 에 저장된다.",
        "input_schema": {"type": "object", "properties": {
            "command": {"type": "string"},
            "timeout_min": {"type": "integer", "default": 30},
            "where": {"type": "string", "enum": ["sandbox", "host"], "default": "sandbox",
                      "description": "host 는 맥에서 직접 실행(MPS 가능, 격리 없음). 승인된 경우에만 허용됨. host 에서는 /data 대신 $LAB_DATA, /hf_cache 대신 $HF_HOME 를 쓴다"}},
            "required": ["command"]}},
    "search_notebook": {
        "name": "search_notebook", "description": "과거 실험의 연구노트를 키워드로 검색한다.",
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    "read_past_experiment": {
        "name": "read_past_experiment",
        "description": "과거 실험의 파일(report/report.md, plan.md, results/ 안의 파일 등)을 읽기 전용으로 본다.",
        "input_schema": {"type": "object", "properties": {"exp_id": {"type": "string"}, "path": _PATH},
                         "required": ["exp_id", "path"]}},
    "list_data": {
        "name": "list_data", "description": "공유 데이터 폴더(/data)의 파일 목록을 본다.",
        "input_schema": {"type": "object", "properties": {"subdir": {"type": "string", "default": "."}}}},
    "report_progress": {
        "name": "report_progress",
        "description": "연구자에게 진행 상황을 한두 문장으로 알린다(디스코드). 단계 전환·중간 결과·문제 발생 때만 쓴다.",
        "input_schema": {"type": "object", "properties": {"message": {"type": "string"}}, "required": ["message"]}},
    "request_command_approval": {
        "name": "request_command_approval",
        "description": "승인 목록에 없는 명령(재집계·점검 스크립트 등)을 실행 전에 연구자에게 경량 승인(버튼 한 번)으로 요청하고 결정을 기다린다. "
                       "실행할 명령을 한 번에 묶어서 요청한다. 승인된 명령은 같은 문자열로 다시 실행할 수 있다. "
                       "읽기 전용 점검(ls, cat, head, wc, grep, find 등, 리다이렉트·파이프 쓰기 없음)은 승인 없이 바로 된다. "
                       "재학습·본 실행 재실행·설정 변경은 이 도구가 아니라 실행 담당의 변경 승인 대상이다(retrains=true 면 거부됨).",
        "input_schema": {"type": "object", "properties": {
            "commands": {"type": "array", "items": {"type": "string"}, "description": "실행할 정확한 명령 문자열들(최대 10개)"},
            "purpose": {"type": "string", "description": "무엇을 왜 하는가(연구자가 버튼 옆에서 읽는다). 2~3문장"},
            "retrains": {"type": "boolean", "description": "모델 재학습·본 실행 재실행이 들어가는가"},
            "outputs": {"type": "array", "items": {"type": "string"}, "description": "새로 쓰는 파일·폴더(기존 산출물을 덮어쓰지 않을 것)"}},
            "required": ["commands", "purpose", "retrains"]}},
    "post_perf_report": {
        "name": "post_perf_report",
        "description": "#성능고도화 채널(에이전트 학습·성능 향상 보고 전용)에 글을 올린다. 계획서에 #성능고도화 게시 항목이 있거나, "
                       "이 실험에서 에이전트가 배운 요령·실수 패턴이 나왔을 때 쓴다. 연구 결과 보고는 여기 올리지 않는다. "
                       "게시 기록은 notes/perf_reports.jsonl 에 남는다.",
        "input_schema": {"type": "object", "properties": {
            "title": {"type": "string", "description": "제목(한 줄)"},
            "message": {"type": "string", "description": "본문(3000자 안). 무엇을 배웠고 다음에 무엇을 다르게 하는가"}},
            "required": ["title", "message"]}},
    # ---- 종료 도구 ----
    "submit_memo": {
        "name": "submit_memo",
        "description": "전문가 메모를 제출한다(자문 단계에서는 설계 자문, 해석 단계에서는 결과 해석).",
        "input_schema": {"type": "object", "properties": {
            "memo_markdown": {"type": "string", "description": "메모 전문"},
            "summary": {"type": "string", "description": "연구자에게 보일 결론 1~2문장(200자 안). 수치는 결론에 꼭 필요한 것만"},
            "key_concerns": {"type": "array", "items": {"type": "string"},
                             "description": "핵심 우려·교란·한계. 항목마다 한 문장(120자 안), 수치는 하나 정도"},
            "recommendations": {"type": "array", "items": {"type": "string"}}},
            "required": ["memo_markdown", "summary", "key_concerns", "recommendations"]}},
    "finish_plan": {
        "name": "finish_plan", "description": "자문을 통합한 실험 계획을 제출하고 계획 단계를 끝낸다.",
        "input_schema": {"type": "object", "properties": {
            "plan_markdown": {"type": "string", "description": "가설, 설계, 지표, 분석 계획, 해석 기준을 담은 계획서 전문"},
            "summary": {"type": "string", "description": "연구자에게 보일 3~5줄 요약"},
            "needs_network": {"type": "boolean", "description": "모델/데이터 다운로드 등 외부 네트워크가 필요한가"},
            "needs_host_accel": {"type": "boolean", "description": "맥 GPU(MPS) 등 호스트 직접 실행이 꼭 필요한가"},
            "est_runtime_min": {"type": "integer", "description": "예상 총 실행 시간(분)"},
            "run_commands": {"type": "array", "items": {"type": "string"},
                             "description": "연구자가 승인할 본 실행 명령의 정확한 문자열. 실행 단계에서는 이 명령만 허용"},
            "consult_values": {"type": "array", "description":
                               "자문 확인값: 자문 메모(notes/consult_*.md, notes/ 점검 산출물)에 나온 수치·건수를 빠짐없이 옮긴 표. "
                               "보고서 단계에서 이 표와 대조하며, 빠진 값이 있으면 보고서가 완료되지 않는다. 수치가 없으면 빈 배열",
                               "items": {"type": "object", "properties": {
                                   "item": {"type": "string", "description": "무엇의 값인가(예: 정확 일치 중복 문항 수)"},
                                   "value": {"type": "string", "description": "자문이 낸 값 그대로(예: 50건, 문항 번호 목록은 파일 경로)"},
                                   "source": {"type": "string", "description": "출처 파일(notes/...)과 자문 역할"},
                                   "plan_use": {"type": "string", "description":
                                                "계획에서 어떻게 쓰는가. '그대로' 또는 '정의 변경: 이유와 예상 차이'(예: 정규화를 NFC·공백으로 좁혀 100→90 예상)"}},
                                   "required": ["item", "value", "source", "plan_use"]}},
            "prebuild": {"type": "array", "description":
                         "선행 단계: 구현 전에 전문가가 순서대로 만들 산출물(명세 확정, 코퍼스 생성기, 분석 명세 등). 요청서가 담당과 순서를 정했으면 "
                         "그대로 옮긴다. 개발자는 이 산출물이 모두 나온 뒤에 시작하고, 나온 파일은 고정된다. 없으면 빈 배열",
                         "items": {"type": "object", "properties": {
                             "role": {"type": "string", "enum": list(CONSULTANTS)},
                             "task": {"type": "string", "description": "할 일과 완료 기준"},
                             "outputs": {"type": "array", "items": {"type": "string"},
                                         "description": "만들 파일 또는 폴더(/로 끝냄). notes/·results/·code/ 안. 이 밖에는 write_file 로 쓸 수 없다"}},
                             "required": ["role", "task", "outputs"]}},
            "risks": {"type": "array", "items": {"type": "string"}}},
            "required": ["plan_markdown", "summary", "needs_network", "needs_host_accel", "est_runtime_min", "run_commands",
                         "consult_values"]}},
    "finish_execution": {
        "name": "finish_execution", "description": "실행 단계를 끝낸다.",
        "input_schema": {"type": "object", "properties": {
            "status": {"type": "string", "enum": ["success", "partial", "failed"]},
            "notes": {"type": "string", "description": "무엇을 실행했고, 계획에서 벗어난 점과 문제점은 무엇인가"},
            "result_files": {"type": "array", "items": {"type": "string"}}},
            "required": ["status", "notes"]}},
    "request_change": {
        "name": "request_change", "description": "실험 설계나 실행 설정을 바꿔야 할 때, 변경 전에 연구자 승인을 요청하고 작업을 멈춘다.",
        "input_schema": {"type": "object", "properties": {
            "current": {"type": "string", "description": "승인된 계획의 현재 설정"},
            "proposed": {"type": "string", "description": "제안하는 변경"},
            "reason": {"type": "string", "description": "변경이 필요한 이유"},
            "impact": {"type": "string", "description": "가설·비교·결과 해석에 미치는 영향"},
            "run_commands": {"type": "array", "items": {"type": "string"},
                             "description": "실행 명령을 바꿀 때 승인받을 전체 명령 목록"}},
            "required": ["current", "proposed", "reason", "impact"]}},
    "finish_build": {
        "name": "finish_build", "description": "구현(또는 전체 분석 파이프라인 구축) 단계를 끝낸다.",
        "input_schema": {"type": "object", "properties": {
            "status": {"type": "string", "enum": ["ready", "partial", "failed"]},
            "summary": {"type": "string", "description": "무엇을 만들었는지(구조, 진입점, 실행 방법)"},
            "entrypoints": {"type": "array", "items": {"type": "string"},
                            "description": "실행 명령어들(예: python code/run_experiment.py --seeds 0 1 2)"},
            "tests_run": {"type": "array", "items": {"type": "string"}, "description": "수행한 테스트와 결과"},
            "known_limits": {"type": "array", "items": {"type": "string"}}},
            "required": ["status", "summary", "entrypoints", "tests_run"]}},
    "finish_report": {
        "name": "finish_report", "description": "보고서(report/report.md)를 다 쓴 뒤 제출한다.",
        "input_schema": {"type": "object", "properties": {
            "discord_summary": {"type": "string", "description": "디스코드에 올릴 요약(1200자 이내): 결과, 핵심 수치, 한계"},
            "key_findings": {"type": "array", "items": {"type": "string"}},
            "caveats": {"type": "array", "items": {"type": "string"}},
            "attachments": {"type": "array", "items": {"type": "string"},
                            "description": "연구자에게 첨부할 파일(실험 폴더 기준 경로, 보고서·그림·표 위주)"}},
            "required": ["discord_summary", "key_findings", "caveats", "attachments"]}},
    "submit_review": {
        "name": "submit_review", "description": "검증 결과를 제출한다.",
        "input_schema": {"type": "object", "properties": {
            "verdict": {"type": "string", "enum": ["pass", "revise"]},
            "issues": {"type": "array", "items": {"type": "object", "properties": {
                "severity": {"type": "string", "enum": ["critical", "major", "minor"]},
                "owner": {"type": "string", "enum": list(ROLES),
                          "description": "이 문제를 고쳐야 할 담당자. 수치·문장 오류는 documenter, 코드·결과 오류는 practitioner, "
                                         "해석 오류는 해당 분야 전문가(linguist/cogsci/lm)"},
                "where": {"type": "string"}, "problem": {"type": "string"}, "fix": {"type": "string"}},
                "required": ["severity", "owner", "problem"]}},
            "checks_run": {"type": "array", "items": {"type": "string"}, "description": "직접 수행한 검증(재계산 등)"},
            "summary": {"type": "string"}},
            "required": ["verdict", "issues", "checks_run", "summary"]}},
}

_CONSULT_TOOLS = ["list_files", "read_file", "write_file", "run_command", "search_notebook",
                  "read_past_experiment", "list_data", "submit_memo", "finish_build"]
ROLE_TOOLS = {
    **{r: list(_CONSULT_TOOLS) for r in CONSULTANTS},
    "practitioner": ["list_files", "read_file", "write_file", "run_command", "list_data", "search_notebook",
                     "read_past_experiment", "report_progress", "finish_plan", "finish_execution", "request_change"],
    "developer": ["list_files", "read_file", "write_file", "run_command", "list_data", "search_notebook",
                  "read_past_experiment", "report_progress", "request_command_approval", "finish_build"],
    "documenter": ["list_files", "read_file", "write_file", "run_command", "search_notebook",
                   "read_past_experiment", "post_perf_report", "finish_report"],
    "tester": ["list_files", "read_file", "write_file", "run_command", "submit_review"],
}


def tool_schemas(role: str, only: list[str] | None = None) -> list[dict]:
    names = [n for n in ROLE_TOOLS[role] if only is None or n in only]
    return [SCHEMAS[n] for n in names]


class Toolbox:
    def __init__(self, *, cfg, exp_id: str, role: str, sandbox, notebook, notify,
                 network_allowed: bool = False, host_allowed: bool = False,
                 enforce_protocol: bool = False, approved_protocol_sha256: str | None = None,
                 enforce_commands: bool = False, should_stop=None, extra_write: tuple = ()):
        self.cfg, self.exp_id, self.role = cfg, exp_id, role
        self.enforce_commands = enforce_commands      # 승인 뒤 단계의 개발자: 승인 목록 밖 명령은 실행 거부(approvals.py)
        self.should_stop = should_stop
        self.extra_write = extra_write                # 선행 단계에서 계획이 정한 산출물 위치
        self.sandbox, self.notebook, self.notify = sandbox, notebook, notify
        self.network_allowed = network_allowed
        self.host_allowed = host_allowed
        self.enforce_protocol = enforce_protocol
        self.approved_protocol_sha256 = approved_protocol_sha256
        self.exp_dir = (cfg.experiments_dir / exp_id).resolve()
        self._last_progress = 0.0
        logs = self.exp_dir / "logs"
        self._run_count = len(list(logs.glob("run_*.log"))) if logs.exists() else 0

    # ---- 경로 안전 ----
    def _safe(self, rel: str, base: Path | None = None) -> Path:
        base = (base or self.exp_dir).resolve()
        p = (base / rel).resolve()
        if p != base and base not in p.parents:
            raise PermissionError(f"실험 폴더 밖은 접근할 수 없음: {rel}")
        return p

    def _writable(self, rel: str) -> bool:
        norm = posixpath.normpath(rel.replace("\\", "/"))      # '..' 로 허용 폴더를 벗어나지 못하게 먼저 정리한다
        return any(norm.startswith(pref) for pref in WRITE_PREFIXES.get(self.role, ()) + tuple(self.extra_write))

    # ---- 실행 ----
    def execute(self, name: str, args: dict) -> ToolOutput:
        if name not in ROLE_TOOLS[self.role]:
            return ToolOutput(f"이 역할({self.role})은 '{name}' 도구를 쓸 수 없음", is_error=True)
        try:
            from . import bus
            bus.tool(self.cfg, self.role, name, args, exp=self.exp_id)      # 관제 화면에 도구 호출 단위로 남긴다
        except Exception:
            pass
        return getattr(self, f"t_{name}")(**args)

    def t_list_files(self, path: str = ".") -> ToolOutput:
        p = self._safe(path)
        if not p.exists():
            return ToolOutput(f"없음: {path}", is_error=True)
        if p.is_file():
            return ToolOutput(f"{path} ({p.stat().st_size} bytes)")
        rows = []
        for f in sorted(p.rglob("*")):
            if f.is_file() and "__pycache__" not in f.parts:
                rows.append(f"{f.relative_to(self.exp_dir)}  ({f.stat().st_size} bytes)")
            if len(rows) >= 300:
                rows.append("...(300개까지만 표시)")
                break
        return ToolOutput("\n".join(rows) or "(비어 있음)")

    def t_read_file(self, path: str, max_chars: int = 12000) -> ToolOutput:
        p = self._safe(path)
        if not p.is_file():
            return ToolOutput(f"파일 없음: {path}", is_error=True)
        data = p.read_bytes()
        if b"\x00" in data[:2048]:
            return ToolOutput(f"바이너리 파일({len(data)} bytes)은 읽을 수 없음", is_error=True)
        text = data.decode("utf-8", "replace")
        if len(text) > max_chars:
            text = text[:max_chars] + f"\n...[{len(text) - max_chars}자 더 있음]"
        return ToolOutput(text)

    def t_write_file(self, path: str, content: str) -> ToolOutput:
        p = self._safe(path)
        if not self._writable(path):
            return ToolOutput(f"이 역할({self.role})은 '{path}'에 쓸 수 없음. 허용: {WRITE_PREFIXES.get(self.role, ()) + tuple(self.extra_write)}",
                              is_error=True)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return ToolOutput(f"저장함: {path} ({len(content)}자)")

    def t_run_command(self, command: str, timeout_min: int = 30, where: str = "sandbox") -> ToolOutput:
        if self.enforce_protocol:
            if not self.approved_protocol_sha256:
                return ToolOutput("승인된 실행 명세가 없음", is_error=True)
            try:
                protocol = check_protocol(self.exp_dir, self.approved_protocol_sha256)
            except (ValueError, KeyError, OSError) as e:
                return ToolOutput(f"실행 명세 검증 실패: {e}", is_error=True)
            if command not in protocol["run_commands"]:
                return ToolOutput("승인된 실행 명령이 아님. 설정 변경은 request_change로 요청하세요.", is_error=True)
        kind = self._command_kind(command) if self.enforce_commands and not self.enforce_protocol else None
        if kind == "denied":
            return ToolOutput("승인 목록에 없는 명령이라 실행하지 않음. 읽기 전용 점검(ls, cat, head, wc, grep 등)은 바로 되고, "
                              "그 밖의 명령은 먼저 `request_command_approval`로 묶어서 승인받으세요(재학습 없는 재집계는 버튼 한 번). "
                              "재학습·본 실행 재실행이 필요하면 실행하지 말고 finish_build 에 남은 일로 적으세요.", is_error=True)
        if where == "host" and not self.host_allowed:
            return ToolOutput("호스트 직접 실행은 계획에서 선언되고 연구자가 승인한 경우에만 가능함. where=sandbox 로 실행하세요.",
                              is_error=True)
        timeout_min = max(1, min(int(timeout_min), self.cfg.run_timeout_min))
        self._run_count += 1
        logs = self.exp_dir / "logs"
        logs.mkdir(exist_ok=True)
        r = self.sandbox.run(self.exp_id, self.exp_dir, command, timeout_s=timeout_min * 60,
                             network=self.network_allowed, host=(where == "host"))
        log = logs / f"run_{self._run_count:03d}.log"
        log.write_text(f"[{self.role}] $ {command}\n[exit {r.exit_code}] {r.seconds:.1f}s timed_out={r.timed_out}\n\n{r.output}",
                       encoding="utf-8")
        if self.enforce_protocol:
            audit = self.cfg.lab_home / "audits" / f"{self.exp_id}.jsonl"
            audit.parent.mkdir(parents=True, exist_ok=True)
            with audit.open("a", encoding="utf-8") as out:
                out.write(json.dumps({"command": command, "exit_code": r.exit_code,
                                      "protocol_sha256": sha256(self.exp_dir / "protocol.json"),
                                      "code_sha256": code_sha256(self.exp_dir)},
                                     ensure_ascii=False) + "\n")
        if kind in ("approved", "protocol"):           # 승인 명령 실행 기록(본 실행 성공 판정용 감사 기록과 분리)
            audit = self.cfg.lab_home / "audits" / f"{self.exp_id}.commands.jsonl"
            audit.parent.mkdir(parents=True, exist_ok=True)
            with audit.open("a", encoding="utf-8") as out:
                out.write(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "role": self.role, "kind": kind,
                                      "command": command, "exit_code": r.exit_code, "log": f"logs/{log.name}",
                                      "code_sha256": code_sha256(self.exp_dir)}, ensure_ascii=False) + "\n")
        tail = r.output[-6000:]
        head = f"[exit {r.exit_code}] {r.seconds:.0f}초" + (" [시간 초과]" if r.timed_out else "")
        return ToolOutput(f"{head} (전체 로그: logs/{log.name})\n{tail}", is_error=r.exit_code != 0)

    def _command_kind(self, command: str) -> str:
        c = command.strip()
        if approvals.is_read_only(c):
            return "read_only"
        if c in approvals.approved_commands(self.cfg, self.exp_id):
            return "approved"
        try:
            if self.approved_protocol_sha256 and c in check_protocol(self.exp_dir, self.approved_protocol_sha256)["run_commands"]:
                return "protocol"
        except (ValueError, KeyError, OSError):
            pass
        return "denied"

    def t_request_command_approval(self, commands: list, purpose: str, retrains: bool = False,
                                   outputs: list | None = None) -> ToolOutput:
        if retrains:
            return ToolOutput("재학습·본 실행 재실행은 경량 승인 대상이 아님. 실행하지 말고 finish_build(또는 fix 응답)에 "
                              "필요한 이유와 명령을 적으면 실행 담당이 변경 승인(request_change)을 받는다.", is_error=True)
        cmds = [str(c).strip() for c in (commands or []) if str(c).strip()][:10]
        if not cmds:
            return ToolOutput("commands 가 비었음", is_error=True)
        todo = [c for c in cmds if self._command_kind(c) == "denied"]
        if not todo:
            return ToolOutput("요청한 명령은 모두 이미 실행할 수 있음(승인됨·본 실행 명령·읽기 전용).")
        req = approvals.request(self.cfg, self.exp_id, role=self.role, commands=todo, purpose=purpose, outputs=outputs)
        if req["status"] == "approved":
            return ToolOutput("이미 승인된 명령임. 그대로 실행하면 됨.")
        mode = getattr(self.cfg, "light_approval", "button")
        if mode == "auto":                             # 무인 운영·테스트용: 기록은 남기고 자동 승인
            approvals.decide(self.cfg, self.exp_id, req["id"], True, by="auto(LIGHT_APPROVAL=auto)")
        else:
            try:
                ask = getattr(self.notify, "ask_command_approval", None)
                if ask:
                    ask({"id": self.exp_id}, req)
                else:
                    self.notify.post({"id": self.exp_id}, f"명령 승인 요청 {req['id']}: " + "; ".join(todo)
                                     + f"\n`/approve {self.exp_id}` 로 승인", role=self.role)
            except Exception:
                pass
        timeout_s = max(1, int(getattr(self.cfg, "light_approval_timeout_min", 60))) * 60
        status = approvals.wait(self.cfg, self.exp_id, req["id"], timeout_s=timeout_s, should_stop=self.should_stop)
        if status == "approved":
            return ToolOutput(f"{req['id']} 승인됨. 승인된 명령: " + " / ".join(todo)
                              + " (같은 문자열로 실행해야 함. 승인 기록: notes/approved_command_" + req["id"] + ".md)")
        if status == "rejected":
            return ToolOutput(f"{req['id']} 연구자가 거부함. 이 명령은 실행하지 말고, 거부된 사실과 남은 일을 finish_build 에 적으세요.",
                              is_error=True)
        return ToolOutput(f"{req['id']} 승인 대기 {'중단' if status == 'stopped' else '시간 초과'}. 실행하지 말고 "
                          "남은 일로 finish_build 에 적으세요.", is_error=True)

    def t_post_perf_report(self, title: str, message: str) -> ToolOutput:
        from . import learning
        from .policy import load_policy
        if not load_policy(self.cfg, self.exp_id).allows_discord:
            return ToolOutput("이 실험의 자료 정책이 디스코드 게시를 허용하지 않음. 게시하지 않았다고 보고서에 적으세요.", is_error=True)
        q = learning.enqueue(self.role, f"[{self.exp_id}] {title}", message[:3000], group=f"{self.exp_id}-perf")
        rec = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "role": self.role, "title": title, "queue_file": q.name,
               "channel": getattr(self.cfg, "perf_channel", "성능고도화")}
        notes = self.exp_dir / "notes"
        notes.mkdir(exist_ok=True)
        with (notes / "perf_reports.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return ToolOutput(f"#성능고도화 게시 대기열에 넣음({q.name}). 연구실이 켜져 있으면 1분 안에 올라감. 기록: notes/perf_reports.jsonl")

    def t_search_notebook(self, query: str) -> ToolOutput:
        hits = [h for h in self.notebook.search(query) if h["exp_id"] != self.exp_id]
        if not hits:
            return ToolOutput("관련된 과거 실험 없음")
        return ToolOutput("\n\n".join(f"## {h['exp_id']}\n{h['excerpt']}" for h in hits))

    def t_read_past_experiment(self, exp_id: str, path: str) -> ToolOutput:
        if not re.fullmatch(r"EXP-\d+", exp_id.upper()):
            return ToolOutput("exp_id 형식 오류", is_error=True)
        base = (self.cfg.experiments_dir / exp_id.upper()).resolve()
        p = self._safe(path, base)
        if not p.is_file():
            return ToolOutput(f"파일 없음: {exp_id}/{path}", is_error=True)
        return ToolOutput(p.read_text(encoding="utf-8", errors="replace")[:12000])

    def t_list_data(self, subdir: str = ".") -> ToolOutput:
        p = self._safe(subdir, self.cfg.data_dir)
        if not p.exists():
            return ToolOutput("(데이터 폴더 비어 있음)")
        rows = [f"{f.relative_to(self.cfg.data_dir)}  ({f.stat().st_size} bytes)"
                for f in sorted(p.rglob("*")) if f.is_file()][:300]
        return ToolOutput("\n".join(rows) or "(비어 있음)")

    def t_report_progress(self, message: str) -> ToolOutput:
        now = time.time()
        if now - self._last_progress < 45:
            return ToolOutput("너무 자주 보고함. 잠시 후 다시.")
        self._last_progress = now
        self.notify.digest({"id": self.exp_id}, f"{message[:900]}", role=self.role)
        return ToolOutput("보고함")

    # ---- 종료 도구: payload 만 돌려주고 루프를 끝낸다 ----
    def t_submit_memo(self, **kw) -> ToolOutput:
        return ToolOutput("메모 제출됨", terminal=kw)

    def t_finish_plan(self, **kw) -> ToolOutput:
        return ToolOutput("계획 제출됨", terminal=kw)

    def t_finish_build(self, **kw) -> ToolOutput:
        return ToolOutput("구현 종료 제출됨", terminal=kw)

    def t_finish_execution(self, **kw) -> ToolOutput:
        return ToolOutput("실행 종료 제출됨", terminal=kw)

    def t_request_change(self, **kw) -> ToolOutput:
        return ToolOutput("변경 승인 요청됨", terminal={"change_request": kw})

    def t_finish_report(self, **kw) -> ToolOutput:
        rp = self.exp_dir / "report" / "report.md"
        if not rp.is_file():
            return ToolOutput("report/report.md 가 아직 없음. 먼저 write_file 로 보고서를 쓰세요.", is_error=True)
        missing = consult_check(self.exp_dir, rp.read_text(encoding="utf-8", errors="replace"))
        if missing:
            return ToolOutput("보고서 미완료: plan.md 의 '자문 확인값'이 보고서 '## 자문 확인값 대조' 절에 다 없다. "
                              "각 값마다 최종 값(results/ 출처), 상태(재현·변경·미재현), 달라졌으면 이유를 적고 다시 제출하세요.\n빠진 것:\n"
                              + "\n".join(f"- {m}" for m in missing), is_error=True)
        return ToolOutput("보고서 제출됨", terminal=kw)

    def t_submit_review(self, **kw) -> ToolOutput:
        return ToolOutput("검증 제출됨", terminal=kw)


# ---------------- 자문 확인값 대조 ----------------
CONSULT_SECTION = "자문 확인값 대조"
_NUM = re.compile(r"\d+(?:\.\d+)?")


def consult_values(exp_dir: Path) -> list[dict]:
    try:
        plan = json.loads((Path(exp_dir) / "plan.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [v for v in plan.get("consult_values") or [] if isinstance(v, dict) and str(v.get("value", "")).strip()]


def _section(text: str, title: str) -> str | None:
    m = re.search(rf"^(#+)\s*[0-9.]*\s*{re.escape(title)}.*$", text, flags=re.M)
    if not m:
        return None
    level = len(m.group(1))
    rest = text[m.end():]
    end = re.search(rf"^#{{1,{level}}}\s", rest, flags=re.M)
    return rest[:end.start()] if end else rest


def consult_check(exp_dir: Path, report_text: str) -> list[str]:
    """보고서가 자문 확인값을 모두 대조했는지. 빠진 항목 설명 목록(비면 통과)."""
    vals = consult_values(exp_dir)
    if not vals:
        return []
    sec = _section(report_text, CONSULT_SECTION)
    if sec is None:
        return [f"'## {CONSULT_SECTION}' 절이 없음 (대조할 값 {len(vals)}개)"]
    out = []
    for v in vals:
        nums = _NUM.findall(str(v["value"]))
        found = all(n in sec for n in nums) if nums else str(v.get("item", "")).strip()[:20] in sec
        if not found:
            out.append(f"{v.get('item', '')}: {v['value']} ({v.get('source', '')})")
    return out
