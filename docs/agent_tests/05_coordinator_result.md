# 실험 실무 담당 — 테스트 응답

## 자문 통합 검토

### 자문 간 충돌 여부
세 전문가 자문 사이에 직접적 충돌은 없음. 통합 시 조정한 사항:
- **영역 분할 세부화**: 언어학 자문에서 관심 영역을 "관계절 동사"와 "주절 주어"로 지정했으나, 인지과학 자문의 spillover 분석을 위해 관심 영역 전후 2개 어절도 영역으로 포함.
- **인간 데이터 비교 방식**: 인지과학 자문에서 Kwon et al. (2010) 등 기존 SPR 데이터 참조를 제안. 직접 인간 실험은 수행하지 않으므로, 선행연구 보고 수치와의 질적 비교(방향성 일치 여부)로 범위를 한정.
- **모델 수**: LM 연구 자문에서 Qwen 2.5 7B 단일 모델 추천. 비교 가능성을 위해 보조 모델(EXAONE 3.0 7.8B)을 선택적 추가로 계획에 포함(시간 여유 시 실행).

---

## 실험 계획서

### 실험 ID: EXP-2026-001
### 제목: 한국어 주격/대격 관계절의 LLM Surprisal 패턴과 인간 읽기시간 비교
### 연구 질문: 한국어 주격 관계절(SRC)과 대격 관계절(ORC)에서 LLM의 surprisal 차이가 인간의 읽기시간 차이와 동일한 방향을 보이는가?

### 가설:
  - H1: ORC의 관계절 동사 영역 surprisal이 SRC보다 유의하게 높다 (인간 읽기시간의 ORC 난이도 효과와 일치).
  - H0: SRC와 ORC 간 관계절 동사 영역 surprisal에 유의한 차이가 없다.

### 설계:
  - 독립변인: 관계절 유형 (2수준: SRC, ORC)
  - 종속변인: 어절별 surprisal (bits)
  - 통제변인: 어절 수(문장 길이), 어휘 빈도, 핵어 명사 생물성, 관계절 내 명사구 생물성
  - 설계 유형: within-item (각 항목이 SRC/ORC 두 조건 모두에 대응)

### 자극:
  - 조건 수: 2 (SRC, ORC)
  - 조건당 문항 수: 20
  - 필러 수: 40
  - 총 문장 수: 80 (실험 40 + 필러 40)
  - 배분: LLM 실험이므로 Latin square 불필요 — 모든 조건을 모델에 입력 (단, 조건 간 순서 효과 없음을 전제)
  - 자극 CSV 컬럼: `item_id`, `condition`, `sentence`, `region_pre2`, `region_pre1`, `region_rc_verb` (관심), `region_head_noun`, `region_main_subj` (관심), `region_main_verb`, `region_post1`

### 자극 예시 (언어학 자문 기반):
| item_id | condition | sentence |
|---------|-----------|----------|
| 1 | SRC | 기자를 ___ 만난 교수가 학생에게 자료를 보냈다 |
| 1 | ORC | 기자가 ___ 만난 교수가 학생에게 자료를 보냈다 |

- SRC: [NP-를 __t__ V-ㄴ] NP-가 ... (핵어 명사 = 관계절 주어)
- ORC: [NP-가 __t__ V-ㄴ] NP-가 ... (핵어 명사 = 관계절 목적어)

### 영역 분할 (어절 단위):
```
SRC 예: "기자를 | 만난 | 교수가 | 학생에게 | 자료를 | 보냈다"
         pre1   rc_verb head_noun  post1     post2   main_verb

ORC 예: "기자가 | 만난 | 교수가 | 학생에게 | 자료를 | 보냈다"
         pre1   rc_verb head_noun  post1     post2   main_verb
```
- 관심 영역 1: `rc_verb` (관계절 동사) — 관계절 유형 효과 예측 지점
- 관심 영역 2: `head_noun` (핵어 명사 = 주절 주어) — 재분석/통합 비용 예측 지점

