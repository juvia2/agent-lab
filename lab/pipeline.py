"""연구실 본체: 실험 접수, 대기열, 단계별 진행, 승인 게이트, 검증→수정 순환."""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .agents import ROLE_META, label, model_for, system_for
from .config import ROOT, Config
from .ledger import PHASE_STATUS, Ledger
from .llm import BudgetExceeded, NoBackend, Stopped, run_agent
from .notebook import Notebook
from .notify import Notifier
from .sandbox import Sandbox
from .tools import CONSULTANTS, ROLE_TOOLS, Toolbox, tool_schemas

log = logging.getLogger("lab")

STATUS_LABEL = {"queued": "⏳ 대기", "planning": "🧭 설계 중", "awaiting_approval": "🔐 승인 대기",
                "running": "🔬 실행 중", "analyzing": "📊 분석 중", "done": "✅ 완료",
                "failed": "❌ 실패", "stopped": "⏹ 중단", "paused": "⏸ 일시정지"}
PHASE_LABEL = {"consult": "전문가 자문", "plan": "계획 통합", "build": "코드 구현", "execute": "실험 실행",
               "analyze": "전체 분석", "interpret": "전문가 해석", "report": "보고서·검증"}
MAX_REVIEW_ROUNDS = 3        # 초안 1회 + 수정 2회

GITIGNORE = "hf_cache/\ndata/\nledger.db*\n*.pt\n*.bin\n*.safetensors\n*.ckpt\n*.npy\n__pycache__/\n"


def _only(role: str, *exclude: str) -> list[str]:
    return [n for n in ROLE_TOOLS[role] if n not in exclude]


def fmt_issues(issues: list[dict]) -> str:
    rows = []
    for i in issues:
        rows.append(f"- [{i.get('severity')}/{i.get('owner')}] {i.get('where', '')} {i.get('problem', '')}"
                    + (f" → 제안: {i['fix']}" if i.get("fix") else ""))
    return "\n".join(rows) or "(없음)"


def _short(t: str, n: int) -> str:
    t = (t or "").strip()
    return t if len(t) <= n else t[:n] + "…"


