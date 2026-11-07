"""에이전트에게 주는 도구들. 모든 파일 접근은 실험 폴더 안으로 제한된다."""
from __future__ import annotations

import re
import time
from pathlib import Path

from .llm import ToolOutput

CONSULTANTS = ("linguist", "cogsci", "lm", "statistician", "corpus")   # 자문·해석 전문가 5인
ROLES = CONSULTANTS + ("practitioner", "developer", "documenter", "tester")

# ---- 역할별 쓰기 허용 위치 (실험 폴더 기준) ----
WRITE_PREFIXES = {
    **{r: ("notes/", "results/derived/") for r in CONSULTANTS},
    "practitioner": ("code/", "results/", "notes/"),
    "developer": ("code/", "results/derived/", "notes/"),
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
    # ---- 종료 도구 ----
    "submit_memo": {
        "name": "submit_memo",
        "description": "전문가 메모를 제출한다(자문 단계에서는 설계 자문, 해석 단계에서는 결과 해석).",
        "input_schema": {"type": "object", "properties": {
            "memo_markdown": {"type": "string", "description": "메모 전문"},
            "summary": {"type": "string", "description": "연구자에게 보일 1~2문장 요약"},
            "key_concerns": {"type": "array", "items": {"type": "string"}, "description": "핵심 우려·교란·한계"},
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
            "risks": {"type": "array", "items": {"type": "string"}}},
            "required": ["plan_markdown", "summary", "needs_network", "needs_host_accel", "est_runtime_min"]}},
    "finish_execution": {
        "name": "finish_execution", "description": "실행 단계를 끝낸다.",
        "input_schema": {"type": "object", "properties": {
            "status": {"type": "string", "enum": ["success", "partial", "failed"]},
            "notes": {"type": "string", "description": "무엇을 실행했고, 계획에서 벗어난 점과 문제점은 무엇인가"},
            "result_files": {"type": "array", "items": {"type": "string"}}},
            "required": ["status", "notes"]}},
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
                  "read_past_experiment", "list_data", "submit_memo"]
ROLE_TOOLS = {
    **{r: list(_CONSULT_TOOLS) for r in CONSULTANTS},
    "practitioner": ["list_files", "read_file", "write_file", "run_command", "list_data", "search_notebook",
                     "read_past_experiment", "report_progress", "finish_plan", "finish_execution"],
    "developer": ["list_files", "read_file", "write_file", "run_command", "list_data", "search_notebook",
                  "read_past_experiment", "report_progress", "finish_build"],
    "documenter": ["list_files", "read_file", "write_file", "run_command", "search_notebook",
                   "read_past_experiment", "finish_report"],
    "tester": ["list_files", "read_file", "write_file", "run_command", "submit_review"],
}


def tool_schemas(role: str, only: list[str] | None = None) -> list[dict]:
    names = [n for n in ROLE_TOOLS[role] if only is None or n in only]
    return [SCHEMAS[n] for n in names]


class Toolbox:
    def __init__(self, *, cfg, exp_id: str, role: str, sandbox, notebook, notify,
                 network_allowed: bool = False, host_allowed: bool = False):
        self.cfg, self.exp_id, self.role = cfg, exp_id, role
        self.sandbox, self.notebook, self.notify = sandbox, notebook, notify
        self.network_allowed = network_allowed
        self.host_allowed = host_allowed
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
        norm = str(Path(rel)).replace("\\", "/")
        while norm.startswith("./"):
            norm = norm[2:]
        return any(norm.startswith(pref) for pref in WRITE_PREFIXES.get(self.role, ()))

    # ---- 실행 ----
    def execute(self, name: str, args: dict) -> ToolOutput:
        if name not in ROLE_TOOLS[self.role]:
            return ToolOutput(f"이 역할({self.role})은 '{name}' 도구를 쓸 수 없음", is_error=True)
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
            return ToolOutput(f"이 역할({self.role})은 '{path}'에 쓸 수 없음. 허용: {WRITE_PREFIXES.get(self.role)}",
                              is_error=True)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return ToolOutput(f"저장함: {path} ({len(content)}자)")

    def t_run_command(self, command: str, timeout_min: int = 30, where: str = "sandbox") -> ToolOutput:
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
        tail = r.output[-6000:]
        head = f"[exit {r.exit_code}] {r.seconds:.0f}초" + (" [시간 초과]" if r.timed_out else "")
        return ToolOutput(f"{head} (전체 로그: logs/{log.name})\n{tail}", is_error=r.exit_code != 0)

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
        self.notify.post({"id": self.exp_id}, f"📡 {message[:900]}", role=self.role)
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

    def t_finish_report(self, **kw) -> ToolOutput:
        if not (self.exp_dir / "report" / "report.md").is_file():
            return ToolOutput("report/report.md 가 아직 없음. 먼저 write_file 로 보고서를 쓰세요.", is_error=True)
        return ToolOutput("보고서 제출됨", terminal=kw)

    def t_submit_review(self, **kw) -> ToolOutput:
        return ToolOutput("검증 제출됨", terminal=kw)
