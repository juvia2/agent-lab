"""모델 백엔드·라우터 시험. 실제 claude/codex/gemini/Ollama 없이 가짜 CLI 스크립트와 가짜 HTTP 서버로 검증한다."""
import dataclasses
import json
import os
import stat
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import ScriptedClient
from lab.backends import (AnthropicAPIBackend, Backend, BackendError, BackendUnavailable, CLIBackend,
                          OpenAICompatBackend, Router, parse_reply, parse_route, render_transcript, tool_protocol)
from lab.config import Config
from lab.ledger import Ledger
from lab.llm import NoBackend, run_agent, ToolOutput
from lab.notify import ConsoleNotifier
from lab.pipeline import Lab
from test_pipeline import script, submit

TOOLS = [{"name": "write_file", "description": "파일 쓰기",
          "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}}}]


def routes_all(name):
    return {r: [(name, None)] for r in ("director", "linguist", "cogsci", "lm", "statistician", "corpus", "developer", "practitioner",
                                        "documenter", "tester", "default")}


# ------------------------------------------------------------ 규약 파싱
def test_parse_reply_handles_code_fences_inside_content():
    content = "# 보고서\n```python\nprint('x')\n```\n끝"
    text = "작업합니다.\n<tool_call>" + json.dumps({"name": "write_file", "input": {"path": "a.md", "content": content}},
                                                 ensure_ascii=False) + "</tool_call>"
    blocks = parse_reply(text)
    assert blocks[0] == {"type": "text", "text": "작업합니다."}
    assert blocks[1]["type"] == "tool_use" and blocks[1]["input"]["content"] == content


def test_parse_reply_tolerates_json_fence_and_flags_broken_json():
    ok = parse_reply('<tool_call>```json\n{"name": "x", "input": {"a": 1}}\n```</tool_call>')
    assert ok[0]["name"] == "x" and ok[0]["input"] == {"a": 1}
    bad = parse_reply('<tool_call>{"name": "x", "input": {"a": </tool_call>')
    assert bad[0]["name"] == "_parse_error"
    assert parse_reply("그냥 최종 답변")[0]["type"] == "text"


def test_parse_error_is_returned_to_model_not_crash():
    class C:
        messages = None

        def __init__(self):
            self.n = 0
            self.messages = self

        def create(self, **kw):
            self.n += 1
            txt = '<tool_call>{"name": "x", "input": {</tool_call>' if self.n == 1 else "완료"
            blocks = parse_reply(txt)
            content = [SimpleNamespace(type=b["type"], **({"text": b["text"]} if b["type"] == "text" else
                                                          {"id": b["id"], "name": b["name"], "input": b["input"]}))
                       for b in blocks]
            return SimpleNamespace(content=content, stop_reason="tool_use" if self.n == 1 else "end_turn",
                                   usage=SimpleNamespace(input_tokens=1, output_tokens=1))

    seen = []
    res = run_agent(C(), model="m", system="[ROLE:x]", prompt="go", tools=TOOLS,
                    execute=lambda n, a: seen.append(n) or ToolOutput("ok"))
    assert res.text == "완료" and seen == []                    # 깨진 호출은 실행되지 않고 오류가 모델에 돌아간다
    assert "형식" in json.dumps(res.messages, ensure_ascii=False)


def test_render_transcript_compacts_old_tool_results():
    big = "가" * 5000
    msgs = [{"role": "user", "content": "시작"}]
    for i in range(6):
        msgs.append({"role": "assistant", "content": [{"type": "tool_use", "id": f"t{i}", "name": "read_file",
                                                       "input": {"path": f"{i}"}}]})
        msgs.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": f"t{i}", "content": big}]})
    txt = render_transcript(msgs)
    assert "생략" in txt and len(txt) < len(big) * 6          # 오래된 결과는 줄어든다
    assert txt.count(big) >= 1                                 # 최근 결과는 그대로
    assert "[도구 결과: read_file]" in txt
    assert "write_file" in tool_protocol(TOOLS) and "내장 도구" in tool_protocol(TOOLS)


def test_parse_route():
    assert parse_route("claude/opus, codex ,local/qwen3:14b") == [("claude", "opus"), ("codex", None),
                                                                  ("local", "qwen3:14b")]


# ------------------------------------------------------------ 가짜 CLI
def fake_cli(tmp_path: Path, name: str, body: str) -> str:
    p = tmp_path / name
    p.write_text("#!/usr/bin/env python3\n" + body, encoding="utf-8")
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return str(p)


CLAUDE_FAKE = '''import sys, os, json
stdin = sys.stdin.read()
args = sys.argv[1:]
sysprompt = args[args.index("--system-prompt") + 1]
res = "OK " + ("KEY_LEAKED" if os.environ.get("ANTHROPIC_API_KEY") else "KEY_STRIPPED")
res += " tools=" + str("write_file" in sysprompt) + " tools_flag=" + repr(args[args.index("--tools") + 1])
res += " model=" + (args[args.index("--model") + 1] if "--model" in args else "-")
res += " stdin_has_user=" + str("[사용자]" in stdin)
print(json.dumps({"is_error": False, "result": res + '\\n<tool_call>{"name":"write_file","input":{"path":"a","content":"b"}}</tool_call>',
                  "usage": {"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 1000}}))
'''


def test_claude_cli_backend_strips_api_key_and_parses(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret")
    be = CLIBackend("claude", fake_cli(tmp_path, "claude", CLAUDE_FAKE), 30)
    r = be.complete(system="[ROLE:tester] 시스템", messages=[{"role": "user", "content": "안녕"}], tools=TOOLS,
                    model="opus", max_tokens=100)
    text = r.content[0].text
    assert "KEY_STRIPPED" in text and "tools=True" in text and "tools_flag=''" in text and "model=opus" in text
    assert "stdin_has_user=True" in text
    assert r.stop_reason == "tool_use" and r.content[1].name == "write_file"
    assert r.usage.input_tokens == 10 + 1000 // 10 and r.usage.output_tokens == 5
    keep = CLIBackend("claude", be.binary, 30, keep_api_keys=True)
    assert "KEY_LEAKED" in keep.complete(system="[ROLE:x]", messages=[{"role": "user", "content": "a"}], tools=[],
                                         model=None, max_tokens=10).content[0].text


def test_claude_cli_login_and_limit_errors_are_classified(tmp_path):
    def mk(msg):
        return CLIBackend("claude", fake_cli(tmp_path, "c" + str(abs(hash(msg))),
                                             f'import json,sys\nsys.stdin.read()\nprint(json.dumps({{"is_error": True, "result": {msg!r}}}))\n'), 30)
    with pytest.raises(BackendUnavailable) as e:
        mk("Not logged in · Please run /login").complete(system="[ROLE:x]", messages=[{"role": "user", "content": "a"}],
                                                         tools=[], model=None, max_tokens=5)
    assert e.value.cooldown >= 3600
    with pytest.raises(BackendUnavailable) as e:
        mk("5-hour usage limit reached").complete(system="[ROLE:x]", messages=[{"role": "user", "content": "a"}],
                                                  tools=[], model=None, max_tokens=5)
    assert e.value.cooldown == 1800
    with pytest.raises(BackendError):
        mk("something odd").complete(system="[ROLE:x]", messages=[{"role": "user", "content": "a"}], tools=[],
                                     model=None, max_tokens=5)


CODEX_FAKE = '''import sys, os
stdin = sys.stdin.read()
a = sys.argv[1:]
out = a[a.index("-o") + 1]
assert "--sandbox" in a and a[a.index("--sandbox") + 1] == "read-only"
assert a[-1] == "-"
open(out, "w").write("codex 응답 " + ("LEAK" if os.environ.get("OPENAI_API_KEY") else "CLEAN") + " sys=" + str("[ROLE:developer]" in stdin))
print('{"type":"turn.completed","usage":{"input_tokens":50,"output_tokens":7}}')
'''

GEMINI_FAKE = '''import sys, os, json
stdin = sys.stdin.read()
a = sys.argv[1:]
assert "plan" in a
print(json.dumps({"response": "gemini 응답 " + ("LEAK" if os.environ.get("GEMINI_API_KEY") else "CLEAN") + " sys=" + str("[ROLE:practitioner]" in stdin),
                  "stats": {"models": {"m": {"tokens": {"prompt": 40, "candidates": 9}}}}}))
'''


def test_codex_and_gemini_backends(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setenv("GEMINI_API_KEY", "y")
    cx = CLIBackend("codex", fake_cli(tmp_path, "codex", CODEX_FAKE), 30)
    r = cx.complete(system="[ROLE:developer] s", messages=[{"role": "user", "content": "a"}], tools=TOOLS, model=None,
                    max_tokens=10)
    assert "CLEAN" in r.content[0].text and "sys=True" in r.content[0].text and r.usage.input_tokens == 50
    gm = CLIBackend("gemini", fake_cli(tmp_path, "gemini", GEMINI_FAKE), 30)
    r = gm.complete(system="[ROLE:practitioner] s", messages=[{"role": "user", "content": "a"}], tools=TOOLS,
                    model=None, max_tokens=10)
    assert "CLEAN" in r.content[0].text and "sys=True" in r.content[0].text and r.usage.output_tokens == 9


def test_missing_cli_reports_unavailable(tmp_path):
    be = CLIBackend("codex", str(tmp_path / "nope"), 5)
    assert be.available()[0] is False


# ------------------------------------------------------------ 로컬(OpenAI 호환) 서버
class _H(BaseHTTPRequestHandler):
    seen: list = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _H.seen.append(body)
        n = len(_H.seen)
        if n == 1:
            msg = {"role": "assistant", "content": "<think>생각</think>쓰겠습니다",
                   "tool_calls": [{"id": "call_1", "type": "function",
                                   "function": {"name": "write_file", "arguments": json.dumps({"path": "a", "content": "b"})}}]}
        else:
            msg = {"role": "assistant", "content": "끝났습니다"}
        out = json.dumps({"choices": [{"message": msg, "finish_reason": "stop"}],
                          "usage": {"prompt_tokens": 11, "completion_tokens": 3}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


def test_local_backend_native_tool_calls_roundtrip():
    _H.seen = []
    srv = HTTPServer(("127.0.0.1", 0), _H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        be = OpenAICompatBackend(f"http://127.0.0.1:{srv.server_port}/v1", "qwen-test", timeout_s=10)
        router = Router(SimpleNamespace(routes={"practitioner": [("local", None)]}), {"local": be})
        wrote = []
        res = run_agent(router, model="x", system="[ROLE:practitioner] s", prompt="해줘", tools=TOOLS,
                        execute=lambda n, a: wrote.append((n, a)) or ToolOutput("ok"))
        assert wrote == [("write_file", {"path": "a", "content": "b"})]
        assert res.text == "끝났습니다"                              # <think> 는 제거된다
        first, second = _H.seen
        assert first["model"] == "qwen-test" and first["tools"][0]["function"]["name"] == "write_file"
        roles = [m["role"] for m in second["messages"]]
        assert roles == ["system", "user", "assistant", "tool"]
        assert second["messages"][2]["tool_calls"][0]["id"] == "call_1" and second["messages"][3]["tool_call_id"] == "call_1"
        assert router.stats["local"]["calls"] == 2
    finally:
        srv.shutdown()


def test_local_backend_down_is_unavailable():
    be = OpenAICompatBackend("http://127.0.0.1:9/v1", "m", timeout_s=2)
    with pytest.raises(BackendUnavailable):
        be.complete(system="s", messages=[{"role": "user", "content": "a"}], tools=[], model=None, max_tokens=5)
    assert OpenAICompatBackend("http://x", "", timeout_s=2).available()[0] is False


# ------------------------------------------------------------ 라우터
class Fake(Backend):
    def __init__(self, name, behavior):
        self.name, self.behavior, self.calls = name, behavior, 0

    def complete(self, **kw):
        self.calls += 1
        if isinstance(self.behavior, Exception):
            raise self.behavior
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=f"from {self.name}")], stop_reason="end_turn",
                               usage=SimpleNamespace(input_tokens=5, output_tokens=5), backend=self.name)


def mk_router(routes, **backs):
    return Router(SimpleNamespace(routes={"tester": routes}), backs)


def call(r, role="tester"):
    return r.create(system=f"[ROLE:{role}] x", messages=[{"role": "user", "content": "a"}], tools=[])


def test_router_falls_back_and_remembers_cooldown():
    a, b = Fake("claude", BackendUnavailable("한도", 1800)), Fake("codex", None)
    r = mk_router([("claude", None), ("codex", None)], claude=a, codex=b)
    assert call(r).content[0].text == "from codex"
    assert call(r).content[0].text == "from codex"
    assert a.calls == 1 and b.calls == 2                         # 두 번째부터는 쉬는 백엔드를 건드리지 않는다
    r.reset_cooldowns()
    call(r)
    assert a.calls == 2                                          # /resume 등으로 쿨다운을 풀면 다시 시도
    assert "codex: 3회" in r.usage_summary()


def test_router_transient_error_does_not_cool_immediately_but_after_three():
    a, b = Fake("claude", BackendError("타임아웃")), Fake("gemini", None)
    r = mk_router([("claude", None), ("gemini", None)], claude=a, gemini=b)
    for _ in range(3):
        call(r)
    assert a.calls == 3
    call(r)
    assert a.calls == 3                                          # 3연속 실패 후 잠시 쉰다


def test_router_all_down_raises_nobackend_with_reasons():
    r = mk_router([("claude", None), ("local", None)], claude=Fake("claude", BackendUnavailable("로그인 필요", 100)),
                  local=Fake("local", BackendUnavailable("서버 꺼짐", 100)))
    with pytest.raises(NoBackend) as e:
        call(r)
    assert "로그인 필요" in str(e.value) and "서버 꺼짐" in str(e.value) and "[tester]" in str(e.value)


def test_router_skips_missing_and_unknown_backends():
    class Missing(Fake):
        def available(self):
            return False, "미설치"
    r = mk_router([("zzz", None), ("claude", None), ("gemini", None)], claude=Missing("claude", None),
                  gemini=Fake("gemini", None))
    assert call(r).content[0].text == "from gemini"


def test_role_without_route_uses_default():
    r = Router(SimpleNamespace(routes={"default": [("gemini", None)]}), {"gemini": Fake("gemini", None)})
    assert call(r, "documenter").content[0].text == "from gemini"


# ------------------------------------------------------------ 파이프라인 통합
def make_routed_lab(tmp_path, scripted, routes, backends):
    cfg = dataclasses.replace(Config.from_env(), lab_home=tmp_path / "lab", sandbox_backend="host",
                              anthropic_api_key=None, routes=routes)
    cfg.ensure_dirs()
    router = Router(cfg, backends)
    return Lab(cfg, Ledger(cfg.ledger_path), router, ConsoleNotifier()), router


def test_pipeline_runs_through_router_with_mid_run_fallback(tmp_path):
    """claude 가 중간에 한도 소진으로 막혀도 다음 백엔드가 이어받아 실험이 끝난다."""
    scripted = ScriptedClient(script())

    class Flaky(Backend):
        name = "claude"

        def __init__(self, inner, fail_after):
            self.inner, self.n, self.fail_after = inner, 0, fail_after

        def complete(self, **kw):
            self.n += 1
            if self.n > self.fail_after:
                raise BackendUnavailable("usage limit reached", 3600)
            return self.inner.complete(**kw)

    api = AnthropicAPIBackend(scripted, "m")
    flaky = Flaky(AnthropicAPIBackend(scripted, "m"), fail_after=5)
    routes = {r: [("claude", None), ("api", None)] for r in
              ("director", "linguist", "cogsci", "lm", "statistician", "corpus", "developer", "practitioner", "documenter", "tester")}
    lab, router = make_routed_lab(tmp_path, scripted, routes, {"claude": flaky, "api": api})
    exp = submit(lab)
    lab.process_one()
    e = lab.ledger.get(exp["id"])
    assert e["status"] == "done", e["error"]
    assert router.stats["api"]["calls"] > 0 and router.stats["claude"]["calls"] == 5
    assert "claude:" in lab.status_text() or "api:" in lab.status_text()


def test_no_backend_pauses_experiment_and_resume_keeps_budget(tmp_path):
    dead = Fake("claude", BackendUnavailable("로그인 필요", 7200))
    routes = {r: [("claude", None)] for r in
              ("director", "linguist", "cogsci", "lm", "statistician", "corpus", "developer", "practitioner", "documenter", "tester", "default")}
    lab, router = make_routed_lab(tmp_path, None, routes, {"claude": dead})
    notifier_msgs = []
    lab.notifier.post = lambda exp, text, files=None: notifier_msgs.append(text)
    exp = submit(lab)
    lab.process_one()
    e = lab.ledger.get(exp["id"])
    assert e["status"] == "paused" and "로그인 필요" in e["error"]
    assert any("일시정지" in m and "/resume" in m for m in notifier_msgs)
    budget = e["token_budget"]
    assert "재개" in lab.resume(exp["id"])
    assert lab.ledger.get(exp["id"])["token_budget"] == budget       # 백엔드 문제로 멈춘 것은 예산을 늘리지 않는다
    assert router._cooling("claude") is None                          # 재개하면 쿨다운도 풀린다
