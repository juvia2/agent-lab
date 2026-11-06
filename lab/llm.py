"""에이전트 실행 루프(도구 사용 반복). client 는 `.messages.create` 를 가진 객체(Anthropic SDK 또는 backends.Router)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


class BudgetExceeded(Exception):
    pass


class Stopped(Exception):
    pass


class NoBackend(Exception):
    """이 역할에 쓸 수 있는 모델 백엔드가 하나도 없다(한도 소진·로그인 풀림 등). 실험은 일시정지된다."""


@dataclass
class ToolOutput:
    text: str
    terminal: dict | None = None     # 종료 도구가 호출되면 payload 가 들어간다
    is_error: bool = False


@dataclass
class AgentResult:
    text: str
    terminal: dict | None
    messages: list = field(default_factory=list)
    turns: int = 0


def make_client(api_key: str | None):
    import anthropic
    return anthropic.Anthropic(api_key=api_key, max_retries=5, timeout=600.0)


def _block_to_dict(b: Any) -> dict:
    if b.type == "text":
        return {"type": "text", "text": b.text}
    if b.type == "tool_use":
        return {"type": "tool_use", "id": b.id, "name": b.name, "input": b.input}
    return {"type": "text", "text": ""}


def _clip(text: str, limit: int = 14000) -> str:
    if len(text) <= limit:
        return text
    h = limit * 2 // 3
    return text[:h] + f"\n...[{len(text) - limit}자 생략]...\n" + text[-(limit - h):]


def run_agent(client, *, model: str, system: str, prompt: str | None = None,
              messages: list | None = None, tools: list[dict], execute: Callable[[str, dict], ToolOutput],
              on_usage: Callable[[int], None] | None = None,
              should_stop: Callable[[], bool] | None = None,
              max_turns: int = 40, max_tokens: int = 8192) -> AgentResult:
    """도구 호출이 끝날 때까지(또는 종료 도구가 불릴 때까지) 반복한다."""
    msgs: list = list(messages) if messages else []
    if prompt is not None:
        msgs.append({"role": "user", "content": prompt})
    text_out = ""
    for turn in range(1, max_turns + 1):
        if should_stop and should_stop():
            raise Stopped()
        kwargs = dict(model=model, max_tokens=max_tokens, system=system, messages=msgs)
        if tools:
            kwargs["tools"] = tools
        resp = client.messages.create(**kwargs)
        used = (getattr(resp.usage, "input_tokens", 0) or 0) + (getattr(resp.usage, "output_tokens", 0) or 0)
        if on_usage:
            on_usage(used)          # 예산 초과 시 BudgetExceeded 를 던진다
        content = [_block_to_dict(b) for b in resp.content]
        msgs.append({"role": "assistant", "content": content})
        text_out = "".join(b["text"] for b in content if b["type"] == "text") or text_out

        calls = [b for b in content if b["type"] == "tool_use"]
        if not calls:
            if resp.stop_reason == "max_tokens":
                msgs.append({"role": "user", "content": "출력이 잘렸습니다. 이어서 계속하세요."})
                continue
            return AgentResult(text_out, None, msgs, turn)

        results, terminal = [], None
        for c in calls:
            try:
                if c["name"] == "_parse_error":      # CLI 텍스트 규약에서 tool_call JSON 이 깨진 경우
                    out = ToolOutput(f"{c['input'].get('error')}\n시작 부분: {c['input'].get('raw_head')}\n"
                                     "<tool_call>{\"name\": ..., \"input\": {...}}</tool_call> 형식의 유효한 JSON 으로 다시 호출하세요.",
                                     is_error=True)
                else:
                    out = execute(c["name"], c["input"])
            except (BudgetExceeded, Stopped):
                raise
            except Exception as e:  # 도구 오류는 모델에게 돌려주어 스스로 고치게 한다
                out = ToolOutput(f"도구 오류: {type(e).__name__}: {e}", is_error=True)
            if out.terminal is not None:
                terminal = out.terminal
            results.append({"type": "tool_result", "tool_use_id": c["id"], "content": _clip(out.text),
                            **({"is_error": True} if out.is_error else {})})
        msgs.append({"role": "user", "content": results})
        if terminal is not None:
            return AgentResult(text_out, terminal, msgs, turn)
    return AgentResult(text_out + "\n[최대 반복 횟수 도달]", None, msgs, max_turns)
