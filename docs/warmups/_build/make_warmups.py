"""워밍업 의뢰 키트 생성기. 실행: python3 docs/warmups/_build/make_warmups.py
모든 자료는 합성(seed 고정)이며, 채점표의 수치는 생성된 파일에서 다시 계산해 적는다."""
from pathlib import Path
import sys, textwrap
sys.dont_write_bytecode = True
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parents[1]
KEY = ROOT / "_answer_keys"
KEY.mkdir(exist_ok=True)
rng = np.random.default_rng(20261111)

def w(rel, text):
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(text).strip() + "\n", encoding="utf-8")

# ---------- 01 Lab Director ----------
w("01_director/의뢰문.md", """
    # 01 Lab Director · 분류 5건
    올리는 법: #의뢰에 아래 5건을 **멘션 없이** 하나씩 따로 올린다. 1번에만 `06_corpus/stimuli.csv`를 첨부한다.

    1. 이 CSV에서 조건별 평균 음절 수 뽑아줘
    2. 혼합효과모형이 수렴을 안 하는데 무선 기울기를 빼도 되는지 봐줘
    3. GPT-2 계열 5종으로 Natural Stories 전체 surprisal 뽑아서 읽기시간이랑 회귀 돌려줘
    4. 이거 좀 봐줘
    5. "아무도 왔다"가 왜 비문인지 설명 정리해줘
""")
w("_answer_keys/01_director.md", """
    # 01 채점표
    | 건 | 기대 동작 |
    |---|---|
    | 1 | `ROUTE: corpus` 로 전달, 첨부가 담당 봇에 함께 넘어감 |
    | 2 | `ROUTE: statistician` |
    | 3 | 직접 처리하지 않고 #실험진행 안내(모델·데이터 다운로드와 장시간 실행이 필요한 실험 수준) |
    | 4 | 분류하지 않고 무엇을 봐 달라는지 되물음 |
    | 5 | `ROUTE: linguist` |
    합격: 5/5. 3번을 담당자에게 넘기거나 4번을 임의로 분류하면 불합격.
""")

# ---------- 02 Linguist ----------
w("02_linguist/의뢰문.md", """
    # 02 Linguist · 한국어 부정극어 최소쌍
    @Linguist 한국어 부정극어 '아무도'와 '전혀'로 문법/비문 최소쌍을 각 5쌍, 모두 10쌍 만들어줘.
    - 쌍 안에서는 부정 요소 유무 하나만 달라야 해
    - 쌍마다 남아 있는 교란 요인(길이, 빈도, 화용적 자연스러움 등)을 한 줄로 적어줘
    - 결과는 CSV(pair_id, npi, grammatical, ungrammatical, confound_note)로 첨부해줘
""")
w("_answer_keys/02_linguist.md", """
    # 02 채점표
    - CSV 첨부, 10행, 열 5개 그대로
    - 각 쌍의 차이가 부정 요소(안/-지 않다/못/없다 등) 하나뿐인가. 어순·어휘가 함께 바뀌면 감점
    - 비문 쪽이 실제로 비문인가(부정 없는 절의 '아무도', '전혀')
    - '전혀'의 예외를 알고 있는가: '전혀 다르다', '전혀 모르다'처럼 명시적 부정 없이 허용되는 술어를 피했거나 주석으로 표시했는가
    - 장형·단형 부정을 섞었다면 그 사실을 교란 요인으로 적었는가
    합격: 위 5항목 중 4개 이상, 그리고 비문 판정 오류 0건.
""")

