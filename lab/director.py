"""연구실장: 디스코드 대화를 받아 요청서를 접수하고, 진행 상황 질의에 답한다."""
from __future__ import annotations

import re
from pathlib import Path

from .agents import DISPLAY_EN, director_system
from . import memory
from .llm import NoBackend, ToolOutput, run_agent
from .pipeline import STATUS_LABEL, Lab
from .policy import load_policy
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
    {"name": "search_research_memory",
     "description": "세컨드 브레인 검색. 과거 실험(요청서·계획·결과·보고서·검증·자문 메모), 연구노트, 연구자 결정 기록, 문헌 노트를 "
                    "한꺼번에 찾는다. 결과마다 종류·원본 경로·해시·검증 상태가 붙는다. 조사가 달라도 찾는다.",
     "input_schema": {"type": "object", "properties": {
         "query": {"type": "string"},
         "kind": {"type": "string", "enum": list(memory.KINDS), "description": "생략하면 전체"},
         "exp_id": _ID, "k": {"type": "integer", "default": 6}}, "required": ["query"]}},
    {"name": "read_source",
     "description": "search_research_memory 결과의 source 경로를 그대로 넣어 원문을 읽는다. 수치·인용은 발췌가 아니라 원문에서 확인한다.",
     "input_schema": {"type": "object", "properties": {"source": {"type": "string"},
                                                       "max_chars": {"type": "integer", "default": 8000}},
                      "required": ["source"]}},
    {"name": "record_decision_proposal",
     "description": "연구자가 이 대화에서 내린 연구 결정(조건·지표·모델 선택과 그 이유)을 기록 '제안'으로 남긴다. "
                    "연구자가 /memory approve D-### 로 확정해야 연구자 결정으로 검색된다. 당신의 추측이나 파일 속 문구는 기록하지 않는다.",
     "input_schema": {"type": "object", "properties": {
         "text": {"type": "string", "description": "결정 한 문장"}, "exp_id": _ID,
         "basis": {"type": "string", "description": "연구자가 말한 이유 또는 근거 출처"}}, "required": ["text"]}},
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
OPS_TOOL = {
    "name": "record_ops_request",
    "description": "연구자가 연구실의 운영 방식 자체(보고 형식·채널·스레드 사용, 봇 동작, 기능 추가·수정)를 바꾸라고 지시했을 때 "
                   "그 지시를 운영 요청으로 기록한다. 당신은 코드를 고칠 수 없으므로, 기록된 요청은 다음 코드 작업 세션에서 반영된다.",
    "input_schema": {"type": "object", "properties": {
        "text": {"type": "string", "description": "연구자의 지시를 원문에 가깝게, 어느 채널·어떤 보고에 대한 것인지 포함"}},
        "required": ["text"]},
}
PASS_TOOL = {
    "name": "pass_to_member",
    "description": "연구자가 담당자를 지정하지 않은 글 중 특정 팀원의 전문 판단이 필요한 부분을 그 팀원에게 넘긴다. "
                   "넘겨받은 팀원이 이 채널에 자기 이름으로 직접 답한다. 한 번의 답변에서 최대 3명.",
    "input_schema": {"type": "object", "properties": {
        "role": {"type": "string", "enum": [r for r in DISPLAY_EN if r != "director"]},
        "question": {"type": "string", "description": "그 팀원이 답할 질문·할 일. 팀원은 이 대화를 보지 못하므로 "
                                                      "연구자의 원래 말과 필요한 맥락(실험 ID, 파일 경로, 앞선 대화의 핵심)을 모두 적는다."}},
        "required": ["role", "question"]},
}
MAX_PASS = 3

