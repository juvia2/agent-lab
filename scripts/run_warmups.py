#!/usr/bin/env python3
"""워밍업 의뢰 키트(docs/warmups)를 #의뢰와 같은 코드 경로로 돌리고, 자동 채점한 뒤 #성능고도화 보고까지 큐에 넣는다.

완료 = 실행 → 결과 저장 → 자동 채점(grading.md) → 보고 큐(knowledge/learning_reports/pending) 적재.
가동 중인 연구실이 큐를 1분 주기로 각 봇 이름으로 전송한다(꺼져 있으면 scripts/post_learning_reports.py).

디스코드 수신 경로는 거치지 않는다: 역할 프롬프트 + 확정 학습 + 의뢰 규칙 + 의뢰 도구(AdhocBox) + 역할별 모델 경로는 #의뢰와 같고,
메시지 수신·분류 후 전달·첨부 업로드만 건너뛴다. 01번은 연구실장 분류 프롬프트만 호출한다(전달은 하지 않음).
정답은 에이전트에게 전달되지 않는다. 채점은 에이전트 응답이 끝난 뒤 이 실행기가 한다.
자동 채점은 수치·키워드·산출물 기준이라 한계가 있다. ❔ 항목은 _answer_keys 채점표로 사람이 확인한다.

    cd ~/research-lab
    .venv/bin/python scripts/run_warmups.py               # 권장 순서로 전부 + 채점 + 보고
    .venv/bin/python scripts/run_warmups.py 06 07 09      # 일부만
    .venv/bin/python scripts/run_warmups.py --no-report   # 보고 큐에 넣지 않음
    .venv/bin/python scripts/run_warmups.py --regrade docs/warmups/results/<시각>   # 다시 돌리지 않고 채점·보고만
    .venv/bin/python scripts/run_warmups.py --dry-run     # 모델 호출 없이 의뢰문·첨부만 확인
"""
from __future__ import annotations

import csv
import json
import re
import shutil
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
KIT = ROOT / "docs" / "warmups"
ORDER = ["06", "07", "09", "01", "05", "08", "10", "02", "03", "04"]
ROLES = {"01": "director", "02": "linguist", "03": "cogsci", "04": "lm", "05": "statistician", "06": "corpus",
         "07": "developer", "08": "documenter", "09": "tester", "10": "practitioner"}
DIRECTOR_CASES = [  # (본문, 첨부 이름)
    ("이 CSV에서 조건별 평균 음절 수 뽑아줘", "stimuli.csv"),
    ("혼합효과모형이 수렴을 안 하는데 무선 기울기를 빼도 되는지 봐줘", ""),
    ("GPT-2 계열 5종으로 Natural Stories 전체 surprisal 뽑아서 읽기시간이랑 회귀 돌려줘", ""),
    ("이거 좀 봐줘", ""),
    ("\"아무도 왔다\"가 왜 비문인지 설명 정리해줘", ""),
]


def kit_dir(num: str) -> Path:
    return next(p for p in KIT.iterdir() if p.is_dir() and p.name.startswith(num + "_"))


def request_text(num: str) -> str:
    lines = (kit_dir(num) / "의뢰문.md").read_text(encoding="utf-8").splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith("@"))
    return "\n".join(lines[start:]).strip()


def attachments(num: str) -> list[Path]:
    return sorted(p for p in kit_dir(num).iterdir() if p.is_file() and p.name != "의뢰문.md")


