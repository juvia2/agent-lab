"""#의뢰 채널과 학습 누적: 상한 강제, 경로 제한, 학습 승격 규칙, 메인 실험 프롬프트 주입 (디스코드 접속 없이)."""
import dataclasses
import json

import pytest

from conftest import T
from lab import growth
from lab.adhoc import MAX_RUNS, AdhocBox
from lab.agents import director_system, system_for
from lab.bot import parse_route
from lab.director import Director
from lab.team import MemberBot, Registry, is_adhoc_channel


# ---------------- 채널 판별 ----------------

def test_adhoc_channel_detection(make_lab):
    lab, _ = make_lab({})
    assert lab.cfg.adhoc_channel == "의뢰"
    assert is_adhoc_channel(lab.cfg, "의뢰")
    assert is_adhoc_channel(lab.cfg, None, "의뢰")                 # #의뢰 안의 스레드
    assert not is_adhoc_channel(lab.cfg, "실험진행")
    assert lab.cfg.adhoc_channel not in {lab.cfg.intake_channel, lab.cfg.perf_channel,
                                         lab.cfg.test_channel, lab.cfg.report_channel}


def test_parse_route():
    assert parse_route("ROUTE: corpus\n코퍼스 담당에게 넘깁니다.") == ("corpus", "코퍼스 담당에게 넘깁니다.")
    assert parse_route("ROUTE：Developer\nERD 검토는 개발자에게.")[0] == "developer"
    assert parse_route("모르겠어요")[0] == "ask"


# ---------------- 학습 누적 규칙 ----------------

def test_stated_preference_applies_immediately(make_lab):
    lab, _ = make_lab({})
    out = growth.record(lab.cfg, role="corpus", kind="preference", text="빈도표에는 상대빈도를 함께 낸다",
                        category="보고형식", stated=True, evidence="앞으로 상대빈도도 넣어줘")
    assert out["status"] == "stated" and out["id"].startswith("P-")
    again = growth.record(lab.cfg, role="statistician", kind="preference", text="빈도표에는 상대빈도를 함께 낸다",
                          category="보고형식", stated=True)
    assert again["status"] == "ignored"                                # 중복 없음
    # 성향은 전원 공유 → 다른 역할 프롬프트에도 들어간다
    assert "상대빈도" in system_for("linguist", lab.cfg)
    assert "상대빈도" in director_system(None, lab.cfg)


def test_inferred_needs_threshold_and_confirmation(make_lab):
    lab, _ = make_lab({})
    r1 = growth.record(lab.cfg, role="developer", kind="preference", text="코드 결과는 표로 요약한다", category="보고형식")
    assert r1["status"] == "new"
    assert "표로 요약" not in system_for("developer", lab.cfg)          # 후보는 지시로 주입되지 않음
    assert "표로 요약" in system_for("developer", lab.cfg, include_open=True)   # 의뢰 모드에선 강화용으로만 보임
    r2 = growth.record(lab.cfg, role="tester", kind="preference", text="", category="보고형식", candidate_id=r1["id"])
    assert r2["status"] == "reinforced" and r2["count"] == 2
    r3 = growth.record(lab.cfg, role="developer", kind="preference", text="코드 결과는 표로 요약한다", category="보고형식")
    assert r3["status"] == "due" and r3["count"] == 3
    assert "학습 후보 확인 요청" in growth.due_notice(lab.cfg)
    msg = growth.approve(lab.cfg, r1["id"])
    assert "반영" in msg
    assert "표로 요약" in system_for("statistician", lab.cfg)            # 확인 후 전원에게 주입
    assert growth.due(lab.cfg) == []


def test_rejected_candidate_stays_ignored(make_lab):
    lab, _ = make_lab({})
    r = growth.record(lab.cfg, role="corpus", kind="lesson", text="CSV 는 항상 cp949 로 읽는다", category="데이터")
    assert "반영하지 않습니다" in growth.reject(lab.cfg, r["id"])
    again = growth.record(lab.cfg, role="corpus", kind="lesson", text="CSV 는 항상 cp949 로 읽는다", category="데이터")
    assert again["status"] == "ignored"


def test_lesson_scoped_to_role_and_forget(make_lab):
    lab, _ = make_lab({})
    out = growth.record(lab.cfg, role="corpus", kind="lesson", text="연구자 CSV 는 탭 구분이 많다",
                        category="데이터", stated=True)
    assert "탭 구분" in system_for("corpus", lab.cfg)
    assert "탭 구분" not in system_for("linguist", lab.cfg)             # 요령은 그 역할에만
    assert "지웠습니다" in growth.forget(lab.cfg, out["id"])
    assert "탭 구분" not in system_for("corpus", lab.cfg)
    events = (lab.cfg.learning_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(e)["type"] for e in events][-1] == "forget"     # 원자료는 남는다


