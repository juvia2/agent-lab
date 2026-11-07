"""팀원 봇: 연구실장 외 9명이 각자 디스코드 봇으로 연구자와 대화한다.

- 봇마다 .env 의 BOT_TOKEN_<역할> 토큰을 쓴다. 토큰이 없는 역할은 건너뛴다(연구실장 봇 혼자서도 전처럼 동작).
- 대답 규칙: 연구자(오너) 메시지만. 봇이 쓴 글에는 대답하지 않는다(봇끼리 무한 대화 방지).
    DM → 받은 봇 / 자기를 @멘션 → 어느 채널·스레드든 대답
- 답변은 역할 프롬프트 + 읽기 전용 도구(현황·실험 파일·연구노트)로 만든다. 모델 경로는 역할별 ROUTE_* 를 그대로 탄다.
- 실험 접수·중단·승인은 하지 않는다(연구실장과 연구자 몫).
- 파이프라인 진행 알림도 담당 역할의 봇 이름으로 실험 스레드에 올라간다(bot.DiscordNotifier 참고).
"""
from __future__ import annotations

import asyncio
import logging
import os
import re

import discord

from .agents import DISPLAY_EN, label, model_for, system_for
from .director import DIRECTOR_TOOLS, Director, _merge
from .llm import NoBackend, ToolOutput, run_agent

log = logging.getLogger("lab.team")

# 팀원 역할. 대화는 실험 스레드·점검 채널의 멘션 또는 DM으로 시작한다.
MEMBER_CHANNELS = {
    "linguist": None,
    "cogsci": None,
    "lm": None,
    "statistician": None,
    "corpus": None,
    "practitioner": None,
    "developer": None,
    "documenter": None,
    "tester": None,
}
READ_TOOLS = {"lab_status", "list_experiments", "get_experiment", "list_experiment_files",
              "read_experiment_file", "search_notebook"}
MEMBER_TOOLS = [t for t in DIRECTOR_TOOLS if t["name"] in READ_TOOLS]

CHAT_RULES = """

---
## 지금은 디스코드 대화 중이다
연구자가 디스코드에서 당신({name}, {label})에게 직접 말을 걸었다. 동료에게 말하듯 한국어로 간결하게 답한다.
- 실험 단계용 제출 도구(submit_memo 등)는 지금 없다. 읽기 도구(연구실 현황, 실험 파일, 연구노트)만 있다.
  실험에 대해 물으면 도구로 실제 파일·상태를 확인하고 답한다. 수치는 파일에서 읽은 것만, 출처 파일과 함께 말한다.
- 실험 접수·중단·재개·승인은 하지 않는다. 그런 요청이면 연구실장(@Lab Director)에게 말하라고 안내한다.
  승인은 연구자만 버튼이나 /approve 로 할 수 있다.
- 디스코드 메시지이므로 보통 3~10문장, 1500자 이내. 필요할 때만 목록·표를 쓴다.
- 당신 영역 밖의 질문이면 아는 만큼 짧게 답하고 맞는 동료를 "@영문이름"으로 추천한다.
  동료: {roster}
- 모르면 모른다고 말한다. 추측을 사실처럼 쓰지 않는다."""


def token_env(role: str) -> str:
    return f"BOT_TOKEN_{role.upper()}"


def channel_for(cfg, role: str) -> None:
    return MEMBER_CHANNELS[role]


def member_channels(cfg) -> list[str]:
    return []


class Registry:
    """봇 user id ↔ 역할. 연구실장 봇도 'director' 로 등록된다."""

    def __init__(self):
        self.by_user: dict[int, str] = {}
        self.by_role: dict[str, int] = {}

    def add(self, user_id: int, role: str) -> None:
        self.by_user[user_id] = role
        self.by_role[role] = user_id

    def humanize(self, text: str, owner_id: int | None) -> str:
        def repl(m):
            uid = int(m.group(1))
            if uid in self.by_user:
                return "@" + DISPLAY_EN[self.by_user[uid]]
            return "@연구자" if uid == owner_id else "@someone"
        return re.sub(r"<@!?(\d+)>", repl, text)

    def linkify(self, text: str) -> str:
        for role in sorted(self.by_role, key=lambda r: -len(DISPLAY_EN[r])):
            text = text.replace("@" + DISPLAY_EN[role], f"<@{self.by_role[role]}>")
        return text


def should_answer(my_user_id: int, home: str | None, *, author_is_bot: bool, author_is_owner: bool, is_dm: bool,
                  text_channel_name: str | None, team_mention_ids: set[int]) -> bool:
    """팀원 봇이 이 메시지에 대답할지 (디스코드 객체 없이 테스트할 수 있게 분리)."""
    if author_is_bot or not author_is_owner:
        return False
    if is_dm:
        return True
    if my_user_id in team_mention_ids:
        return True
    if team_mention_ids:                        # 다른 팀원만 불렀으면 양보
        return False
    return False