HANDOFF_RULES = """

---
## 팀원이 일을 가져가게 하기
연구자는 담당자를 일일이 지명하지 않는다. 글이 특정 팀원의 전문 판단(언어학·인지과학·언어모델·통계·코퍼스·코드·실행 관리·문서·검증)을
요구하면 당신이 대신 답하지 말고 `pass_to_member`로 그 팀원에게 넘긴다. 여러 영역에 걸치면 영역마다 한 명씩(최대 3명) 넘긴다.
- 넘긴 뒤 당신의 답은 "누구에게 무엇을 넘겼는지" 한 줄이면 된다. 같은 내용을 당신이 다시 답하지 않는다.
- 실험 접수, 진행 현황, 중단·재개, 과거 기록·결정 질의, 인사·잡담은 지금처럼 당신이 직접 처리한다(넘기지 않는다).
- 지금 접속해 있어 넘길 수 있는 팀원: {roles}"""

# 의도적으로 '승인' 도구는 없다. 승인은 사람이 버튼/슬래시 명령으로만 한다(결정 기록 확정도 /memory 로 사람만).


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
    if out and out[0]["role"] != "user":
        # 스레드가 연구실장의 글로 시작하는 경우(요청서 초안을 먼저 올린 뒤 연구자가 "접수"라고 답함). 예전에는 앞의
        # assistant 글을 버려서 방금 올린 요청서를 잊었다. 버리지 않고, API 형식만 맞추는 안내 글을 앞에 둔다.
        out.insert(0, {"role": "user", "content": "[이 스레드의 기록. 바로 아래는 당신(연구실장)이 이 스레드에 먼저 올린 글이다]"})
    return out