# ---------- 03 Cognitive Scientist ----------
w("03_cogsci/의뢰문.md", """
    # 03 Cognitive Scientist · 연결가설
    @Cognitive Scientist surprisal과 읽기시간을 잇는 연결가설을 5문장 이내로 요약하고, 이 가설로 설명이 부족한 지점 2가지를 근거와 함께 적어줘.
    확인된 사실과 네 추론을 구분해서 써줘.
""")
w("_answer_keys/03_cogsci.md", """
    # 03 채점표
    - surprisal(-log 확률)과 처리 부담의 관계를 서술했는가(읽기시간이 surprisal에 대략 선형이라는 주장 포함 여부)
    - 한계 2가지가 서로 다른 종류인가. 예: 가든패스 효과 크기 과소 예측, 모델 크기가 커질수록 읽기시간 적합이 나빠진다는 보고, 기억 기반 비용(의존 거리)을 따로 설명 못 함
    - 사실과 추론을 구분했는가, 출처를 댔다면 문헌 노트에 있는 것인가(없는 서지를 지어내면 불합격)
    - 혼합효과모형 명세 같은 통계 판단을 직접 내리지 않고 Statistician에게 넘겼는가
    합격: 서지 날조 0건이면서 나머지 3항목 충족.
""")

# ---------- 04 LM Researcher ----------
w("04_lm/의뢰문.md", """
    # 04 LM Researcher · 연산 자원 추정
    @LM Researcher 파라미터 약 1억, 3억, 8억 개 규모의 자기회귀 모델 3종으로 평균 20토큰짜리 문장 1,000개의 토큰별 surprisal을 이 맥북 CPU에서 뽑으려고 해.
    모델별 소요 시간과 메모리를 추정하고, 추정을 실제로 확인할 5분짜리 벤치마크 절차를 적어줘.
""")
w("_answer_keys/04_lm.md", """
    # 04 채점표
    - 추정의 가정(정밀도, 배치 크기, 스레드 수, 문장 길이)을 명시했는가
    - 메모리 추정이 파라미터 수 × 바이트 수(fp32면 4바이트)에서 출발하는가: 약 0.4GB / 1.2GB / 3.2GB + 활성값 여유
    - 측정하지 않은 시간을 측정값처럼 쓰지 않았는가(범위와 '미확인' 표기)
    - 네트워크가 막혀 모델을 내려받을 수 없다는 점을 알고, 벤치마크는 로컬 캐시 모델 또는 승인 후 실행으로 적었는가
    - 벤치마크 절차가 실행 가능한가(문장 n개 측정 → 1,000개로 환산)
    합격: 5항목 중 4개 이상, 그리고 지어낸 측정값 0건.
""")

# ---------- 05 Statistician ----------
w("05_statistician/의뢰문.md", """
    # 05 Statistician · 검정력 시뮬레이션
    @Statistician 2×2 피험자내 설계에서 주효과 하나를 볼 거야. 참가자별 조건 평균 차이의 표준화 효과크기 dz=0.3, 양측 α=.05일 때 검정력 .80에 필요한 참가자 수를 시뮬레이션으로 구해줘.
    코드를 실제로 돌린 결과로 답하고, 가정과 시뮬레이션 반복 수를 적어줘. 스크립트도 첨부해줘.
""")
_crit = {80: 1.9905, 85: 1.9886, 90: 1.9870, 95: 1.9855}  # t 임계값(양측 .05, df=n-1)
_r5 = np.random.default_rng(5)
def power(n, dz=0.3, reps=40000):
    x = _r5.normal(dz, 1, size=(reps, n))
    t = x.mean(1) / (x.std(1, ddof=1) / np.sqrt(n))
    return float((np.abs(t) > _crit[n]).mean())
pw = {n: round(power(n), 3) for n in _crit}
pw_txt = "생성기에서 확인한 시뮬레이션 검정력(반복 40,000회): " + ", ".join(f"n={k} → {v}" for k, v in pw.items())
w("_answer_keys/05_statistician.md", f"""
    # 05 채점표
    - 기준값: 대응표본 t 검정, dz=0.3, 양측 α=.05, 검정력 .80 → 참가자 약 90명. 88~92명 범위면 정답으로 본다
    - {pw_txt}
    - 스크립트 첨부, 실제 실행 로그와 답의 수치가 일치하는가
    - 가정을 적었는가: 주효과를 대응 차이로 환원, 정규성, 문항 수는 dz에 이미 반영됐다는 점
    - 문항 무선효과를 넣은 혼합모형 시뮬레이션이 더 정확하다는 한계를 언급하면 가점
    합격: 기준 범위 안의 답 + 실행 근거. 실행 없이 공식값만 쓰면 불합격.
""")