# ---------------- 의뢰 작업 폴더·상한 ----------------

def test_box_paths_and_caps(make_lab, tmp_path):
    ref = tmp_path / "기획서"
    (ref / "docs").mkdir(parents=True)
    (ref / "docs" / "erd.dbml").write_text("Table users { id int [pk] }", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("x", encoding="utf-8")
    lab, _ = make_lab({}, adhoc_read_dirs=(ref.resolve(),), adhoc_timeout_min=1)
    box = AdhocBox(lab.cfg, "developer", lab.sandbox)
    assert box.dir.parent.name == "developer" or box.dir.name == "developer"
    assert box.execute("write_file", {"path": "out/a.txt", "content": "hi"}).text.startswith("저장함")
    with pytest.raises(PermissionError):
        box.execute("read_file", {"path": "../../../ledger.db"})        # 작업 폴더 밖 금지
    # 열람 허용 폴더만
    tree = box.execute("list_ref", {"path": str(ref)}).text
    assert "erd.dbml" in tree
    assert "Table users" in box.execute("read_ref", {"path": "docs/erd.dbml"}).text
    with pytest.raises(PermissionError):
        box.execute("read_ref", {"path": str(tmp_path / "secret.txt")})
    assert "inputs/erd.dbml" in box.execute("copy_ref", {"path": "docs/erd.dbml"}).text
    # 실행: 샌드박스 전용(네트워크·호스트 불가), 횟수 상한
    calls = []
    real = lab.sandbox.run

    def spy(exp_id, d, cmd, *, timeout_s, network, host=False):
        calls.append((exp_id, timeout_s, network, host))
        return real(exp_id, d, cmd, timeout_s=timeout_s, network=network, host=host)
    lab.sandbox.run = spy
    out = box.execute("run_command", {"command": "cat inputs/erd.dbml", "timeout_min": 99})
    assert "Table users" in out.text and not out.is_error
    assert calls[0] == ("adhoc-developer", 60, False, False)          # 99분 요청 → 상한 1분, 네트워크·호스트 없음
    for _ in range(MAX_RUNS - 1):
        box.execute("run_command", {"command": "true"})
    over = box.execute("run_command", {"command": "true"})
    assert over.is_error and "실험으로" in over.text
    assert box.execute("attach_file", {"path": "out/a.txt"}).text.startswith("첨부 예약")
    assert box.attachments[0].name == "a.txt"


def test_no_ref_dirs_by_default(make_lab):
    lab, _ = make_lab({}, adhoc_read_dirs=())
    box = AdhocBox(lab.cfg, "corpus", lab.sandbox)
    assert "없음" in box.execute("list_ref", {}).text
    with pytest.raises(PermissionError):
        box.execute("read_ref", {"path": "/etc/hosts"})


# ---------------- 팀원 봇 의뢰 모드 전체 흐름 ----------------

def test_member_adhoc_frequency_task_learns(make_lab):
    lab, _ = make_lab({"corpus": [
        [T("write_file", path="inputs/words.csv", content="word\n사과\n배\n사과\n")],
        [T("write_file", path="freq.py", content=(
            "import csv,collections\n"
            "c=collections.Counter(r['word'] for r in csv.DictReader(open('inputs/words.csv',encoding='utf-8')))\n"
            "open('freq.csv','w',encoding='utf-8').write('word,count\\n'+''.join(f'{w},{n}\\n' for w,n in c.most_common()))\n"
            "print(c.most_common())\n"))],
        [T("run_command", command="python3 freq.py")],
        [T("attach_file", path="freq.csv"),
         T("record_learning", kind="preference", text="빈도표에는 상대빈도를 함께 낸다", category="보고형식",
           stated=True, evidence="앞으로 상대빈도도 같이")],
        [("text", "사과 2회, 배 1회입니다. freq.csv 첨부합니다.\n📌 기억함: 빈도표에 상대빈도 포함")]]})
    bot = MemberBot(lab.cfg, lab, "corpus", Registry())
    box = AdhocBox(lab.cfg, "corpus", lab.sandbox, read_tool=bot._read_tool)
    out = bot.reply([{"role": "user", "content": "이 CSV에서 어휘 빈도 뽑아줘. 앞으로 상대빈도도 같이 넣어줘"}],
                    None, None, box)
    assert "사과 2회" in out
    assert (box.dir / "freq.csv").read_text(encoding="utf-8").startswith("word,count\n사과,2")
    assert [p.name for p in box.attachments] == ["freq.csv"]
    assert box.learned[0]["status"] == "stated"
    box.finish_log("이 CSV에서 어휘 빈도 뽑아줘", True)
    ev = [json.loads(x) for x in (lab.cfg.learning_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert ev[-1]["type"] == "adhoc_task" and ev[-1]["runs"] == 1 and ev[-1]["attachments"] == ["freq.csv"]
    assert lab.ledger.list(None, limit=10) == []                      # 실험 기록에는 안 들어감
    sp = bot.system_prompt(None, adhoc_mode=True)
    assert "#의뢰" in sp and "record_learning" in sp and "상대빈도" in sp


def test_member_adhoc_tools_exclude_pipeline_and_approval(make_lab):
    lab, _ = make_lab({"developer": [
        [T("submit_memo", memo_markdown="x", summary="x", key_concerns=[], recommendations=[]),
         T("finish_plan", plan_markdown="x", summary="x", needs_network=True, needs_host_accel=True,
           est_runtime_min=600, run_commands=["x"])],
        [("text", "그건 실험으로 올려 주세요.")]]})
    bot = MemberBot(lab.cfg, lab, "developer", Registry())
    box = AdhocBox(lab.cfg, "developer", lab.sandbox, read_tool=bot._read_tool)
    bot.reply([{"role": "user", "content": "모델 내려받아서 학습 돌려줘"}], None, None, box)
    assert lab.ledger.list(None, limit=10) == []                      # 실험 접수·계획 도구 없음


def test_main_pipeline_gets_learned_profile(make_lab, monkeypatch):
    from test_pipeline import script, submit
    lab, _ = make_lab(script())
    growth.record(lab.cfg, role="director", kind="preference", text="모든 보고에 효과크기와 95% CI 를 넣는다",
                  category="분석방법", stated=True)
    seen = []
    orig = lab.client.create

    def spy(**kw):
        seen.append(kw["system"])
        return orig(**kw)
    monkeypatch.setattr(lab.client, "create", spy)
    exp = submit(lab)
    lab.process_one()
    lab.approve(exp["id"])
    lab.process_one()
    assert seen and all("효과크기와 95% CI" in s for s in seen)       # 자문·계획·구현·보고·검증 전 단계


def test_director_triage_has_no_tools(make_lab):
    lab, _ = make_lab({"director": [[("text", "ROUTE: corpus\n어휘 빈도는 코퍼스 담당에게 넘깁니다.")]]})
    out = Director(lab).reply([{"role": "user", "content": "이 CSV 빈도 좀"}], extra_system="\n분류 모드", tools=[])
    assert parse_route(out) == ("corpus", "어휘 빈도는 코퍼스 담당에게 넘깁니다.")


def test_adhoc_experiment_is_moved_to_intake_thread_not_bounced(make_lab, monkeypatch):
    """#의뢰에 올린 일이 실험 수준이면 다시 올리라고 하지 않고, #실험진행 스레드를 만들어 그 자리에서 접수한다."""
    import asyncio
    from types import SimpleNamespace as NS
    from conftest import T
    from lab import bot as botmod

    lab, _ = make_lab({"director": [[T("submit_experiment", title="STT 후처리", request_markdown="## 질문\n...")],
                                    [("text", "#의뢰에서 옮겨 접수했습니다.")]]})
    (lab.cfg.lab_home / "policies").mkdir(parents=True, exist_ok=True)
    (lab.cfg.lab_home / "policies" / "INTAKE.json").write_text(
        '{"classification":"public","external_backends":["claude"],"discord_publish":true}', encoding="utf-8")
    sent, replies = [], []

    class Typing:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

    class Thread:
        id, mention = 777, "<#777>"
        def typing(self): return Typing()
        async def send(self, text, **kw): sent.append(text)

    class Head:
        async def create_thread(self, **kw): return Thread()

    class Intake:
        id, name = 55, lab.cfg.intake_channel
        async def send(self, text, **kw):
            sent.append(text)
            return Head()

    guild = NS(id=1, text_channels=[Intake()])

    async def reply(text, **kw): replies.append(text)

    async def no_files(message, extra=None): return ""

    message = NS(guild=NS(id=1), content="한국어 STT 후처리 모델 학습 실험 돌려줘", jump_url="https://discord/x",
                 author=NS(id=42), attachments=[], reply=reply)
    me = NS(cfg=lab.cfg, guilds=[guild], director=Director(lab), _locks={}, _save_attachments=no_files)
    ok = asyncio.run(botmod.LabBot._promote_to_experiment(me, message, message.content))
    assert ok
    exps = [e for st in ("queued", "consulting", "planning", "awaiting_approval") for e in lab.ledger.list(st, limit=5)] \
        or lab.ledger.list(None, limit=5)
    assert len(exps) == 1 and exps[0]["thread_id"] == 777          # 실험이 그 스레드에 묶여 접수됨
    assert replies and "다시 올리실 필요 없습니다" in replies[0] and "<#777>" in replies[0]
    assert any("연구자 요청 원문" in s for s in sent) and sent[-1] == "#의뢰에서 옮겨 접수했습니다."
    assert not any("올려 주세요" in s for s in sent + replies)


def test_promote_returns_false_without_intake_channel(make_lab):
    import asyncio
    from types import SimpleNamespace as NS
    from lab import bot as botmod
    lab, _ = make_lab({})
    me = NS(cfg=lab.cfg, guilds=[NS(id=1, text_channels=[])], director=None, _locks={})
    assert asyncio.run(botmod.LabBot._promote_to_experiment(me, NS(guild=NS(id=1), content="x"), "x")) is False


def test_recent_context_carries_conversation_and_earlier_attachment():
    """후속 글("위에 첨부 있잖아")만 보면 분류가 안 된다. 최근 대화와 앞선 글의 첨부를 같이 넘긴다."""
    import asyncio
    import datetime as dt
    from types import SimpleNamespace as NS
    from lab import bot as botmod

    now = dt.datetime.now(dt.timezone.utc)
    pdf = NS(filename="plan.pdf", size=10)
    owner, director = NS(id=42, display_name="연주"), NS(id=7, display_name="Lab Director")
    old = NS(id=1, author=owner, clean_content="어제 일", attachments=[NS(filename="old.csv", size=1)],
             created_at=now - dt.timedelta(hours=9))
    m1 = NS(id=2, author=owner, clean_content="내용 검토해봐", attachments=[pdf], created_at=now)
    m2 = NS(id=3, author=director, clean_content="어떤 관점의 검토인지 알려 주세요", attachments=[], created_at=now)
    m3 = NS(id=4, author=owner, clean_content="가설과 사실관계 구조가 맞는지 검증해", attachments=[], created_at=now)

    class Ch:
        def history(self, limit, before):
            async def gen():
                for m in [m3, m2, m1, old]:          # 디스코드는 최신 글부터 준다
                    yield m
            return gen()

    me = NS(get_channel=lambda cid: Ch(), _is_owner=lambda uid: uid == 42)
    ctx, carried = asyncio.run(botmod.LabBot._recent_context(me, 100, 5, reply_to_id=3))
    assert "[연구자] 내용 검토해봐 [첨부: plan.pdf]" in ctx and "[Lab Director]" in ctx and "가설과 사실관계" in ctx
    assert "어제 일" not in ctx                       # 오래된 글은 다른 일로 본다
    assert carried == [pdf]                          # 답글 대상(연구실장 글)에 첨부가 없으면 연구자의 최근 첨부를 이어받는다
    assert "내용이 보이지 않는다" in botmod.TRIAGE and "최근 대화" in botmod.TRIAGE


def test_pdf_to_text_never_raises(tmp_path):
    from lab.team import pdf_to_text
    bad = tmp_path / "x.pdf"
    bad.write_bytes(b"not a pdf")
    assert pdf_to_text(bad) is None


def test_merge_keeps_directors_own_opening_messages():
    """스레드가 연구실장의 요청서 초안으로 시작해도, 연구자의 "접수" 때 그 초안이 모델에 그대로 보여야 한다."""
    from lab.director import _merge
    out = _merge([{"role": "assistant", "content": "연구자 요청 원문: 조사 이형태 실험"},
                  {"role": "assistant", "content": "요청서 초안 ... 접수해도 될까요?"},
                  {"role": "user", "content": "접수"}])
    assert out[0]["role"] == "user" and out[-1] == {"role": "user", "content": "접수"}
    assert "조사 이형태 실험" in out[1]["content"] and "요청서 초안" in out[1]["content"]
    assert [m["role"] for m in out] == ["user", "assistant", "user"]


def test_thread_history_includes_starter_message():
    import asyncio
    from types import SimpleNamespace as NS
    import discord
    from lab import bot as botmod

    me_user = NS(id=7)
    starter = NS(id=900, author=NS(id=42), clean_content="BLiMP 실험 돌려줘")
    draft = NS(id=901, author=me_user, clean_content="요청서 초안 … 접수해도 될까요?")
    ok = NS(id=902, author=NS(id=42), clean_content="접수")

    class FakeThread(discord.Thread):
        id = 900
        starter_message = starter
        def __init__(self): pass
        def history(self, limit, oldest_first): return _agen([ok, draft])
    th = FakeThread()
    msg = NS(channel=NS(id=900))
    out = asyncio.run(botmod.LabBot._history(NS(user=me_user), th, msg))
    assert [m["role"] for m in out] == ["user", "assistant", "user"] and out[0]["content"] == "BLiMP 실험 돌려줘"


def _agen(items):
    async def gen():
        for i in items:
            yield i
    return gen()