### 분석 계획:
  - 기술 통계: 조건(SRC/ORC) × 영역별 surprisal 평균, 표준오차
  - 추론 통계:
    - 혼합효과모델: `surprisal ~ condition * region + (1 + condition | item_id)`
    - 관심 영역 개별 분석: `surprisal ~ condition + (1 | item_id)` (rc_verb, head_noun 각각)
    - 대비: ORC - SRC (양의 차이 = ORC가 더 어려움)
  - 모델 비교: △AIC로 condition 효과 유무 비교
  - 효과크기: Cohen's d (조건 간 surprisal 차이)
  - 인간 데이터 질적 비교: Kwon et al. (2010) 보고 RT 패턴 방향과 LLM surprisal 패턴 방향 일치 여부

### 코드 구성:
  - 데이터 생성: `scripts/generate_stimuli.py` — 자극 CSV 생성, 영역 분할
  - 모델 실행: `scripts/run_model.py` — Qwen 2.5 7B surprisal 계산 (MPS), 토큰→어절 집계
  - 분석: `scripts/analyze.py` — 혼합효과모델, 기술통계, 효과크기
  - 시각화: `scripts/plot_results.py` — 영역별 surprisal 선그래프 (조건별), 관심 영역 막대그래프
  - (선택) 보조 모델: `scripts/run_model_exaone.py` — EXAONE 3.0 비교 실행

### 예상 산출물:
  - `data/stimuli.csv` — 자극 데이터 (80문장, 영역 분할 포함)
  - `data/results_qwen25_7b_raw.csv` — 토큰별/어절별 surprisal 원데이터
  - `data/results_qwen25_7b_analyzed.csv` — 조건×영역 기술/추론 통계
  - `figures/EXP-2026-001_region_surprisal.png` — 영역별 surprisal 선그래프
  - `figures/EXP-2026-001_critical_region_bar.png` — 관심 영역 조건 비교 막대그래프
  - `reports/EXP-2026-001_report.md` — 최종 보고서

### 연산 예산:
  - 예상 토큰: ~160K (80문장 × 평균 ~20토큰 × 순방향 1회, 오버헤드 포함)
  - 예상 시간: ~15분 (Qwen 2.5 7B, MPS, 배치 처리)
  - 백엔드: `local` (Ollama, Qwen 2.5 7B Q4_K_M)
  - 보조: ~15분 추가 (EXAONE 3.0, 시간 여유 시)

### 승인 필요 사항:
  - [ ] 네트워크 접근: 불필요 (모델은 사전 다운로드 전제, `ollama pull qwen2.5:7b`)
  - [x] 호스트 실행: **필요** — MPS(Apple GPU) 사용을 위해 도커가 아닌 호스트에서 Ollama 실행
  - [ ] 60분 초과: 불필요 (예상 총 소요 ~30분)

### 실행 순서:
```
[1/6] generate_stimuli.py → data/stimuli.csv 생성 → 행·열 수 점검
[2/6] run_model.py → data/results_qwen25_7b_raw.csv → NaN/결측 점검
[3/6] analyze.py → data/results_qwen25_7b_analyzed.csv → 통계량 범위 점검
[4/6] plot_results.py → figures/ → 시각적 점검
[5/6] (선택) run_model_exaone.py → 보조 결과
[6/6] 결과 파일 → 전문가 3인 해석 요청 → 서류화 담당에게 보고서 작성 전달
```

### 중간 점검 기준:
| 단계 | 점검 항목 | 기준 |
|------|----------|------|
| 자극 생성 | CSV 행 수 | 실험 40행 + 필러 40행 = 80행 |
| 자극 생성 | 영역 컬럼 | 모든 영역 non-null |
| 모델 실행 | 결과 행 수 | 80문장 × 영역 수 ≥ 400행 |
| 모델 실행 | surprisal 범위 | 0 < surprisal < 30 (이상값 플래그) |
| 분석 | p값 범위 | 0 ≤ p ≤ 1 |
| 분석 | 효과크기 부호 | ORC > SRC → 양의 d |
