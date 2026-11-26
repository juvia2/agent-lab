"""디스코드 봇: 연구자와 연구실의 유일한 접점. 연구자 본인(DISCORD_OWNER_ID)의 명령만 받는다."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
import time
import uuid
from pathlib import Path

import discord
from discord import app_commands

from . import approvals, bus, growth, learning, memory, reading
from .ledger import ACTIVE
from .notify import Notifier
from .policy import blocked_text, load_policy, set_policy
from .pipeline import PHASE_LABEL, STATUS_LABEL

log = logging.getLogger("lab.bot")
MAX_LEN = 1900
MAX_FILE = 8 * 1024 * 1024           # 디스코드 업로드 한도에 안전하게 맞춘 값
MAX_UPLOAD = 100 * 1024 * 1024       # 연구자가 올리는 데이터 파일 한도
CONTEXT_MSGS = 12                    # #의뢰에서 분류·팀원에게 넘겨 줄 최근 대화 수
CONTEXT_AGE = 2 * 3600               # 이보다 오래된 글은 다른 일로 본다(초)

TRIAGE = """

---
## 지금은 #{channel} 의뢰를 분류 중이다
연구자가 담당자를 지정하지 않고 실험과 별개의 단건 업무를 올렸다. 당신은 직접 처리하지 않고, 이 일을 가져갈 팀원을 정한다.
보통 한 명이면 충분하다. 일이 서로 다른 영역에 걸쳐 있을 때만 나눠서 최대 3명에게 맡긴다.
팀원(역할 키 → 영역):
- linguist 언어학 · cogsci 인지·뇌과학 · lm 언어모델·토크나이저·학습 · statistician 통계·검정·설계
- corpus 코퍼스·어휘 빈도·자극 데이터·CSV 전처리 · developer 코드·테스트·폴더 구조·DB/ERD 검토
- practitioner 실험 일정·실행 관리 · documenter 문서·보고서·요약 · tester 수치 재계산·검증
반드시 이 형식으로만 답한다:
- 팀원이 맡을 일이면 맡을 팀원마다 한 줄씩:  CLAIM: <역할 키> | <그 팀원이 맡을 일 한 문장>
  (앞사람의 결과가 뒷사람에게 필요하면 그 순서대로 적는다. 뒷사람은 앞사람의 답과 작업 파일을 볼 수 있다)
- 실험 수준의 일(모델·데이터 다운로드, 맥 GPU, 장시간 학습, 여러 전문가 설계)이면 한 줄:  ROUTE: experiment
- 무슨 일인지 불분명하면 한 줄:  ROUTE: ask
맥락과 첨부를 다루는 법:
- "[이 채널의 최근 대화]"가 주어지면 지금 글은 그 대화를 이어가는 것으로 읽는다. "위에 첨부 있잖아", "여기", "그거 검증해" 같은
  짧은 후속 글은 앞선 요청·첨부를 가리킨다. 앞에서 이미 물은 것을 다시 묻지 않는다.
- 첨부 파일의 내용은 당신에게 보이지 않는 것이 정상이다(파일 이름만 보인다). 맡은 팀원은 파일을 직접 읽을 수 있다.
  그러니 "내용이 보이지 않는다"는 이유로 되묻지 않는다. 파일이 있고 할 일(검토·검증·요약·교정 등)이 최근 대화까지 합쳐
  짐작되면 팀원에게 넘긴다. 관점이 넓게 열려 있으면 가장 맞는 팀원 한 명에게 "전반 검토"로 넘긴다
  (기획서·보고서의 논리·가설·사실관계 검증은 tester, 문서 구성·문장은 documenter).
- ROUTE: ask 는 최근 대화와 첨부를 다 봐도 무슨 일인지 알 수 없을 때만 쓴다.
마지막 줄: 연구자에게 보일 한 문장(누가 왜 맡는지 / 왜 실험 수준인지 / 무엇이 불분명한지 되묻기).
실험 수준이면 연구실이 알아서 실험 채널로 옮겨 접수하므로, 연구자에게 다시 올리라고 쓰지 않는다."""

PROMOTED = """

---
## 이 요청은 #{channel} 에서 넘어왔다
연구자가 #{channel} 에 올린 일이 실험 수준이라 이 실험 스레드로 옮겨졌다. 연구자에게 다시 올리라고 하지 않는다.
지금 바로 실험 접수 절차(요청서 정리 → 확인 → submit_experiment)를 진행한다. 원문에 확인을 생략하라는 말
("알아서 진행해" 등)이 있으면 바로 접수한다. 답의 첫 줄에 이 요청이 #{channel} 에서 옮겨졌다는 것을 한 문장으로 알린다."""


def command_text(data: dict | None) -> str:
    """슬래시 명령 상호작용 → "/learn action=approve item_id=L-003" 같은 한 줄."""
    data = data or {}
    opts = " ".join(f"{o.get('name')}={o.get('value')}" for o in data.get("options") or [] if "value" in o)
    return ("/" + str(data.get("name", "?")) + (" " + opts if opts else ""))[:300]


def parse_route(text: str) -> tuple[str, str]:
    """연구실장 분류 결과에서 (역할 키|experiment|ask, 안내 문장)."""
    m = re.search(r"ROUTE\s*[:：]\s*([A-Za-z_]+)", text or "")
    route = m.group(1).lower() if m else "ask"
    rest = re.sub(r"^.*ROUTE\s*[:：]\s*[A-Za-z_]+\s*", "", (text or "").strip(), count=1, flags=re.S).strip()
    return route, rest


_EMOJI = re.compile(r"[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\u21A9\u21AA\u23E9-\u23FA\u2139]"
                    r"(?:\uFE0F|\u200D[\U0001F000-\U0001FAFF\u2600-\u27BF])*\uFE0F? ?")


KEEP_EMOJI = ("⚠", "📌")                  # 주의·핵심 표시만 허용(LAB_RULES 표기, 2026-11-16 연구자 지시)


def strip_emoji(text: str) -> str:
    """디스코드에 올리는 글에서 이모지를 지운다(2026-11-16 연구자 지시). ⚠️·📌 와 화살표(→)·괄호 기호는 남긴다."""
    return _EMOJI.sub(lambda m: m.group(0) if m.group(0).startswith(KEEP_EMOJI) else "", text or "")


def chunks(text: str, n: int = MAX_LEN) -> list[str]:
    text = strip_emoji(text).strip() or "(내용 없음)"
    out: list[str] = []
    while len(text) > n:
        cut = text.rfind("\n", 0, n)
        cut = cut if cut > n // 2 else n
        out.append(text[:cut])
        text = text[cut:].lstrip("\n")
    out.append(text)
    return out


def safe_name(name: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣._-]+", "_", name)[:120] or "file"


# ===================== 승인 버튼 (재시작 후에도 동작하는 동적 버튼) =====================
class ApprovalButton(discord.ui.DynamicItem[discord.ui.Button],
                     template=r"lab:(?P<action>approve|reject):(?P<exp>EXP-\d+)"):
    def __init__(self, action: str, exp_id: str):
        ok = action == "approve"
        super().__init__(discord.ui.Button(
            label="승인" if ok else "거부",
            style=discord.ButtonStyle.success if ok else discord.ButtonStyle.danger,
            custom_id=f"lab:{action}:{exp_id}"))
        self.action, self.exp_id = action, exp_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item, match, /):
        return cls(match["action"], match["exp"])

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != interaction.client.cfg.discord_owner_id:
            await interaction.response.send_message("연구자 본인만 승인할 수 있습니다.", ephemeral=True)
            return False
        return True

    async def callback(self, interaction: discord.Interaction) -> None:
        if not load_policy(interaction.client.cfg, self.exp_id).allows_discord:
            await interaction.response.send_message("비공개 실험은 로컬 콘솔에서 계획을 검토하고 승인하세요.", ephemeral=True)
            return
        lab = interaction.client.lab
        bus.emit(interaction.client.cfg, "command", root="CMD",
                 text=f"{'승인' if self.action == 'approve' else '거부'} 버튼 {self.exp_id}")
        fn = lab.approve if self.action == "approve" else lab.reject
        msg = await asyncio.to_thread(fn, self.exp_id)
        base = (interaction.message.content or "")[:1500]
        await interaction.response.edit_message(content=f"{base}\n\n→ {msg}", view=None)


class CommandApprovalButton(discord.ui.DynamicItem[discord.ui.Button],
                            template=r"lab:cmd:(?P<action>ok|no):(?P<exp>EXP-\d+):(?P<rid>R-\d+)"):
    """경량 승인(재학습 없는 재집계·점검 명령) 버튼. 결정은 approvals 파일에 남고 대기 중인 에이전트가 이어간다."""
    def __init__(self, action: str, exp_id: str, rid: str):
        ok = action == "ok"
        super().__init__(discord.ui.Button(
            label="명령 승인" if ok else "거부",
            style=discord.ButtonStyle.success if ok else discord.ButtonStyle.danger,
            custom_id=f"lab:cmd:{action}:{exp_id}:{rid}"))
        self.action, self.exp_id, self.rid = action, exp_id, rid

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item, match, /):
        return cls(match["action"], match["exp"], match["rid"])

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != interaction.client.cfg.discord_owner_id:
            await interaction.response.send_message("연구자 본인만 승인할 수 있습니다.", ephemeral=True)
            return False
        return True

    async def callback(self, interaction: discord.Interaction) -> None:
        bus.emit(interaction.client.cfg, "command", root="CMD",
                 text=f"명령 {'승인' if self.action == 'ok' else '거부'} 버튼 {self.exp_id} {self.rid}")
        msg = await asyncio.to_thread(interaction.client.lab.decide_command, self.exp_id, self.rid, self.action == "ok")
        base = (interaction.message.content or "")[:1500]
        await interaction.response.edit_message(content=f"{base}\n\n→ {msg}", view=None)