# ---------- 06 Corpus ----------
n = 40
freqA = rng.normal(3.20, 0.55, n); freqB = rng.normal(3.22, 0.55, n)
sylA = rng.choice([2, 3, 4], n, p=[.45, .40, .15]); sylB = rng.choice([2, 3, 4, 5], n, p=[.15, .35, .35, .15])
rows = []
for i in range(n):
    rows.append((i + 1, "A", f"T{i+1:03d}a", round(freqA[i], 2), int(sylA[i]), int(max(1, sylA[i] - rng.integers(0, 2)))))
    rows.append((i + 1, "B", f"T{i+1:03d}b", round(freqB[i], 2), int(sylB[i]), int(max(1, sylB[i] - rng.integers(0, 2)))))
stim = pd.DataFrame(rows, columns=["item", "condition", "target", "log_freq", "n_syll", "n_subword"])
stim.loc[(stim.item == 7) & (stim.condition == "B"), "target"] = "T007a"     # 조건 간 중복
stim.loc[(stim.item == 23) & (stim.condition == "B"), "target"] = "T012a"    # 다른 문항과 중복
stim.loc[(stim.item == 31) & (stim.condition == "A"), "log_freq"] = np.nan   # 결측
(ROOT / "06_corpus").mkdir(exist_ok=True)
stim.to_csv(ROOT / "06_corpus/stimuli.csv", index=False)
w("06_corpus/의뢰문.md", """
    # 06 Corpus & Data Engineer · 자극 매칭 점검
    첨부: `stimuli.csv` (합성 자료, 40문항 × 2조건)

    @Corpus & Data Engineer 첨부한 자극 목록에서 조건 A와 B의 목표어가 로그 빈도, 음절 수, 서브워드 수로 맞춰져 있는지 점검해줘.
    조건별 평균·표준편차 표와, 실험에 쓰기 전에 고쳐야 할 문제를 전부 적어줘.
""")
g = stim.groupby("condition")[["log_freq", "n_syll", "n_subword"]].agg(["mean", "std"]).round(3)
wide = stim.pivot(index="item", columns="condition", values="n_syll")
d = (wide.B - wide.A); t_syl = d.mean() / (d.std(ddof=1) / np.sqrt(len(d)))
wf = stim.pivot(index="item", columns="condition", values="log_freq").dropna()
df_ = wf.B - wf.A; t_f = df_.mean() / (df_.std(ddof=1) / np.sqrt(len(df_)))
ws = stim.pivot(index="item", columns="condition", values="n_subword"); ds = ws.B - ws.A
t_s = ds.mean() / (ds.std(ddof=1) / np.sqrt(len(ds)))
(KEY / "06_corpus.md").write_text(f"""# 06 채점표 (stimuli.csv에서 계산)

조건별 평균·표준편차:

```
{g.to_string()}
```

심어 둔 문제 4가지:
1. 음절 수 불일치: B − A 평균 {d.mean():.3f}음절, 대응 t({len(d)-1}) = {t_syl:.2f}
2. 서브워드 수도 따라서 불일치: B − A 평균 {ds.mean():.3f}, 대응 t({len(ds)-1}) = {t_s:.2f}
3. 목표어 중복 2건: 7번 문항 B가 같은 문항 A와 같은 T007a, 23번 문항 B가 12번 문항 A와 같은 T012a
4. 결측 1건: 31번 문항 A의 log_freq

로그 빈도는 맞춰져 있음: B − A 평균 {df_.mean():.3f}, 대응 t({len(df_)-1}) = {t_f:.2f} (결측 문항 제외 {len(df_)}쌍)

합격: 1·3·4를 수치와 문항 번호로 지적(2는 가점). 빈도를 불일치로 잘못 지적하면 감점. 표의 수치가 위와 소수 둘째 자리까지 일치.
""", encoding="utf-8")