class Lab:
    def __init__(self, cfg: Config, ledger: Ledger, client, notifier: Notifier,
                 sandbox: Sandbox | None = None, notebook: Notebook | None = None):
        self.cfg, self.ledger, self.client, self.notifier = cfg, ledger, client, notifier
        self.sandbox = sandbox or Sandbox(cfg)
        self.notebook = notebook or Notebook(cfg.notebook_dir)
        cfg.ensure_dirs()
        self._ensure_git()

    # ================= 연구자 조작 =================
    def submit(self, title: str, request_md: str, *, priority: int = 0, thread_id: int | None = None,
               channel_id: int | None = None, requester_id: int | None = None,
               consult: list[str] | None = None) -> dict:
        consult = [c for c in (consult or list(CONSULTANTS)) if c in CONSULTANTS] or list(CONSULTANTS)
        eid = self.ledger.create_experiment(title=title, request_md=request_md, priority=priority,
                                            thread_id=thread_id, channel_id=channel_id,
                                            requester_id=requester_id, token_budget=self.cfg.token_budget,
                                            meta={"consult": consult})
        d = self.cfg.experiments_dir / eid
        for sub in ("code", "results/derived", "logs", "report/figures", "review", "notes"):
            (d / sub).mkdir(parents=True, exist_ok=True)
        (d / "request.md").write_text(request_md, encoding="utf-8")
        src = ROOT / "templates" / "lab_utils.py"
        if src.exists():
            shutil.copy(src, d / "code" / "lab_utils.py")
        exp = self.ledger.get(eid)
        ahead = len([e for e in self.ledger.list("queued") if e["id"] != eid])
        self.notifier.post(exp, f"📥 **{eid}** 접수 — {title}\n"
                                f"자문: {', '.join(label(r) for r in consult)}\n"
                                f"대기열 앞에 {ahead}건. 진행 상황은 이 스레드에 올라옵니다.")
        return exp

    def stop(self, exp_id: str) -> str:
        exp = self.ledger.get(exp_id)
        if not exp:
            return f"{exp_id}: 없는 실험입니다."
        if exp["status"] in ("done", "failed", "stopped"):
            return f"{exp['id']}는 이미 {STATUS_LABEL[exp['status']]} 상태입니다."
        self.ledger.update(exp["id"], status="stopped")
        self.sandbox.kill(exp["id"])
        self.ledger.add_event(exp["id"], "stopped", "연구자 요청으로 중단")
        self.notifier.post(self.ledger.get(exp["id"]), f"⏹ {exp['id']} 중단했습니다. 이어서 하려면 `/resume {exp['id']}`")
        return f"{exp['id']} 중단함."

    def resume(self, exp_id: str) -> str:
        exp = self.ledger.get(exp_id)
        if not exp:
            return f"{exp_id}: 없는 실험입니다."
        if exp["status"] not in ("failed", "paused", "stopped"):
            return f"{exp['id']}는 {STATUS_LABEL[exp['status']]} 상태라 재개할 수 없습니다."
        fields: dict = {"error": None}
        if exp["status"] == "paused" and exp.get("error") == "토큰 예산 초과":
            fields["token_budget"] = exp["token_budget"] + self.cfg.token_budget
        if hasattr(self.client, "reset_cooldowns"):      # 한도·로그인을 고친 뒤 이어가는 경우가 많다
            self.client.reset_cooldowns()
        if exp["approval_reasons"] and not exp["approved"]:
            self.ledger.update(exp["id"], status="awaiting_approval", **fields)
            self.notifier.ask_approval(self.ledger.get(exp["id"]), json.loads(exp["approval_reasons"]),
                                       "(승인이 필요한 상태로 돌아왔습니다)")
            return f"{exp['id']}는 승인이 필요합니다."
        self.ledger.update(exp["id"], status="queued", **fields)
        self.ledger.add_event(exp["id"], "resumed", f"재개 (단계: {PHASE_LABEL.get(exp['phase'], exp['phase'])})")
        return f"{exp['id']} 재개: '{PHASE_LABEL.get(exp['phase'], exp['phase'])}' 단계부터 이어서 진행합니다."

    def approve(self, exp_id: str) -> str:
        exp = self.ledger.get(exp_id)
        if not exp or exp["status"] != "awaiting_approval":
            return f"{exp_id}: 승인 대기 상태가 아닙니다."
        self.ledger.update(exp["id"], approved=1, status="queued")
        self.ledger.add_event(exp["id"], "approved", "연구자 승인: " + (exp["approval_reasons"] or ""))
        self.notifier.post(self.ledger.get(exp["id"]), f"🔓 {exp['id']} 승인되었습니다. 구현·실행을 시작합니다.")
        return f"{exp['id']} 승인함."

    def reject(self, exp_id: str) -> str:
        exp = self.ledger.get(exp_id)
        if not exp or exp["status"] != "awaiting_approval":
            return f"{exp_id}: 승인 대기 상태가 아닙니다."
        self.ledger.update(exp["id"], status="stopped")
        self.ledger.add_event(exp["id"], "rejected", "연구자가 승인 거부")
        self.notifier.post(self.ledger.get(exp["id"]), f"🚫 {exp['id']} 승인이 거부되어 중단했습니다.")
        return f"{exp['id']} 거부함."

    def set_priority(self, exp_id: str, priority: int) -> str:
        exp = self.ledger.get(exp_id)
        if not exp:
            return f"{exp_id}: 없는 실험입니다."
        self.ledger.update(exp["id"], priority=int(priority))
        return f"{exp['id']} 우선순위 {priority}"

    # ================= 현황 =================
    def status_text(self) -> str:
        exps = self.ledger.list(limit=200)
        if not exps:
            return "아직 접수된 실험이 없습니다."
        groups = [("진행 중", ("planning", "running", "analyzing")), ("승인 대기", ("awaiting_approval",)),
                  ("대기열", ("queued",)), ("멈춤/실패", ("paused", "failed", "stopped"))]
        out = ["📊 **연구실 현황**"]
        for name, sts in groups:
            rows = [e for e in exps if e["status"] in sts]
            if rows:
                out.append(f"\n**{name}**")
                out += [f"- {e['id']} {_short(e['title'], 40)} — {STATUS_LABEL[e['status']]}"
                        f" ({PHASE_LABEL.get(e['phase'], e['phase'])})" for e in rows]
        done = [e for e in exps if e["status"] == "done"][:5]
        if done:
            out.append("\n**최근 완료**")
            out += [f"- {e['id']} {_short(e['title'], 40)}" for e in done]
        if hasattr(self.client, "usage_summary"):
            out.append(f"\n🔀 모델 호출(가동 이후): {self.client.usage_summary()}")
        return "\n".join(out)

    def describe(self, exp_id: str) -> str:
        e = self.ledger.get(exp_id)
        if not e:
            return f"{exp_id}: 없는 실험입니다."
        lines = [f"{e['id']} — {e['title']}",
                 f"상태: {STATUS_LABEL[e['status']]} / 단계: {PHASE_LABEL.get(e['phase'], e['phase'])}",
                 f"토큰: {e['tokens_used']:,} / {e['token_budget']:,}"]
        meta = json.loads(e.get("meta_json") or "{}")
        if meta.get("consult"):
            lines.append("자문 대상: " + ", ".join(label(r) for r in meta["consult"]))
        if e["approval_reasons"]:
            lines.append(f"승인 사유: {', '.join(json.loads(e['approval_reasons']))} (승인됨={bool(e['approved'])})")
        if e["error"]:
            lines.append(f"오류: {e['error']}")
        if e["summary"]:
            lines.append(f"요약: {e['summary']}")
        evs = self.ledger.events(e["id"], 12)
        if evs:
            lines.append("최근 기록:")
            lines += [f"  {time.strftime('%m-%d %H:%M', time.localtime(v['ts']))} [{v['kind']}] {_short(v['message'], 220)}"
                      for v in evs]
        d = self.cfg.experiments_dir / e["id"]
        if d.exists():
            cnt = {s: len([f for f in (d / s).rglob('*') if f.is_file()]) if (d / s).exists() else 0
                   for s in ("code", "results", "logs", "report", "review", "notes")}
            lines.append("파일 수: " + ", ".join(f"{k} {v}" for k, v in cnt.items()))
        return "\n".join(lines)

    # ================= 워커 =================
    def process_one(self) -> bool:
        exp = self.ledger.claim_next()
        if not exp:
            return False
        self._run_experiment(exp)
        return True

    def worker_loop(self, stop_event: threading.Event, idle: float = 3.0) -> None:
        while not stop_event.is_set():
            try:
                did = self.process_one()
            except Exception:
                log.exception("worker error")
                did = False
            if not did:
                stop_event.wait(idle)

    def start_workers(self, stop_event: threading.Event) -> list[threading.Thread]:
        threads = []
        for i in range(self.cfg.max_concurrent):
            t = threading.Thread(target=self.worker_loop, args=(stop_event,), name=f"lab-worker-{i}", daemon=True)
            t.start()
            threads.append(t)
        return threads

    def _run_experiment(self, exp: dict) -> None:
        eid = exp["id"]
        handlers = {"consult": self._phase_consult, "plan": self._phase_plan, "build": self._phase_build,
                    "execute": self._phase_execute, "analyze": self._phase_analyze,
                    "interpret": self._phase_interpret, "report": self._phase_report}
        cur = exp
        try:
            while True:
                cur = self.ledger.get(eid)
                if cur["status"] == "stopped":
                    return
                if not handlers[cur["phase"]](cur):
                    return
        except Stopped:
            self.ledger.add_event(eid, "stopped", "작업 중단 확인")
        except BudgetExceeded:
            self.ledger.update(eid, status="paused", error="토큰 예산 초과")
            self.ledger.add_event(eid, "paused", "토큰 예산 초과로 일시정지")
            self.notifier.post(self.ledger.get(eid), f"⏸ {eid}: 토큰 예산을 다 썼습니다. 예산을 더 주고 이어가려면 `/resume {eid}`")
        except NoBackend as e:
            self.ledger.update(eid, status="paused", error=_short(str(e), 900))
            self.ledger.add_event(eid, "paused", f"모델 백엔드 없음: {e}")
            self.notifier.post(self.ledger.get(eid),
                               f"⏸ {eid}: 지금 쓸 수 있는 모델이 없어 일시정지했습니다.\n{_short(str(e), 700)}\n"
                               f"한도가 풀리거나 로그인/서버를 고친 뒤 `/resume {eid}` 로 이어가세요.")
        except Exception as e:
            log.error("experiment %s failed:\n%s", eid, traceback.format_exc())
            self.ledger.update(eid, status="failed", error=f"{type(e).__name__}: {e}"[:1000])
            self.ledger.add_event(eid, "failed", f"{type(e).__name__}: {e}")
            self.notifier.post(self.ledger.get(eid),
                               f"❌ {eid} 실패 ({PHASE_LABEL.get(cur['phase'], cur['phase'])} 단계)\n"
                               f"원인: {_short(str(e), 600)}\n이어서 하려면 `/resume {eid}`")

    # ================= 공통 도우미 =================
    def _say(self, eid: str, text: str, files: list[Path] | None = None, role: str | None = None) -> None:
        """진행 알림. 'label(역할)'로 시작하는 문장은 그 역할의 팀원 봇 이름으로 나간다."""
        self.ledger.add_event(eid, "progress", text)
        if role is None:
            role = next((r for r in ROLE_META if text.startswith(label(r))), None)
        try:
            self.notifier.post(self.ledger.get(eid), text, files, role=role)
        except Exception:
            log.exception("notify failed")

    def _advance(self, eid: str, phase: str) -> None:
        self.ledger.update(eid, phase=phase, status=PHASE_STATUS[phase])

    def _fail(self, eid: str, text: str) -> bool:
        self.ledger.update(eid, status="failed", error=_short(text, 1000))
        self.ledger.add_event(eid, "failed", text)
        self.notifier.post(self.ledger.get(eid), f"❌ {eid} 실패\n{_short(text, 1200)}\n이어서 하려면 `/resume {eid}`")
        return False

    def _meta(self, eid: str) -> dict:
        return json.loads(self.ledger.get(eid).get("meta_json") or "{}")

    def _set_meta(self, eid: str, **kw) -> None:
        m = self._meta(eid)
        m.update(kw)
        self.ledger.update(eid, meta_json=json.dumps(m, ensure_ascii=False))

    def _perms(self, exp: dict) -> tuple[bool, bool]:
        plan = json.loads(exp["plan_json"]) if exp.get("plan_json") else {}
        pol = self.cfg.network_policy
        network = bool(plan.get("needs_network")) and (pol == "allow" or (pol == "ask" and bool(exp["approved"])))
        host = bool(plan.get("needs_host_accel")) and bool(exp["approved"])
        return network, host

    def _gate_reasons(self, plan: dict) -> list[str]:
        reasons = []
        if plan.get("needs_network") and self.cfg.network_policy == "ask":
            reasons.append("네트워크 사용 (모델·데이터 다운로드)")
        if plan.get("needs_host_accel"):
            reasons.append("맥 호스트에서 직접 실행 (MPS/GPU, 격리 없음)")
        est = int(plan.get("est_runtime_min") or 0)
        if est > self.cfg.approval_runtime_min:
            reasons.append(f"예상 실행 시간 {est}분 (기준 {self.cfg.approval_runtime_min}분 초과)")
        return reasons

    def _usage_cb(self, eid: str):
        def cb(n: int) -> None:
            used = self.ledger.add_tokens(eid, n)
            if used > self.ledger.get(eid)["token_budget"]:
                raise BudgetExceeded()
        return cb

    def _stop_fn(self, eid: str):
        return lambda: self.ledger.get(eid)["status"] == "stopped"

    def _call(self, eid: str, role: str, prompt: str, *, only: list[str] | None = None, network: bool = False,
              host: bool = False, max_tokens: int = 8192):
        tb = Toolbox(cfg=self.cfg, exp_id=eid, role=role, sandbox=self.sandbox, notebook=self.notebook,
                     notify=self.notifier, network_allowed=network, host_allowed=host)
        return run_agent(self.client, model=model_for(self.cfg, role), system=system_for(role), prompt=prompt,
                         tools=tool_schemas(role, only), execute=tb.execute, on_usage=self._usage_cb(eid),
                         should_stop=self._stop_fn(eid), max_turns=self.cfg.max_agent_turns, max_tokens=max_tokens)

    def _header(self, exp: dict, stage: str) -> str:
        network, host = self._perms(exp)
        return (f"실험 ID: {exp['id']}\n제목: {exp['title']}\n지금 단계: {stage}\n"
                f"작업 디렉터리가 곧 실험 폴더이다(상대경로 사용).\n"
                f"네트워크: {'허용' if network else '차단'} / 호스트 직접 실행: {'허용(where=host, 이때 /data 대신 $LAB_DATA 사용)' if host else '불가'}\n\n"
                f"## 요청서(request.md)\n{exp['request_md']}")

    @staticmethod
    def _write_memo(path: Path, role: str, memo: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        body = [f"# {label(role)} 메모", "", memo.get("memo_markdown", "").strip(), "", "## 핵심 우려"]
        body += [f"- {c}" for c in memo.get("key_concerns", [])] or ["- (없음)"]
        body += ["", "## 권고"] + ([f"- {r}" for r in memo.get("recommendations", [])] or ["- (없음)"])
        path.write_text("\n".join(body) + "\n", encoding="utf-8")

    def _memo_round(self, exp: dict, roles: list[str], *, stage: str, instruction: str, out_fmt: str,
                    extra: dict[str, str] | None = None, force: bool = False) -> dict[str, dict]:
        """전문가 여러 명이 병렬로 메모를 쓴다. 이미 있으면(재개) 건너뛴다."""
        eid = exp["id"]
        d = self.cfg.experiments_dir / eid
        network, host = self._perms(exp)

        def one(role: str):
            out = d / out_fmt.format(role=role)
            if out.exists() and not force:
                return role, None
            prompt = (self._header(exp, stage) + "\n\n" + instruction +
                      (f"\n\n## 검증 담당의 지적(반영해서 다시 쓰세요)\n{extra[role]}" if extra and extra.get(role) else ""))
            res = self._call(eid, role, prompt, network=network, host=host)
            memo = res.terminal or {"memo_markdown": res.text or "(메모를 제출하지 않음)",
                                    "summary": "(정식 메모 제출 없이 종료됨)", "key_concerns": [], "recommendations": []}
            self._write_memo(out, role, memo)
            return role, memo

        got: dict[str, dict] = {}
        with ThreadPoolExecutor(max_workers=max(1, len(roles))) as ex:
            for role, memo in [f.result() for f in [ex.submit(one, r) for r in roles]]:
                if memo:
                    got[role] = memo
        return got

    def _post_memos(self, eid: str, title: str, memos: dict[str, dict]) -> None:
        if not memos:
            return
        self._say(eid, title)
        for role, m in memos.items():                     # 전문가마다 자기 이름으로 올린다
            lines = [f"{label(role)}: {_short(m.get('summary', ''), 300)}"]
            for c in m.get("key_concerns", [])[:3]:
                lines.append(f"  ⚠️ {_short(c, 200)}")
            self._say(eid, "\n".join(lines), role=role)

    # ================= 단계 1: 전문가 자문 =================
    def _phase_consult(self, exp: dict) -> bool:
        eid = exp["id"]
        roles = self._meta(eid).get("consult") or list(CONSULTANTS)
        self._say(eid, f"🧭 설계 자문 시작: {', '.join(label(r) for r in roles)}")
        memos = self._memo_round(
            exp, roles, stage="consult(자문)", out_fmt="notes/consult_{role}.md",
            instruction="자문 단계다. request.md 와 관련 과거 실험을 검토하고, 당신의 전문 영역에서 실험 설계 전에 "
                        "바로잡아야 할 점과 권고를 `submit_memo`로 제출하세요.")
        self._post_memos(eid, "🧭 자문 메모 도착", memos)
        self._advance(eid, "plan")
        return True

    # ================= 단계 2: 계획 통합 =================
    def _phase_plan(self, exp: dict) -> bool:
        eid = exp["id"]
        d = self.cfg.experiments_dir / eid
        memos = sorted(p.name for p in (d / "notes").glob("consult_*.md"))
        prompt = (self._header(exp, "plan(계획 통합)") +
                  f"\n\n자문 메모: {', '.join('notes/' + m for m in memos) or '(없음)'}\n"
                  "자문을 통합해 실험 계획을 세우고 `finish_plan`으로 제출하세요.")
        res = self._call(eid, "practitioner", prompt, only=_only("practitioner", "finish_execution"))
        plan = res.terminal
        if not plan:
            raise RuntimeError("실험 실무 담당이 계획을 제출하지 않고 종료함: " + _short(res.text, 300))
        (d / "plan.md").write_text(plan["plan_markdown"], encoding="utf-8")
        (d / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        self.ledger.update(eid, plan_json=json.dumps(plan, ensure_ascii=False))
        self._say(eid, f"{label('practitioner')} 계획 확정\n{_short(plan['summary'], 900)}\n"
                       f"예상 {plan.get('est_runtime_min', '?')}분"
                       + (f" / 위험: {_short('; '.join(plan.get('risks', [])), 300)}" if plan.get("risks") else ""))
        if plan.get("needs_network") and self.cfg.network_policy == "deny":
            self._say(eid, "ℹ️ 네트워크 정책이 deny 라서 네트워크 없이 진행합니다(필요한 데이터가 없으면 실패할 수 있음).")
        reasons = self._gate_reasons(plan)
        if reasons and not exp["approved"]:
            self.ledger.update(eid, status="awaiting_approval", phase="build",
                               approval_reasons=json.dumps(reasons, ensure_ascii=False))
            self.ledger.add_event(eid, "approval", "승인 필요: " + "; ".join(reasons))
            self.notifier.ask_approval(self.ledger.get(eid), reasons, plan["summary"])
            return False
        self._advance(eid, "build")
        return True

    # ================= 단계 3: 구현 =================
    def _phase_build(self, exp: dict) -> bool:
        eid = exp["id"]
        d = self.cfg.experiments_dir / eid
        network, host = self._perms(exp)
        meta = self._meta(eid)
        fix_note = meta.get("fix_note")
        if fix_note:
            stage = "fix(실행 중 발견된 문제 수정)"
            task = ("실험 실무 담당이 실행 중 아래 문제를 보고했다. 원인을 확인해 코드를 고치고 smoke test 로 다시 확인한 뒤 "
                    f"`finish_build`로 넘기세요.\n\n## 실행 문제\n{fix_note}")
        else:
            stage = "build(구현)"
            task = ("plan.md 와 자문 메모(notes/consult_*.md)를 읽고 구현 요구사항대로 코드를 구현하세요. "
                    "작은 입력으로 끝까지 시험 실행한 뒤 `finish_build`로 넘기세요.")
        self._say(eid, f"{label('developer')} {'수정' if fix_note else '구현'} 시작")
        res = self._call(eid, "developer", self._header(exp, stage) + "\n\n" + task, network=network, host=host)
        b = res.terminal
        if not b:
            raise RuntimeError("백엔드 개발자가 구현 종료를 보고하지 않음: " + _short(res.text, 300))
        (d / "notes" / "build.json").write_text(json.dumps(b, ensure_ascii=False, indent=2), encoding="utf-8")
        self._say(eid, f"{label('developer')} 구현 {b['status']}\n{_short(b['summary'], 700)}\n"
                       f"테스트: {_short('; '.join(b.get('tests_run', [])), 400)}"
                       + (f"\n한계: {_short('; '.join(b['known_limits']), 300)}" if b.get("known_limits") else ""))
        if b["status"] == "failed":
            return self._fail(eid, "구현 실패: " + b["summary"])
        self._set_meta(eid, fix_note=None)
        self._advance(eid, "execute")
        return True

    # ================= 단계 4: 실행 =================
    def _phase_execute(self, exp: dict) -> bool:
        eid = exp["id"]
        d = self.cfg.experiments_dir / eid
        network, host = self._perms(exp)
        self._say(eid, f"{label('practitioner')} 실행 시작")
        prompt = (self._header(exp, "execute(실행)") +
                  "\n\nplan.md 와 notes/build.json, code/README.md 를 읽고 구현된 코드를 실행해 결과를 만드세요. "
                  "이전 시도의 흔적이 있으면 이어서 하세요. 끝나면 `finish_execution`.")
        res = self._call(eid, "practitioner", prompt, only=_only("practitioner", "finish_plan"),
                         network=network, host=host)
        x = res.terminal or {"status": "partial", "notes": "종료 보고 없이 멈춤: " + _short(res.text, 500),
                             "result_files": []}
        (d / "notes" / "execution.json").write_text(json.dumps(x, ensure_ascii=False, indent=2), encoding="utf-8")
        self._say(eid, f"{label('practitioner')} 실행 {x['status']}\n{_short(x['notes'], 900)}")
        if x["status"] == "failed":
            meta = self._meta(eid)
            if meta.get("fix_rounds", 0) < 1:
                self._set_meta(eid, fix_rounds=meta.get("fix_rounds", 0) + 1, fix_note=x["notes"])
                self._say(eid, "↩️ 실행 문제를 백엔드 개발자에게 돌려보내 수정을 요청합니다(1회).")
                self._advance(eid, "build")
                return True
            return self._fail(eid, "실행 실패(수정 후에도): " + x["notes"])
        self._advance(eid, "analyze")
        return True

    # ================= 단계 5: 전체 분석 =================
    def _phase_analyze(self, exp: dict) -> bool:
        eid = exp["id"]
        d = self.cfg.experiments_dir / eid
        network, host = self._perms(exp)
        self._say(eid, f"{label('developer')} 전체 분석 시작")
        prompt = (self._header(exp, "analyze(전체 분석)") +
                  "\n\n실험 결과 전체를 대상으로 plan.md 의 분석 계획을 구현·실행하세요. 데이터 품질 점검을 먼저 하고, "
                  "산출물은 results/derived/ 에 저장하세요(analysis_summary.json 포함). 끝나면 `finish_build`.")
        res = self._call(eid, "developer", prompt, network=network, host=host)
        b = res.terminal
        if not b:
            raise RuntimeError("백엔드 개발자가 분석 종료를 보고하지 않음: " + _short(res.text, 300))
        (d / "notes" / "analysis_build.json").write_text(json.dumps(b, ensure_ascii=False, indent=2), encoding="utf-8")
        warn = "" if (d / "results" / "derived" / "analysis_summary.json").exists() else \
            "\n⚠️ results/derived/analysis_summary.json 이 없습니다."
        self._say(eid, f"{label('developer')} 전체 분석 {b['status']}\n{_short(b['summary'], 700)}{warn}")
        if b["status"] == "failed":
            return self._fail(eid, "전체 분석 실패: " + b["summary"])
        self._advance(eid, "interpret")
        return True

    # ================= 단계 6: 전문가 해석 =================
    def _interpret_instruction(self) -> str:
        return ("해석 단계다. results/ 와 results/derived/ 의 전체 분석 결과를 읽고, 당신의 전문 영역에서 결과를 해석해 "
                "`submit_memo`로 제출하세요. 수치는 파일에서 읽은 값과 출처 파일만 인용하세요. 계획서의 해석 기준과 "
                "자문 때 당신이 낸 우려(notes/consult_*.md)가 결과에서 어떻게 되었는지도 다루세요.")

    def _phase_interpret(self, exp: dict) -> bool:
        eid = exp["id"]
        roles = self._meta(eid).get("consult") or list(CONSULTANTS)
        self._say(eid, f"🔎 결과 해석 시작: {', '.join(label(r) for r in roles)}")
        memos = self._memo_round(exp, roles, stage="interpret(해석)", out_fmt="report/interpretation_{role}.md",
                                 instruction=self._interpret_instruction())
        self._post_memos(eid, "🔎 해석 메모 도착", memos)
        self._advance(eid, "report")
        return True

    # ================= 단계 7: 보고서 ↔ 검증 순환 =================
    def _fix_round(self, exp: dict, issues: list[dict]) -> bool:
        """검증 지적을 담당자별로 처리한다. 결과가 바뀌었으면 True."""
        eid = exp["id"]
        by: dict[str, list[dict]] = {}
        for i in issues:
            by.setdefault(i.get("owner", "documenter"), []).append(i)
        network, host = self._perms(exp)
        changed = False
        if by.get("practitioner"):
            self._say(eid, f"↩️ 검증 지적을 {label('practitioner')}에게 전달 ({len(by['practitioner'])}건)")
            self._call(eid, "practitioner", self._header(exp, "fix(실행 문제 수정)") +
                       "\n\n## 검증 지적\n" + fmt_issues(by["practitioner"]) +
                       "\n\n문제를 고치고 필요한 부분만 다시 실행하세요. 끝나면 `finish_execution`.",
                       only=_only("practitioner", "finish_plan"), network=network, host=host)
            changed = True
        if by.get("developer") or changed:
            self._say(eid, f"↩️ {label('developer')} 코드·분석 수정" +
                      (f" ({len(by.get('developer', []))}건)" if by.get("developer") else " (재실행 반영)"))
            self._call(eid, "developer", self._header(exp, "fix(분석 수정·재실행)") +
                       "\n\n## 검증 지적\n" + fmt_issues(by.get("developer", [])) +
                       ("\n\n(실험이 다시 실행되어 결과가 바뀌었을 수 있으니 전체 분석을 다시 실행하세요.)" if changed else "") +
                       "\n\n수정 후 분석을 다시 실행하고 `finish_build`로 제출하세요.", network=network, host=host)
            changed = True
        roles_all = self._meta(eid).get("consult") or list(CONSULTANTS)
        targets = set(roles_all) if changed else set()
        targets |= {r for r in by if r in CONSULTANTS}
        if targets:
            self._say(eid, "↩️ 전문가 해석 갱신: " + ", ".join(label(r) for r in sorted(targets)))
            extra = {r: fmt_issues(by.get(r, [])) for r in targets if by.get(r)}
            self._memo_round(exp, sorted(targets), stage="interpret(해석 갱신)",
                             out_fmt="report/interpretation_{role}.md",
                             instruction=self._interpret_instruction() + "\n(결과나 지적이 바뀌었으므로 다시 작성)",
                             extra=extra, force=True)
        return changed

    def _phase_report(self, exp: dict) -> bool:
        eid = exp["id"]
        d = self.cfg.experiments_dir / eid
        network, host = self._perms(exp)
        issues: list[dict] = []
        report: dict = {}
        review: dict = {}
        rnd = 0
        for rnd in range(1, MAX_REVIEW_ROUNDS + 1):
            prompt = self._header(exp, "report(보고서 작성)" if rnd == 1 else f"report({rnd - 1}차 수정)")
            prompt += ("\n\n자료를 모두 읽고 `report/report.md` 를 작성한 뒤 `finish_report`로 제출하세요." if rnd == 1 else
                       "\n\n## 검증 담당의 지적\n" + fmt_issues(issues) +
                       "\n\n담당자들이 갱신한 결과·해석(notes/, report/interpretation_*.md, results/derived/)을 다시 읽고 "
                       "보고서를 고쳐 `finish_report`로 다시 제출하세요.")
            res = self._call(eid, "documenter", prompt, network=network, host=host)
            if not res.terminal:
                raise RuntimeError("서류화 담당이 보고서를 제출하지 않고 종료함: " + _short(res.text, 300))
            report = res.terminal
            self._say(eid, f"{label('documenter')} 보고서 {'초안' if rnd == 1 else f'{rnd - 1}차 수정본'} 작성 → 검증 요청")

            vres = self._call(eid, "tester", self._header(exp, f"verify({rnd}차 검증)") +
                              "\n\n보고서·코드·결과를 독립적으로 검증하고 `submit_review`로 제출하세요. "
                              "핵심 수치는 원자료에서 직접 재계산하세요.", network=network, host=host)
            review = vres.terminal or {"verdict": "unverified", "issues": [], "checks_run": [],
                                       "summary": "검증 담당이 판정을 제출하지 않음 — 검증 미완료"}
            (d / "review" / f"review_{rnd}.json").write_text(json.dumps(review, ensure_ascii=False, indent=2),
                                                             encoding="utf-8")
            issues = review.get("issues", [])
            blocking = [i for i in issues if i.get("severity") in ("critical", "major")]
            self._say(eid, f"{label('tester')} {rnd}차 검증: **{review['verdict']}** — {_short(review.get('summary', ''), 400)}\n"
                           f"지적 {len(issues)}건 (치명·주요 {len(blocking)}건), 직접 수행한 검증 {len(review.get('checks_run', []))}건")
            if review["verdict"] != "revise" or not blocking:
                break
            if rnd == MAX_REVIEW_ROUNDS:
                break
            self._fix_round(self.ledger.get(eid), issues)

        unresolved = [i for i in review.get("issues", []) if i.get("severity") in ("critical", "major")] \
            if review.get("verdict") == "revise" else []
        self._append_review_section(d / "report" / "report.md", review, rnd, unresolved)
        return self._finish(eid, report, review, rnd, unresolved)

    @staticmethod
    def _append_review_section(path: Path, review: dict, rounds: int, unresolved: list[dict]) -> None:
        verdict = review.get("verdict")
        head = {"pass": "통과", "revise": "미해결 지적 있음", "unverified": "검증 미완료"}.get(verdict, str(verdict))
        lines = ["", "---", "## 검증 결과 (자동 기록)", f"- 판정: **{head}** ({rounds}차 검증)",
                 f"- 검증 요약: {review.get('summary', '')}"]
        if review.get("checks_run"):
            lines.append("- 검증 담당이 직접 수행한 검증:")
            lines += [f"  - {c}" for c in review["checks_run"]]
        if unresolved:
            lines.append("- **해결되지 않은 지적(결과 해석 시 주의):**")
            lines += [f"  - [{i.get('severity')}] {i.get('where', '')} {i.get('problem', '')}" for i in unresolved]
        minors = [i for i in review.get("issues", []) if i.get("severity") == "minor"]
        if minors:
            lines.append("- 경미한 지적:")
            lines += [f"  - {i.get('problem', '')}" for i in minors]
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    def _finish(self, eid: str, report: dict, review: dict, rounds: int, unresolved: list[dict]) -> bool:
        exp = self.ledger.get(eid)
        d = self.cfg.experiments_dir / eid
        verdict = review.get("verdict")
        vline = {"pass": f"✅ 검증 통과 ({rounds}차)", "revise": f"⚠️ 검증 지적 {len(unresolved)}건 미해결 — 보고서 끝의 '검증 결과'를 확인하세요",
                 "unverified": "⚠️ 검증이 완료되지 않았습니다"}.get(verdict, str(verdict))
        files: list[Path] = [d / "report" / "report.md"]
        for a in report.get("attachments", []):
            p = (d / a).resolve()
            if p.is_file() and d.resolve() in p.parents and p not in files:
                files.append(p)
        files = files[:8]
        summary = _short(report.get("discord_summary", ""), 1500)
        body = (f"{summary}\n\n핵심 발견:\n" + "\n".join(f"- {f}" for f in report.get("key_findings", [])) +
                "\n\n한계:\n" + "\n".join(f"- {c}" for c in report.get("caveats", [])) + f"\n\n검증: {vline}")
        self.notebook.write_entry(eid, exp["title"], "done" if verdict == "pass" else f"done ({head_of(verdict)})", body)
        self.ledger.update(eid, status="done", summary=_short(summary, 1500))
        self.ledger.add_event(eid, "done", f"완료 ({verdict})")
        self._git_commit(f"{eid}: {exp['title']}")
        self.notifier.post_report(self.ledger.get(eid), f"✅ **{eid} 완료** — {exp['title']}\n\n{summary}\n\n{vline}", files)
        return False

    # ================= git =================
    def _ensure_git(self) -> None:
        home = self.cfg.lab_home
        if not shutil.which("git") or (home / ".git").exists():
            return
        try:
            subprocess.run(["git", "init", "-q", str(home)], capture_output=True, timeout=30)
            (home / ".gitignore").write_text(GITIGNORE, encoding="utf-8")
        except Exception:
            log.warning("git init 실패", exc_info=True)

    def _git_commit(self, msg: str) -> None:
        home = self.cfg.lab_home
        if not (home / ".git").exists():
            return
        try:
            subprocess.run(["git", "-C", str(home), "add", "-A"], capture_output=True, timeout=60)
            subprocess.run(["git", "-C", str(home), "-c", "user.name=research-lab", "-c", "user.email=lab@localhost",
                            "commit", "-q", "-m", msg], capture_output=True, timeout=60)
        except Exception:
            log.warning("git commit 실패", exc_info=True)


def head_of(verdict: str | None) -> str:
    return {"revise": "미해결 지적", "unverified": "검증 미완료"}.get(verdict or "", str(verdict))
