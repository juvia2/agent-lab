"""디스코드 봇: 연구자와 연구실의 유일한 접점. 연구자 본인(DISCORD_OWNER_ID)의 명령만 받는다."""
from __future__ import annotations

import asyncio
import logging
import re
import threading
import time
from pathlib import Path

import discord
from discord import app_commands

from .notify import Notifier
from .pipeline import PHASE_LABEL, STATUS_LABEL

log = logging.getLogger("lab.bot")
MAX_LEN = 1900
MAX_FILE = 8 * 1024 * 1024           # 디스코드 업로드 한도에 안전하게 맞춘 값
MAX_UPLOAD = 100 * 1024 * 1024       # 연구자가 올리는 데이터 파일 한도


def chunks(text: str, n: int = MAX_LEN) -> list[str]:
    text = text.strip() or "(내용 없음)"
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
            label="승인" if ok else "거부", emoji="✅" if ok else "🚫",
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
        lab = interaction.client.lab
        fn = lab.approve if self.action == "approve" else lab.reject
        msg = await asyncio.to_thread(fn, self.exp_id)
        base = (interaction.message.content or "")[:1500]
        await interaction.response.edit_message(content=f"{base}\n\n→ {msg}", view=None)


class LabTree(app_commands.CommandTree):
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.client.cfg.discord_owner_id:
            await interaction.response.send_message("이 연구실은 소유자 전용입니다.", ephemeral=True)
            return False
        return True


# ===================== 알림 (워커 스레드 → 디스코드) =====================
class DiscordNotifier(Notifier):
    def __init__(self, cfg):
        self.cfg = cfg
        self.bot: LabBot | None = None

    def _run(self, coro, timeout: float = 120):
        if not self.bot or not self.bot.loop or not self.bot.is_ready():
            coro.close()
            log.warning("디스코드가 아직 준비되지 않아 알림을 건너뜀")
            return None
        try:
            return asyncio.run_coroutine_threadsafe(coro, self.bot.loop).result(timeout)
        except Exception:
            log.exception("디스코드 전송 실패")
            return None

    def post(self, exp, text, files=None):
        self._run(self._post(exp, text, files))

    def post_report(self, exp, text, files=None):
        self._run(self._post(exp, text, files))
        self._run(self._post_named(self.cfg.report_channel, text, files))

    def ask_approval(self, exp, reasons, plan_summary):
        self._run(self._ask(exp, reasons, plan_summary))

    # ---- 비동기 구현 ----
    async def _channel_for(self, exp):
        bot = self.bot
        if exp:
            e = bot.lab.ledger.get(exp["id"])
            tid = e and e.get("thread_id")
            if tid:
                try:
                    ch = bot.get_channel(tid) or await bot.fetch_channel(tid)
                    if isinstance(ch, discord.Thread) and ch.archived:
                        await ch.edit(archived=False)
                    return ch
                except discord.DiscordException:
                    log.warning("스레드 %s 를 찾지 못함", tid)
        return await self._named(self.cfg.progress_channel)

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

    async def _post(self, exp, text, files):
        await self._send(await self._channel_for(exp), text, files)

    async def _post_named(self, name, text, files):
        await self._send(await self._named(name), text, files)

    async def _ask(self, exp, reasons, plan_summary):
        ch = await self._channel_for(exp)
        owner = self.cfg.discord_owner_id
        text = (f"🔐 <@{owner}> **{exp['id']}** 승인이 필요합니다.\n"
                f"사유:\n" + "\n".join(f"- {r}" for r in reasons) +
                f"\n\n계획 요약:\n{plan_summary[:900]}\n\n계획 전문은 `plan.md` 에 있습니다(스레드에서 물어보세요).")
        view = discord.ui.View(timeout=None)
        view.add_item(ApprovalButton("approve", exp["id"]))
        view.add_item(ApprovalButton("reject", exp["id"]))
        await self._send(ch, text, view=view)