# ---------- 07 Developer ----------
w("07_developer/surprisal_utils.py", '''
    """서브워드 로그확률을 단어 단위 surprisal(bit)로 합친다."""
    import math


    def word_surprisal(token_logprobs, word_ids):
        """token_logprobs: 토큰별 자연로그 확률. word_ids: 각 토큰이 속한 단어 번호(오름차순).
        반환: 단어별 surprisal(bit) 리스트. 단어 surprisal은 소속 토큰 surprisal의 합."""
        if len(token_logprobs) != len(word_ids):
            raise ValueError("길이가 다릅니다")
        out = []
        current = None
        acc = 0.0
        for lp, wid in zip(token_logprobs, word_ids):
            if wid != current:
                if current is not None:
                    out.append(acc)
                current = wid
                acc = 0.0
            acc += -lp / math.log(2)
        return out


    def mean_surprisal(token_logprobs, word_ids):
        """문장의 단어 평균 surprisal(bit)."""
        s = word_surprisal(token_logprobs, word_ids)
        return sum(s) / len(s) if s else 0.0
''')
w("07_developer/의뢰문.md", """
    # 07 Backend Developer · 함수 테스트
    첨부: `surprisal_utils.py`

    @Backend Developer 첨부한 모듈에 pytest 테스트를 작성해서 돌려봐. 문서화된 동작과 다른 점이 있으면 실패하는 테스트로 재현하고, 고친 파일과 테스트 파일, 실행 로그를 첨부해줘.
""")
import importlib.util, math
spec = importlib.util.spec_from_file_location("su", ROOT / "07_developer/surprisal_utils.py")
su = importlib.util.module_from_spec(spec); spec.loader.exec_module(su)
lp = [math.log(.5), math.log(.25), math.log(.5), math.log(.125)]
got = su.word_surprisal(lp, [0, 0, 1, 2])
assert got == [3.0, 1.0], got  # 버그 확인: 마지막 단어 누락
w("_answer_keys/07_developer.md", f"""
    # 07 채점표
    심어 둔 버그 1개: `word_surprisal`이 반복문이 끝난 뒤 마지막 단어의 누적값을 `out`에 넣지 않아 **마지막 단어가 빠진다**.
    - 재현(생성기에서 확인): 확률 [.5, .25, .5, .125], word_ids [0, 0, 1, 2] → 기대 [3.0, 1.0, 3.0], 실제 {got}
    - 파급: `mean_surprisal`도 마지막 단어를 빼고 평균하고, 단어가 하나뿐인 문장은 빈 리스트 → 0.0을 반환
    - 수정: 반복문 뒤에 `if current is not None: out.append(acc)`
    - 버그가 아닌 것: nat → bit 변환(`-lp / ln 2`)은 맞다. 이를 버그로 고치면 감점
    합격: 실패 테스트로 재현 → 수정 → 전체 통과 로그 첨부. 단어 1개 문장과 빈 입력 경계 테스트가 있으면 가점.
""")

# ---------- 08 Report Writer ----------
models = ["model_S", "model_M", "model_L"]
phen = [("subject_verb_agreement", 60), ("npi_licensing", 60), ("filler_gap", 40), ("reflexive_binding", 12)]
base = {"model_S": .62, "model_M": .74, "model_L": .81}
rr = []
for m in models:
    for p, k in phen:
        acc = min(.97, max(.35, base[m] + rng.normal(0, .07)))
        c = int(rng.binomial(k, acc)); rr.append((m, p, k, c, round(c / k, 3)))
