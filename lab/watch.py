"""연구실장 감시자와 하루 요약. 서비스(bot.py)에서 스레드 하나로 1분마다 돈다."""
from __future__ import annotations

import json
import logging
import threading
import time

log = logging.getLogger("lab.watch")
RECOVERABLE = ("infra", "refusal", "error")    # 예산 한도 소진·승인 대기는 사람이 정한다


def watchdog_tick(lab, now: float | None = None) -> list[str]:
    """승인 대기가 아닌 정지가 watchdog_min 을 넘으면 단계마다 한 번 재개한다. 두 번째 정지는 '결정 필요'로 바로 올라간다(pipeline._halt).
    stop_kind 가 없는 예전 정지(이 기능 이전)는 건드리지 않는다."""
    now = now or time.time()
    acted = []
    for exp in lab.ledger.list("paused", limit=200) + lab.ledger.list("failed", limit=200):
        meta = json.loads(exp.get("meta_json") or "{}")
        if meta.get("stop_kind") not in RECOVERABLE or exp["updated_at"] > now - lab.cfg.watchdog_min * 60:
            continue
        tries = meta.get("watchdog") or {}
        if tries.get(exp["phase"], 0) >= 1:
            continue
        tries[exp["phase"]] = tries.get(exp["phase"], 0) + 1
        lab._set_meta(exp["id"], watchdog=tries)
        msg = lab.resume(exp["id"])
        lab.ledger.add_event(exp["id"], "watchdog", f"연구실장 자동 조치: {msg}")
        lab.notifier.digest(lab.ledger.get(exp["id"]), f"연구실장 자동 조치({exp['phase']} 단계 정지 {lab.cfg.watchdog_min}분 경과): {msg}")
        acted.append(exp["id"])
    return acted


def _dir(cfg):
    d = cfg.lab_home / "digest"
    d.mkdir(parents=True, exist_ok=True)
    return d


def digest_add(cfg, exp_id: str | None, text: str, role: str | None = None) -> None:
    with (_dir(cfg) / "pending.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": time.time(), "exp": exp_id, "role": role, "text": text[:1500]}, ensure_ascii=False) + "\n")


def digest_text(rows: list[dict], per_exp: int = 4) -> str:
    by: dict[str, list[dict]] = {}
    for r in rows:
        by.setdefault(r.get("exp") or "연구실", []).append(r)
    out = [f"**하루 요약** ({time.strftime('%m-%d')}, 진행 알림 {len(rows)}건)"]
    for key, items in sorted(by.items()):
        out.append(f"\n**{key}** ({len(items)}건)")
        out += [f"- {' '.join(r['text'].split())[:160]}" for r in items[-per_exp:]]
    return "\n".join(out)


def digest_flush(cfg, notifier, now: float | None = None, force: bool = False) -> bool:
    """하루 한 번 digest_hour 이후에 모인 진행 알림을 요약해 접수 채널에 올린다."""
    now = now or time.time()
    d = _dir(cfg)
    today = time.strftime("%Y-%m-%d", time.localtime(now))
    mark, pend = d / "last_sent", d / "pending.jsonl"
    if not force and (time.localtime(now).tm_hour < cfg.digest_hour or (mark.exists() and mark.read_text().strip() == today)):
        return False
    rows = [json.loads(x) for x in pend.read_text(encoding="utf-8").splitlines() if x.strip()] if pend.exists() else []
    mark.write_text(today)
    if not rows:
        return False
    text = digest_text(rows)
    notifier.post(None, text[:1900] + ("\n…(전체는 /status EXP-###)" if len(text) > 1900 else ""))
    with (d / f"sent-{today}.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(pend.read_text(encoding="utf-8"))
    pend.unlink()
    return True


def run(lab, stop: threading.Event, every: float = 60.0) -> threading.Thread:
    def loop():
        while not stop.wait(every):
            try:
                watchdog_tick(lab)
                digest_flush(lab.cfg, lab.notifier)
            except Exception:
                log.exception("watch tick failed")
    t = threading.Thread(target=loop, name="lab-watch", daemon=True)
    t.start()
    return t
