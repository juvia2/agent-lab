"""협업 버스: 동료 호출(ask_agent)·한도, 멘션 없는 수임(claim·pass_to_member), 관제 화면 (디스코드 접속 없이)."""
import json
import threading
import urllib.request

from conftest import T
from lab import bus, console
from lab.adhoc import AdhocBox
from lab.director import Director
from lab.team import MemberBot, Registry


def kinds(lab):
    return [(e["type"], e.get("src"), e.get("dst")) for e in bus.tail(lab.cfg)]


# ---------------- 수임 분류 파싱 ----------------

def test_parse_claims():
    claims, route, note = bus.parse_claims("CLAIM: corpus | 빈도표를 만든다\nCLAIM：Statistician ｜ 조건 간 검정\n둘이 나눠 맡습니다.")
    assert route == "claim" and claims == [("corpus", "빈도표를 만든다"), ("statistician", "조건 간 검정")]
    assert note == "둘이 나눠 맡습니다."
    assert bus.parse_claims("ROUTE: corpus\n넘깁니다")[0] == [("corpus", "")]            # 예전 형식
    assert bus.parse_claims("ROUTE: experiment\n실험으로 올려 주세요")[1] == "experiment"
    assert bus.parse_claims("글쎄요")[1] == "ask"
    assert bus.parse_claims("CLAIM: director | 내가\nCLAIM: nobody | x")[1] == "ask"       # 연구실장·없는 역할은 못 가져감
    many = "\n".join(f"CLAIM: {r} | x" for r in ("corpus", "corpus", "lm", "tester", "developer"))
    assert [r for r, _ in bus.parse_claims(many)[0]] == ["corpus", "lm", "tester"]        # 중복 제거, 최대 3명


# ---------------- 동료 호출 ----------------

def test_member_asks_colleague_and_it_is_logged(make_lab):
    lab, _ = make_lab({
        "statistician": [[T("ask_agent", role="corpus", question="조건당 40문항을 빈도 매칭해서 확보할 수 있나?")],
                         [("text", "코퍼스 담당 확인 결과 40문항 확보가 가능해 검정력 0.8을 맞출 수 있습니다.")]],
        "corpus": [[("text", "가능합니다. 후보 어휘가 120개 있습니다.")]]})
    bot = MemberBot(lab.cfg, lab, "statistician", Registry())
    seen = []
    trace = bus.Trace(lab.cfg, channel="의뢰", on_event=seen.append)
    out = bot.reply([{"role": "user", "content": "문항 수 충분한지 봐줘"}], trace=trace)
    assert "40문항" in out
    assert lab.client.calls == ["statistician", "corpus", "statistician"]
    assert kinds(lab) == [("call", "statistician", "corpus"), ("answer", "corpus", "statistician")]
    assert [e["type"] for e in seen] == ["call", "answer"] and all(e["root"] == trace.root for e in seen)
    sp = bot.system_prompt(None)
    assert "ask_agent" in sp


def test_call_limits_self_cycle_depth_and_count(make_lab):
    lab, _ = make_lab({
        # linguist → 자기 자신(거절) → cogsci 호출. cogsci 는 linguist 를 되부르려다 거절, lm 을 부른다. lm 은 더 못 부른다.
        "linguist": [[T("ask_agent", role="linguist", question="나?")],
                     [T("ask_agent", role="cogsci", question="연결가설은?")],
                     [("text", "정리했습니다.")]],
        "cogsci": [[T("ask_agent", role="linguist", question="되묻기")],
                   [T("ask_agent", role="lm", question="surprisal 계산 가능?")],
                   [("text", "가능하다고 합니다.")]],
        "lm": [[T("ask_agent", role="tester", question="한 단계 더")],
               [("text", "가능합니다.")]]})
    bot = MemberBot(lab.cfg, lab, "linguist", Registry())
    trace = bus.Trace(lab.cfg)
    bot.reply([{"role": "user", "content": "설계 봐줘"}], trace=trace)
    ks = kinds(lab)
    assert ("refused", "linguist", "linguist") in ks                    # 자기 자신
    assert ("refused", "cogsci", "linguist") in ks                      # 되부르기(순환)
    assert ("call", "cogsci", "lm") in ks and ("answer", "lm", "cogsci") in ks
    assert not any(k == "call" and s == "lm" for k, s, _ in ks)         # 깊이 상한: lm 에게는 호출 도구가 없다
    assert "tester" not in lab.client.calls
    assert trace.calls == 2

    # 요청 1건당 호출 횟수 상한
    t2 = bus.Trace(lab.cfg)
    t2.calls = bus.MAX_CALLS
    out = bus.ask(t2, ("linguist",), "corpus", "하나 더", lambda r, q, c: "x")
    assert out.is_error and "상한" in out.text
    assert bus.ask(t2, ("linguist",), "director", "실장님", lambda r, q, c: "x").is_error   # 연구실장은 호출 대상이 아님


