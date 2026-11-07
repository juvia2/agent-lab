# 인지·뇌과학 연구원 테스트 결과

## 자문 요청
한국어 주격/대격 관계절 × LLM surprisal ↔ 인간 읽기시간 비교 실험

---

## 인지과학 자문

### 연결 가설

본 실험의 이론적 토대는 **Surprisal Theory**(Hale 2001; Levy 2008)이다. 이 이론에 따르면, 단어 w의 처리 난이도는 문맥이 주어졌을 때 그 단어의 놀람값(surprisal), 즉 −log P(w|context)에 비례한다. 이를 인간 읽기시간과 LLM surprisal의 연결 가설로 구체화하면:

**H_link**: LLM이 산출하는 토큰별 surprisal이 인간 독자의 영역별(region-by-region) 읽기시간과 양의 선형 관계를 보인다면, 해당 LLM이 인간과 유사한 *계산 수준*(Marr's computational level)의 예측 구조를 학습했다고 추론할 수 있다.

한국어 관계절의 경우 구체적으로:
- **주격 관계절** (예: `[_i 밥을 먹은] 아이_i가`): 관계절 내 주어 공백(subject gap) → filler-gap 의존성이 짧고, DLT 기준 통합 비용이 낮음
- **대격 관계절** (예: `[아이가 _i 먹은] 밥_i을`): 관계절 내 목적어 공백(object gap) → filler-gap 의존성이 길고, 중간에 개입하는 명사구(아이가)가 유사성 간섭(similarity-based interference)을 유발

따라서 인간 읽기시간 선행연구의 일반적 예측은 **대격 관계절의 관계절 동사(및 핵명사) 영역에서 처리 비용이 더 높다**는 것이다. LLM surprisal이 이 비대칭을 반영하는지가 핵심 검증 포인트이다.

단, 한 가지 중요한 단서: 한국어는 핵어 후치(head-final) 언어이므로, 관계절이 핵명사 앞에 위치하여 영어와 처리 방향이 다르다. 이로 인해 영어 기반 이론(DLT, cue-based retrieval)의 예측이 한국어에 직접 적용되지 않을 수 있다. 특히 **한국어 주격 관계절이 오히려 더 어렵다**는 반대 패턴이 일부 연구(Kwon et al. 2010)에서 보고되었으므로, 방향 예측에 주의가 필요하다.

### 인간 데이터 대응

#### 옵션 A: 기존 데이터셋 활용 (권장)
한국어 관계절 읽기시간 데이터가 이미 공개된 연구를 활용한다:
- **Kwon et al. (2010)**: 한국어 주격/대격 관계절 자기조절 읽기 실험. 영역별 읽기시간 보고. *주격 관계절 난이도 우세* 패턴 보고.
- **Yun et al. (2015)**: 한국어 관계절 시선추적 데이터. 첫 고정시간(FFD), 주시시간(GD), 회귀(regression) 측정.
- 이들 연구의 자극 세트와 *동일하거나 유사한* 자극으로 LLM surprisal을 산출하면, 직접 비교가 가능하다.

#### 옵션 B: 새 인간 데이터 수집
조건당 20문항이면 파이럿으로는 충분하나, 혼합효과모델 적합을 위해 최소 40명 이상의 피험자가 필요하다(power analysis 기반, 예상 효과크기 d ≈ 0.3–0.5).
- **패러다임**: 자기조절 읽기(SPR, moving-window)
  - 이유: 온라인 실험이 용이, 영역별 측정 가능, 선행연구와 비교 가능
- **측정값**: 각 영역의 읽기시간(ms), 이해문제 정확도
- **보정**: 잔차 읽기시간(residual RT) — 단어 길이와 로그 빈도를 회귀한 잔차 사용

**추천**: 옵션 A로 진행하되, 기존 연구의 자극이 확보되지 않으면 새 자극으로 옵션 B를 소규모 파이럿으로 수행.

### 분석 설계

#### 분석 1: LLM surprisal 조건 효과 (1차 분석)
LLM surprisal에서 관계절 유형(주격 vs 대격)의 효과가 나타나는지 확인한다.

```
# 혼합효과모델 (LMM)
surprisal ~ rc_type * region + (1 + rc_type | item)
```
- `rc_type`: 주격(SRC) vs 대격(ORC), 대비코딩(−0.5, +0.5)
- `region`: 관계절 주어 / 관계절 목적어 / 관계절 동사 / 핵명사 / 핵명사+1 (spillover)
- 무선효과: 문항(item)의 절편 + 조건 기울기. 피험자 무선효과는 LLM에 불필요(동일 모델이 모든 문항 처리).
- **핵심 검정**: `rc_type × region` 상호작용 — 특정 영역에서 조건 간 surprisal 차이가 유의한가

#### 분석 2: LLM surprisal ↔ 인간 RT 상관 (2차 분석)
기존 인간 데이터가 확보된 경우:

```
# 인간 RT 예측 모델
RT ~ surprisal_LLM + word_length + log_freq + (1 + surprisal_LLM | subject) + (1 | item)
```
- `surprisal_LLM`: LLM이 산출한 어절별 surprisal (고정효과)
- `word_length`, `log_freq`: 통제 변인
- **핵심 지표**: surprisal_LLM의 고정효과 계수(β)가 유의하게 양수인가
- **모델 비교**: surprisal 포함 모델 vs 미포함 모델의 △AIC / △LogLik

#### 분석 3: 모델 간 비교 (보조 분석)
여러 LLM을 사용할 경우, 어느 모델의 surprisal이 인간 RT를 더 잘 예측하는지:

```
# 각 모델별로 분석 2를 반복
△LogLik_model_A vs △LogLik_model_B
```
- psychometric predictive power 비교
- 모델 크기·한국어 학습 데이터 비율과 예측력의 관계 탐색

#### 효과크기
- Cohen's d: 조건 간 surprisal 차이의 표준화 효과크기
- 모델 R²: surprisal 변수가 설명하는 RT 분산 비율
- 95% 신뢰구간(또는 베이지안이면 95% CrI) 필수 보고

### 해석 범위

#### 해석 가능한 것
1. LLM surprisal이 한국어 관계절 유형에 따라 체계적으로 달라지는지 (모델의 통사적 민감도)
2. LLM surprisal과 인간 읽기시간의 상관 정도 (행동 수준 유사성)
3. 여러 모델 중 어느 것이 인간 패턴에 더 가까운지 (모델 비교)

#### 해석할 수 없는 것 (주의 — Marr 수준 구분)
1. **알고리즘 수준 동일성**: surprisal 패턴이 유사하더라도, LLM이 인간과 같은 *과정*(incremental parsing, working memory retrieval)을 거친다고 결론 내릴 수 없다. 이는 Marr의 계산 수준(what) 유사성이지 알고리즘 수준(how) 유사성이 아니다.
2. **인과적 설명**: LLM surprisal이 인간 RT를 예측한다 해도, LLM이 인간 처리를 *설명*한다는 주장은 과잉이다. 예측력(predictive power)과 설명력(explanatory power)은 다르다.
3. **일반화**: 결과는 (a) 테스트한 관계절 유형, (b) 사용한 LLM 모델·크기, (c) 한국어에 한정된다. "LLM이 관계절을 '이해'한다"는 주장은 불가하다.

#### 대안 설명 (최소 2가지)
- **대안 1**: LLM의 surprisal 패턴이 인간과 유사한 것은, 둘 다 *같은 학습 데이터 분포*(한국어 텍스트)에 노출되었기 때문이다. 즉 공유하는 것은 인지 메커니즘이 아니라 통계적 규칙성이다.
- **대안 2**: LLM의 surprisal 차이가 *형태·어휘적 요인*(빈도, n-gram)에 의한 것이지, 통사 구조적 민감도를 반영하지 않을 수 있다. n-gram 기반 surprisal 모델과의 비교가 이를 변별한다.

### 선행연구 참조

#### 한국어 관계절 인간 처리
- Kwon, N., Gordon, P. C., Lee, Y., Kluender, R., & Polinsky, M. (2010). Cognitive and linguistic factors affecting subject/object asymmetry: An eye-tracking study of pre-nominal relative clauses in Korean. *Language*, 86(3), 546–582.
- Yun, J., Chen, Z., Hunter, T., Whitman, J., & Hale, J. (2015). Uncertainty in processing relative clauses across East Asian languages. *Journal of East Asian Linguistics*, 24(2), 113–148.

#### LLM surprisal과 인간 읽기시간
- Wilcox, E. G., Gauthier, J., Hu, J., Qian, P., & Levy, R. (2020). On the predictive power of neural language models for human real-time comprehension behavior. *CogSci 2020*.
- Shain, C., Meister, C., Pimentel, T., Cotterell, R., & Levy, R. (2022). Large-scale evidence that language models can capture core properties of human sentence processing. *arXiv:2210.12214*.
- Oh, B.-D., & Schuler, W. (2023). Why does surprisal from larger language models provide a poorer fit to human reading times? *TACL*, 11, 336–350.

#### 한국어 LLM 평가
- Park, S., et al. (2021). KLUE: Korean Language Understanding Evaluation. *NeurIPS 2021 Datasets and Benchmarks*.

---

## 테스트 평가 메모

### 프로파일 적용 체크리스트
| 항목 | 적용 여부 | 비고 |
|------|----------|------|
| 연결 가설 제시 | ✓ | Surprisal Theory 기반 + DLT + cue-based retrieval |
| 인간 데이터 제안 | ✓ | 기존 데이터(옵션 A) + 새 수집(옵션 B) 구분 |
| 통계 모델 수식 제시 | ✓ | LMM 3개 수준, 대비코딩 명시, 무선효과 구조 |
| 해석 한계 명시 | ✓ | Marr 수준 구분, 과잉 인지화 경계, 대안 설명 2개 |
| 선행연구 참조 | ✓ | 한국어 관계절 + LLM-인간 비교 + 한국어 LLM |
| 과잉 인지화 경계 | ✓ | '이해'에 인용부호, 예측력 ≠ 설명력 구분 |
| 수준 구분 명확화 | ✓ | 계산 수준 유사성으로 한정 |
| 대안 설명 제시 | ✓ | 통계 규칙성 공유설 + 형태·어휘적 혼입설 |
| 일반화 제한 | ✓ | 관계절 유형, 모델 크기/종류, 한국어 한정 명시 |
| 출력 형식 준수 | ✓ | 연결가설/인간데이터/분석설계/해석범위/선행연구 |

### 전문성 깊이 평가
- **강점**: 한국어 관계절의 주격 우세 효과(Kwon et al. 2010 반영)라는 영어와 반대되는 패턴을 명시적으로 경고한 점이 도메인 특화 지식을 보여줌. LMM 수식에서 LLM 실험 시 피험자 무선효과 불필요라는 실용적 판단 포함. Oh & Schuler (2023)의 "큰 모델의 surprisal이 오히려 인간 RT를 덜 잘 예측"하는 역설적 결과 인용.
- **잠재적 개선점**: 베이지안 분석의 사전분포 구체 설정(weakly informative prior 추천 등)은 분량상 생략됨. 온라인 실험 플랫폼(Gorilla, PCIbex)의 한국어 지원 현황에 대한 구체적 코멘트 가능.
