"""한 과제 = 한 스레드(연구실 전체 지침): 접수 경로와 무관하게 실험 글은 그 실험의 스레드로만 간다."""
import asyncio
import json
import threading
from types import SimpleNamespace as NS

import discord
import pytest

from lab import learning, watch
from lab.bot import DiscordNotifier
from lab.director import open_ops_requests
from test_pipeline import script, submit


class Channel:
    def __init__(self, id, name=""):
        self.id, self.name, self.sent, self.fail = id, name, [], False

    async def send(self, text, **kw):
        if self.fail:
            raise OSError("네트워크 끊김")
        self.sent.append((text, kw.get("view")))


class Intake(Channel):
    def __init__(self, id, name):
        super().__init__(id, name)
        self.threads, self.no_thread = [], False

    async def create_thread(self, **kw):
        await asyncio.sleep(0)
        if self.no_thread:
            raise discord.Forbidden(NS(status=403, reason="x"), "권한 없음")
        self.threads.append(Channel(900 + len(self.threads), kw["name"]))
        return self.threads[-1]


@pytest.fixture
def discord_lab(make_lab):
    lab, _ = make_lab(script())
    (lab.cfg.lab_home / "policies").mkdir(parents=True, exist_ok=True)
    for pid in ("EXP-001", "EXP-002"):
        (lab.cfg.lab_home / "policies" / f"{pid}.json").write_text(
            '{"classification":"public","external_backends":["claude"],"discord_publish":true}', encoding="utf-8")
    loop = asyncio.new_event_loop()
    t = threading.Thread(target=loop.run_forever, daemon=True)
    t.start()
    intake, test = Intake(1, lab.cfg.intake_channel), Channel(2, lab.cfg.test_channel)

    async def fetch(cid):
        for c in intake.threads:
            if c.id == cid:
                return c
        raise discord.NotFound(NS(status=404, reason="x"), "없음")

    n = DiscordNotifier(lab.cfg)
    n.bot = NS(lab=lab, loop=loop, is_ready=lambda: True, get_channel=lambda cid: None, fetch_channel=fetch,
               guilds=[NS(id=1, text_channels=[intake, test])])
    lab.notifier = n
    yield lab, n, intake, test
    loop.call_soon_threadsafe(loop.stop)
    t.join(5)
    loop.close()


def test_experiment_without_thread_gets_one_and_reuses_it(discord_lab):
    lab, n, intake, _ = discord_lab
    exp = submit(lab)
    n.post(exp, "첫 글")
    n.ask_approval(exp, ["계획 확정"], "요약")
    assert intake.sent == [] and len(intake.threads) == 1
    assert len(intake.threads[0].sent) == 2 and exp["id"] in intake.threads[0].name
    assert lab.ledger.get(exp["id"])["thread_id"] == intake.threads[0].id