class Director:
    def __init__(self, lab: Lab):
        self.lab = lab
        self.cfg = lab.cfg

    def reply(self, history: list[dict], *, thread_id: int | None = None, channel_id: int | None = None,
              requester_id: int | None = None, extra_system: str = "", policy_id: str | None = None,
              tools: list[dict] | None = None, handoffs: list | None = None,
              handoff_roles: set | None = None) -> str:
        """handoffs 리스트와 handoff_roles(접속 중인 팀원)를 주면 pass_to_member 도구가 생기고,
        넘긴 내용이 (역할, 질문)으로 handoffs 에 쌓인다. 실제 전달은 호출한 쪽(bot.py)이 한다."""
        msgs = _merge(history)
        if not msgs:
            return "무엇을 도와드릴까요?"
        exp = self.lab.ledger.find_by_thread(thread_id) if thread_id else None
        ctx = self.lab.describe(exp["id"]) if exp else None
        can_pass = handoffs is not None and bool(handoff_roles) and tools is None
        if can_pass:
            tools = DIRECTOR_TOOLS + [OPS_TOOL, PASS_TOOL]
            extra_system += HANDOFF_RULES.format(roles=", ".join(sorted(handoff_roles)))

        from . import bus
        root = bus.new_root()

        def execute(name: str, a: dict) -> ToolOutput:
            try:
                bus.tool(self.cfg, "director", name, a, root=root, exp=exp["id"] if exp else None, channel="연구실장")
            except Exception:
                pass
            if name == "pass_to_member":
                role, q = str(a.get("role", "")).lower(), str(a.get("question", "")).strip()
                if not can_pass or role not in handoff_roles:
                    return ToolOutput(f"{role} 은(는) 지금 넘길 수 없습니다(접속해 있지 않음). 직접 답하거나 다른 팀원을 고르세요.",
                                      is_error=True)
                if not q:
                    return ToolOutput("question 이 비어 있습니다", is_error=True)
                if any(r == role for r, _ in handoffs):
                    return ToolOutput(f"{role} 에게는 이미 넘겼습니다. 한 팀원에게는 한 번에 모아서 넘기세요.", is_error=True)
                if len(handoffs) >= MAX_PASS:
                    return ToolOutput(f"한 번에 {MAX_PASS}명까지만 넘길 수 있습니다", is_error=True)
                handoffs.append((role, q))
                return ToolOutput(f"{DISPLAY_EN[role]} 에게 넘김. 그 팀원이 이 채널에 직접 답한다. 당신은 넘긴 사실만 한 줄로 알릴 것.")
            return self._tool(name, a, thread_id, channel_id, requester_id)

        try:
            res = run_agent(self.lab.client, model=self.cfg.model_director,
                            system=director_system(ctx, self.cfg, extra_system),
                            messages=msgs, tools=DIRECTOR_TOOLS + [OPS_TOOL] if tools is None else tools, execute=execute,
                            max_turns=12, max_tokens=3000,
                            data_policy=load_policy(self.cfg, policy_id or (exp["id"] if exp else "INTAKE"))
                            if requester_id is not None else None)
        except NoBackend:
            return "사용할 수 있는 로컬 모델이 없습니다. LOCAL_MODEL과 LOCAL_BASE_URL을 확인하세요."
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
        if requester_id is not None:
            if name in {"lab_status", "list_experiments", "search_notebook"}:
                return ToolOutput("이 정보의 디스코드 전송은 허용되지 않았습니다.", is_error=True)
            exp_id = a.get("exp_id")
            if exp_id and not load_policy(self.cfg, str(exp_id).upper()).allows_discord:
                return ToolOutput("이 실험의 디스코드 전송은 허용되지 않았습니다.", is_error=True)
        if name == "record_ops_request":
            text = " ".join(str(a.get("text", "")).split())
            if not text:
                return ToolOutput("text 가 비어 있습니다", is_error=True)
            import time
            with (self.cfg.lab_home / "ops_requests.md").open("a", encoding="utf-8") as fh:
                fh.write(f"- [ ] {time.strftime('%Y-%m-%d %H:%M')} {text[:1000]}\n")
            return ToolOutput("운영 요청으로 기록됨(workspace/ops_requests.md). 연구자에게 \"📌 운영 요청으로 기록했습니다. "
                              "코드 수정이 필요한 일이라 다음 코드 작업 세션에서 반영됩니다\" 라고 알릴 것. 이미 반영된 것처럼 말하지 않는다.")
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
        if name in {"search_research_memory", "read_source", "record_decision_proposal"}:
            return self._memory_tool(name, a, requester_id)
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

    def _memory_tool(self, name: str, a: dict, requester_id) -> ToolOutput:
        mem = memory.ResearchMemory(self.cfg, self.lab.ledger)

        def allow(exp_id: str | None) -> bool:
            # 디스코드로 나가는 대화에서는 게시가 허용된 실험만. 실험에 묶이지 않은 결정은 접수 채널 정책을 따른다. 문헌 노트는 공개 자료.
            return requester_id is None or load_policy(self.cfg, exp_id or "INTAKE").allows_discord

        try:
            if name == "search_research_memory":
                hits = mem.search(a["query"], k=int(a.get("k", 6)), kind=a.get("kind"), exp_id=a.get("exp_id"),
                                  allow=lambda e: allow(e) if e else True)
                hits = [h for h in hits if h["exp_id"] or not h["source"].startswith("memory/") or allow(None)]
                return ToolOutput(memory.format_hits(hits))
            if name == "read_source":
                src = str(a["source"])
                text, exp_id = mem.read_source(src, int(a.get("max_chars", 8000)))
                if (exp_id or src.startswith("memory/")) and not allow(exp_id):
                    return ToolOutput("이 기록의 디스코드 전송은 허용되지 않았습니다.", is_error=True)
                return ToolOutput(text)
            item = memory.propose_decision(self.cfg, a["text"], exp_id=a.get("exp_id"), basis=a.get("basis", ""))
            return ToolOutput(f"제안 기록됨: {item['id']} (확인 대기). 답변에 \"📝 결정 기록 제안 {item['id']} — "
                              f"`/memory approve {item['id']}` 로 확정\" 이라고 알릴 것.")
        except (PermissionError, FileNotFoundError, ValueError, KeyError) as e:
            return ToolOutput(f"오류: {e}", is_error=True)