# ===================== 봇 =====================
class LabBot(discord.Client):
    def __init__(self, cfg, lab, director, notifier: DiscordNotifier, stop_event: threading.Event,
                 startup_note: str = ""):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.cfg, self.lab, self.director = cfg, lab, director
        self.notifier, self.stop_event, self.startup_note = notifier, stop_event, startup_note
        self.tree = LabTree(self)
        self._locks: dict[int, asyncio.Lock] = {}
        self._started = False
        self._register_commands()

    # ---- 시작 ----
    async def setup_hook(self):
        self.add_dynamic_items(ApprovalButton)
        if self.cfg.discord_guild_id:
            g = discord.Object(id=self.cfg.discord_guild_id)
            self.tree.copy_global_to(guild=g)
            await self.tree.sync(guild=g)
        else:
            await self.tree.sync()

    async def on_ready(self):
        if self._started:
            return
        self._started = True
        log.info("로그인: %s", self.user)
        await self._ensure_channels()
        recovered = self.lab.ledger.reset_interrupted()
        self.lab.start_workers(self.stop_event)
        msg = "🟢 **연구실 가동**" + (f"\n🔄 중단됐던 실험 {len(recovered)}건을 이어서 진행합니다: {', '.join(recovered)}"
                                    if recovered else "")
        if self.startup_note:
            msg += "\n" + self.startup_note
        await self.notifier._post(None, msg, None)

    async def _ensure_channels(self):
        names = [self.cfg.intake_channel, self.cfg.progress_channel, self.cfg.report_channel]
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

    # ---- 일반 대화 ----
    def _is_owner(self, uid: int) -> bool:
        return uid == self.cfg.discord_owner_id

    async def on_message(self, message: discord.Message):
        if message.author.bot or not self._is_owner(message.author.id):
            return
        ch = message.channel
        text = (message.content or "").strip()
        if not text and not message.attachments:
            return
        thread_id = None
        target = None
        if isinstance(ch, discord.TextChannel) and ch.name == self.cfg.intake_channel:
            title = re.sub(r"\s+", " ", text)[:60] or "새 요청"
            target = await message.create_thread(name=f"💬 {title}"[:100], auto_archive_duration=10080)
            thread_id = target.id
        elif isinstance(ch, discord.Thread) and (
                (ch.parent and ch.parent.name == self.cfg.intake_channel) or self.lab.ledger.find_by_thread(ch.id)):
            target, thread_id = ch, ch.id
        elif isinstance(ch, discord.DMChannel):
            target = ch
        if target is None:
            return
        lock = self._locks.setdefault(target.id, asyncio.Lock())
        async with lock:
            try:
                note = await self._save_attachments(message)
                history = await self._history(target, message)
                if note:
                    history.append({"role": "user", "content": note})
                async with target.typing():
                    reply = await asyncio.to_thread(
                        self.director.reply, history, thread_id=thread_id,
                        channel_id=getattr(message.channel, "id", None), requester_id=message.author.id)
            except Exception as e:
                log.exception("대화 처리 오류")
                reply = f"⚠️ 처리 중 오류가 났습니다: {type(e).__name__}: {str(e)[:300]}"
            for part in chunks(reply):
                await target.send(part)

    async def _history(self, target, message) -> list[dict]:
        if target.id == message.channel.id:
            msgs = [m async for m in target.history(limit=30, oldest_first=False)]
            msgs.reverse()
        else:                                       # 방금 만든 스레드: 첫 메시지만 있다
            msgs = [message]
        out = []
        for m in msgs:
            role = "assistant" if m.author.id == self.user.id else "user"
            content = m.clean_content
            if content:
                out.append({"role": role, "content": content})
        return out

    async def _save_attachments(self, message: discord.Message) -> str:
        saved = []
        up = self.cfg.data_dir / "uploads"
        up.mkdir(parents=True, exist_ok=True)
        for a in message.attachments:
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

        @tree.command(name="approve", description="승인 대기 중인 실험 승인")
        async def approve(i: discord.Interaction, exp_id: str):
            await i.response.send_message(await asyncio.to_thread(lab.approve, exp_id))

        @tree.command(name="reject", description="승인 대기 중인 실험 거부")
        async def reject(i: discord.Interaction, exp_id: str):
            await i.response.send_message(await asyncio.to_thread(lab.reject, exp_id))

        @tree.command(name="priority", description="대기 중인 실험의 우선순위 변경(클수록 먼저)")
        async def priority(i: discord.Interaction, exp_id: str, value: int):
            await i.response.send_message(lab.set_priority(exp_id, value))

        @tree.command(name="report", description="완료된 실험의 보고서와 산출물 받기")
        @app_commands.describe(exp_id="예: EXP-003", path="비우면 report/report.md")
        async def report(i: discord.Interaction, exp_id: str, path: str = "report/report.md"):
            base = (self.cfg.experiments_dir / exp_id.upper()).resolve()
            p = (base / path).resolve()
            if not re.fullmatch(r"EXP-\d+", exp_id.upper()) or (base not in p.parents) or not p.is_file():
                await i.response.send_message("파일을 찾지 못했습니다.", ephemeral=True)
                return
            if p.stat().st_size > MAX_FILE:
                await i.response.send_message(f"용량이 커서 첨부할 수 없습니다: {p}", ephemeral=True)
                return
            await i.response.send_message(f"{exp_id.upper()} / {path}", file=discord.File(str(p)))

        @tree.command(name="help", description="사용법")
        async def help_(i: discord.Interaction):
            await i.response.send_message(
                f"**연구실 사용법**\n"
                f"- `#{self.cfg.intake_channel}` 에 하고 싶은 실험을 자유롭게 쓰면 연구실장이 요청서로 정리해 접수합니다. "
                f"데이터 파일은 같이 첨부하세요(`/data/uploads/` 로 저장).\n"
                f"- 실험마다 스레드가 열리고, 거기서 진행 상황·결과·전문가 의견을 자유롭게 물어보세요.\n"
                f"- 승인이 필요한 실험은 스레드에 ✅/🚫 버튼이 뜹니다(`/approve`, `/reject` 도 가능).\n"
                f"- `/status [EXP-###]` `/stop` `/resume` `/priority` `/report`")
