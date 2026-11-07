"""팀원 봇: 대답 규칙, 멘션 변환, 답변 생성, 진행 알림의 역할 표시 (디스코드 접속 없이)."""
from conftest import T
from lab.agents import DISPLAY_EN, ROLE_META
from lab.team import (MEMBER_CHANNELS, MEMBER_TOOLS, MemberBot, Registry, build_members, channel_for,
                      member_channels, should_answer)
from lab.tools import CONSULTANTS
from test_pipeline import script, submit

ME, OTHER, DIRECTOR = 101, 202, 303


def ask(**kw):
    base = dict(author_is_bot=False, author_is_owner=True, is_dm=False, text_channel_name=None, team_mention_ids=set())
    base.update(kw)
    return should_answer(ME, None, **base)


def test_answer_rules():
    assert ask(team_mention_ids={ME})                                             # 어디서든 멘션
    assert ask(is_dm=True)                                                        # DM
    assert not ask(text_channel_name="봇점검")                                   # 멘션 없는 글에는 대답 안 함
    assert not ask(text_channel_name="봇점검", team_mention_ids={OTHER})         # 다른 팀원만 부르면 양보
    assert ask(text_channel_name="통계-설계", team_mention_ids={ME, OTHER})       # 같이 부르면 각자 대답
    assert not ask(text_channel_name="언어학")                                    # 남의 채널
    assert not ask(text_channel_name=None)                                        # 멘션 없는 실험 스레드 → 연구실장 몫
    assert not ask(is_dm=True, author_is_owner=False)                             # 연구자 외 무시
    assert not ask(team_mention_ids={ME}, author_is_bot=True)                     # 봇끼리 대화 금지


def test_channels_unique_and_roles_known(make_lab):
    lab, _ = make_lab({})
    assert member_channels(lab.cfg) == []
    assert all(channel_for(lab.cfg, r) is None for r in MEMBER_CHANNELS)
    assert len({lab.cfg.intake_channel, lab.cfg.perf_channel, lab.cfg.test_channel, lab.cfg.report_channel}) == 4
    for r in MEMBER_CHANNELS:
        assert r in ROLE_META and r in DISPLAY_EN
    for r in CONSULTANTS:
        assert r in MEMBER_CHANNELS


def test_mentions_roundtrip():
    reg = Registry()
    reg.add(ME, "statistician")
    reg.add(DIRECTOR, "director")
    assert reg.humanize(f"<@{ME}> 이거 <@!{DIRECTOR}> 확인", owner_id=9) == "@Statistician 이거 @Lab Director 확인"
    assert reg.linkify("@Statistician 에게 물어보고 @Lab Director 에게 접수") == f"<@{ME}> 에게 물어보고 <@{DIRECTOR}> 에게 접수"


def test_build_members_only_with_tokens(make_lab, monkeypatch):
    lab, _ = make_lab({})
    for r in MEMBER_CHANNELS:
        monkeypatch.delenv(f"BOT_TOKEN_{r.upper()}", raising=False)
    monkeypatch.setenv("BOT_TOKEN_STATISTICIAN", "x.y.z")
    got = build_members(lab.cfg, lab, Registry())
    assert [m.role for m, _ in got] == ["statistician"]


def test_member_reply_uses_role_route_and_read_tools(make_lab):
    lab, _ = make_lab({"statistician": [
        [T("submit_memo", memo_markdown="x", summary="x", key_concerns=[], recommendations=[])],   # 쓰기 도구 → 거절
        [T("lab_status")],
        [("text", "조건당 20문항이면 검정력이 부족할 수 있습니다.")]]})
    bot = MemberBot(lab.cfg, lab, "statistician", Registry())
    out = bot.reply([{"role": "user", "content": "20문항이면 충분해?"}])
    assert "검정력" in out
    assert lab.client.calls == ["statistician"] * 3                    # 역할 경로로 호출됨
    assert {t["name"] for t in MEMBER_TOOLS} <= {"lab_status", "list_experiments", "get_experiment",
                                                  "list_experiment_files", "read_experiment_file", "search_notebook"}
    sp = bot.system_prompt(None)
    assert "[ROLE:statistician]" in sp and "디스코드 대화 중" in sp and "@Lab Director" in sp


def test_pipeline_progress_posted_as_roles(make_lab):
    lab, notifier = make_lab(script())
    submit(lab)
    lab.process_one()
    roles = set(r for r in notifier.roles if r)
    assert set(CONSULTANTS) <= roles                                    # 자문·해석 메모는 각 전문가 이름으로
    assert {"practitioner", "developer", "documenter", "tester"} <= roles
    assert None in notifier.roles                                       # 접수·완료 같은 공지는 연구실장
