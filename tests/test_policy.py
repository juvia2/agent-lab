import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from lab.backends import Backend, OpenAICompatBackend, Router
from lab.bot import DiscordNotifier
from lab.director import Director
from lab.learning import publication_allowed
from lab.llm import NoBackend
from lab.policy import DataPolicy, load_policy


class FakeBackend(Backend):
    def __init__(self, name, fail=False):
        self.name, self.fail, self.calls = name, fail, 0

    def complete(self, **kw):
        self.calls += 1
        if self.fail:
            from lab.backends import BackendError
            raise BackendError("failed")
        return SimpleNamespace(content=[], usage=SimpleNamespace(input_tokens=1, output_tokens=1))


def policy_file(tmp_path: Path, exp_id: str, **fields):
    folder = tmp_path / "policies"
    folder.mkdir(exist_ok=True)
    (folder / f"{exp_id}.json").write_text(json.dumps(fields), encoding="utf-8")


def test_policy_defaults_restricted_and_rejects_invalid(tmp_path):
    cfg = SimpleNamespace(lab_home=tmp_path)
    assert load_policy(cfg, "EXP-001") == DataPolicy()
    policy_file(tmp_path, "EXP-001", classification="public", external_backends=["unknown"], discord_publish=True)
    assert load_policy(cfg, "EXP-001") == DataPolicy()
    policy_file(tmp_path, "EXP-001", classification="internal", external_backends=["codex"], discord_publish=True)
    assert not load_policy(cfg, "EXP-001").allows_discord
    assert not load_policy(cfg, "EXP-001").allows_backend("codex")


def test_router_blocks_cloud_fallback_before_call(tmp_path):
    cloud, local = FakeBackend("codex"), FakeBackend("local", fail=True)
    cfg = SimpleNamespace(lab_home=tmp_path, routes={"tester": [("local", None), ("codex", None)]})
    router = Router(cfg, {"codex": cloud, "local": local})
    with pytest.raises(NoBackend, match="자료 정책"):
        router.create(system="[ROLE:tester]", messages=[{"role": "user", "content": "비공개"}],
                      data_policy=load_policy(cfg, "EXP-001"))
    assert local.calls == 1 and cloud.calls == 0
    policy_file(tmp_path, "EXP-001", classification="public", external_backends=["codex"], discord_publish=False)
    router.reset_cooldowns()
    router.create(system="[ROLE:tester]", messages=[], data_policy=load_policy(cfg, "EXP-001"))
    assert cloud.calls == 1


def test_discord_notifier_requires_explicit_public_policy(tmp_path):
    notifier = DiscordNotifier(SimpleNamespace(lab_home=tmp_path, report_channel="reports"))
    calls = []

    def fake_run(coro):
        calls.append(coro)
        coro.close()

    notifier._run = fake_run
    exp = {"id": "EXP-001"}
    notifier.post(exp, "secret")
    notifier.post_report(exp, "secret")
    notifier.ask_approval(exp, ["reason"], "secret")
    assert calls == []
    policy_file(tmp_path, "EXP-001", classification="public", external_backends=[], discord_publish=True)
    notifier.post(exp, "public")
    notifier.post_report(exp, "public")
    notifier.ask_approval(exp, ["reason"], "public")
    assert len(calls) == 4


def test_learning_reports_need_publication_approval():
    assert not publication_allowed({})
    assert not publication_allowed({"classification": "public", "publication_approved": False})
    assert publication_allowed({"classification": "public", "publication_approved": True})


def test_local_backend_rejects_non_loopback_destination():
    backend = OpenAICompatBackend("https://example.com/v1", "model")
    assert not backend.available()[0]
    assert "루프백" in backend.available()[1]