class LabTree(app_commands.CommandTree):
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.client.cfg.discord_owner_id:
            await interaction.response.send_message("이 연구실은 소유자 전용입니다.", ephemeral=True)
            return False
        try:                                      # 관제 화면의 '내린 명령' 기록
            bus.emit(self.client.cfg, "command", root="CMD", text=command_text(interaction.data))
        except Exception:
            pass
        return True


# ===================== 알림 (워커 스레드 → 디스코드) =====================
class DiscordNotifier(Notifier):
    def __init__(self, cfg):
        self.cfg = cfg
        self.bot: LabBot | None = None
        self._held_lock = threading.Lock()
        self._thread_lock = asyncio.Lock()
        self.members: dict = {}           # 역할 → MemberBot (토큰이 있는 팀원만)

    def _run(self, coro, timeout: float = 120) -> bool:
        """보냈으면 True. 실패하면 부른 쪽이 보류하거나 남긴다."""
        if not self.bot or not self.bot.loop or not self.bot.is_ready():
            coro.close()
            log.warning("디스코드가 아직 준비되지 않음")
            return False
        fut = asyncio.run_coroutine_threadsafe(coro, self.bot.loop)
        try:
            fut.result(timeout)
            return True
        except Exception:
            fut.cancel()                  # 시간 초과 뒤에 늦게 나가 재시도와 겹치지 않게
            log.exception("디스코드 전송 실패")
            return False

    def _deliver(self, kind: str, exp: dict, p: dict, held: bool = False) -> bool:
        if not load_policy(self.cfg, exp["id"]).allows_discord:
            log.warning("%s 디스코드 전송 차단(자료 정책): %s", exp["id"], kind)
            return True
        coro = {"post": lambda: self._post(exp, p["text"], p.get("files"), p.get("role")),
                "report": lambda: self._post_named(self.cfg.report_channel, p["text"], p.get("files")),
                "ask": lambda: self._ask(exp, p["reasons"], p["summary"]),
                "command": lambda: self._ask_command(exp, p["req"])}[kind]()
        ok = self._run(coro)
        if not ok and not held:           # 채널 본문에 흩어 올리지 않고 보류함에 두었다가 watch.py 가 다시 보낸다
            row = {"id": uuid.uuid4().hex, "kind": kind, "exp": exp["id"], "p": p}
            with self._held_lock, self._held_file().open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        return ok

    def _held_file(self) -> Path:
        d = self.cfg.lab_home / "digest"
        d.mkdir(parents=True, exist_ok=True)
        return d / "held.jsonl"

    def _held_rows(self) -> list[dict]:
        f = self._held_file()
        return [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()] if f.exists() else []

    def flush_held(self) -> int:
        """보류한 글을 다시 보낸다(watch.py 가 1분마다 부른다). 이미 끝난 승인 요청은 버린다."""
        if not self.bot or not self.bot.is_ready():
            return 0
        with self._held_lock:
            rows = self._held_rows()
        sent, failed = 0, set()
        for r in rows:
            if r["exp"] in failed:        # 같은 실험의 글 순서를 지킨다
                continue
            exp = self.bot.lab.ledger.get(r["exp"])
            stale = not exp or (r["kind"] == "ask" and exp["status"] != "awaiting_approval") or (
                r["kind"] == "command" and r["p"]["req"]["id"] not in {q["id"] for q in approvals.pending(self.cfg, r["exp"])})
            if not stale:
                if not self._deliver(r["kind"], exp, r["p"], held=True):
                    failed.add(r["exp"])
                    continue
                sent += 1
            with self._held_lock:
                left = [x for x in self._held_rows() if x["id"] != r["id"]]
                tmp = self._held_file().with_suffix(".tmp")
                tmp.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in left), encoding="utf-8")
                tmp.replace(self._held_file())
        return sent

    def post(self, exp, text, files=None, role=None):
        if not exp:
            return self._run(self._post(None, text, files, role))
        self._deliver("post", exp, {"text": text, "files": [str(f) for f in files or []], "role": role})
        return True                       # 보냈거나 보류함에 있다

    def digest(self, exp, text, files=None, role=None):
        if exp and not load_policy(self.cfg, exp["id"]).allows_discord:
            return
        from .watch import digest_add
        digest_add(self.cfg, exp["id"] if exp else None, text, role)

    def post_report(self, exp, text, files=None):
        p = {"text": text, "files": [str(f) for f in files or []]}
        self._deliver("post", exp, p)
        self._deliver("report", exp, p)

    def ask_approval(self, exp, reasons, plan_summary):
        self._deliver("ask", exp, {"reasons": reasons, "summary": plan_summary})

    def ask_command_approval(self, exp, req):
        self._deliver("command", exp, {"req": req})

    async def _ask_command(self, exp, req):
        from .notify import command_approval_text
        ch = await self._channel_for(exp)
        view = discord.ui.View(timeout=None)
        view.add_item(CommandApprovalButton("ok", exp["id"], req["id"]))
        view.add_item(CommandApprovalButton("no", exp["id"], req["id"]))
        await self._send(ch, f"<@{self.cfg.discord_owner_id}> " + command_approval_text(exp, req), view=view)

    # ---- 비동기 구현 ----
    async def _channel_for(self, exp):
        """실험 글은 그 실험의 스레드로만 간다. 스레드가 없으면(로컬·DM 접수, 삭제됨) 만들어 장부에 적는다.
        못 만들거나 못 찾으면 채널 본문으로 새지 않게 예외를 낸다(_deliver 가 보류)."""
        bot = self.bot
        if not exp:
            return await self._named(self.cfg.test_channel)
        async with self._thread_lock:     # 동시에 올라온 글이 스레드를 둘 만들지 않게
            e = bot.lab.ledger.get(exp["id"])
            if not e:
                raise LookupError(f"{exp['id']} 이(가) 장부에 없음")
            tid = e.get("thread_id")
            if tid:
                try:
                    ch = bot.get_channel(tid) or await bot.fetch_channel(tid)
                    if isinstance(ch, discord.Thread) and ch.archived:
                        await ch.edit(archived=False)
                    return ch
                except discord.NotFound:
                    log.warning("%s 스레드 %s 가 삭제됨 → 새로 만듦", e["id"], tid)
            intake = next((c for g in bot.guilds if not self.cfg.discord_guild_id or g.id == self.cfg.discord_guild_id
                           for c in g.text_channels if c.name == self.cfg.intake_channel), None)
            if intake is None:
                raise LookupError(f"#{self.cfg.intake_channel} 채널이 없어 스레드를 만들 수 없음")
            th = await intake.create_thread(name=f"{e['id']} {e['title']}"[:100], type=discord.ChannelType.public_thread,
                                            auto_archive_duration=10080)
            bot.lab.ledger.update(e["id"], thread_id=th.id, channel_id=intake.id)
            log.info("%s 스레드 생성: %s", e["id"], th.id)
            return th

    async def _named(self, name: str):
        for g in self.bot.guilds:
            ch = discord.utils.get(g.text_channels, name=name)
            if ch:
                return ch
        if self.cfg.discord_owner_id:
            user = await self.bot.fetch_user(self.cfg.discord_owner_id)
            return await user.create_dm()
        return None

    async def _send(self, ch, text, files=None, view=None):
        if ch is None:
            return
        parts = chunks(text)
        attach, notes = [], []
        for f in files or []:
            f = Path(f)
            if f.is_file() and f.stat().st_size <= MAX_FILE:
                attach.append(discord.File(str(f), filename=f.name))
            elif f.is_file():
                notes.append(f"(용량 초과로 첨부하지 못함: {f})")
        if notes:
            parts[-1] += "\n" + "\n".join(notes)
        for i, p in enumerate(parts):
            last = i == len(parts) - 1
            await ch.send(p, files=attach[:10] if last and attach else None, view=view if last else None)

    async def _post(self, exp, text, files, role=None):
        ch = await self._channel_for(exp)
        member = self.members.get(role) if role else None
        if member is not None and member.is_ready() and isinstance(ch, (discord.TextChannel, discord.Thread)):
            try:                          # 같은 스레드에 그 역할의 봇 이름으로 올린다
                mch = member.get_channel(ch.id) or await member.fetch_channel(ch.id)
                await self._send(mch, text, files)
                return
            except discord.DiscordException:
                log.warning("%s 봇으로 전송 실패 → 연구실장 봇이 대신 보냄", role)
        if role:                          # 연구실장 봇이 대신 올리면 누구의 글인지 밝힌다
            from .agents import label
            text = f"**{label(role)}**\n{text}"
        await self._send(ch, text, files)

    async def _post_named(self, name, text, files):
        await self._send(await self._named(name), text, files)

    async def _ask(self, exp, reasons, plan_summary):
        ch = await self._channel_for(exp)
        owner = self.cfg.discord_owner_id
        text = (f"<@{owner}> **{exp['id']}** 승인이 필요합니다.\n"
                f"사유:\n" + "\n".join(f"- {r}" for r in reasons) +
                f"\n\n계획 요약:\n{plan_summary[:900]}\n\n계획 전문은 `plan.md` 에 있습니다(스레드에서 물어보세요).")
        if self.bot.lab.ledger.get(exp["id"])["phase"] == "build":     # 실행 중 변경 승인이 아니라 계획 승인
            text += "\n승인하면 계획의 제안값을 그대로 확정합니다. 바꿀 것이 있으면 거부하고 스레드에 적어 주세요."
        view = discord.ui.View(timeout=None)
        view.add_item(ApprovalButton("approve", exp["id"]))
        view.add_item(ApprovalButton("reject", exp["id"]))
        await self._send(ch, text, view=view)