class MemberBot(discord.Client):
    def __init__(self, cfg, lab, role: str, registry: Registry):
        intents = discord.Intents.default()
        # 멘션과 DM은 Message Content Intent 없이도 본문을 받을 수 있다.
        intents.message_content = False
        super().__init__(intents=intents)
        self.cfg, self.lab, self.role, self.registry = cfg, lab, role, registry
        self.home = channel_for(cfg, role)
        self._director = Director(lab)
        self._locks: dict[int, asyncio.Lock] = {}

    async def on_ready(self):
        self.registry.add(self.user.id, self.role)
        log.info("팀원 봇 접속: %s (%s)", self.user, label(self.role))

    # ---- 대답 여부 ----
    def should_answer(self, message: discord.Message) -> bool:
        ch = message.channel
        return should_answer(
            self.user.id, self.home, author_is_bot=message.author.bot,
            author_is_owner=message.author.id == self.cfg.discord_owner_id,
            is_dm=isinstance(ch, discord.DMChannel),
            text_channel_name=ch.name if isinstance(ch, discord.TextChannel) else None,
            team_mention_ids={u.id for u in message.mentions if u.id in self.registry.by_user})

    async def on_message(self, message: discord.Message):
        if not self.should_answer(message):
            return
        lock = self._locks.setdefault(message.channel.id, asyncio.Lock())
        async with lock:
            try:
                history = await self._history(message)
                ctx = None
                if isinstance(message.channel, discord.Thread):
                    exp = self.lab.ledger.find_by_thread(message.channel.id)
                    ctx = self.lab.describe(exp["id"]) if exp else None
                async with message.channel.typing():
                    reply = await asyncio.to_thread(self.reply, history, ctx)
            except Exception as e:
                log.exception("[%s] 대화 처리 오류", self.role)
                reply = f"⚠️ 처리 중 오류가 났습니다: {type(e).__name__}: {str(e)[:300]}"
        from .bot import chunks
        for i, part in enumerate(chunks(self.registry.linkify(reply))):
            if i == 0:
                await message.reply(part, mention_author=False)
            else:
                await message.channel.send(part)

    async def _history(self, message: discord.Message) -> list[dict]:
        msgs = [m async for m in message.channel.history(limit=20, before=message)]
        msgs.reverse()
        msgs.append(message)
        out = []
        for m in msgs:
            text = self.registry.humanize(m.content or "", self.cfg.discord_owner_id).strip()
            if not text:
                continue
            if m.author.id == self.user.id:
                out.append({"role": "assistant", "content": text})
            elif m.author.id in self.registry.by_user:          # 다른 팀원의 말은 맥락으로만
                out.append({"role": "user", "content": f"[{DISPLAY_EN[self.registry.by_user[m.author.id]]}의 메시지] {text}"})
            else:
                out.append({"role": "user", "content": text})
        return out

    # ---- 답변 생성 (워커 스레드) ----
    def system_prompt(self, ctx: str | None) -> str:
        roster = ", ".join(f"@{DISPLAY_EN[r]}({label(r) if r != 'director' else '🧑‍💼 연구실장'})"
                           for r in DISPLAY_EN if r != self.role)
        s = system_for(self.role) + CHAT_RULES.format(name=DISPLAY_EN[self.role], label=label(self.role), roster=roster)
        if ctx:
            s += "\n\n## 이 스레드의 실험 상태\n" + ctx
        return s

    def reply(self, history: list[dict], ctx: str | None = None) -> str:
        msgs = _merge(history)
        if not msgs:
            return "무엇을 도와드릴까요?"

        def execute(name: str, a: dict) -> ToolOutput:
            if name not in READ_TOOLS:
                return ToolOutput(f"{name} 은(는) 쓸 수 없는 도구입니다", is_error=True)
            return self._director._tool(name, a, None, None, None)

        try:
            res = run_agent(self.lab.client, model=model_for(self.cfg, self.role), system=self.system_prompt(ctx),
                            messages=msgs, tools=MEMBER_TOOLS, execute=execute, max_turns=8, max_tokens=2500)
        except NoBackend as e:
            return f"지금 답변에 쓸 수 있는 모델이 없습니다(한도·로그인·로컬 서버 확인 필요).\n{str(e)[:400]}"
        return res.text.strip() or "(응답이 비어 있습니다. 다시 말씀해 주세요.)"


def build_members(cfg, lab, registry: Registry) -> list[tuple[MemberBot, str]]:
    """토큰이 있는 역할만 봇을 만든다."""
    out = []
    for role in MEMBER_CHANNELS:
        tok = os.environ.get(token_env(role), "").strip()
        if tok:
            out.append((MemberBot(cfg, lab, role, registry), tok))
    return out
