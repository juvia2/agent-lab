import dataclasses
import re
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lab.config import Config  # noqa: E402
from lab.ledger import Ledger  # noqa: E402
from lab.notify import ConsoleNotifier  # noqa: E402
from lab.pipeline import Lab  # noqa: E402


class ScriptedClient:
    """역할별로 미리 정해 둔 응답(턴)을 순서대로 돌려주는 가짜 Anthropic 클라이언트."""

    def __init__(self, script: dict[str, list], tokens_per_call: int = 100):
        self.script = {k: list(v) for k, v in script.items()}
        self.lock = threading.Lock()
        self.tokens = tokens_per_call
        self.calls: list[str] = []
        self.messages = self
        self._n = 0

    def create(self, **kw):
        m = re.search(r"\[ROLE:(\w+)\]", kw["system"])
        role = m.group(1)
        with self.lock:
            self.calls.append(role)
            q = self.script.get(role)
            if not q:
                raise AssertionError(f"스크립트에 {role} 의 남은 턴이 없음 (호출 순서 {self.calls})")
            turn = q.pop(0)
            self._n += 1
            n = self._n
        blocks, has_tool = [], False
        for i, spec in enumerate(turn):
            if spec[0] == "text":
                blocks.append(SimpleNamespace(type="text", text=spec[1]))
            else:
                has_tool = True
                blocks.append(SimpleNamespace(type="tool_use", id=f"tu_{n}_{i}", name=spec[1], input=spec[2]))
        return SimpleNamespace(content=blocks, stop_reason="tool_use" if has_tool else "end_turn",
                               usage=SimpleNamespace(input_tokens=self.tokens, output_tokens=0))


def T(name, **inp):
    return ("tool", name, inp)


@pytest.fixture
def make_lab(tmp_path):
    def _make(script, *, tokens=100, **cfg_over):
        cfg = dataclasses.replace(Config.from_env(), lab_home=tmp_path / "lab", sandbox_backend="host",
                                  anthropic_api_key=None, **cfg_over)
        cfg.ensure_dirs()
        notifier = ConsoleNotifier()
        lab = Lab(cfg, Ledger(cfg.ledger_path), ScriptedClient(script, tokens), notifier)
        return lab, notifier
    return _make