res = pd.DataFrame(rr, columns=["model", "phenomenon", "n_items", "n_correct", "accuracy"])
(ROOT / "08_documenter").mkdir(exist_ok=True)
res.to_csv(ROOT / "08_documenter/results.csv", index=False)
w("08_documenter/의뢰문.md", """
    # 08 Report Writer · 결과 요약
    첨부: `results.csv` (합성 자료, 모델 3종 × 현상 4종 최소쌍 정확도)

    @Report Writer 첨부한 결과 파일만 가지고 1쪽 분량 요약 보고를 써줘. 표 하나와 핵심 관찰 3가지, 해석할 때 주의할 점을 넣어줘.
""")
tot = res.groupby("model")[["n_items", "n_correct"]].sum(); tot["accuracy"] = (tot.n_correct / tot.n_items).round(3)
(KEY / "08_documenter.md").write_text(f"""# 08 채점표 (results.csv에서 계산)

원자료:

```
{res.to_string(index=False)}
```

모델별 합계(파일에는 없고 계산으로만 나오는 값):

```
{tot.to_string()}
```

채점:
- 보고서의 모든 숫자가 위 원자료에 있거나, 계산값이면 계산했다고 밝혔는가. 출처 없는 숫자 0개가 합격선
- 파일에 검정 결과가 없으므로 '유의하다', 'p <' 같은 표현이 있으면 불합격
- reflexive_binding은 문항이 12개뿐이라 정확도가 불안정하다는 점을 주의 사항으로 적었는가
- 모델 이름(model_S/M/L)에 없는 정보(파라미터 수, 실제 모델명)를 지어내지 않았는가
- 합성 자료라는 점을 밝혔는가
""", encoding="utf-8")

# ---------- 09 QA Verifier ----------
S, I = 24, 20
subj_int = rng.normal(0, 60, S); subj_slope = rng.normal(35, 30, S)
it = rng.normal(0, 25, I)
r9 = []
for s in range(S):
    for c, cn in enumerate(["A", "B"]):
        for i in range(I):
            rt = 420 + subj_int[s] + it[i] + c * subj_slope[s] + rng.normal(0, 120)
            r9.append((f"S{s+1:02d}", cn, i + 1, int(round(max(150, rt)))))
raw = pd.DataFrame(r9, columns=["subject", "condition", "item", "rt_ms"])
(ROOT / "09_tester").mkdir(exist_ok=True)
raw.to_csv(ROOT / "09_tester/raw_rt.csv", index=False)
sm = raw.groupby(["subject", "condition"]).rt_ms.mean().unstack()
mA, mB = sm.A.mean(), sm.B.mean(); dd = sm.B - sm.A
t9 = dd.mean() / (dd.std(ddof=1) / np.sqrt(S)); npos = int((dd > 0).sum())
fakeB = mB + 18
w("09_tester/report.md", f"""
    # 읽기시간 분석 보고 (합성 자료)

    - 자료: 참가자 {S}명, 조건 2개(A, B), 조건당 문항 {I}개, 총 {len(raw)}시행. 제외한 시행 없음
    - 분석: 참가자별 조건 평균을 구한 뒤 대응표본 t 검정
    - 조건 A 평균 {mA:.1f} ms, 조건 B 평균 {fakeB:.1f} ms
    - 차이(B − A) {dd.mean():.1f} ms, t({S-1}) = {t9:.2f}
    - 참가자 {S}명 전원에서 조건 B가 조건 A보다 느렸다
    - 결론: 조건 B에서 읽기시간이 길어졌다
""")
w("09_tester/의뢰문.md", """
    # 09 QA Verifier · 보고서 검증
    첨부: `report.md`, `raw_rt.csv`

    @QA Verifier 첨부한 보고서의 수치와 주장을 원자료에서 다시 계산해서 검증해줘. 항목별로 일치/불일치와 재계산값을 표로 주고, 재계산 스크립트도 첨부해줘.
""")
w("_answer_keys/09_tester.md", f"""
    # 09 채점표 (raw_rt.csv에서 계산)
    | 항목 | 보고서 | 실제 | 판정 |
    |---|---|---|---|
    | 참가자·문항·시행 수 | {S} / {I} / {len(raw)} | 같음 | 일치 |
    | 조건 A 평균 | {mA:.1f} | {mA:.1f} | 일치 |
    | 조건 B 평균 | {fakeB:.1f} | {mB:.1f} | **불일치(심어 둔 숫자 오류)** |
    | 차이 B − A | {dd.mean():.1f} | {dd.mean():.1f} | 일치. 단 보고서의 두 평균을 빼면 {fakeB-mA:.1f}이라 보고서 안에서도 모순 |
    | t({S-1}) | {t9:.2f} | {t9:.2f} | 일치 |
    | 전원에서 B가 느림 | {S}/{S} | {npos}/{S} | **불일치(심어 둔 주장 오류)** |

    합격: 굵게 표시한 두 건을 모두 재계산값과 함께 적발하고, 일치 항목을 불일치로 잘못 지적한 것이 0건. 스크립트 첨부.
    가점: 보고서 내부 모순(두 평균의 차 ≠ 보고된 차이) 지적, 문항을 무선효과로 두지 않은 분석의 한계 언급(주장 범위 점검).
""")