def test_colleague_has_only_read_tools(make_lab):
    lab, _ = make_lab({
        "developer": [[T("ask_agent", role="tester", question="이 수치 맞나?")], [("text", "확인 받았습니다.")]],
        "tester": [[T("submit_experiment", title="x", request_markdown="x"), T("run_command", command="rm -rf /")],
                   [("text", "읽기만 가능해 파일로 확인했습니다.")]]})
    bot = MemberBot(lab.cfg, lab, "developer", Registry())
    bot.reply([{"role": "user", "content": "검증 받아줘"}])
    assert lab.ledger.list(None, limit=5) == []                          # 불린 동료는 접수·실행을 못 한다


# ---------------- 멘션 없이 가져가기 ----------------

def test_director_passes_to_member_without_mention(make_lab):
    lab, _ = make_lab({"director": [
        [T("pass_to_member", role="statistician", question="EXP-001 의 LMM 무선효과 구조가 적절한가? 연구자 질문: '이 모형 괜찮아?'"),
         T("pass_to_member", role="linguist", question="접속 안 한 팀원"),
         T("pass_to_member", role="statistician", question="중복")],
        [("text", "통계 담당에게 넘겼습니다.")]]})
    handoffs = []
    seen = []
    orig = lab.client.create

    def spy(**kw):
        seen.append(kw)
        return orig(**kw)
    lab.client.create = spy
    out = Director(lab).reply([{"role": "user", "content": "이 모형 괜찮아?"}], handoffs=handoffs,
                              handoff_roles={"statistician", "corpus"})
    assert out == "통계 담당에게 넘겼습니다."
    assert handoffs == [("statistician", "EXP-001 의 LMM 무선효과 구조가 적절한가? 연구자 질문: '이 모형 괜찮아?'")]
    assert "pass_to_member" in {t["name"] for t in seen[0]["tools"]} and "팀원이 일을 가져가게" in seen[0]["system"]
    assert "approve" not in " ".join(t["name"] for t in seen[0]["tools"])       # 승인 도구는 여전히 없다


def test_no_pass_tool_when_nobody_connected_or_triage(make_lab):
    lab, _ = make_lab({"director": [[("text", "네")], [("text", "CLAIM: corpus | 빈도표")]]})
    seen = []
    orig = lab.client.create

    def spy(**kw):
        seen.append(kw)
        return orig(**kw)
    lab.client.create = spy
    d = Director(lab)
    d.reply([{"role": "user", "content": "안녕"}], handoffs=[], handoff_roles=set())
    assert "pass_to_member" not in {t["name"] for t in seen[0]["tools"]}
    d.reply([{"role": "user", "content": "빈도 좀"}], tools=[], handoffs=[], handoff_roles={"corpus"})
    assert not seen[1].get("tools")                                       # 분류는 도구 없이


# ---------------- 의뢰: 작업 세션 기록, 동료 작업 폴더 ----------------

def test_adhoc_session_logged_and_peer_files_readonly(make_lab):
    lab, _ = make_lab({"statistician": [
        [T("read_peer_file", role="corpus"), T("read_peer_file", role="corpus", path="freq.csv"),
         T("read_peer_file", role="corpus", path="../../../ledger.db"), T("run_command", command="echo hi")],
        [("text", "빈도표를 이어받아 계산했습니다.")]]})
    AdhocBox(lab.cfg, "corpus", lab.sandbox).t_write_file("freq.csv", "word,freq\n사과,12\n")
    bot = MemberBot(lab.cfg, lab, "statistician", Registry())
    box = AdhocBox(lab.cfg, "statistician", lab.sandbox, read_tool=bot._read_tool)
    res = []
    orig = box.execute
    box.execute = lambda n, a: (res.append((n, orig(n, a))) or res[-1][1])
    bot.reply([{"role": "user", "content": "이어서 계산"}], None, None, box)
    outs = [o for n, o in res if n == "read_peer_file"]
    assert "freq.csv" in outs[0].text and "사과,12" in outs[1].text
    assert ("session", "statistician", None) in kinds(lab)
    assert not (box.dir.parent / "corpus" / "x").exists()
    import pytest
    with pytest.raises(PermissionError):
        box.t_read_peer_file("corpus", "../../../ledger.db")
    assert box.t_read_peer_file("statistician").is_error and box.t_read_peer_file("../x").is_error


