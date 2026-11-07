"""연구실장: 디스코드 대화를 받아 요청서를 접수하고, 진행 상황 질의에 답한다."""
from __future__ import annotations

import re
from pathlib import Path

from .agents import director_system
from .llm import ToolOutput, run_agent
from .pipeline import STATUS_LABEL, Lab
from .tools import CONSULTANTS

_PATH = {"type": "string", "description": "실험 폴더 기준 상대경로"}
_ID = {"type": "string", "description": "예: EXP-003"}

DIRECTOR_TOOLS = [
    {"name": "lab_status", "description": "연구실 전체 현황(진행·대기·승인대기·최근 완료)을 본다.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "list_experiments", "description": "실험 목록을 상태별로 본다.",
     "input_schema": {"type": "object", "properties": {"status": {"type": "string"}}}},
    {"name": "get_experiment", "description": "실험 하나의 상태, 단계, 최근 기록, 오류, 파일 수를 본다.",
     "input_schema": {"type": "object", "properties": {"exp_id": _ID}, "required": ["exp_id"]}},
    {"name": "list_experiment_files", "description": "실험 폴더의 파일 목록을 본다.",
     "input_schema": {"type": "object", "properties": {"exp_id": _ID}, "required": ["exp_id"]}},
    {"name": "read_experiment_file",
     "description": "실험 폴더 안의 파일을 읽는다(request.md, plan.md, notes/consult_*.md, report/report.md, "
                    "report/interpretation_*.md, results/*, logs/* 등).",
     "input_schema": {"type": "object", "properties": {"exp_id": _ID, "path": _PATH,
                                                       "max_chars": {"type": "integer", "default": 8000}},
                      "required": ["exp_id", "path"]}},
    {"name": "search_notebook", "description": "과거 실험의 연구노트를 키워드로 검색한다.",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "submit_experiment",
     "description": "정리한 요청서로 실험을 접수한다. 연구자가 확인했거나 확인을 생략하라고 한 뒤에만 호출한다.",
     "input_schema": {"type": "object", "properties": {
         "title": {"type": "string"},
         "request_markdown": {"type": "string", "description": "요청서 전문(제목/연구 질문·가설/데이터/방법/완료 기준/제약/가정)"},
         "priority": {"type": "integer", "default": 0},
         "consult": {"type": "array", "items": {"type": "string", "enum": list(CONSULTANTS)},
                     "description": "자문·해석에 참여할 전문가. 생략하면 5명 모두"}},
         "required": ["title", "request_markdown"]}},
    {"name": "stop_experiment", "description": "실험을 중단한다.",
     "input_schema": {"type": "object", "properties": {"exp_id": _ID}, "required": ["exp_id"]}},
    {"name": "resume_experiment", "description": "실패·중단·일시정지된 실험을 재개한다.",
     "input_schema": {"type": "object", "properties": {"exp_id": _ID}, "required": ["exp_id"]}},
    {"name": "set_priority", "description": "대기 중인 실험의 우선순위를 바꾼다(클수록 먼저).",
     "input_schema": {"type": "object", "properties": {"exp_id": _ID, "priority": {"type": "integer"}},
                      "required": ["exp_id", "priority"]}},
]
# 의도적으로 '승인' 도구는 없다. 승인은 사람이 버튼/슬래시 명령으로만 한다.


def _merge(history: list[dict]) -> list[dict]:
    """API 형식에 맞게: 첫 메시지는 user, 같은 역할 연속 메시지는 합친다."""
    out: list[dict] = []
    for m in history:
        text = (m.get("content") or "").strip()
        if not text:
            continue
        if out and out[-1]["role"] == m["role"]:
            out[-1]["content"] += "\n\n" + text
        else:
            out.append({"role": m["role"], "content": text})
    while out and out[0]["role"] != "user":
        out.pop(0)
    return out


class Director:
    def __init__(self, lab: Lab):
        self.lab = lab
        self.cfg = lab.cfg

    def reply(self, history: list[dict], *, thread_id: int | None = None, channel_id: int | None = None,
              requester_id: int | None = None) -> str:
        msgs = _merge(history)
        if not msgs:
            return "무엇을 도와드릴까요?"
        exp = self.lab.ledger.find_by_thread(thread_id) if thread_id else None
        ctx = self.lab.describe(exp["id"]) if exp else None

        def execute(name: str, a: dict) -> ToolOutput:
            return self._tool(name, a, thread_id, channel_id, requester_id)

        res = run_agent(self.lab.client, model=self.cfg.model_director, system=director_system(ctx),
                        messages=msgs, tools=DIRECTOR_TOOLS, execute=execute, max_turns=12, max_tokens=3000)
        return res.text.strip() or "(응답이 비어 있습니다. 다시 말씀해 주세요.)"

    # ---------- 도구 ----------
    def _file(self, exp_id: str, rel: str) -> Path:
        if not re.fullmatch(r"EXP-\d+", exp_id.upper()):
            raise ValueError("exp_id 형식 오류")
        base = (self.cfg.experiments_dir / exp_id.upper()).resolve()
        p = (base / rel).resolve()
        if p != base and base not in p.parents:
            raise PermissionError("실험 폴더 밖은 읽을 수 없음")
        return p

    def _tool(self, name: str, a: dict, thread_id, channel_id, requester_id) -> ToolOutput:
        lab = self.lab
        if name == "lab_status":
            return ToolOutput(lab.status_text())
        if name == "list_experiments":
            rows = lab.ledger.list(a.get("status"), limit=30)
            return ToolOutput("\n".join(f"{e['id']} [{STATUS_LABEL[e['status']]}] {e['title']}" for e in rows) or "없음")
        if name == "get_experiment":
            return ToolOutput(lab.describe(a["exp_id"]))
        if name == "list_experiment_files":
            d = self._file(a["exp_id"], ".")
            if not d.exists():
                return ToolOutput("없는 실험", is_error=True)
            return ToolOutput("\n".join(f"{f.relative_to(d)} ({f.stat().st_size}B)" for f in sorted(d.rglob("*"))
                                        if f.is_file() and "__pycache__" not in f.parts)[:6000] or "(비어 있음)")
        if name == "read_experiment_file":
            p = self._file(a["exp_id"], a["path"])
            if not p.is_file():
                return ToolOutput("파일 없음", is_error=True)
            data = p.read_bytes()
            if b"\x00" in data[:2048]:
                return ToolOutput("바이너리 파일", is_error=True)
            n = int(a.get("max_chars", 8000))
            t = data.decode("utf-8", "replace")
            return ToolOutput(t[:n] + (f"\n...[{len(t) - n}자 더 있음]" if len(t) > n else ""))
        if name == "search_notebook":
            hits = lab.notebook.search(a["query"])
            return ToolOutput("\n\n".join(f"## {h['exp_id']}\n{h['excerpt']}" for h in hits) or "관련 실험 없음")
        if name == "submit_experiment":
            exp = lab.submit(a["title"], a["request_markdown"], priority=int(a.get("priority", 0)),
                             thread_id=thread_id, channel_id=channel_id, requester_id=requester_id,
                             consult=a.get("consult"))
            return ToolOutput(f"접수됨: {exp['id']}")
        if name == "stop_experiment":
            return ToolOutput(lab.stop(a["exp_id"]))
        if name == "resume_experiment":
            return ToolOutput(lab.resume(a["exp_id"]))
        if name == "set_priority":
            return ToolOutput(lab.set_priority(a["exp_id"], a["priority"]))
        return ToolOutput(f"알 수 없는 도구: {name}", is_error=True)