# ===================== 봇 =====================
class LabBot(discord.Client):
    def __init__(self, cfg, lab, director, notifier: DiscordNotifier, stop_event: threading.Event,
                 startup_note: str = "", members: list | None = None, registry=None):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.cfg, self.lab, self.director = cfg, lab, director
        self.notifier, self.stop_event, self.startup_note = notifier, stop_event, startup_note
        self.tree = LabTree(self)
        self._locks: dict[int, asyncio.Lock] = {}
        self._started = False
        self.members = members or []          # [(MemberBot, token), ...]
        self.registry = registry
        notifier.members = {m.role: m for m, _ in self.members}
        for m, _ in self.members:             # 팀원이 #의뢰에서 실험 수준의 일을 받으면 연구실장이 옮겨 접수한다
            m.promote = self._promote_to_experiment
            m.save_reading_inputs = self._save_reading_inputs
            m.recall = self._recent_context   # 팀원 봇은 멘션 안 된 글을 못 읽는다. 연구실장 봇이 최근 대화·첨부를 대신 읽어 준다
        self._member_tasks: list[asyncio.Task] = []
        self._register_commands()

    # ---- 시작 ----
    async def setup_hook(self):
        self.add_dynamic_items(ApprovalButton, CommandApprovalButton)
        for member, token in self.members:     # 팀원 봇들은 같은 이벤트 루프에서 접속한다
            self._member_tasks.append(asyncio.create_task(self._run_member(member, token)))
        if self.cfg.discord_guild_id:
            g = discord.Object(id=self.cfg.discord_guild_id)
            self.tree.copy_global_to(guild=g)
            await self.tree.sync(guild=g)
        else:
            await self.tree.sync()

    async def _run_member(self, member, token):
        try:
            await member.start(token)
        except discord.LoginFailure:
            log.error("%s 봇 토큰이 잘못됐습니다(.env 의 BOT_TOKEN_%s). 이 팀원만 빼고 계속합니다.",
                      member.role, member.role.upper())
        except discord.PrivilegedIntentsRequired:
            log.error("%s 봇: Developer Portal 에서 MESSAGE CONTENT INTENT 를 켜야 합니다. 이 팀원만 빼고 계속합니다.",
                      member.role)
        except Exception:
            log.exception("%s 봇 접속 오류", member.role)

    async def close(self):
        for member, _ in self.members:
            try:
                await member.close()
            except Exception:
                pass
        await super().close()

    async def on_ready(self):
        if self.registry is not None:
            self.registry.add(self.user.id, "director")
        if self._started:
            return
        self._started = True
        log.info("로그인: %s", self.user)
        await self._ensure_channels()
        recovered = self.lab.ledger.reset_interrupted()
        self.lab.start_workers(self.stop_event)
        from . import watch
        watch.run(self.lab, self.stop_event)      # 연구실장 감시자(정지 30분) + 하루 요약
        team = [m.role for m, _ in self.members]
        msg = "**연구실 가동**" + (f" · 팀원 봇 {len(team)}명 접속 시도" if team else "") + (f"\n중단됐던 실험 {len(recovered)}건을 이어서 진행합니다: {', '.join(recovered)}"
                                    if recovered else "")
        if self.startup_note:
            msg += "\n" + self.startup_note
        await self.notifier._post(None, msg, None)
        self._member_tasks.append(asyncio.create_task(self._learning_loop()))
        self._member_tasks.append(asyncio.create_task(self._presence_loop()))

    async def _ensure_channels(self):
        names = [self.cfg.intake_channel, self.cfg.perf_channel, self.cfg.test_channel, self.cfg.report_channel,
                 self.cfg.adhoc_channel, self.cfg.reading_channel]
        for g in self.guilds:
            if self.cfg.discord_guild_id and g.id != self.cfg.discord_guild_id:
                continue
            for n in names:
                if not discord.utils.get(g.text_channels, name=n):
                    try:
                        await g.create_text_channel(n)
                        log.info("채널 생성: #%s", n)
                    except discord.DiscordException:
                        log.warning("채널 #%s 가 없고 만들 권한도 없음", n)

    # ---- 학습 완료 보고 (#성능고도화 전용) ----
    async def _learning_loop(self):
        """knowledge/learning_reports/pending 을 주기적으로 비운다. 각 보고는 그 역할의 봇 이름으로 올린다."""
        await asyncio.sleep(20)                       # 팀원 봇 로그인 대기
        while not self.is_closed():
            try:
                await self.flush_learning_reports()
            except Exception:
                log.exception("학습 보고 전송 오류")
            await asyncio.sleep(60)

    async def _presence_loop(self):
        """디스코드 상태 점: 일하는 중이면 온라인(초록), 아니면 자리 비움(달). 버스 기록과 진행 중 실험으로 판단한다."""
        shown: dict = {}
        while not self.is_closed():
            try:
                busy = bus.busy_roles(bus.tail(self.cfg))
                if any(self.lab.ledger.list(st, limit=1) for st in ACTIVE):
                    busy.add("director")
                for client, role in [(self, "director")] + [(m, m.role) for m, _ in self.members]:
                    status = discord.Status.online if role in busy else discord.Status.idle
                    last = shown.get(role)              # 재접속하면 디스코드가 온라인으로 되돌리므로 5분마다 다시 보낸다
                    if client.is_ready() and (not last or last[0] != status or time.time() - last[1] > 300):
                        await client.change_presence(status=status)
                        shown[role] = (status, time.time())
            except Exception:
                log.exception("상태 표시 갱신 오류")
            await asyncio.sleep(10)

    async def flush_learning_reports(self) -> int:
        items = learning.pending_items()
        if not items:
            return 0
        guild = next((g for g in self.guilds if not self.cfg.discord_guild_id or g.id == self.cfg.discord_guild_id), None)
        ch = guild and discord.utils.get(guild.text_channels, name=self.cfg.perf_channel)
        if ch is None:
            log.warning("#%s 채널이 없어 학습 보고를 보내지 못함", self.cfg.perf_channel)
            return 0
        from .agents import DISPLAY_EN

        async def open_thread(item, head: int) -> int | None:
            try:
                tid = (await ch.get_partial_message(head).create_thread(name=item["title"][:100],
                                                                        auto_archive_duration=10080)).id
            except discord.DiscordException as e:
                if getattr(e, "code", None) != 160004:      # 160004 = 이미 열려 있음(글에서 연 스레드 ID는 글 ID와 같다)
                    log.warning("학습 보고 스레드 생성 실패 → 나머지는 큐에 남김")
                    return None
                tid = head
            learning.remember_thread(item["group"], tid)
            return tid

        sent = 0
        for path, item in items:
            if not learning.publication_allowed(item):
                continue
            role = item.get("role", "director")
            tid = learning.thread_for(item)         # 같은 과제의 보고는 첫 글에 연 스레드로 모은다
            head = learning.head_for(item)
            if head and not tid:                    # 앞서 스레드를 못 열었다: 다시 열고, 안 되면 큐에 남긴다
                tid = await open_thread(item, head)
                if not tid:
                    continue
            dest_id = tid or ch.id
            member = self.notifier.members.get(role)
            target = None
            if member is not None and member.is_ready():
                try:
                    target = member.get_channel(dest_id) or await member.fetch_channel(dest_id)
                except discord.DiscordException:
                    target = None
            f = learning.attachment(item)
            msg = None
            for cand in ([target] if target else []) + [None]:    # 팀원 봇이 실패하면(스레드 권한 등) 연구실장 봇이 올린다
                try:
                    dest = cand or (ch if not tid else (self.get_channel(tid) or await self.fetch_channel(tid)))
                    kw = {"file": discord.File(f)} if f else {}
                    msg = await dest.send(embed=discord.Embed.from_dict(learning.embed(item, DISPLAY_EN.get(role, role))), **kw)
                    break
                except discord.DiscordException:
                    continue
            if msg is None:
                log.warning("%s 학습 보고 전송 실패(다음 주기에 재시도)", role)
                continue
            if item.get("group") and not tid:
                learning.remember_head(item["group"], msg.id)
                await open_thread(item, msg.id)
            learning.mark_sent(path)
            sent += 1
            await asyncio.sleep(0.7)
        return sent

    # ---- 일반 대화 ----
    def _is_owner(self, uid: int) -> bool:
        return uid == self.cfg.discord_owner_id

    async def on_message(self, message: discord.Message):
        if message.author.bot or not self._is_owner(message.author.id):
            return
        if self.registry is not None:
            team = {u.id for u in message.mentions if u.id in self.registry.by_user}
            top_reading = isinstance(message.channel, discord.TextChannel) and self._is_reading(message.channel)
            if team and self.user.id not in team and not top_reading:   # 다른 팀원을 불렀으면 그 팀원이 답한다
                return
        ch = message.channel
        text = (message.content or "").strip()
        if not text and not message.attachments:
            return
        if not self._listens(ch, message):         # 연구실 채널·그 스레드·DM·멘션이 아니면 조용히 넘어간다
            return
        exp = self.lab.ledger.find_by_thread(ch.id) if isinstance(ch, discord.Thread) else None
        policy_id = exp["id"] if exp else ("ADHOC" if self._is_adhoc(ch) else
                                           "READING" if self._is_reading(ch) else "INTAKE")
        if not load_policy(self.cfg, policy_id).allows_discord:
            await message.channel.send(blocked_text(policy_id))
            return
        if self._is_reading(ch):                  # #논문리딩: 세션 시작·튜터에게 넘기기·마무리
            await self._reading(message)
            return
        thread_id = None
        target = None
        if isinstance(ch, discord.TextChannel) and ch.name == self.cfg.intake_channel:
            title = re.sub(r"\s+", " ", text)[:60] or "새 요청"
            target = await message.create_thread(name=f"{title}"[:100], auto_archive_duration=10080)
            thread_id = target.id
        elif isinstance(ch, discord.Thread) and (
                (ch.parent and ch.parent.name == self.cfg.intake_channel) or self.lab.ledger.find_by_thread(ch.id)):
            target, thread_id = ch, ch.id
        elif isinstance(ch, discord.DMChannel):
            target = ch
        elif self._is_adhoc(ch):
            if self.user in message.mentions:      # 연구실장을 직접 부른 의뢰(현황 질의 등)는 평소처럼 답한다
                target = ch
            else:                                  # 담당자 지정 없는 의뢰 → 분류해서 팀원에게 넘긴다
                await self._triage(message)
                return
        else:                                      # #성능고도화·#results-산출물·#봇점검과 그 스레드, 멘션: 멘션 없이도 그 자리에서 답한다
            target = ch
        lock = self._locks.setdefault(target.id, asyncio.Lock())
        async with lock:
            try:
                note = await self._save_attachments(message)
                history = await self._history(target, message)
                if note:
                    history.append({"role": "user", "content": note})
                handoffs: list = []
                ready = self._ready_roles() if not isinstance(target, discord.DMChannel) else set()
                async with target.typing():
                    reply = await asyncio.to_thread(
                        self.director.reply, history, thread_id=thread_id,
                        channel_id=getattr(message.channel, "id", None), requester_id=message.author.id,
                        policy_id="ADHOC" if self._is_adhoc(ch) else None,
                        handoffs=handoffs, handoff_roles=ready)
            except Exception as e:
                handoffs = []
                log.exception("대화 처리 오류")
                reply = f"처리 중 오류가 났습니다: {type(e).__name__}: {str(e)[:300]}"
            for part in chunks(reply):
                await target.send(part)
        if handoffs:                              # 멘션 없이도 맞는 팀원이 가져가서 자기 이름으로 답한다
            exp_now = self.lab.ledger.find_by_thread(target.id) if isinstance(target, discord.Thread) else None
            trace = bus.Trace(self.cfg, channel=getattr(target, "name", "") or "", exp_id=exp_now["id"] if exp_now else None)
            trace.emit("request", text=text)
            for role, question in handoffs:
                member = self.notifier.members.get(role)
                if member is not None and member.is_ready():
                    await member.take(target.id, question, exp=exp_now, trace=trace,
                                      policy_id="ADHOC" if self._is_adhoc(ch) else "INTAKE")

    def _listens(self, ch, message) -> bool:
        """연구자의 글에 연구실장이 반응할 자리인가. 연구실 채널 전부(와 그 스레드), DM, 멘션."""
        if isinstance(ch, discord.DMChannel) or self.user in message.mentions:
            return True
        base = ch.parent if isinstance(ch, discord.Thread) else ch
        return getattr(base, "name", None) in {self.cfg.intake_channel, self.cfg.report_channel, self.cfg.perf_channel,
                                               self.cfg.test_channel, self.cfg.adhoc_channel, self.cfg.reading_channel}

    def _is_reading(self, ch) -> bool:
        if isinstance(ch, discord.Thread):
            return bool(ch.parent) and ch.parent.name == self.cfg.reading_channel
        return isinstance(ch, discord.TextChannel) and ch.name == self.cfg.reading_channel

    # ---- #논문리딩 ----
    async def _reading(self, message: discord.Message):
        ch = message.channel
        store = reading.ReadingStore(self.cfg)
        if isinstance(ch, discord.Thread):
            sess = store.find_by_thread(ch.id)
            if sess:
                await self._reading_followup(message, sess)
                return
        text = (message.content or "").strip()
        has_pdf = any(a.filename.lower().endswith(reading.PAPER_EXT + (".zip",)) for a in message.attachments)
        url = reading.find_url(text)
        local = reading.find_local_path(text, self.cfg.reading_dirs)
        if isinstance(ch, discord.TextChannel) and reading.wants_review(text, has_pdf or bool(local), url):
            await self._review_start(message, url if url and not reading.pdf_url(url) else None, local)
            return
        if isinstance(ch, discord.TextChannel) and (has_pdf or local or (url and reading.pdf_url(url))):
            await self._reading_start(message, url if not (has_pdf or local) else None, local)
            return
        if isinstance(ch, discord.TextChannel) and re.search(r"(^|\s)(~/|/Users/|/Volumes/)", text):
            await message.reply("그 폴더를 읽을 수 없습니다. 맥의 " + ", ".join(str(d) for d in self.cfg.reading_dirs)
                                + " 안의 경로만 받습니다(.env READING_DIRS). 또는 폴더를 .zip 으로 묶거나 파일을 여러 개 첨부해 주세요.",
                                mention_author=False)
            return
        # 논문 없이 쓴 글(예전에 읽은 논문 질문, 연구 지향 확인 등)은 연구실장이 리딩 기록을 찾아 답한다
        target = ch
        async with target.typing():
            history = await self._history(target, message)
            reply = await asyncio.to_thread(
                self.director.reply, history, channel_id=ch.id, requester_id=message.author.id, policy_id="READING",
                extra_system=f"\n\n---\n## 지금은 #{self.cfg.reading_channel} 채널이다\n연구자가 공부용 논문을 튜터들과 같이 읽는 채널이다. "
                             "논문 PDF나 arXiv 링크를 올리면 세션이 열린다. 예전에 읽은 논문을 물으면 search_research_memory 의 "
                             "'논문 리딩 노트'를 찾아 출처와 함께 답한다.\n\n" + reading.trend_text(self.cfg, 8))
        for part in chunks(reply):
            await target.send(part)

    async def _save_reading_inputs(self, message: discord.Message, pid: str) -> list[str]:
        d = reading.ReadingStore(self.cfg).dir(pid) / "inputs"
        d.mkdir(parents=True, exist_ok=True)
        saved = []
        for a in message.attachments:
            if a.size > MAX_UPLOAD:
                continue
            name = safe_name(a.filename)
            await a.save(d / name)
            if name.lower().endswith(".zip"):          # 논문 폴더를 묶은 zip: 논문 파일만 꺼낸다
                got = await asyncio.to_thread(reading.extract_zip, d / name, d)
                saved += got or [f"({name}: 논문 파일(PDF·텍스트·TeX)을 찾지 못함)"]
            else:
                saved.append(name)
        saved += await self._pdf_texts(d)
        return saved

    async def _pdf_texts(self, d) -> list[str]:
        """inputs/ 의 PDF 중 아직 텍스트를 안 뽑은 것을 뽑는다. 실패한 것만 안내 문구로 돌려준다."""
        from .team import pdf_to_text
        notes = []
        for pdf in sorted(d.glob("*.pdf")):
            if (d / (pdf.name + ".txt")).exists():
                continue
            if await asyncio.to_thread(pdf_to_text, pdf) is None:
                notes.append(f"({pdf.name}: 텍스트를 뽑지 못함. 스캔본이면 본문 텍스트를 붙여 주세요)")
        return notes

    async def _reading_start(self, message: discord.Message, url: str | None, local=None):
        store = reading.ReadingStore(self.cfg)
        text = (message.content or "").strip()
        pid = store.new(note=text, url=url or (str(local) if local else ""))
        thread = await message.create_thread(name=f"{pid} 논문 리딩"[:100], auto_archive_duration=10080)
        store.update(pid, thread_id=thread.id)
        inputs = store.dir(pid) / "inputs"
        inputs.mkdir(parents=True, exist_ok=True)
        saved = await self._save_reading_inputs(message, pid)
        if local is not None:                     # 맥 폴더 경로: 논문 파일만 읽기 전용으로 복사(원본은 그대로)
            saved += await asyncio.to_thread(reading.copy_folder, local, inputs)
            saved += await self._pdf_texts(inputs)
        if url:
            got = await asyncio.to_thread(reading.fetch_pdf, url, inputs / "paper.pdf")
            if got:
                saved.append("paper.pdf (링크에서 받음)")
                saved += await self._pdf_texts(inputs)
            else:
                saved.append("(링크에서 PDF를 받지 못함)")
        body = store.paper_text(pid)
        store.log(pid, "연구자", text or "(논문만 올림)")
        if not body:
            await thread.send(f"{pid} 세션을 열었지만 논문 본문을 읽지 못했습니다({'; '.join(saved) or '첨부 없음'}). "
                              "이 스레드에 PDF를 다시 올리거나 본문 텍스트를 붙인 뒤 `/reading retry` 를 써 주세요.")
            return
        ready = self._ready_roles()
        ask = (f"[연구자가 논문과 함께 쓴 말]\n{text or '(없음)'}\n\n[논문 앞부분]\n{body[:7000]}\n\n"
               + reading.trend_text(self.cfg, 8))
        try:
            out = await asyncio.to_thread(self.director.reply, [{"role": "user", "content": ask}],
                                          requester_id=message.author.id, policy_id="READING", tools=[],
                                          extra_system=reading.SELECT.format(channel=self.cfg.reading_channel))
        except Exception:
            log.exception("리딩 제목·담당 선정 오류")
            out = ""
        title, tags, tutors, note = reading.parse_select(out)
        tutors = [r for r in tutors if r in ready] or [r for r in reading.TUTOR_POOL if r in ready][:2] or ["lm"]
        store.update(pid, title=title, tags=tags, tutors=tutors, lead=tutors[0])
        try:                                      # 스레드 이름 = 논문 제목(연구자 지시)
            await thread.edit(name=(title or f"{pid} 논문 리딩")[:100])
        except discord.DiscordException:
            pass
        from .agents import DISPLAY_EN
        files = [f for f in store.files(pid) if not f.endswith(".pdf.txt")]
        await thread.send(
            f"{title or pid} ({pid})\n받은 파일: {', '.join(files)}"
            + (f"\n주제: {', '.join(tags)}" if tags else "")
            + f"\n연구실 10명이 각자 분야의 리딩 리포트를 씁니다. 리포트가 다 올라오면 이 스레드에서 자유롭게 질문하세요"
              f"(멘션 없이 물으면 맞는 담당이 답하고, @이름 으로 지정할 수 있습니다). 질문 1차 담당: "
            + ", ".join(DISPLAY_EN[r] for r in tutors)
            + ". 다 읽으면 \"정리해줘\" 또는 `/reading close` 로 리딩 노트를 남깁니다.")
        await self._reading_reports(thread, pid)

    async def _review_start(self, message: discord.Message, url: str | None, local=None):
        """연구자가 쓴 글(블로그 글·분석 문서)에 팀원들이 첨언한다. 글 안에 원 논문 링크가 있으면 원문도 받아 사실관계를 대조한다."""
        store = reading.ReadingStore(self.cfg)
        text = (message.content or "").strip()
        pid = store.new(note=text, url=url or (str(local) if local else ""))
        store.update(pid, kind="review")
        thread = await message.create_thread(name=f"첨언 {pid}"[:100], auto_archive_duration=10080)
        store.update(pid, thread_id=thread.id)
        inputs = store.dir(pid) / "inputs"
        inputs.mkdir(parents=True, exist_ok=True)
        got_title = ""
        if url:
            got = await asyncio.to_thread(reading.fetch_page, url, inputs / "article.md")
            if got:
                got_title = got[0]
            else:
                await thread.send("그 링크의 글을 받지 못했습니다(비공개 글·로그인 필요·자바스크립트로만 그려지는 페이지일 수 있음). "
                                  "글 본문을 이 스레드에 붙이거나 .md/.txt 로 첨부해 주세요.")
        saved = await self._save_reading_inputs(message, pid)
        if local is not None:
            saved += await asyncio.to_thread(reading.copy_folder, local, inputs)
            saved += await self._pdf_texts(inputs)
        if not reading.article_text(self.cfg, pid):  # 링크가 없으면 첨부한 글(첫 텍스트 파일)이나 붙여 넣은 본문을 글로 쓴다
            docs = [f for f in sorted(inputs.glob("*")) if f.suffix.lower() in (".md", ".txt") and not f.name.endswith(".pdf.txt")]
            body = docs[0].read_text(encoding="utf-8", errors="replace") if docs else \
                (text if len(text) > 800 else "")
            if body:
                (inputs / "article.md").write_text(body, encoding="utf-8")
        art = reading.article_text(self.cfg, pid)
        store.log(pid, "연구자", text or "(글만 올림)")
        if not art:
            if url:
                return
            await thread.send("첨언할 글 본문을 찾지 못했습니다. 글 링크나 본문(.md/.txt)을 올려 주세요.")
            return
        for link in reading.paper_links(art)[:1]:     # 글이 다루는 원 논문(글 속 첫 학술 링크)을 받아 사실관계 대조에 쓴다
            dest = inputs / f"source_{len(list(inputs.glob('source_*.pdf'))) + 1}.pdf"
            if await asyncio.to_thread(reading.fetch_pdf, link, dest):
                saved.append(f"{dest.name} (글 속 원 논문 링크에서 받음)")
        saved += await self._pdf_texts(inputs)
        try:
            out = await asyncio.to_thread(
                self.director.reply, [{"role": "user", "content": f"[연구자가 쓴 말]\n{text or '(없음)'}\n\n[글 앞부분]\n{art[:5000]}"}],
                requester_id=message.author.id, policy_id="READING", tools=[],
                extra_system=reading.REVIEW_SELECT.format(channel=self.cfg.reading_channel))
        except Exception:
            log.exception("첨언 담당 선정 오류")
            out = ""
        title, tags, who, note = reading.parse_review_select(out)
        named = [self.registry.by_user[u.id] for u in message.mentions
                 if self.registry is not None and u.id in self.registry.by_user]
        if named:                                  # @멘션한 팀원만 첨언(연구실장 포함 가능). 없으면 전원
            who = [r for r in reading.REPORTERS if r in named]
        title = title or got_title
        ready = self._ready_roles() | {"director"}
        tutors = [r for r in who if r in reading.TUTOR_POOL and r in ready] or ["linguist"]
        store.update(pid, title=title, tags=tags, reviewers=who, tutors=tutors, lead=tutors[0])
        try:
            await thread.edit(name=f"첨언: {title}"[:100] if title else f"첨언 {pid}")
        except discord.DiscordException:
            pass
        from .agents import DISPLAY_EN
        src = reading.source_text(self.cfg, pid)
        await thread.send(
            f"첨언 세션 {pid}: {title or '(제목 미상)'}\n"
            f"원 논문 대조: {'원문을 받아 대조합니다' if src else '원문을 받지 못해 글 기준으로만 봅니다(사실관계는 원문 미확인으로 표시)'}\n"
            f"첨언: {', '.join(DISPLAY_EN[r] for r in who)}" + (f"\n{note}" if note else "")
            + "\n첨언이 다 올라오면 이 스레드에서 이어서 반론하거나 더 물어보세요. \"전원\"을 넣어 물으면 모두가 각자 답하고, "
              "@이름 으로 특정 팀원만 부를 수 있습니다. \"정리해줘\"로 첨언 요약 노트를 남깁니다.")
        await self._reading_reports(thread, pid, who, mode="review")

    async def _reading_reports(self, thread, pid: str, roles: list[str] | None = None, mode: str | None = None) -> None:
        """연구실 10명 전원이 각자 리딩 리포트를 쓰고 자기 봇 이름으로 올린다. 실패하면 한 번 다시 쓰고,
        그래도 안 되면 목록에 남겨 /reading retry 로 이어 쓴다. 봇이 접속해 있지 않아도 리포트는 쓰고 연구실장 봇이 대신 올린다."""
        from .agents import DISPLAY_EN, director_system, label, model_for, system_for
        from .team import past_readings
        sess = reading.ReadingStore(self.cfg).get(pid) or {}
        mode = mode or ("review" if sess.get("kind") == "review" else "report")
        kind = "첨언" if mode == "review" else "리딩 리포트"
        roles = roles or reading.missing_reports(self.cfg, pid)
        policy = load_policy(self.cfg, "READING")
        sem = asyncio.Semaphore(max(1, self.cfg.reading_parallel))
        trace = bus.Trace(self.cfg, channel=self.cfg.reading_channel)
        trace.emit("request", text=f"{pid} {kind} {len(roles)}건")
        failed: list[str] = []

        def director_search(q: str) -> str:
            hits = memory.ResearchMemory(self.cfg, self.lab.ledger).search(
                q, k=6, allow=lambda e: load_policy(self.cfg, e).allows_discord if e else True)
            return memory.format_hits(hits)

        async def one(role: str) -> None:
            async with sem:
                trace.emit("claim", src=role, text=f"{pid} {kind}")
                if role == "director":
                    base, model, search = director_system(None, self.cfg), self.cfg.model_director, director_search
                else:
                    base, model = system_for(role, self.cfg), model_for(self.cfg, role)
                    search = lambda q: past_readings(self.cfg, q)  # noqa: E731
                path, err = None, ""
                for _ in range(2):
                    try:
                        path = await asyncio.to_thread(
                            reading.write_report, self.cfg, self.lab.client, role, pid, system_base=base, model=model,
                            data_policy=policy, memory_search=search, name=DISPLAY_EN[role],
                            label=label(role) if role != "director" else "연구실장", mode=mode)
                        break
                    except Exception as e:
                        err = f"{type(e).__name__}: {str(e)[:150]}"
                        log.warning("%s %s 실패(%s): %s", pid, kind, role, err)
                trace.emit("done", src=role, ok=path is not None)
                if path is None:
                    failed.append(f"{DISPLAY_EN[role]} ({err})")
                    return
                text = f"**{kind} · {DISPLAY_EN[role]}**\n" + reading.report_preview(path.read_text(encoding="utf-8"))
                member = self.notifier.members.get(role) if role != "director" else None
                posted = False
                if member is not None and member.is_ready():
                    posted = await member.post_report(thread.id, text, path)
                if not posted:                    # 연구실장 봇이 대신 올린다(그 팀원 봇이 없거나 게시 실패)
                    parts = chunks(text if role == "director" else f"[{DISPLAY_EN[role]}] " + text)
                    for i, part in enumerate(parts):
                        kw = {"files": [discord.File(str(path), filename=path.name)]} if i == len(parts) - 1 else {}
                        await thread.send(part, **kw)

        async with thread.typing():
            await asyncio.gather(*(one(r) for r in roles))
        total = len(sess.get("reviewers") or reading.REPORTERS) if mode == "review" else len(reading.REPORTERS)
        done = total - len(reading.missing_reports(self.cfg, pid))
        msg = (f"{kind} {done}/{total}건 완료. 저장: workspace/reading/{pid}/{'reviews' if mode == 'review' else 'reports'}/")
        if failed:
            msg += "\n작성하지 못함: " + "; ".join(failed) + f"\n이 스레드에서 `/reading retry` 로 빠진 {kind}만 다시 씁니다."
        await thread.send(msg)

    async def _reading_followup(self, message: discord.Message, sess: dict):
        pid, store = sess["id"], reading.ReadingStore(self.cfg)
        text = (message.content or "").strip()
        saved = await self._save_reading_inputs(message, pid) if message.attachments else []
        if reading.CLOSE_WORDS.search(text):
            store.log(pid, "연구자", text)
            await self._reading_close(message.channel, pid)
            return
        url = reading.find_url(text)
        if url and not reading.pdf_url(url):           # 스레드 안에서 올린 글 링크(내 분석 등)도 읽어서 담당이 보게 한다
            got = await asyncio.to_thread(reading.fetch_page, url, store.dir(pid) / "inputs" / "article.md")
            saved.append("article.md (링크의 글)" if got else "(링크의 글을 받지 못함)")
            if got:
                text += f"\n[연구자가 링크한 글을 세션 파일 article.md 로 저장함. read_paper·search_paper 로 읽을 수 있다. 제목: {got[0]}]"
        store.log(pid, "연구자", text + (f" [첨부: {', '.join(saved)}]" if saved else ""))
        ready = self._ready_roles()
        recent = store.history_text(pid, limit=6, each=400)
        try:
            out = await asyncio.to_thread(
                self.director.reply, [{"role": "user", "content": f"[최근 대화]\n{recent}\n\n[지금 연구자의 글]\n{text}"}],
                requester_id=message.author.id, policy_id="READING", tools=[],
                extra_system=reading.ROUTE_Q.format(channel=self.cfg.reading_channel, pid=pid,
                                                    tutors=", ".join(sess.get("tutors", []))))
        except Exception:
            log.exception("리딩 질문 분배 오류")
            out = ""
        roles = [r for r in reading.parse_answer(out, sess.get("tutors") or ["lm"]) if r in ready]
        if reading.ALL_WORDS.search(text):       # "전원 의견", "각자 해석" → 접속한 팀원 모두가 각자 답한다
            roles = [r for r in reading.REPORTERS if r != "director" and r in ready]
        if not roles:
            roles = [r for r in sess.get("tutors", []) if r in ready][:1]
        if not roles:
            await message.reply("지금 접속해 있는 튜터가 없습니다.", mention_author=False)
            return
        trace = bus.Trace(self.cfg, channel=self.cfg.reading_channel)
        trace.emit("request", text=f"{pid}: {text[:200]}")
        if len(roles) > 2:                         # 여러 명이면 동시에(한도 보호용 상한) 각자 자기 해석으로 답한다
            sem = asyncio.Semaphore(max(1, self.cfg.reading_parallel))

            async def each(r):
                async with sem:
                    await self.notifier.members[r].tutor(
                        message.channel.id, pid, f"[연구자의 질문 · 팀원 전원이 각자 답하는 중. 당신 분야의 해석만, 다른 팀원과 겹치지 않게]\n{text}",
                        trace=trace)
            await message.reply(f"{len(roles)}명이 각자 답합니다.", mention_author=False)
            await asyncio.gather(*(each(r) for r in roles))
            return
        for n, r in enumerate(roles):
            await self.notifier.members[r].tutor(message.channel.id, pid, f"[연구자의 질문]\n{text}",
                                                 trace=trace, reply_to=message if n == 0 else None)

    async def _reading_close(self, channel, pid: str) -> str:
        store = reading.ReadingStore(self.cfg)
        sess = store.get(pid) or {}
        ready = self._ready_roles()
        writer = "documenter" if "documenter" in ready else next((r for r in sess.get("tutors", []) if r in ready), None)
        if writer is None:
            await channel.send("리딩 노트를 쓸 팀원 봇이 접속해 있지 않습니다.")
            return ""
        member = self.notifier.members[writer]
        async with channel.typing():
            md = await asyncio.to_thread(member.tutor_reply, pid,
                                         (reading.CLOSE_REVIEW_PROMPT if sess.get("kind") == "review" else reading.CLOSE_PROMPT)
                                         .format(log=store.history_text(pid, limit=60, each=2500)),
                                         load_policy(self.cfg, "READING"), None, max_tokens=6000)
        path = store.close(pid, md)
        due = growth.due_notice(self.cfg, [c["id"] for c in growth.due(self.cfg) if c["kind"] == "research"])
        from .agents import DISPLAY_EN
        head = (f"{pid} 리딩 노트를 남겼습니다({DISPLAY_EN[writer]} 작성, workspace/reading/notes/{path.name}). "
                "연구실장 기억 검색에서 '논문 리딩 노트'로 찾을 수 있습니다.")
        parts = chunks(head + "\n\n" + md + ("\n\n" + due if due else ""))
        for i, part in enumerate(parts):
            kw = {"files": [discord.File(str(path), filename=path.name)]} if i == len(parts) - 1 else {}
            await channel.send(part, **kw)
        return head

    def _is_adhoc(self, ch) -> bool:
        if isinstance(ch, discord.Thread):
            return bool(ch.parent) and ch.parent.name == self.cfg.adhoc_channel
        return isinstance(ch, discord.TextChannel) and ch.name == self.cfg.adhoc_channel

    async def _triage(self, message: discord.Message):
        text = (message.content or "").strip()
        if not text and not message.attachments:
            return
        names = ", ".join(a.filename for a in message.attachments)
        now_text = text + (f"\n[첨부: {names}]" if names else "")
        # 분류는 글 하나만 보면 후속 글("위에 첨부 있잖아")을 이해하지 못한다. 최근 대화와 앞선 글의 첨부를 같이 본다.
        ctx, carried = await self._recent_context(message.channel.id, message.id,
                                                  getattr(message.reference, "message_id", None), query=text)
        if message.attachments:
            carried = []
        if carried:
            now_text += f"\n[앞선 글의 첨부(이어받음): {', '.join(a.filename for a in carried)}]"
        ask = (f"[이 채널의 최근 대화. 지금 글은 이 대화를 이어가는 것일 수 있다]\n{ctx}\n\n[지금 올라온 글]\n" if ctx else "") + now_text
        extra = TRIAGE.format(channel=self.cfg.adhoc_channel)
        try:
            out = await asyncio.to_thread(self.director.reply, [{"role": "user", "content": ask}],
                                          requester_id=message.author.id, extra_system=extra,
                                          policy_id="ADHOC", tools=[])
        except Exception as e:
            log.exception("의뢰 분류 오류")
            await message.reply(f"분류 중 오류: {type(e).__name__}. 담당자를 @멘션해서 다시 올려 주세요.",
                                mention_author=False)
            return
        claims, route, note = bus.parse_claims(out)
        from .agents import DISPLAY_EN
        log.info("의뢰 분류: route=%s claims=%s 맥락=%d자 이어받은 첨부=%d", route, [r for r, _ in claims], len(ctx), len(carried))
        if route == "experiment" and await self._promote_to_experiment(message, now_text, context=ctx, extra_files=carried):
            return                                 # 다시 올리게 하지 않고 #실험진행 스레드로 옮겨 접수했다
        if route != "claim":
            await message.reply(note or ("이 일은 실험으로 올려 주세요." if route == "experiment"
                                         else "어떤 일인지 조금 더 알려 주시거나 담당자를 @멘션해 주세요."), mention_author=False)
            return
        ready = self._ready_roles()
        absent = [DISPLAY_EN[r] for r, _ in claims if r not in ready]
        claims = [(r, t) for r, t in claims if r in ready]
        if not claims:
            await message.reply(f"{note}\n(@{', @'.join(absent)} 봇이 접속해 있지 않습니다. 토큰·초대를 확인하세요.)",
                                mention_author=False)
            return
        who = ", ".join(DISPLAY_EN[r] for r, _ in claims)
        await message.reply(f"{note or who + ' 이(가) 가져갑니다.'}"
                            + (f"\n(접속해 있지 않아 제외: {', '.join(absent)})" if absent else ""), mention_author=False)
        trace = bus.Trace(self.cfg, channel=self.cfg.adhoc_channel)
        trace.emit("request", text=now_text)
        done: list[tuple[str, str]] = []           # 팀원 봇은 서로의 글 본문을 못 읽으므로 앞사람의 답을 직접 넘겨준다
        for n, (role, task) in enumerate(claims):
            member = self.notifier.members[role]
            try:
                mch = member.get_channel(message.channel.id) or await member.fetch_channel(message.channel.id)
                mmsg = await mch.fetch_message(message.id)
            except discord.DiscordException:
                await message.channel.send(f"@{DISPLAY_EN[role]} 봇이 이 채널을 읽을 수 없습니다(채널 권한 확인).")
                continue
            trace.emit("claim", src=role, text=task or "의뢰 전체")
            body = (f"[이 채널의 최근 대화(연구실장이 옮겨 적음). 지금 의뢰는 이 대화를 이어가는 것일 수 있다]\n{ctx}\n\n"
                    f"[지금 의뢰]\n" if ctx else "") + (now_text or "(본문 없음)")
            if len(claims) > 1:
                others = "; ".join(f"{DISPLAY_EN[r]}: {t}" for r, t in claims if r != role)
                earlier = ", ".join(r for r, _ in claims[:n])
                body += (f"\n\n[이 의뢰는 여러 팀원이 나눠 맡았다. 당신이 맡은 부분: {task}]\n[동료가 맡은 부분 — {others}]"
                         + (f"\n[먼저 끝낸 동료의 작업 파일은 read_peer_file 로 읽을 수 있다: {earlier}]" if earlier else ""))
                for r, said in done:
                    body += f"\n\n[먼저 끝낸 {DISPLAY_EN[r]}의 답]\n{said[:2500]}"
                await mch.send(f"맡습니다: {task}", allowed_mentions=discord.AllowedMentions.none())
            said = await member._on_adhoc(mmsg, forwarded=body, src=message, trace=trace, extra_files=carried)
            if said:
                done.append((role, said))

    async def _recent_context(self, channel_id: int, before_id: int, reply_to_id: int | None = None,
                              query: str = "") -> tuple[str, list]:
        """(최근 대화를 옮겨 적은 글, 이어받을 첨부 목록). 팀원 봇은 멘션 안 된 글의 본문·첨부를 읽지 못하므로
        연구실장 봇이 대신 읽어 넘긴다. 첨부는 답글 대상의 것, 없으면 연구자가 가장 최근에 올린 것."""
        try:
            ch = self.get_channel(channel_id) or await self.fetch_channel(channel_id)
            msgs = [m async for m in ch.history(limit=CONTEXT_MSGS, before=discord.Object(id=before_id))]
        except discord.DiscordException:
            log.exception("최근 대화 읽기 실패")
            return "", []
        msgs.reverse()
        now = discord.utils.utcnow()
        msgs = [m for m in msgs if (now - m.created_at).total_seconds() <= CONTEXT_AGE]
        lines = []
        for m in msgs:
            who = "연구자" if self._is_owner(m.author.id) else getattr(m.author, "display_name", "팀원")
            body = re.sub(r"\s+", " ", m.clean_content or "").strip()[:600]
            names = ", ".join(a.filename for a in m.attachments)
            if body or names:
                lines.append(f"[{who}] {body}" + (f" [첨부: {names}]" if names else ""))
        ref = next((m for m in msgs if m.id == reply_to_id), None) if reply_to_id else None
        carried = list(ref.attachments) if ref is not None and ref.attachments else []
        if not carried:
            carried = next((list(m.attachments) for m in reversed(msgs)
                            if m.attachments and self._is_owner(m.author.id)), [])
        ctx = "\n".join(lines)
        if query:                              # 최근 창 밖의 예전 대화는 장기 기억에서 관련된 것만 꺼낸다
            oldest = msgs[0].created_at.timestamp() if msgs else now.timestamp()
            past = memory.recall_exchanges(self.cfg, query, before_ts=oldest)
            if past:
                ctx = ("[예전 대화 기억(장기 기억에서 찾음). 오래된 내용이니 지금도 맞는지 확인하고 쓴다]\n"
                       + memory.format_exchanges(past) + ("\n\n[최근 대화]\n" + ctx if ctx else ""))
        return ctx, carried

    async def _promote_to_experiment(self, message: discord.Message, text: str, *, draft: str = "",
                                     context: str = "", extra_files: list | None = None) -> bool:
        """#의뢰에 올라온 실험 수준의 요청을 #실험진행 스레드로 옮겨 접수 절차를 잇는다. 연구자가 다시 올릴 필요가 없다.
        draft: 팀원이 적어 준 요청서 초안(있으면 연구실장에게 같이 넘긴다). 옮기지 못하면 False(호출한 쪽이 예전처럼 안내)."""
        gid = getattr(getattr(message, "guild", None), "id", None)
        guild = next((g for g in self.guilds if g.id == gid), None)
        intake = guild and discord.utils.get(guild.text_channels, name=self.cfg.intake_channel)
        if intake is None or not load_policy(self.cfg, "INTAKE").allows_discord:
            return False
        body = (text or "").strip() or "(본문 없음, 첨부만 있음)"
        try:
            title = re.sub(r"\s+", " ", message.content or "").strip()[:60] or "새 요청"
            head = await intake.send(f"#{self.cfg.adhoc_channel} 에서 넘어온 실험 요청입니다. 원문: {message.jump_url}")
            thread = await head.create_thread(name=f"{title}"[:100], auto_archive_duration=10080)
            for part in chunks("연구자 요청 원문(#" + self.cfg.adhoc_channel + "):\n" + body):
                await thread.send(part, allowed_mentions=discord.AllowedMentions.none())
            await message.reply(f"실험 수준의 일이라 {thread.mention} 로 옮겨 접수를 진행합니다. 다시 올리실 필요 없습니다. "
                                "이어지는 확인·질문은 그 스레드에서 답해 주세요.", mention_author=False)
        except discord.DiscordException:
            log.exception("실험 채널로 옮기기 실패")
            return False
        log.info("의뢰를 실험 스레드로 옮김: %s", thread.id)
        bus.Trace(self.cfg, channel=self.cfg.intake_channel).emit("request", text=body)
        lock = self._locks.setdefault(thread.id, asyncio.Lock())
        async with lock:
            try:
                note = await self._save_attachments(message, extra_files)
                history = [{"role": "user", "content": body}]
                if context:
                    history.insert(0, {"role": "user", "content": f"[#{self.cfg.adhoc_channel} 의 앞선 대화. 참고]\n" + context[:4000]})
                if draft:
                    history.append({"role": "user", "content": "[팀원이 적은 요청서 초안. 참고만 한다]\n" + draft[:3000]})
                if note:
                    history.append({"role": "user", "content": note})
                async with thread.typing():
                    reply = await asyncio.to_thread(
                        self.director.reply, history, thread_id=thread.id, channel_id=intake.id,
                        requester_id=message.author.id,
                        extra_system=PROMOTED.format(channel=self.cfg.adhoc_channel))
            except Exception as e:
                log.exception("옮긴 실험 요청 처리 오류")
                reply = (f"접수 처리 중 오류가 났습니다: {type(e).__name__}: {str(e)[:300]}\n"
                         "이 스레드에 '다시 접수해'라고 답하면 이어서 처리합니다.")
            for part in chunks(reply):
                await thread.send(part)
        return True

    def _ready_roles(self) -> set:
        return {r for r, m in self.notifier.members.items() if m is not None and m.is_ready()}

    async def _history(self, target, message) -> list[dict]:
        if target.id == message.channel.id:
            msgs = [m async for m in target.history(limit=30, oldest_first=False)]
            msgs.reverse()
            if isinstance(target, discord.Thread) and len(msgs) < 30:
                # 글에서 만든 스레드의 첫 글(연구자의 요청 원문)은 부모 채널에 있어 스레드 기록에 안 나온다. 직접 가져와 맨 앞에 둔다.
                try:
                    first = target.starter_message or await target.parent.fetch_message(target.id)
                    if first is not None and all(m.id != first.id for m in msgs):
                        msgs.insert(0, first)
                except (discord.DiscordException, AttributeError):
                    pass
        else:                                       # 방금 만든 스레드: 첫 메시지만 있다
            msgs = [message]
        out = []
        for m in msgs:
            role = "assistant" if m.author.id == self.user.id else "user"
            content = m.clean_content
            if content:
                out.append({"role": role, "content": content})
        return out

    async def _save_attachments(self, message: discord.Message, extra: list | None = None) -> str:
        saved = []
        up = self.cfg.data_dir / "uploads"
        up.mkdir(parents=True, exist_ok=True)
        for a in list(message.attachments) + list(extra or []):
            if a.size > MAX_UPLOAD:
                saved.append(f"(용량 초과로 저장하지 않음: {a.filename})")
                continue
            name = f"{time.strftime('%Y%m%d-%H%M%S')}_{safe_name(a.filename)}"
            await a.save(up / name)
            saved.append(f"/data/uploads/{name}")
        if not saved:
            return ""
        return "[연구자가 파일을 첨부함. 실험에서는 /data 아래 경로로 읽을 수 있음]\n" + "\n".join(saved)

    # ---- 슬래시 명령 ----
    def _register_commands(self):
        tree, lab = self.tree, self.lab

        @tree.command(name="status", description="연구실 현황, 또는 실험 하나의 상세 상태")
        @app_commands.describe(exp_id="예: EXP-003 (비우면 전체 현황)")
        async def status(i: discord.Interaction, exp_id: str | None = None):
            if not exp_id or not load_policy(self.cfg, exp_id.upper()).allows_discord:
                await i.response.send_message("이 상태 정보의 디스코드 전송은 허용되지 않았습니다.", ephemeral=True)
                return
            text = lab.describe(exp_id) if exp_id else lab.status_text()
            await i.response.send_message(chunks(text)[0])
            for p in chunks(text)[1:]:
                await i.followup.send(p)

        @tree.command(name="stop", description="실험 중단")
        async def stop(i: discord.Interaction, exp_id: str):
            await i.response.send_message(await asyncio.to_thread(lab.stop, exp_id))

        @tree.command(name="resume", description="실패·중단·일시정지된 실험 재개")
        async def resume(i: discord.Interaction, exp_id: str):
            await i.response.send_message(await asyncio.to_thread(lab.resume, exp_id))

        @tree.command(name="approve", description="승인 대기 중인 실험 승인(대기 중인 명령 승인 요청이 있으면 그것을 승인)")
        async def approve(i: discord.Interaction, exp_id: str):
            if not load_policy(self.cfg, exp_id.upper()).allows_discord:
                await i.response.send_message("비공개 실험은 로컬 콘솔에서 계획을 검토하고 승인하세요.", ephemeral=True)
                return
            await i.response.send_message(await asyncio.to_thread(lab.approve, exp_id))

        @tree.command(name="reject", description="승인 대기 중인 실험 거부")
        async def reject(i: discord.Interaction, exp_id: str):
            await i.response.send_message(await asyncio.to_thread(lab.reject, exp_id))

        @tree.command(name="amend", description="추가 과업: 쓰기·실행이 필요한 후속 일을 개발→통계→QA→저장으로 맡긴다")
        @app_commands.describe(exp_id="예: EXP-001", task="할 일(무엇을 계산·저장할지)")
        async def amend(i: discord.Interaction, exp_id: str, task: str):
            await i.response.send_message(await asyncio.to_thread(lab.amend, exp_id.upper(), task))

        @tree.command(name="priority", description="대기 중인 실험의 우선순위 변경(클수록 먼저)")
        async def priority(i: discord.Interaction, exp_id: str, value: int):
            await i.response.send_message(lab.set_priority(exp_id, value))

        @tree.command(name="report", description="완료된 실험의 보고서와 산출물 받기")
        @app_commands.describe(exp_id="예: EXP-003", path="비우면 report/report.md")
        async def report(i: discord.Interaction, exp_id: str, path: str = "report/report.md"):
            if not load_policy(self.cfg, exp_id.upper()).allows_discord:
                await i.response.send_message("이 실험의 디스코드 파일 전송은 허용되지 않았습니다.", ephemeral=True)
                return
            base = (self.cfg.experiments_dir / exp_id.upper()).resolve()
            p = (base / path).resolve()
            if not re.fullmatch(r"EXP-\d+", exp_id.upper()) or (base not in p.parents) or not p.is_file():
                await i.response.send_message("파일을 찾지 못했습니다.", ephemeral=True)
                return
            if p.stat().st_size > MAX_FILE:
                await i.response.send_message(f"용량이 커서 첨부할 수 없습니다: {p}", ephemeral=True)
                return
            await i.response.send_message(f"{exp_id.upper()} / {path}", file=discord.File(str(p)))

        @tree.command(name="policy", description="실험의 자료 정책 열기(디스코드 게시·클라우드 모델 허용)/닫기")
        @app_commands.describe(exp_id="예: EXP-003", action="open 열기 / close 닫기(로컬 전용)")
        @app_commands.choices(action=[app_commands.Choice(name=n, value=n) for n in ("open", "close")])
        async def policy_(i: discord.Interaction, exp_id: str, action: app_commands.Choice[str]):
            await i.response.send_message(set_policy(self.cfg, exp_id, action.value == "open"))

        @tree.command(name="learn", description="누적 학습(연구자 성향·업무 요령) 보기·확인·삭제")
        @app_commands.describe(action="list 보기 / approve 후보 반영 / reject 후보 거절 / forget 확정 항목 삭제",
                               item_id="L-### (후보) 또는 P-### (확정 항목)")
        @app_commands.choices(action=[app_commands.Choice(name=n, value=n) for n in ("list", "approve", "reject", "forget")])
        async def learn(i: discord.Interaction, action: app_commands.Choice[str], item_id: str | None = None):
            a = action.value
            if a == "list":
                text = growth.summary(self.cfg)
            elif not item_id:
                text = "ID 를 함께 적어 주세요(예: L-003, P-002)."
            else:
                text = {"approve": growth.approve, "reject": growth.reject, "forget": growth.forget}[a](self.cfg, item_id)
            await i.response.send_message(chunks(text)[0])
            for p in chunks(text)[1:]:
                await i.followup.send(p)

        @tree.command(name="memory", description="연구실장 세컨드 브레인의 결정 기록 보기·확정·거절·폐기")
        @app_commands.describe(action="list 보기 / approve 제안 확정 / reject 제안 거절 / retire 확정 결정 폐기", item_id="D-###")
        @app_commands.choices(action=[app_commands.Choice(name=n, value=n) for n in ("list", "approve", "reject", "retire")])
        async def memory_(i: discord.Interaction, action: app_commands.Choice[str], item_id: str | None = None):
            a = action.value
            if a == "list":
                text = memory.decisions_summary(self.cfg)
            elif not item_id:
                text = "ID 를 함께 적어 주세요(예: D-003)."
            else:
                text = {"approve": memory.approve_decision, "reject": memory.reject_decision,
                        "retire": memory.retire_decision}[a](self.cfg, item_id)
            await i.response.send_message(chunks(text)[0])
            for p in chunks(text)[1:]:
                await i.followup.send(p)

        @tree.command(name="reading", description="논문 리딩: 세션 목록 / 연구 지향 보기 / 이 스레드 세션 정리")
        @app_commands.describe(action="list 세션 목록 / lens 연구 지향·최근 리딩 / close 이 스레드 리딩 노트 / retry 빠진 리딩 리포트 다시 쓰기")
        @app_commands.choices(action=[app_commands.Choice(name=n, value=n) for n in ("list", "lens", "close", "retry")])
        async def reading_(i: discord.Interaction, action: app_commands.Choice[str]):
            if i.user.id != self.cfg.discord_owner_id:
                await i.response.send_message("연구자만 쓸 수 있습니다.", ephemeral=True)
                return
            a = action.value
            if a in ("close", "retry"):
                sess = reading.ReadingStore(self.cfg).find_by_thread(getattr(i.channel, "id", None))
                if not sess:
                    await i.response.send_message("논문 리딩 스레드 안에서 써 주세요.", ephemeral=True)
                    return
                if a == "close":
                    await i.response.send_message(f"{sess['id']} 리딩 노트를 작성합니다.")
                    await self._reading_close(i.channel, sess["id"])
                    return
                todo = reading.missing_reports(self.cfg, sess["id"])
                if not reading.ReadingStore(self.cfg).paper_text(sess["id"]) and not reading.article_text(self.cfg, sess["id"]):
                    await i.response.send_message("아직 읽을 수 있는 논문 본문이 없습니다. PDF나 본문을 먼저 올려 주세요.")
                    return
                if not todo:
                    await i.response.send_message("빠진 리포트·첨언이 없습니다.")
                    return
                await i.response.send_message(f"빠진 {len(todo)}건을 다시 씁니다.")
                await self._reading_reports(i.channel, sess["id"], todo)
                return
            text = reading.list_summary(self.cfg) if a == "list" else reading.lens_summary(self.cfg)
            parts = chunks(text)
            await i.response.send_message(parts[0])
            for part in parts[1:]:
                await i.followup.send(part)

        @tree.command(name="help", description="사용법")
        async def help_(i: discord.Interaction):
            await i.response.send_message(
                f"**연구실 사용법**\n"
                f"- `#{self.cfg.intake_channel}` 에 하고 싶은 실험을 자유롭게 쓰면 연구실장이 요청서로 정리해 접수합니다. "
                f"데이터 파일은 같이 첨부하세요(`/data/uploads/` 로 저장).\n"
                f"- 실험마다 스레드가 열리고, 거기서 진행 상황·결과·전문가 의견을 자유롭게 물어보세요.\n"
                f"- 승인이 필요한 실험은 스레드에 승인/거부 버튼이 뜹니다(`/approve`, `/reject` 도 가능).\n"
                f"- `#{self.cfg.adhoc_channel}` 는 실험과 별개의 단건 업무 창구입니다. 담당자를 @멘션하면 그 팀원이 바로 처리하고, "
                f"멘션 없이 올리면 연구실장이 맞는 팀원에게 넘깁니다(샌드박스·네트워크 없음·{self.cfg.adhoc_timeout_min}분 상한). "
                f"실험 수준의 일이면 `#{self.cfg.intake_channel}` 스레드로 자동으로 옮겨 접수합니다(다시 올릴 필요 없음).\n"
                f"- 실험 스레드가 자료 정책으로 막히면 `/policy EXP-### open` 으로 엽니다(디스코드 게시·클라우드 모델 허용). `close` 로 다시 닫습니다.\n"
                f"- 처리하며 배운 성향·요령은 누적되어 메인 실험에도 반영됩니다. `/learn list` 로 보고 `approve`/`reject`/`forget`.\n"
                f"- 연구실장은 과거 실험·결정을 출처와 검증 상태를 붙여 찾아 줍니다. 대화에서 내린 연구 결정은 제안으로 남고 "
                f"`/memory approve D-###` 로 확정합니다(`/memory list`).\n"
                f"- `#{self.cfg.reading_channel}` 에 공부할 논문 폴더(파일 여러 개, .zip, 맥 폴더 경로) 또는 arXiv·ACL·OpenReview 링크를 올리면 논문 제목으로 스레드가 열리고 10명 전원이 각자 리딩 리포트를 씁니다. 이어서 튜터들과 과외하듯 질문할 수 있습니다. "
                f"스레드에서 멘션 없이 물으면 맞는 튜터가 답하고, \"정리해줘\"로 리딩 노트를 남깁니다. 대화에서 밝힌 연구 관심·입장은 "
                f"연구 지향으로 누적되어 모든 에이전트에 반영됩니다(`/reading lens`).\n"
                f"- `/status [EXP-###]` `/stop` `/resume` `/amend`(추가 과업) `/priority` `/report` `/learn` `/memory` `/reading`\n"
                f"- 즉시 알림은 승인 필요·결정 필요·완료 3종이고, 나머지 진행 상황은 매일 하루 요약으로 올라옵니다.")