# ---------------- 실험 단계도 버스에, 관제 화면 ----------------

def test_pipeline_stages_on_bus_and_console(make_lab):
    from test_pipeline import script, submit
    lab, _ = make_lab(script())
    exp = submit(lab)
    lab.process_one()
    stages = [e for e in bus.tail(lab.cfg) if e["type"] == "stage"]
    assert stages and all(e["exp"] == exp["id"] for e in stages)
    assert {e["src"] for e in stages} & {"linguist", "statistician", "practitioner"}

    st = console.state(lab.cfg)
    assert st["experiments"][0]["id"] == exp["id"] and len(st["roles"]) == 10
    assert all(r["avatar"].startswith("<svg") for r in st["roles"])
    srv = console.serve(lab.cfg, 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        host, port = srv.server_address
        assert host == "127.0.0.1"                                        # 로컬 전용
        page = urllib.request.urlopen(f"http://127.0.0.1:{port}/").read().decode()
        assert "연구실 관제" in page
        data = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/state?after=0").read())
        assert any(e["type"] == "stage" for e in data["events"])
        newer = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/state?after={stages[-1]['ts'] + 1}").read())
        assert newer["events"] == []
        try:
            urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{port}/api/state", data=b"{}", method="POST"))
            assert False, "쓰기 요청이 받아들여짐"
        except urllib.error.HTTPError as e:
            assert e.code in (405, 501)                                   # 읽기 전용: 명령을 받는 주소가 없다
    finally:
        srv.shutdown()


def test_every_agent_has_avatar_in_both_forms():
    import xml.etree.ElementTree as ET
    from lab import avatars
    from lab.agents import DISPLAY_EN
    for r in DISPLAY_EN:
        for theme in (None, "dark", "light"):
            ET.fromstring(avatars.svg(r, theme))                          # 올바른 SVG
        assert '"B"' not in avatars.svg(r) and "class=\"d\"" in avatars.svg(r)
        assert "hsl(" in avatars.svg(r, "dark") and 'class=' not in avatars.svg(r, "dark")
    assert avatars.svg("nobody") == ""


def test_busy_roles_follow_claims_calls_and_stages():
    now = 10_000.0
    ev = lambda t, ago, **k: {"type": t, "ts": now - ago, **k}
    events = [
        ev("request", 30), ev("claim", 25, root="A", src="statistician"),
        ev("call", 20, root="A", src="statistician", dst="corpus"),                  # 답 기다리는 중
        ev("claim", 50, root="B", src="linguist"), ev("done", 40, root="B", src="linguist"),
        ev("claim", 300, root="C", src="tester"), ev("call", 290, root="C", src="tester", dst="lm"),
        ev("answer", 280, root="C", src="lm", dst="tester"),                        # 답 받음 → lm 은 쉼
        ev("stage", 60, src="practitioner"), ev("stage", 600, src="documenter"),    # 10분 전 단계는 끝난 것
        ev("claim", 7 * 3600, root="D", src="developer"),                           # 6시간 넘은 수임은 무시
    ]
    assert bus.busy_roles(events, now) == {"director", "statistician", "corpus", "tester", "practitioner"}
    assert bus.busy_roles([ev("request", 120)], now) == set()


# ---------------- 관제 화면: 도구 호출 단위 기록, 명령 목록·내린 명령 ----------------

def test_tool_calls_are_logged_per_agent(make_lab):
    lab, _ = make_lab({
        "statistician": [[T("lab_status"), T("ask_agent", role="corpus", question="파일 있나?")], [("text", "확인했습니다.")]],
        "corpus": [[T("search_notebook", query="빈도")], [("text", "없습니다.")]],
        "director": [[T("lab_status")], [("text", "현황입니다.")]]})
    MemberBot(lab.cfg, lab, "statistician", Registry()).reply([{"role": "user", "content": "봐줘"}])
    Director(lab).reply([{"role": "user", "content": "현황"}])
    tools = [(e["src"], e["text"]) for e in bus.tail(lab.cfg) if e["type"] == "tool"]
    assert tools == [("statistician", "lab_status()"), ("corpus", "search_notebook(query=빈도)"), ("director", "lab_status()")]
    now = bus.tail(lab.cfg)[-1]["ts"]
    assert "director" in bus.busy_roles(bus.tail(lab.cfg), now + 5)        # 도구를 막 쓴 역할은 일하는 중
    assert "director" not in bus.busy_roles(bus.tail(lab.cfg), now + 300)


def test_tool_summary_keeps_short_args_only():
    s = bus.tool_summary("write_file", {"path": "a/b.py", "content": "비밀 " * 500})
    assert s == "write_file(path=a/b.py)"                                  # 파일 내용은 기록하지 않는다
    assert len(bus.tool_summary("run_command", {"command": "x" * 1000})) < 120
    assert bus.tool_summary("lab_status", None) == "lab_status()"


def test_pipeline_tool_calls_on_bus(make_lab):
    from test_pipeline import script, submit
    lab, _ = make_lab(script())
    exp = submit(lab)
    lab.process_one()
    tools = [e for e in bus.tail(lab.cfg) if e["type"] == "tool"]
    assert tools and all(e["exp"] == exp["id"] and e["root"] == exp["id"] for e in tools)
    assert any(e["text"].startswith("submit_memo(") for e in tools)


def test_command_text_and_command_list_matches_bot():
    import re
    from pathlib import Path
    from lab.bot import command_text
    assert command_text({"name": "learn", "options": [{"name": "action", "value": "approve"},
                                                      {"name": "item_id", "value": "L-003"}]}) == "/learn action=approve item_id=L-003"
    assert command_text({"name": "help"}) == "/help" and command_text(None) == "/?"
    src = (Path(__file__).resolve().parent.parent / "lab" / "bot.py").read_text(encoding="utf-8")
    in_bot = set(re.findall(r'@tree\.command\(name="([a-z_]+)"', src))
    shown = {c.split()[0].lstrip("/") for c, _ in console.COMMANDS}
    assert in_bot == shown                                                 # 화면의 명령 목록이 실제 명령과 같다


def test_console_state_has_commands_and_page_panels(make_lab):
    lab, _ = make_lab({})
    bus.emit(lab.cfg, "command", root="CMD", text="/status exp_id=EXP-001")
    st = console.state(lab.cfg)
    assert st["commands"][0]["cmd"].startswith("/status") and st["events"][-1]["type"] == "command"
    for needle in ('id="now"', 'id="cmdlist"', 'id="issued"', "보기 전용"):
        assert needle in console.PAGE


def test_practitioner_asks_colleague_during_experiment(make_lab):
    lab, notifier = make_lab({
        "practitioner": [[T("ask_agent", role="statistician", question="시드 3개로 충분한가?")], [("text", "통계 담당 의견대로 시드 5개로 늘립니다.")]],
        "statistician": [[("text", "분산이 커서 5개 이상을 권합니다.")]],
        "developer": [[("text", "구현합니다.")]]})
    exp = lab.submit("시드 수", "시드 수 점검")
    out = lab._call(exp["id"], "practitioner", "실행 전 점검")
    assert "시드 5개" in out.text
    assert lab.client.calls == ["practitioner", "statistician", "practitioner"]
    assert [(t, s, d) for t, s, d in kinds(lab) if t != "stage"] == [
        ("claim", "practitioner", None), ("call", "practitioner", "statistician"),
        ("answer", "statistician", "practitioner"), ("done", "practitioner", None)]
    posted = [(r, txt) for r, (_, txt, _) in zip(notifier.roles, notifier.sent) if "→" in txt]
    assert posted[0][0] == "practitioner" and "@Statistician" in posted[0][1]      # 질문은 코디 이름으로
    assert posted[1][0] == "statistician" and "5개 이상" in posted[1][1]           # 답은 통계 담당 이름으로
    lab._call(exp["id"], "developer", "구현")                                      # 다른 팀원도 같은 구조(묻지 않으면 수임·완료만)
    assert [(e["type"], e.get("src")) for e in bus.tail(lab.cfg)][-2:] == [("claim", "developer"), ("done", "developer")]
