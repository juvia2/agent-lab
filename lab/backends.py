"""모델 호출 백엔드와 라우터.

연구실의 모든 모델 호출은 `Router.messages.create(...)` 를 지난다(Anthropic SDK 와 같은 모양이라 llm.run_agent 는 그대로 쓴다).
역할(system 프롬프트의 `[ROLE:xxx]`)마다 우선순위 목록이 있고, 앞선 백엔드가 막히면(한도 소진·로그인 풀림·꺼짐) 다음으로 넘어간다.

백엔드
  claude  : `claude -p`        (Claude 구독 로그인. 토큰 과금 없음, 플랜 한도 안에서 동작)
  codex   : `codex exec`       (ChatGPT/Codex 구독 로그인)
  gemini  : `gemini -p`        (Google 로그인)
  local   : OpenAI 호환 서버    (Ollama / LM Studio / mlx-lm.server …, 완전 무료)
  api     : Anthropic API      (토큰 과금. 기본 경로에는 넣지 않음)

CLI 3종은 각자 에이전트 루프를 갖고 있지만 여기서는 '한 턴짜리 모델'로만 쓴다. 내장 도구(셸·파일)는 끄거나 읽기전용으로 두고,
도구 호출은 `<tool_call>{...}</tool_call>` 텍스트 규약으로 주고받는다. 실제 도구는 연구실의 Toolbox 가 실행한다(권한·샌드박스 유지).
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from .llm import NoBackend

log = logging.getLogger("lab.backends")

ROLE_RE = re.compile(r"\[ROLE:(\w+)\]")
TOOL_RE = re.compile(r"<tool_call>(.*?)</tool_call>", re.DOTALL)
THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)

RATE_RE = re.compile(r"rate.?limit|usage limit|limit reached|quota|exhausted|too many requests|\b429\b|overloaded|"
                     r"resource_exhausted|try again later|capacity", re.I)
AUTH_RE = re.compile(r"not logged in|please log ?in|login required|/login|unauthori[sz]ed|\b401\b|authentication|"
                     r"invalid api key|credential|sign in|not authenticated|oauth", re.I)

# 구독 로그인으로만 동작하도록, CLI 를 부를 때 지우는 키(남아 있으면 CLI 가 API 과금 경로를 택할 수 있다)
STRIP_ENV = {
    "claude": ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"),
    "codex": ("OPENAI_API_KEY", "CODEX_API_KEY"),
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GENAI_USE_VERTEXAI"),
}


class BackendUnavailable(Exception):
    """이 백엔드는 한동안 쓸 수 없다(미설치·로그인 필요·한도 소진). cooldown 초 동안 건너뛴다."""

    def __init__(self, msg: str, cooldown: int = 1800):
        super().__init__(msg)
        self.cooldown = cooldown


class BackendError(Exception):
    """일시적 실패(타임아웃·형식 오류 등). 이번 호출만 다음 백엔드로 넘긴다."""


# ---------------------------------------------------------------- 공통 변환
def _shrink(obj: Any, n: int) -> Any:
    if isinstance(obj, str):
        return obj if len(obj) <= n else obj[:n] + f"…[{len(obj) - n}자 생략]"
    if isinstance(obj, dict):
        return {k: _shrink(v, n) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_shrink(v, n) for v in obj]
    return obj


def render_transcript(messages: list[dict], keep_recent: int = 8) -> str:
    """Anthropic 형식 대화를 CLI 에 줄 텍스트로. 오래된 도구 결과·입력은 줄여 토큰을 아낀다."""
    names: dict[str, str] = {}
    out: list[str] = []
    total = len(messages)
    for idx, m in enumerate(messages):
        old = idx < total - keep_recent and idx > 0
        content = m["content"]
        if m["role"] == "user":
            if isinstance(content, str):
                out.append("[사용자]\n" + content)
                continue
            for b in content:
                if b.get("type") == "tool_result":
                    txt = b.get("content", "")
                    if isinstance(txt, list):
                        txt = "".join(x.get("text", "") for x in txt)
                    if old and len(txt) > 800:
                        txt = txt[:500] + f"\n…[{len(txt) - 800}자 생략]…\n" + txt[-300:]
                    tag = "도구 오류" if b.get("is_error") else "도구 결과"
                    out.append(f"[{tag}: {names.get(b.get('tool_use_id'), '?')}]\n{txt}")
                elif b.get("type") == "text":
                    out.append("[사용자]\n" + b["text"])
        else:
            parts = []
            if isinstance(content, str):
                parts.append(content)
            else:
                for b in content:
                    if b["type"] == "text" and b["text"].strip():
                        parts.append(b["text"] if not old else _shrink(b["text"], 1500))
                    elif b["type"] == "tool_use":
                        names[b["id"]] = b["name"]
                        inp = _shrink(b["input"], 600) if old else b["input"]
                        parts.append("<tool_call>" + json.dumps({"name": b["name"], "input": inp}, ensure_ascii=False)
                                     + "</tool_call>")
            out.append("[당신의 이전 응답]\n" + "\n".join(parts))
    return "\n\n".join(out)


def tool_protocol(tools: list[dict]) -> str:
    if not tools:
        return "도구는 없다. 최종 답변을 일반 텍스트로 작성한다."
    cat = "\n".join(f"- {t['name']}: {t['description']}\n  입력 스키마: {json.dumps(t['input_schema'], ensure_ascii=False)}"
                    for t in tools)
    return (
        "## 도구 사용 규약 (반드시 지킨다)\n"
        "당신 환경의 내장 도구(셸, 파일 읽기/쓰기, 웹 등)는 **사용하지 않는다**. 아래 연구실 도구만 쓴다.\n"
        "도구를 부르려면 응답에 다음 형식을 그대로 쓴다(여러 개를 한 번에 써도 된다):\n"
        '<tool_call>{"name": "도구이름", "input": {"인자": "값"}}</tool_call>\n'
        "- 안쪽은 반드시 유효한 JSON 한 개다. 문자열 안의 줄바꿈·따옴표는 JSON 규칙대로 이스케이프한다.\n"
        "- 도구를 부른 응답은 거기서 끝낸다. 결과는 다음 턴에 [도구 결과]로 돌아온다. 결과를 지어내지 않는다.\n"
        "- 도구가 더 필요 없고 일을 마쳤으면 tool_call 없이 최종 답변을 쓴다(종료 도구가 있으면 그것을 호출한다).\n\n"
        "## 사용 가능한 도구\n" + cat)


def parse_reply(text: str) -> list[dict]:
    """모델 텍스트 → Anthropic 형식 content 블록."""
    blocks: list[dict] = []
    pos = 0
    for m in TOOL_RE.finditer(text):
        pre = text[pos:m.start()].strip()
        if pre:
            blocks.append({"type": "text", "text": pre})
        raw = m.group(1).strip()
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
        try:
            obj = json.loads(raw)
            blocks.append({"type": "tool_use", "id": "tu_" + uuid.uuid4().hex[:12],
                           "name": str(obj["name"]), "input": obj.get("input") or {}})
        except Exception as e:
            blocks.append({"type": "tool_use", "id": "tu_" + uuid.uuid4().hex[:12], "name": "_parse_error",
                           "input": {"error": f"tool_call JSON 파싱 실패: {e}", "raw_head": raw[:200]}})
        pos = m.end()
    tail = text[pos:].strip()
    if tail:
        blocks.append({"type": "text", "text": tail})
    return blocks


def _resp(blocks: list[dict], in_tok: int, out_tok: int, backend: str, stop: str | None = None):
    content = []
    for b in blocks:
        if b["type"] == "text":
            content.append(SimpleNamespace(type="text", text=b["text"]))
        else:
            content.append(SimpleNamespace(type="tool_use", id=b["id"], name=b["name"], input=b["input"]))
    has_tool = any(b["type"] == "tool_use" for b in blocks)
    return SimpleNamespace(content=content, stop_reason=stop or ("tool_use" if has_tool else "end_turn"),
                           usage=SimpleNamespace(input_tokens=in_tok, output_tokens=out_tok), backend=backend)


def _est(*texts: str) -> int:
    return sum(len(t) for t in texts) // 3 + 1


def _classify(blob: str, what: str) -> Exception:
    if AUTH_RE.search(blob):
        return BackendUnavailable(f"{what}: 로그인이 필요합니다 ({blob.strip()[:160]})", cooldown=6 * 3600)
    if RATE_RE.search(blob):
        return BackendUnavailable(f"{what}: 사용 한도/과부하 ({blob.strip()[:160]})", cooldown=1800)
    return BackendError(f"{what}: {blob.strip()[:300]}")


# ---------------------------------------------------------------- 백엔드
class Backend:
    name = "?"

    def available(self) -> tuple[bool, str]:
        return True, ""

    def complete(self, *, system: str, messages: list[dict], tools: list[dict], model: str | None,
                 max_tokens: int):
        raise NotImplementedError


class CLIBackend(Backend):
    """claude / codex / gemini 를 한 턴짜리 모델로 부른다(텍스트 도구 규약)."""

    def __init__(self, kind: str, binary: str, timeout_s: int, keep_api_keys: bool = False):
        assert kind in ("claude", "codex", "gemini")
        self.name, self.kind, self.binary, self.timeout = kind, kind, binary, timeout_s
        self.keep_api_keys = keep_api_keys

    def available(self) -> tuple[bool, str]:
        if shutil.which(self.binary) is None:
            return False, f"`{self.binary}` 명령을 찾을 수 없음(미설치)"
        return True, ""

    def _env(self) -> dict:
        env = dict(os.environ)
        if not self.keep_api_keys:
            for k in STRIP_ENV[self.kind]:
                env.pop(k, None)
        return env

    def complete(self, *, system, messages, tools, model, max_tokens):
        convo = render_transcript(messages)
        proto = tool_protocol(tools)
        tail = "\n\n---\n위 대화의 **다음 한 턴만** 응답하세요."
        with tempfile.TemporaryDirectory(prefix="lab-cli-") as cwd:
            if self.kind == "claude":
                cmd = [self.binary, "-p", "--output-format", "json", "--tools", "", "--no-session-persistence",
                       "--disable-slash-commands", "--setting-sources", "project",
                       "--system-prompt", system + "\n\n" + proto]
                if model:
                    cmd += ["--model", model]
                stdin = convo + tail
                out_file = None
            elif self.kind == "codex":
                out_file = str(Path(cwd) / "last.txt")
                cmd = [self.binary, "exec", "--skip-git-repo-check", "--ephemeral", "--sandbox", "read-only",
                       "--json", "-o", out_file, "-C", cwd]
                if model:
                    cmd += ["-m", model]
                cmd += ["-"]
                stdin = system + "\n\n" + proto + "\n\n# 대화\n" + convo + tail
            else:  # gemini
                out_file = None
                cmd = [self.binary, "--approval-mode", "plan", "-o", "json", "--skip-trust",
                       "-p", "아래 표준입력의 지시를 따라 다음 한 턴만 응답하세요."]
                if model:
                    cmd += ["-m", model]
                stdin = system + "\n\n" + proto + "\n\n# 대화\n" + convo + tail
            try:
                p = subprocess.run(cmd, input=stdin, capture_output=True, text=True, cwd=cwd, env=self._env(),
                                   timeout=self.timeout)
            except subprocess.TimeoutExpired:
                raise BackendError(f"{self.kind}: {self.timeout}초 안에 응답하지 않음")
            except FileNotFoundError:
                raise BackendUnavailable(f"{self.kind}: 명령을 찾을 수 없음", cooldown=3600)
            text, in_tok, out_tok = self._extract(p, out_file)
        if not text.strip():
            raise BackendError(f"{self.kind}: 빈 응답")
        if not in_tok and not out_tok:
            in_tok, out_tok = _est(system, proto, stdin), _est(text)
        return _resp(parse_reply(THINK_RE.sub("", text)), in_tok, out_tok, self.kind)

    def _extract(self, p: subprocess.CompletedProcess, out_file: str | None) -> tuple[str, int, int]:
        so, se = p.stdout or "", p.stderr or ""
        if self.kind == "claude":
            try:
                j = json.loads(so)
            except Exception:
                raise _classify(so + se, "claude")
            if j.get("is_error"):
                raise _classify(str(j.get("result", "")) + se, "claude")
            u = j.get("usage") or {}
            tin = (u.get("input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0) + \
                  (u.get("cache_read_input_tokens") or 0) // 10      # 캐시 읽기는 가볍게 센다
            return str(j.get("result", "")), tin, u.get("output_tokens") or 0
        if self.kind == "codex":
            txt = ""
            if out_file and Path(out_file).exists():
                txt = Path(out_file).read_text(encoding="utf-8", errors="replace")
            if p.returncode != 0 and not txt.strip():
                raise _classify(se + so, "codex")
            tin = tout = 0
            for ln in so.splitlines():                              # --json 이벤트에서 usage 를 최대한 찾는다
                try:
                    ev = json.loads(ln)
                except Exception:
                    continue
                u = (ev.get("usage") or (ev.get("msg") or {}).get("info", {}).get("total_token_usage")
                     or (ev.get("msg") or {}).get("usage"))
                if isinstance(u, dict):
                    tin = u.get("input_tokens", tin) or tin
                    tout = u.get("output_tokens", tout) or tout
            return txt, tin, tout
        # gemini
        if p.returncode != 0 and not so.strip():
            raise _classify(se, "gemini")
        try:
            j = json.loads(so)
            txt = str(j.get("response", ""))
            tin = tout = 0
            for mv in ((j.get("stats") or {}).get("models") or {}).values():
                tk = mv.get("tokens") or {}
                tin += tk.get("prompt", 0) or 0
                tout += tk.get("candidates", 0) or 0
            if j.get("error"):
                raise _classify(json.dumps(j["error"], ensure_ascii=False), "gemini")
            return txt, tin, tout
        except (json.JSONDecodeError, AttributeError):
            if p.returncode != 0:
                raise _classify(se + so, "gemini")
            return so, 0, 0


class OpenAICompatBackend(Backend):
    """Ollama / LM Studio / mlx-lm.server 같은 OpenAI 호환 로컬 서버. 도구 호출은 서버의 네이티브 function calling."""
    name = "local"

    def __init__(self, base_url: str, default_model: str, api_key: str = "", timeout_s: int = 1800):
        self.base, self.default_model, self.key, self.timeout = base_url.rstrip("/"), default_model, api_key, timeout_s

    def available(self) -> tuple[bool, str]:
        if not self.default_model:
            return False, "LOCAL_MODEL 이 설정되지 않음(.env)"
        return True, ""

    @staticmethod
    def _to_openai(system: str, messages: list[dict]) -> list[dict]:
        out: list[dict] = [{"role": "system", "content": system}]
        for m in messages:
            c = m["content"]
            if m["role"] == "user":
                if isinstance(c, str):
                    out.append({"role": "user", "content": c})
                    continue
                texts = []
                for b in c:
                    if b.get("type") == "tool_result":
                        t = b.get("content", "")
                        if isinstance(t, list):
                            t = "".join(x.get("text", "") for x in t)
                        out.append({"role": "tool", "tool_call_id": b["tool_use_id"],
                                    "content": ("[오류] " if b.get("is_error") else "") + t})
                    elif b.get("type") == "text":
                        texts.append(b["text"])
                if texts:
                    out.append({"role": "user", "content": "\n".join(texts)})
            else:
                if isinstance(c, str):
                    out.append({"role": "assistant", "content": c})
                    continue
                text = "".join(b["text"] for b in c if b["type"] == "text")
                calls = [{"id": b["id"], "type": "function",
                          "function": {"name": b["name"], "arguments": json.dumps(b["input"], ensure_ascii=False)}}
                         for b in c if b["type"] == "tool_use"]
                msg: dict = {"role": "assistant", "content": text}
                if calls:
                    msg["tool_calls"] = calls
                out.append(msg)
        return out

    def complete(self, *, system, messages, tools, model, max_tokens):
        body: dict = {"model": model or self.default_model, "messages": self._to_openai(system, messages),
                      "max_tokens": max_tokens, "stream": False}
        if tools:
            body["tools"] = [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                                               "parameters": t["input_schema"]}} for t in tools]
        req = urllib.request.Request(self.base + "/chat/completions", data=json.dumps(body).encode("utf-8"),
                                     headers={"Content-Type": "application/json",
                                              **({"Authorization": f"Bearer {self.key}"} if self.key else {})})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                j = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "replace")[:300]
            if e.code in (404, 400) and "model" in msg.lower():
                raise BackendUnavailable(f"local: 모델 `{body['model']}` 없음 — `ollama pull {body['model']}` ({msg[:100]})", 600)
            raise BackendError(f"local: HTTP {e.code} {msg}")
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
            raise BackendUnavailable(f"local: 서버에 연결할 수 없음({self.base}): {e}", cooldown=300)
        try:
            ch = j["choices"][0]
            msg = ch["message"]
        except Exception:
            raise BackendError("local: 응답 형식 오류: " + json.dumps(j, ensure_ascii=False)[:200])
        blocks: list[dict] = []
        text = THINK_RE.sub("", msg.get("content") or "").strip()
        if text:
            blocks.append({"type": "text", "text": text})
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function", {})
            args = fn.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args or "{}")
                except Exception:
                    args = {"_raw": args[:300]}
            blocks.append({"type": "tool_use", "id": tc.get("id") or "tu_" + uuid.uuid4().hex[:12],
                           "name": fn.get("name", "?"), "input": args})
        if not blocks:
            raise BackendError("local: 빈 응답")
        u = j.get("usage") or {}
        stop = "max_tokens" if ch.get("finish_reason") == "length" and not msg.get("tool_calls") else None
        return _resp(blocks, u.get("prompt_tokens") or _est(system), u.get("completion_tokens") or _est(text),
                     "local", stop)


class AnthropicAPIBackend(Backend):
    """토큰 과금 경로. ROUTE_* 에 `api` 를 직접 적었을 때만 쓰인다."""
    name = "api"

    def __init__(self, client, default_model: str):
        self.client, self.default_model = client, default_model

    def available(self) -> tuple[bool, str]:
        return (True, "") if self.client is not None else (False, "ANTHROPIC_API_KEY 없음")

    def complete(self, *, system, messages, tools, model, max_tokens):
        kw: dict = dict(model=model or self.default_model, max_tokens=max_tokens, system=system, messages=messages)
        if tools:
            kw["tools"] = tools
        try:
            r = self.client.messages.create(**kw)
        except Exception as e:
            raise _classify(f"{type(e).__name__}: {e}", "api")
        r.backend = "api"
        return r


# ---------------------------------------------------------------- 라우터
class Router:
    """역할별 우선순위대로 백엔드를 시도한다. `.messages.create` 가 Anthropic 클라이언트와 같은 모양이다."""

    def __init__(self, cfg, backends: dict[str, Backend] | None = None):
        self.cfg = cfg
        self.backends = backends if backends is not None else build_backends(cfg)
        self.messages = self
        self._lock = threading.Lock()
        self._cool: dict[str, tuple[float, str]] = {}
        self._fails: dict[str, int] = {}
        self.stats: dict[str, dict] = {}

    # --- 상태 ---
    def _cooling(self, name: str) -> str | None:
        with self._lock:
            t = self._cool.get(name)
            if t and t[0] > time.time():
                return f"{int((t[0] - time.time()) / 60) + 1}분 쉬는 중 ({t[1][:80]})"
            return None

    def _set_cool(self, name: str, secs: int, why: str) -> None:
        with self._lock:
            self._cool[name] = (time.time() + secs, why)
        log.warning("백엔드 %s 를 %d분간 건너뜁니다: %s", name, secs // 60, why[:200])

    def _count(self, name: str, role: str, tokens: int) -> None:
        with self._lock:
            s = self.stats.setdefault(name, {"calls": 0, "tokens": 0, "roles": {}})
            s["calls"] += 1
            s["tokens"] += tokens
            s["roles"][role] = s["roles"].get(role, 0) + 1
            self._fails[name] = 0

    def usage_summary(self) -> str:
        with self._lock:
            if not self.stats:
                return "모델 호출 기록 없음"
            return " / ".join(f"{n}: {s['calls']}회·{s['tokens']:,}토큰" for n, s in sorted(self.stats.items()))

    def reset_cooldowns(self) -> None:
        with self._lock:
            self._cool.clear()

    # --- 호출 ---
    def create(self, **kw):
        system = kw["system"]
        m = ROLE_RE.search(system)
        role = m.group(1) if m else "director"
        routes = self.cfg.routes.get(role) or self.cfg.routes.get("default") or []
        tried: list[str] = []
        for name, model in routes:
            be = self.backends.get(name)
            if be is None:
                tried.append(f"{name}: 알 수 없는 백엔드")
                continue
            cool = self._cooling(name)
            if cool:
                tried.append(f"{name}: {cool}")
                continue
            ok, why = be.available()
            if not ok:
                tried.append(f"{name}: {why}")
                self._set_cool(name, 300, why)
                continue
            try:
                resp = be.complete(system=system, messages=kw["messages"], tools=kw.get("tools") or [],
                                   model=model, max_tokens=kw.get("max_tokens", 8192))
            except BackendUnavailable as e:
                self._set_cool(name, e.cooldown, str(e))
                tried.append(str(e))
                continue
            except BackendError as e:
                with self._lock:
                    self._fails[name] = self._fails.get(name, 0) + 1
                    n = self._fails[name]
                if n >= 3:
                    self._set_cool(name, 300, f"연속 실패 {n}회: {e}")
                tried.append(str(e))
                log.warning("백엔드 %s 일시 실패(%s) → 다음 백엔드", name, e)
                continue
            self._count(name, role, (resp.usage.input_tokens or 0) + (resp.usage.output_tokens or 0))
            if tried:
                log.info("[%s] %s 로 처리(앞선 시도: %s)", role, name, "; ".join(t[:80] for t in tried))
            return resp
        raise NoBackend(f"[{role}] 사용할 수 있는 모델 백엔드가 없습니다 — " + " | ".join(tried or ["경로 없음"]))

    # --- 점검 ---
    def probe(self, name: str, model: str | None = None) -> tuple[bool, str]:
        """실제로 한 번 불러 본다(--check 용). 쿨다운은 건드리지 않는다."""
        be = self.backends.get(name)
        if be is None:
            return False, "알 수 없는 백엔드"
        ok, why = be.available()
        if not ok:
            return False, why
        try:
            r = be.complete(system="[ROLE:probe] 당신은 연결 점검용 응답기다.",
                            messages=[{"role": "user", "content": "한 단어로 pong 이라고만 답하세요."}],
                            tools=[], model=model, max_tokens=32)
            txt = "".join(getattr(b, "text", "") for b in r.content).strip()
            return True, f"응답: {txt[:40]!r}"
        except (BackendUnavailable, BackendError) as e:
            return False, str(e)


def parse_route(spec: str) -> list[tuple[str, str | None]]:
    """'claude/opus, codex, local/qwen3:14b' → [('claude','opus'), ('codex',None), ('local','qwen3:14b')]"""
    out = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        name, _, model = part.partition("/")
        out.append((name.strip().lower(), model.strip() or None))
    return out


def build_backends(cfg) -> dict[str, Backend]:
    t = cfg.cli_timeout_min * 60
    be: dict[str, Backend] = {
        "claude": CLIBackend("claude", cfg.claude_bin, t, cfg.keep_api_keys),
        "codex": CLIBackend("codex", cfg.codex_bin, t, cfg.keep_api_keys),
        "gemini": CLIBackend("gemini", cfg.gemini_bin, t, cfg.keep_api_keys),
        "local": OpenAICompatBackend(cfg.local_base_url, cfg.local_model, cfg.local_api_key, t * 2),
    }
    if cfg.anthropic_api_key:
        from .llm import make_client
        be["api"] = AnthropicAPIBackend(make_client(cfg.anthropic_api_key), cfg.model_thinker)
    else:
        be["api"] = AnthropicAPIBackend(None, cfg.model_thinker)
    return be