def test_concurrent_posts_make_one_thread(discord_lab):
    lab, n, intake, _ = discord_lab
    exp = submit(lab)
    ts = [threading.Thread(target=n.post, args=(exp, f"글{i}")) for i in range(4)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(intake.threads) == 1 and len(intake.threads[0].sent) == 4


def test_deleted_thread_is_recreated(discord_lab):
    lab, n, intake, _ = discord_lab
    exp = submit(lab, thread_id=12345)
    n.post(exp, "글")
    assert len(intake.threads) == 1 and intake.sent == []
    assert lab.ledger.get(exp["id"])["thread_id"] == intake.threads[0].id


def test_post_is_held_not_dumped_in_channel_and_retried(discord_lab):
    lab, n, intake, _ = discord_lab
    exp = submit(lab)
    intake.no_thread = True
    n.post(exp, "글")
    lab.ledger.update(exp["id"], status="awaiting_approval")
    n.ask_approval(exp, ["계획 확정"], "요약")
    assert intake.sent == []
    assert n.flush_held() == 0
    intake.no_thread = False
    assert n.flush_held() == 2
    assert [bool(v) for _, v in intake.threads[0].sent] == [False, True]        # 승인 버튼도 되살아난다
    assert n.flush_held() == 0


def test_held_post_respects_policy_at_retry(discord_lab):
    lab, n, intake, _ = discord_lab
    exp = submit(lab)
    intake.no_thread = True
    n.post(exp, "글")
    intake.no_thread = False
    (lab.cfg.lab_home / "policies" / f"{exp['id']}.json").write_text(
        '{"classification":"restricted","external_backends":[],"discord_publish":false}', encoding="utf-8")
    n.flush_held()
    assert intake.sent == [] and intake.threads == []


def test_stale_held_approval_is_dropped(discord_lab):
    lab, n, intake, _ = discord_lab
    exp = submit(lab)
    intake.no_thread = True
    n.ask_approval(exp, ["계획 확정"], "요약")                                    # 상태가 승인 대기가 아님
    intake.no_thread = False
    n.flush_held()
    assert intake.threads == []


def test_digest_goes_to_each_experiments_thread(discord_lab):
    lab, n, intake, test = discord_lab
    a, b = submit(lab), submit(lab)
    n.digest(a, "A 진행")
    n.digest(b, "B 진행")
    assert watch.digest_flush(lab.cfg, n, force=True)
    assert len(intake.threads) == 2 and test.sent == [] and intake.sent == []
    one, two = intake.threads
    assert "A 진행" in one.sent[0][0] and "B 진행" not in one.sent[0][0] and "B 진행" in two.sent[0][0]


def test_failed_digest_is_kept(discord_lab):
    lab, n, _, test = discord_lab
    watch.digest_add(lab.cfg, None, "연구실 알림")
    test.fail = True
    assert watch.digest_flush(lab.cfg, n, force=True) is False
    d = lab.cfg.lab_home / "digest"
    assert "연구실 알림" in (d / "pending.jsonl").read_text(encoding="utf-8")
    assert not (d / "last_sent").exists() and not list(d.glob("sent-*"))
    test.fail = False
    assert watch.digest_flush(lab.cfg, n, force=True) and "연구실 알림" in test.sent[0][0]


def test_digest_row_added_while_sending_is_kept(tmp_path):
    cfg = NS(lab_home=tmp_path, digest_hour=21)
    watch.digest_add(cfg, None, "처음")
    n = NS(post=lambda exp, text: watch.digest_add(cfg, None, "보내는 중 도착"))
    watch.digest_flush(cfg, n, force=True)
    rows = [json.loads(x)["text"] for x in (tmp_path / "digest" / "pending.jsonl").read_text().splitlines()]
    assert rows == ["보내는 중 도착"]


def test_plan_approval_reaches_developer(make_lab):
    lab, _ = make_lab(script())
    exp = submit(lab)
    lab.process_one()
    lab.approve(exp["id"])
    note = (lab.cfg.experiments_dir / exp["id"] / "notes" / "approved_plan.md").read_text(encoding="utf-8")
    assert "승인" in note
    lab.process_one()
    first = next(p for r, p in lab.client.prompts if r == "developer")
    assert "연구자가 plan.md 를 승인" in first


def test_old_approval_without_record_is_not_claimed(make_lab):
    """이 기록이 생기기 전의 승인(EXP-002)은 제안값까지 승인한 것으로 간주하지 않는다."""
    lab, _ = make_lab(script())
    exp = submit(lab)
    lab.ledger.update(exp["id"], approved=1)
    assert "연구자가 plan.md 를 승인" not in lab._header(lab.ledger.get(exp["id"]), "build")


def test_open_ops_requests_lists_unfinished(tmp_path):
    assert open_ops_requests(NS(lab_home=tmp_path)) == []
    (tmp_path / "ops_requests.md").write_text("- [ ] 할 일\n- [x] 끝남\n", encoding="utf-8")
    assert open_ops_requests(NS(lab_home=tmp_path)) == ["할 일"]


def test_rules_reach_every_agent():
    from lab import agents
    assert "한 과제는 한 스레드" in agents._RULES_PATH.read_text(encoding="utf-8")


def test_learning_head_is_remembered_until_thread_opens(tmp_path):
    item = {"group": "g"}
    assert learning.head_for(item, tmp_path) is None
    learning.remember_head("g", 5, tmp_path)
    assert learning.head_for(item, tmp_path) == 5 and learning.thread_for(item, tmp_path) is None
    learning.remember_thread("g", 5, tmp_path)
    assert learning.thread_for(item, tmp_path) == 5


def test_learning_reports_wait_when_thread_cannot_open(monkeypatch, tmp_path):
    """묶음의 스레드를 못 열면 나머지는 채널에 흩지 않고 큐에 남긴다."""
    from lab.bot import LabBot
    items = [(tmp_path / f"{i}.json", {"role": "developer", "title": f"t{i}", "description": "d", "group": "g",
                                       "classification": "public", "publication_approved": True}) for i in range(3)]
    for p, _ in items:
        p.write_text("{}")
    threads, done = [], []
    monkeypatch.setattr(learning, "QUEUE", tmp_path / "q")
    monkeypatch.setattr(learning, "pending_items", lambda: [x for x in items if x[0] not in done])
    monkeypatch.setattr(learning, "mark_sent", done.append)

    class Perf(Channel):
        ok = False
        async def send(self, text=None, **kw):
            self.sent.append(kw["embed"].title)
            return NS(id=77)
        def get_partial_message(self, mid):
            async def create_thread(**kw):
                if not self.ok:
                    raise discord.Forbidden(NS(status=403, reason="x"), "권한 없음")
                threads.append(mid)
                return NS(id=mid)
            return NS(create_thread=create_thread)

    perf, th = Perf(3, "성능고도화"), Perf(77)

    async def fetch(cid): return th
    me = NS(cfg=NS(discord_guild_id=None, perf_channel="성능고도화"), guilds=[NS(id=1, text_channels=[perf])],
            notifier=NS(members={}), get_channel=lambda cid: None, fetch_channel=fetch)
    asyncio.run(LabBot.flush_learning_reports(me))
    assert perf.sent == ["t0"] and len(done) == 1
    perf.ok = True
    asyncio.run(LabBot.flush_learning_reports(me))
    assert perf.sent == ["t0"] and th.sent == ["t1", "t2"] and threads == [77]