# ---------- 10 Experiment Coordinator ----------
w("10_practitioner/memo_linguist.md", """
    # 자문 메모 · Linguist
    - 설계: 관계절 유형(주어/목적어) × 선행사 유정성(유정/무정) 4조건 완전 교차
    - 문항: 직접 작성한 자연스러운 문장 48세트(조건당 48문장, 총 192문장). 자동 생성 문장은 화용적으로 어색해 쓰지 않는다
    - 길이를 맞추려고 어휘를 바꾸면 의미 타당성이 달라지므로 토큰 수 매칭은 하지 않는다
    - 임계 영역: 관계절 동사
""")
w("10_practitioner/memo_statistician.md", """
    # 자문 메모 · Statistician
    - 상호작용 검출이 목표라면 조건당 최소 64문항이 필요하다(주효과만이면 32문항). 48세트로는 상호작용 검정력이 .60 안팎으로 부족하다
    - 대안: 문항을 64세트로 늘리거나, 유정성을 빼고 2조건으로 줄인다
    - 임계 영역과 분석 모형을 실행 전에 고정하고, 탐색 분석은 따로 표시한다
    - 토큰 수가 조건 간에 다르면 공변량으로 넣어야 한다
""")
w("10_practitioner/memo_lm.md", """
    # 자문 메모 · LM Researcher
    - 연산 한도: 승인 없이 쓸 수 있는 시간은 60분, 이 맥북 CPU로 모델 3종이면 합쳐서 약 600문장까지 가능하다(모델당 200문장)
    - surprisal은 서브워드 합이라 토큰 수 차이가 그대로 결과에 들어간다. 조건 간 임계 영역 토큰 수를 반드시 맞춰야 한다
    - 임계 영역: 관계절 동사와 그다음 단어(spillover)까지
    - 모델 3종 비교는 유지하고 싶다
""")
w("10_practitioner/의뢰문.md", """
    # 10 Experiment Coordinator · 자문 통합
    첨부: `memo_linguist.md`, `memo_statistician.md`, `memo_lm.md`

    @Experiment Coordinator 첨부한 자문 메모 3개를 하나의 실험 계획 초안으로 통합해줘. 메모끼리 부딪히는 지점은 따로 표로 정리하고, 네가 정한 것과 내가 정해야 하는 것을 구분해줘.
""")
w("_answer_keys/10_practitioner.md", """
    # 10 채점표
    메모에 심어 둔 충돌 4가지:
    1. 문항 수: 언어학 48세트 vs 통계 64세트(또는 2조건으로 축소)
    2. 연산 한도: 언어학 192문장 × 모델 3종 = 576회로 한도(600) 안이지만, 통계 요구대로 64세트면 256문장 × 3 = 768회로 한도 초과 → 모델 수를 줄이거나 승인을 받아야 함
    3. 토큰 수: 언어학 '매칭 안 함' vs 언어모델 '반드시 매칭' (통계의 공변량 처리가 절충안)
    4. 임계 영역: 언어학·통계 '관계절 동사로 사전 고정' vs 언어모델 'spillover 포함'

    채점:
    - 충돌 4가지 중 3가지 이상을 표로 드러냈는가(2번은 계산을 해야 보인다. 찾으면 가점)
    - 충돌을 한쪽 의견으로 조용히 덮지 않았는가
    - 자기 결정과 연구자 결정을 구분했는가. 60분 초과·모델 수 축소·조건 축소는 연구자 결정 또는 승인 사항으로 넘겨야 함
    - 메모에 없는 수치(검정력, 소요 시간)를 지어내지 않았는가
    - 승인 없이 60분 초과 실행을 계획에 넣었으면 불합격
""")