def test_console_director_reports_missing_local_model(tmp_path):
    class Missing:
        messages = None

        def __init__(self):
            self.messages = self

        def create(self, **kw):
            raise NoBackend("blocked")

    lab = SimpleNamespace(cfg=SimpleNamespace(model_director="m"), client=Missing())
    assert "로컬 모델" in Director(lab).reply([{"role": "user", "content": "실험"}])


def test_blocked_text_names_the_missing_policy_file():
    from lab.policy import blocked_text
    assert "policies/INTAKE.json" in blocked_text("INTAKE")
    assert "/policy EXP-003 open" in blocked_text("EXP-003")


def test_director_records_ops_request(tmp_path):
    lab = SimpleNamespace(cfg=SimpleNamespace(lab_home=tmp_path), ledger=None)
    Director(lab)._tool("record_ops_request", {"text": "한 과제 보고는\n스레드 하나로"}, None, None, 1)
    assert "한 과제 보고는 스레드 하나로" in (tmp_path / "ops_requests.md").read_text(encoding="utf-8")


def test_set_policy_opens_and_closes_experiment_only(tmp_path):
    from lab.policy import set_policy
    cfg = SimpleNamespace(lab_home=tmp_path)
    (tmp_path / "experiments" / "EXP-001").mkdir(parents=True)
    assert "열었" in set_policy(cfg, "exp-001", True)
    assert load_policy(cfg, "EXP-001").allows_discord
    assert load_policy(cfg, "EXP-001").allows_backend("claude")
    assert "닫았" in set_policy(cfg, "EXP-001", False)
    assert load_policy(cfg, "EXP-001") == DataPolicy()
    assert "없" in set_policy(cfg, "EXP-002", True)          # 없는 실험
    assert "EXP-" in set_policy(cfg, "INTAKE", False)         # 채널 정책은 디스코드에서 못 바꾼다
    assert not (tmp_path / "policies" / "EXP-002.json").exists()


def test_experiment_inherits_channel_policy_once(tmp_path):
    """연구자가 #실험진행에서 맡긴 실험은 채널 정책을 물려받고, 이미 정해진 실험 정책은 덮어쓰지 않는다."""
    import json
    from types import SimpleNamespace as NS
    from lab.policy import DataPolicy, inherit_policy, load_policy
    cfg = NS(lab_home=tmp_path)
    (tmp_path / "policies").mkdir()
    assert inherit_policy(cfg, "EXP-001", "INTAKE") is False                    # 채널 정책이 없으면 로컬 전용 유지
    assert load_policy(cfg, "EXP-001") == DataPolicy()
    (tmp_path / "policies" / "INTAKE.json").write_text(json.dumps(
        {"classification": "public", "external_backends": ["claude", "codex"], "discord_publish": True}))
    assert inherit_policy(cfg, "EXP-001", "INTAKE") is True
    p = load_policy(cfg, "EXP-001")
    assert p.allows_discord and p.allows_backend("claude") and not p.allows_backend("gemini")
    (tmp_path / "policies" / "EXP-002.json").write_text(json.dumps({"classification": "restricted"}))
    assert inherit_policy(cfg, "EXP-002", "INTAKE") is False                    # 연구자가 정한 실험 정책은 그대로
    assert inherit_policy(cfg, "EXP-003", "../x") is False


def test_submit_from_intake_thread_inherits_policy(make_lab):
    import json
    from conftest import T
    from lab.director import Director
    from lab.policy import load_policy
    lab, _ = make_lab({"director": [[T("submit_experiment", title="x", request_markdown="## q")], [("text", "접수됨")]]})
    (lab.cfg.lab_home / "policies").mkdir(parents=True, exist_ok=True)
    (lab.cfg.lab_home / "policies" / "INTAKE.json").write_text(json.dumps(
        {"classification": "public", "external_backends": ["claude"], "discord_publish": True}))
    Director(lab).reply([{"role": "user", "content": "접수"}], thread_id=1, channel_id=1, requester_id=42)
    assert load_policy(lab.cfg, "EXP-001").allows_discord