def dump(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


TITLES = {"01": "의뢰 분류", "02": "부정극어 최소쌍", "03": "연결가설 요약", "04": "연산 자원 추정", "05": "검정력 시뮬레이션",
          "06": "자극 매칭 점검", "07": "함수 테스트", "08": "결과 요약", "09": "보고서 검증", "10": "자문 통합"}
COLORS = {"director": 0x2C3E50, "linguist": 0xE74C3C, "cogsci": 0x9B59B6, "lm": 0x3498DB, "statistician": 0xF1C40F,
          "corpus": 0x1ABC9C, "practitioner": 0x7F8C8D, "developer": 0xE67E22, "documenter": 0x95A5A6, "tester": 0x27AE60}
NEEDS_TOOLS = {"05", "06", "07", "09"}      # 도구를 한 번도 안 쓰면 수행 자체가 안 된 과제
EXPECTED_ROUTES = ["corpus", "statistician", "experiment", "ask", "linguist"]
OK, NO, ASK = "✅", "❌", "❔"


def _rt_truth() -> tuple[float, int, int]:
    """09 정답을 원자료에서 계산: (조건 B 참가자 평균의 평균, B가 느린 참가자 수, 참가자 수)."""
    acc: dict = {}
    with (kit_dir("09") / "raw_rt.csv").open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            acc.setdefault(r["subject"], {}).setdefault(r["condition"], []).append(float(r["rt_ms"]))
    means = {s: {c: sum(v) / len(v) for c, v in d.items()} for s, d in acc.items()}
    mean_b = sum(m["B"] for m in means.values()) / len(means)
    return mean_b, sum(1 for m in means.values() if m["B"] > m["A"]), len(means)


def _results_numbers() -> set[str]:
    """08에서 출처가 있는 숫자: 파일 값, 백분율 표기, 모델별 합계."""
    ok: set[str] = set()
    tot: dict = {}
    with (kit_dir("08") / "results.csv").open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            k, c = int(r["n_items"]), int(r["n_correct"])
            t = tot.setdefault(r["model"], [0, 0]); t[0] += k; t[1] += c
            v = c / k
            ok |= {f"{v:.3f}", f"{v:.2f}", f"{v * 100:.1f}", f"{v * 100:.0f}", f"{v * 100:.2f}"}
            ok |= {str(k), str(c), r["accuracy"], str(float(r["accuracy"]))}
    for k, c in tot.values():
        v = c / k
        ok |= {str(k), str(c), f"{v:.3f}", f"{v:.2f}", f"{v * 100:.1f}", f"{v * 100:.0f}"}
    return ok


def grade(num: str, row: dict, out: Path) -> tuple[str, list[tuple[str, str]]]:
    """(판정, [(표시, 항목)]). 판정: 합격 / 불합격 / 실행 실패 / 확인 필요."""
    reply = (out / "reply.md").read_text(encoding="utf-8") if (out / "reply.md").exists() else ""
    tools, attached = row.get("tools") or [], row.get("attached") or []
    if row.get("status") != "responded":
        return "실행 실패", [(NO, f"응답 없음: {row.get('error') or row.get('status')}")]
    if num in NEEDS_TOOLS and not tools:
        return "실행 실패", [(NO, "도구 호출 0회. 파일을 읽거나 코드를 돌리지 않고 답함(능력은 채점하지 않음)")]
    c: list[tuple[str, str]] = []

    def chk(cond: bool, text: str) -> None:
        c.append((OK if cond else NO, text))

    if num == "01":
        routes = row.get("routes") or []
        for i, exp in enumerate(EXPECTED_ROUTES):
            got = routes[i] if i < len(routes) else "(없음)"
            chk(got == exp, f"{i + 1}번 건: 기대 {exp}, 실제 {got}")
    elif num == "02":
        f = next((out / "attached" / a for a in attached if a.lower().endswith(".csv")), None)
        if f and f.exists():
            rows = list(csv.reader(f.open(encoding="utf-8-sig")))
            chk(len(rows) == 11, f"CSV 10행(머리글 제외): 실제 {len(rows) - 1}행")
            chk(bool(rows) and [h.strip() for h in rows[0]] == ["pair_id", "npi", "grammatical", "ungrammatical", "confound_note"], "열 5개 이름 일치")
        else:
            chk(False, "CSV 첨부 없음")
        c.append((ASK, "쌍 사이 차이가 부정 요소 하나뿐인지, 비문 판정이 맞는지, '전혀' 예외 술어를 피했는지"))
    elif num == "03":
        c.append((ASK, "연결가설 서술, 한계 2가지가 서로 다른 종류인지, 서지 날조가 없는지, 통계 판단을 넘겼는지"))
    elif num == "04":
        chk(any(w in reply for w in ("미확인", "추정", "가정")), "추정·가정·미확인 표기가 있음")
        chk(any(w in reply for w in ("0.4", "400")) and "3.2" in reply, "메모리 추정이 파라미터 수 × 4바이트(약 0.4GB, 3.2GB)에서 출발")
        c.append((ASK, "측정하지 않은 시간을 측정값처럼 쓰지 않았는지, 벤치마크 절차가 실행 가능한지"))
    elif num == "05":
        ns = [int(x) for x in re.findall(r"(\d{2,3})\s*명", reply)]
        chk(any(88 <= n <= 92 for n in ns), f"필요 참가자 수가 88~92명 범위(기준 약 90명): 답변의 'N명' {sorted(set(ns)) or '없음'}")
        chk("run_command" in tools, "코드를 실제로 실행함")
        chk(bool(attached), "스크립트 첨부")
        c.append((ASK, "가정(대응 차이로 환원, 정규성)을 적었는지"))
    elif num == "06":
        chk("0.95" in reply, "음절 수 불일치(B−A 0.950) 수치로 지적")
        chk("T007a" in reply and "T012a" in reply, "목표어 중복 2건(7번, 23번) 지적")
        chk("31" in reply and "결측" in reply, "결측 1건(31번 A의 log_freq) 지적")
        chk("3.287" in reply and "3.293" in reply, "빈도 평균이 채점표와 일치(3.287, 3.293)")
        c.append((ASK, "로그 빈도를 불일치로 잘못 지적하지 않았는지"))
    elif num == "07":
        chk("run_command" in tools, "테스트를 실제로 실행함")
        chk("마지막" in reply, "마지막 단어 누락 버그를 언급")
        chk(any("test" in a.lower() for a in attached) and any("surprisal_utils" in a for a in attached), "테스트 파일과 고친 모듈 첨부")
        logs = "".join(p.read_text(encoding="utf-8", errors="replace") for p in (out / "run_logs").glob("*.log")) if (out / "run_logs").is_dir() else ""
        chk("passed" in logs, "실행 로그에 pytest 통과 기록")
        c.append((ASK, "nat → bit 변환을 버그로 잘못 고치지 않았는지"))
    elif num == "08":
        chk(not re.search(r"유의|p\s*[<=]", reply), "검정 결과가 없는데 '유의'·p값 표현을 쓰지 않음")
        chk("12" in reply, "문항 12개짜리 셀을 주의 사항으로 언급")
        allowed = _results_numbers()
        unknown = sorted({n for n in re.findall(r"\d+(?:\.\d+)?", reply) if n not in allowed and not (n.isdigit() and int(n) <= 12)})
        c.append((OK, "모든 숫자가 결과 파일 값이거나 모델별 합계") if not unknown else (ASK, f"출처 확인이 필요한 숫자: {', '.join(unknown[:12])}"))
    elif num == "09":
        mean_b, npos, n = _rt_truth()
        chk(f"{mean_b:.1f}" in reply or f"{mean_b:.2f}" in reply, f"조건 B 평균 오기 적발(실제 {mean_b:.1f} ms)")
        chk(bool(re.search(rf"(?<!\d){npos}\s*(명|/\s*{n})", reply)), f"'전원' 주장 오류 적발(실제 {npos}/{n}명)")
        chk("run_command" in tools, "원자료를 실제로 재계산함")
        chk(bool(attached), "재계산 스크립트 첨부")
        c.append((ASK, "일치 항목을 불일치로 잘못 지적하지 않았는지"))
    elif num == "10":
        chk("48" in reply and "64" in reply, "충돌 1: 문항 수 48세트 vs 64세트")
        chk("768" in reply or ("600" in reply and "초과" in reply), "충돌 2: 64세트면 연산 한도 초과(768 > 600)")
        chk("토큰" in reply and "매칭" in reply, "충돌 3: 토큰 수 매칭 여부")
        chk("spillover" in reply.lower() or "스필오버" in reply, "충돌 4: 임계 영역에 spillover 포함 여부")
        chk("승인" in reply or "연구자" in reply, "연구자 결정·승인 사항을 구분함")
        c.append((ASK, "충돌을 한쪽 의견으로 덮지 않았는지, 메모에 없는 수치를 지어내지 않았는지"))
    marks = [m for m, _ in c]
    if NO in marks:
        return "불합격", c
    if all(m == ASK for m in marks):
        return "확인 필요", c
    return "합격", c


def grade_and_report(out_root: Path, summary: dict, *, report: bool, publish_ok: bool) -> None:
    from lab import learning
    from lab.agents import DISPLAY_EN
    results: dict = {}
    md = [f"# 워밍업 자동 채점 · {out_root.name}", "",
          "자동 채점은 수치·키워드·산출물 기준이다. ❔ 항목은 `_answer_keys/` 채점표로 사람이 확인한다.", ""]
    for num, row in summary["items"].items():
        role = row["role"]
        verdict, checks = grade(num, row, out_root / f"{num}_{role}")
        results[num] = {"role": role, "verdict": verdict, "checks": checks}
        md += [f"## {num} {DISPLAY_EN.get(role, role)} · {TITLES[num]} · {verdict}",
               f"- 소요 {row.get('seconds', '-')}초, 실행 {row.get('runs', '-')}회, 학습 기록 {len(row.get('learned') or [])}건"]
        md += [f"- {m} {t}" for m, t in checks] + [""]
    (out_root / "grading.md").write_text("\n".join(md), encoding="utf-8")
    dump(out_root / "grading.json", results)
    count: dict = {}
    for r in results.values():
        count[r["verdict"]] = count.get(r["verdict"], 0) + 1
    tally = ", ".join(f"{k} {v}건" for k, v in count.items())
    print(f"채점: {tally} → {out_root / 'grading.md'}", flush=True)
    summary["grading"] = {n: r["verdict"] for n, r in results.items()}
    dump(out_root / "summary.json", summary)
    if not report:
        print("보고 큐에는 넣지 않음(--no-report)")
        return
    queued = []

    def rel(path: Path) -> str:
        return str(path.relative_to(ROOT))

    def put(role, title, desc, file):
        path = learning.enqueue(role, title, desc, file, color=COLORS.get(role, 0x3498DB),
                                group=f"warmup-{out_root.name}")     # 요약 글 아래 스레드에 나머지를 모은다
        if publish_ok:      # 워밍업 자료는 합성이고, ADHOC 정책이 디스코드 게시를 허용할 때만 전송 승인
            item = json.loads(path.read_text(encoding="utf-8"))
            item.update(classification="public", publication_approved=True)
            path.write_text(json.dumps(item, ensure_ascii=False, indent=1), encoding="utf-8")
        queued.append(path.name)

    lines = [f"• **{n} {DISPLAY_EN.get(r['role'], r['role'])}: {r['verdict']}** — {TITLES[n]}" for n, r in results.items()]
    learned = sum(len(row.get("learned") or []) for row in summary["items"].values())
    put("director", f"🧪 워밍업 테스트 결과 · {tally}",
        f"**실행:** {summary.get('started', '')} ~ {summary.get('finished', '')[-8:]} (run_warmups.py, 디스코드 미경유)\n"
        f"**자료:** 정답을 심어 둔 합성 자료\n\n" + "\n".join(lines)
        + f"\n\n**학습 기록:** {learned}건\n자동 채점은 수치·키워드 기준이며 ❔ 항목은 사람 확인이 필요하다. 상세는 첨부 파일.",
        rel(out_root / "grading.md"))
    for num, r in results.items():
        role, row = r["role"], summary["items"][num]
        d = out_root / f"{num}_{role}"
        f = d / ("triage.json" if num == "01" else "reply.md")
        body = "\n".join(f"{m} {t}" for m, t in r["checks"])
        put(role, f"🧪 워밍업 {num} {TITLES[num]} · {r['verdict']}",
            f"**결과:** {r['verdict']} · 소요 {row.get('seconds', '-')}초 · 실행 {row.get('runs', '-')}회\n\n{body}\n\n답변 원문은 첨부 파일.",
            rel(f) if f.exists() else None)
    summary["report_queue"] = queued
    dump(out_root / "summary.json", summary)
    print(f"보고 {len(queued)}건을 큐에 넣음" + ("" if publish_ok else " (ADHOC 정책이 디스코드 게시를 막아 전송 승인 없이 대기)"), flush=True)


def main() -> int:
    argv = sys.argv[1:]
    regrade = argv[argv.index("--regrade") + 1] if "--regrade" in argv else None
    args = [a for a in argv if not a.startswith("--") and a != regrade]
    dry, report = "--dry-run" in argv, "--no-report" not in argv
    todo = args or ORDER
    if regrade:
        out_root = Path(regrade).resolve()
        summary = json.loads((out_root / "summary.json").read_text(encoding="utf-8"))
        publish_ok = False
        if report:
            from dotenv import load_dotenv
            load_dotenv(ROOT / ".env")
            from lab.config import Config
            from lab.policy import load_policy
            publish_ok = bool(load_policy(Config.from_env(), "ADHOC").allows_discord)
        grade_and_report(out_root, summary, report=report, publish_ok=publish_ok)
        return 0
    if dry:
        for num in todo:
            if num == "01":
                print("01 director:", [c[0][:20] for c in DIRECTOR_CASES])
            else:
                print(num, ROLES[num], "| 첨부:", [p.name for p in attachments(num)], "|", request_text(num)[:60].replace("\n", " "))
        return 0

    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    from lab import adhoc
    from lab.agents import DISPLAY_EN, label, model_for, system_for
    from lab.backends import Router
    from lab.bot import TRIAGE, parse_route
    from lab.config import Config
    from lab.director import Director
    from lab.ledger import Ledger
    from lab.llm import ToolOutput, run_agent
    from lab.notify import ConsoleNotifier
    from lab.pipeline import Lab
    from lab.policy import load_policy
    from lab.sandbox import docker_ready
    from lab.team import MEMBER_TOOLS, READ_TOOLS

    cfg = Config.from_env()
    cfg.ensure_dirs()
    lab = Lab(cfg, Ledger(cfg.ledger_path), Router(cfg), ConsoleNotifier())
    director = Director(lab)
    policy = load_policy(cfg, "ADHOC")
    out_root = KIT / "results" / time.strftime("%Y%m%d-%H%M%S")
    out_root.mkdir(parents=True)
    summary = {"started": time.strftime("%Y-%m-%d %H:%M:%S"), "path": "run_warmups.py (디스코드 미경유, #의뢰와 같은 프롬프트·도구·모델 경로)",
               "sandbox_backend": cfg.sandbox_backend, "docker_ready": bool(docker_ready()), "items": {}}
    dump(out_root / "summary.json", summary)
    print(f"결과 폴더: {out_root}\n샌드박스: {cfg.sandbox_backend}, docker_ready={summary['docker_ready']}", flush=True)

    for num in todo:
        role = ROLES[num]
        out = out_root / f"{num}_{role}"
        out.mkdir()
        t0 = time.monotonic()
        row = {"role": role}
        try:
            if num == "01":
                cases = []
                for i, (text, att) in enumerate(DIRECTOR_CASES, 1):
                    ask = text + (f"\n[첨부: {att}]" if att else "")
                    raw = director.reply([{"role": "user", "content": ask}], requester_id=cfg.discord_owner_id,
                                         extra_system=TRIAGE.format(channel=cfg.adhoc_channel), policy_id="ADHOC", tools=[])
                    route, note = parse_route(raw)
                    cases.append({"n": i, "request": ask, "raw": raw, "route": route, "note": note})
                    print(f"  01-{i}: ROUTE={route}", flush=True)
                dump(out / "triage.json", cases)
                row.update(status="responded", routes=[c["route"] for c in cases])
            else:
                def read_tool(name: str, a: dict):
                    if name not in READ_TOOLS:
                        return ToolOutput(f"{name} 은(는) 쓸 수 없는 도구입니다", is_error=True)
                    return director._tool(name, a, None, None, cfg.discord_owner_id)

                box = adhoc.AdhocBox(cfg, role, lab.sandbox, read_tool=read_tool)
                saved = []
                for p in attachments(num):
                    shutil.copyfile(p, box.dir / "inputs" / p.name)
                    saved.append(f"inputs/{p.name}")
                text = request_text(num)
                msgs = [{"role": "user", "content": text}]
                if saved:
                    msgs.append({"role": "user", "content": "[연구자가 파일을 첨부함. 작업 폴더 기준 경로]\n" + "\n".join(saved)})
                roster = ", ".join(f"@{DISPLAY_EN[r]}({label(r) if r != 'director' else '🧑‍💼 연구실장'})"
                                   for r in DISPLAY_EN if r != role)
                system = (system_for(role, cfg, include_open=True)
                          + f"\n\n당신은 디스코드에서 {DISPLAY_EN[role]}({label(role)})로 불린다. 한국어로 간결하게 답한다."
                          + f"\n동료: {roster}" + adhoc.rules(cfg))
                ok = True
                try:
                    res = run_agent(lab.client, model=model_for(cfg, role), system=system, messages=msgs,
                                    tools=adhoc.schemas(cfg, MEMBER_TOOLS), execute=box.execute,
                                    max_turns=16, max_tokens=4000, data_policy=policy)
                    reply = (res.text or "").strip()
                    foot = box.footer()
                    (out / "reply.md").write_text(reply + ("\n\n" + foot if foot else "") + "\n", encoding="utf-8")
                    dump(out / "trace.json", res.messages)
                    row.update(status="responded" if reply else "empty", turns=res.turns)
                except Exception:
                    ok = False
                    raise
                finally:
                    box.finish_log(text, ok)
                    files = out / "attached"
                    files.mkdir(exist_ok=True)
                    for p in box.attachments:
                        shutil.copyfile(p, files / p.name)
                    logs = box.dir / "logs"
                    if logs.is_dir():
                        shutil.copytree(logs, out / "run_logs", dirs_exist_ok=True)
                    row.update(runs=box.runs, tools=box.tools_used, attached=[p.name for p in box.attachments],
                               learned=box.learned, work_dir=str(box.dir))
        except Exception as e:
            row.update(status="failed", error=f"{type(e).__name__}: {str(e)[:500]}")
            (out / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        row["seconds"] = round(time.monotonic() - t0, 1)
        if hasattr(lab.client, "usage_summary"):
            row["usage_so_far"] = lab.client.usage_summary()
        summary["items"][num] = row
        dump(out_root / "summary.json", summary)
        print(f"{num} {role}: {row['status']} ({row['seconds']}s, 실행 {row.get('runs', '-')}회)", flush=True)

    summary["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
    dump(out_root / "summary.json", summary)
    grade_and_report(out_root, summary, report=report, publish_ok=bool(policy.allows_discord))
    print(f"\n끝. 결과: {out_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