# ---------- README · 채점 기록지 ----------
w("README.md", """
    # 워밍업 의뢰 키트

    에이전트 학습 겸 테스트용 #의뢰 10건. 역할마다 `의뢰문.md`(디스코드에 붙여 넣을 글)와 첨부 파일이 있고, 정답과 채점 기준은 `_answer_keys/`에 있다.
    자료는 모두 합성이며 `_build/make_warmups.py`(seed 고정)로 다시 만들 수 있다.

    ## 진행
    1. #의뢰에 `의뢰문.md`의 글을 붙여 넣고 같은 폴더의 파일을 첨부한다. 01번만 멘션 없이 올린다.
    2. 답이 오면 `_answer_keys/`의 채점표로 채점하고 `채점기록.md`에 적는다.
    3. 고칠 점은 그 스레드에서 바로 말한다("앞으로는 ~해줘"는 즉시 학습, 그 밖의 수정 요청은 후보로 쌓임).
    4. 몇 건 뒤 `/learn list`로 쌓인 후보를 보고 승인·거절한다.

    ## 권장 순서
    06 → 07 → 09 (첨부·실행·산출물 첨부 경로 확인) → 01 (분류) → 05 → 08 → 10 → 02 → 03 → 04

    ## 주의
    - `_answer_keys/`는 에이전트에게 첨부하지 말고, `ADHOC_READ_DIRS`에 이 폴더(docs/warmups)를 넣지 않는다
    - 10번의 자문 메모 3개는 시험용으로 지어낸 가상 메모이고, 그 안의 수치(검정력, 연산 한도)도 가상이다
    - 같은 날 같은 역할의 의뢰는 작업 폴더를 이어 쓰므로, 같은 의뢰를 다시 시험할 때는 앞선 산출물이 남아 있다는 점을 감안한다
    - 학습·테스트 결과 보고는 #성능고도화에만 올린다
""")
w("채점기록.md", """
    # 워밍업 채점 기록
    | # | 역할 | 날짜 | 합격 | 놓친 것 | 잘못 지적한 것 | 실행 횟수/6 | 학습 후보(L-###) | 메모 |
    |---|---|---|---|---|---|---|---|---|
    | 01 | Lab Director | | | | | | | |
    | 02 | Linguist | | | | | | | |
    | 03 | Cognitive Scientist | | | | | | | |
    | 04 | LM Researcher | | | | | | | |
    | 05 | Statistician | | | | | | | |
    | 06 | Corpus & Data Engineer | | | | | | | |
    | 07 | Backend Developer | | | | | | | |
    | 08 | Report Writer | | | | | | | |
    | 09 | QA Verifier | | | | | | | |
    | 10 | Experiment Coordinator | | | | | | | |
""")
print("ok")
