# Cognitive Scientist 학습 노트 — 최근 3년 논문 15편

- 학습일: 2026-11-07 · 담당: Cognitive Scientist (인지·뇌과학 연구원)
- 교차 영역: 언어모델 서프라이절·표상과 인간 문장처리(읽기시간·ERP·fMRI)의 대응
- 기간: 2023-11 ~ 2026-11 게재 기준 (프리프린트가 더 이른 논문은 표시)
- 읽기 범위: 초록·공개 본문·웹 검색으로 확인한 내용 기준. 원문 전체 정독은 아니며, 수치는 확인된 것만 적었다.

<!-- DIGEST START -->
## 핵심 요약
- 서프라이절-읽기시간 관계는 대규모·다언어 데이터에서 로그 형태로 견고하지만, 구문 중의성 해소 같은 국소적 난이도는 서프라이절만으로 크게 과소예측된다.
- "큰 모델일수록 덜 인간적"이라는 결과는 최종층만 본 탓일 수 있다. 중간층 서프라이절은 큰 모델에서도 인간 데이터와 잘 맞는다.
- 단어 확률 계산은 토크나이저 경계(특히 앞 공백 토큰)를 제대로 처리해야 하며, 한국어 어절 합산에도 같은 원리가 적용된다.
- 한국어 연구에서 LLM 서프라이절은 형태통사 위반에는 민감하지만, 담화 현저성·사회화용적 제약은 반영하지 못한다.
- 뇌 정렬은 형식적 언어 능력과 주로 연결되고, 기능적 능력(추론·지식)과는 약하다.

> 주의: 아래 관계절 관련 제안은 2026-11-06 에이전트 점검용 가상 시나리오에서 나온 것이다. 사용자의 실제 실험 주제·계획으로 확인되지 않았다.

## 향후 연구·연구실 운영에 적용할 후보 아이디어
1. 관계절 실험에서 최종층 서프라이절과 중간층(logit-lens) 서프라이절을 함께 보고하고, 어느 층이 인간 패턴과 맞는지 비교한다.
2. 서프라이절만으로 관계절 비대칭을 설명한다고 주장하지 않는다. 기억 기반 지표(DLT 거리, cue-based 간섭)를 별도 예측변수로 넣어 비교한다.
3. 어절 확률은 Pimentel & Meister 방식으로 공백·경계 보정을 한 뒤 합산한다(Backend Developer와 구현 기준 공유).
4. 한국어 결과 해석 시 담화·사회화용 요인(경어, 화제성)은 모델이 못 잡는 영역으로 명시한다.
5. 베이스 모델과 지시조정 모델의 심리측정 예측력을 따로 보고한다.
<!-- DIGEST END -->

## 논문별 노트

### 1. Large-scale evidence for logarithmic effects of word predictability on reading time
Shain, Meister, Pimentel, Cotterell, Levy · PNAS 121, 2024
- **정리**: 여러 대규모 읽기시간 데이터와 다양한 언어모델 확률로 예측가능성-읽기시간 관계의 함수 형태를 검증해, 로그(=서프라이절) 형태가 일관되게 지지된다고 보고했다.
- **분석**: 서프라이절 이론의 "연결 함수" 논쟁을 데이터 규모로 정리한 기준 논문. 다만 대상은 주로 자연 독해이며 특정 구문 난이도는 다루지 않는다.
- **아이디어**: ① 우리 분석에서 서프라이절을 선형 예측변수로 쓰는 근거로 인용 ② 비선형(GAM) 적합으로 선형성 검정을 한 번 같이 돌려 보고 ③ 한국어 자연 독해 코퍼스가 있으면 같은 검정을 반복해 한국어 일반화 여부 확인

### 2. Large Language Models Are Human-Like Internally
Kuribayashi 외 · TACL 13, 2025 (arXiv 2502.01615)
- **정리**: 큰 LM의 최종층 서프라이절은 인간 읽기 데이터와 덜 맞지만, 중간층에서 어휘 공간으로 디코딩한 서프라이절은 큰 모델에서도 읽기시간·N400을 잘 예측한다고 보였다.
- **분석**: "모델 크기 역설"을 층 선택의 문제로 재해석했다. 해석 단계에서 "큰 모델은 인지적으로 비현실적"이라는 결론을 경계하게 해 준다.
- **아이디어**: ① 관계절 실험에 층별 서프라이절 곡선을 추가 산출 ② 핵어 명사 영역에서 SRC/ORC 차이가 층에 따라 어떻게 변하는지 그림으로 보고 ③ 층 선택은 사전 등록(계획서에 미리 고정)해 사후 선택 편향 방지

### 3. Frequency Explains the Inverse Correlation of LLMs' Size, Training Data Amount, and Surprisal's Fit to Reading Times
Oh & Schuler · EACL 2024
- **정리**: 큰 모델이 읽기시간 예측에서 나빠지는 현상이 주로 저빈도 단어에서 모델이 인간보다 지나치게 잘 예측하기 때문임을 보였다.
- **분석**: 모델-인간 괴리의 원인을 빈도로 좁혀 준다. 우리 자극의 핵심 어휘 빈도 통제가 왜 중요한지에 대한 근거.
- **아이디어**: ① 관계절 핵심 명사·동사의 빈도 구간별로 서프라이절 차이를 분해 ② Corpus & Data Engineer와 빈도 매칭 기준을 이 결과에 맞춰 설정 ③ 빈도를 공변량으로 넣은 모형과 안 넣은 모형을 비교 보고

### 4. Transformer-Based LM Surprisal Predicts Human Reading Times Best with About Two Billion Training Tokens
Oh & Schuler · Findings of EMNLP 2023 (2023-12)
- **정리**: 학습 체크포인트를 따라가며 보니, 읽기시간 예측력은 학습 토큰 약 20억 개 부근에서 최고였다가 이후 떨어진다고 보고했다.
- **분석**: "더 학습한 모델 = 더 인간적"이 아니라는 근거. 학습 궤적 공개 모델(Pythia, OLMo)의 가치를 보여 준다.
- **아이디어**: ① 체크포인트가 공개된 모델로 관계절 효과의 학습 궤적을 그려 보기 ② 한국어 모델은 체크포인트가 드물어 한계로 명시 ③ LM Researcher와 OLMo 체크포인트 활용 가능성 검토

### 5. Large-scale benchmark yields no evidence that language model surprisal explains syntactic disambiguation difficulty
Huang, Wilcox 외 · Journal of Memory and Language 137, 2024
- **정리**: 대규모 정원길 문장 벤치마크에서 LM 서프라이절은 중의성 해소 비용의 크기를 크게 과소예측하고, 구문 간 난이도 순서도 잘 맞추지 못했다.
- **분석**: 관계절 같은 구조적 난이도를 서프라이절 하나로 설명하려는 시도의 한계를 직접 보여 준다. 우리 연구 질문과 가장 가까운 반례 근거.
- **아이디어**: ① 보고서 한계 절에 이 결과를 반드시 인용 ② 서프라이절 차이의 "방향"과 "크기"를 분리해 해석 ③ 인간 데이터와 비교할 때 효과 크기 비율(모델/인간)을 따로 보고

### 6. The Effect of Surprisal on Reading Times in Information Seeking and Repeated Reading
Gruteke Klein, Meiri, Shubi, Berzak · CoNLL 2024
- **정리**: 정보 탐색 읽기와 반복 읽기에서는 일반 서프라이절의 예측력이 떨어지고, 과제 맥락을 넣은 서프라이절도 반복 읽기는 잘 설명하지 못했다.
- **분석**: 서프라이절이 "일반 독해" 조건에 묶인 지표임을 보여 준다. 실험 과제 설계가 해석 범위를 결정한다.
- **아이디어**: ① 비교 대상 인간 데이터의 읽기 과제 유형(자기조절 읽기·안구운동·과제 유무)을 계획서에 명시 ② 과제 유형이 다른 데이터끼리 직접 비교 금지 ③ 반복 노출 문항(연습 문항) 데이터는 분석에서 분리

### 7. Computational surprisal is not enough: Discourse prominence modulates human eye-movement patterns but not GPT expectations in Korean
Kwon 외 · Findings of EMNLP 2026
- **정리**: 한국어 주어-서술어 경어 일치에서 인간 안구운동은 방해어의 담화 현저성에 따라 달라졌지만, 한국어 가능 모델 3개의 서프라이절은 경어 불일치에는 반응해도 현저성에는 반응하지 않았다.
- **분석**: 우리 연구실과 언어·방법이 가장 가까운 최신 논문. 한국어에서 서프라이절이 놓치는 요인을 구체적으로 보여 준다.
- **아이디어**: ① 관계절 실험 후속으로 경어 일치 간섭 실험을 후보 주제로 제안 ② 화제·주어 현저성을 조작 변수로 넣는 설계 검토 ③ 같은 연구진의 인간 안구운동 데이터 공개 여부 확인(비교용 인간 데이터 확보)

### 8. Strong Prediction: Language Model Surprisal Explains Multiple N400 Effects
Michaelov, Bardolph, Van Petten, Bergen, Coulson · Neurobiology of Language 5, 2024
- **정리**: 여러 고전적 N400 효과(의미 관련성, 예측가능성 등)를 LM 서프라이절 하나로 상당 부분 설명할 수 있음을 보였다.
- **분석**: 행동 지표뿐 아니라 ERP에도 서프라이절이 강한 예측변수임을 보여 주지만, 설명된다는 것이 같은 메커니즘이라는 뜻은 아니다(Marr 수준 구분 필요).
- **아이디어**: ① 해석 시 "설명력"과 "메커니즘 동일성"을 구분하는 문장 템플릿을 보고서 규칙에 추가 ② 한국어 ERP 관계절 데이터(Kwon 외 2013)와 서프라이절 비교 가능성 검토 ③ N400과 P600 예측을 분리해 보는 후속 설계

### 9. From Language to Cognition: How LLMs Outgrow the Human Language Network
AlKhamissi 외 · arXiv 2503.01830, 2025
- **정리**: 학습 초기에 뇌 언어망 정렬이 빠르게 오르고 이후 정체되며, 정렬은 형식적 언어 능력과 주로 연결되고 기능적 능력과는 약하게 연결된다고 보고했다.
- **분석**: "언어 능력"과 "사고 능력"을 나눠 보는 관점을 뇌 데이터로 지지한다. 모델이 좋아질수록 인간 언어망과 멀어질 수 있음을 시사.
- **아이디어**: ① 우리 결과 해석에서 형식(구문) 수준 주장과 기능(이해) 수준 주장을 분리 ② 모델 선택 시 "더 큰 모델이 더 인간적"이라는 가정을 버림 ③ 학습 단계별 비교 설계 시 이 논문 지표 참고

### 10. Driving and suppressing the human language network using large language models
Tuckute 외 · Nature Human Behaviour 8, 2024
- **정리**: LLM 기반 인코딩 모델로 언어망 반응을 최대·최소화할 문장을 골라 실제 fMRI에서 예측대로 반응이 커지고 작아짐을 확인했다.
- **분석**: 모델을 "자극 설계 도구"로 쓴 대표 사례. 놀라움·문법성 등 문장 속성이 반응을 좌우한다.
- **아이디어**: ① 자극 선정에 모델 예측을 쓰되, 선정 기준과 평가 지표를 분리해 순환 논리 방지 ② 극단 자극(최대/최소 서프라이절)을 필러로 활용 ③ Corpus & Data Engineer와 모델 기반 자극 필터링 절차 정리

### 11. Artificial neural network language models predict human brain responses to language even after a developmentally realistic amount of training
Hosseini 외 · Neurobiology of Language 5, 2024
- **정리**: 아동이 경험하는 수준(약 1억 단어)만 학습한 모델도 fMRI 언어 반응을 상당히 예측했다.
- **분석**: 데이터 효율과 인지 모델링을 잇는 근거. BabyLM 계열 소형 모델을 인지 모델로 쓸 수 있다는 정당화.
- **아이디어**: ① 한국어 소량 학습 모델로 관계절 효과가 생기는지 보는 학습가능성 실험 후보 ② 학습량-효과 곡선을 그리는 설계 ③ LM Researcher와 소형 모델 학습 자원 추정

### 12. Language is primarily a tool for communication rather than thought
Fedorenko, Piantadosi, Gibson · Nature 630, 2024
- **정리**: 신경과학·행동 증거를 근거로 언어망은 사고 자체가 아니라 의사소통에 특화돼 있다고 주장했다.
- **분석**: LLM 결과를 "사고 능력"으로 확장 해석하지 말아야 할 이론적 근거. 입장 논문이라 반론도 함께 봐야 한다.
- **아이디어**: ① 해석 원칙(과잉 인지화 금지)의 이론적 배경으로 인용 ② QA Verifier의 과잉 주장 점검 목록에 "언어=사고 비약" 항목 추가 ③ 반대 입장 문헌도 같이 제시해 균형 유지

### 13. On the Proper Treatment of Tokenization in Psycholinguistics
Giulianelli, Malagutti, Gastaldi, DuSell, Vieira, Cotterell · EMNLP 2024
- **정리**: 토큰 단위 모델 확률을 문자·영역 단위 확률로 바꾸는 올바른 방법을 제시하고, 관심 영역 단위 서프라이절이 심리측정 예측에 더 낫다고 보였다.
- **분석**: 한국어처럼 토큰과 어절이 어긋나는 언어에서 특히 중요하다. 우리 어절 합산 방식의 이론적 근거.
- **아이디어**: ① 서프라이절 계산 단위를 "어절"과 "관심 영역"으로 이중 산출 ② 토크나이저가 다른 모델 간 비교 시 문자 단위 정규화 적용 ③ Backend Developer 코드 검토 기준에 포함

### 14. How to Compute the Probability of a Word
Pimentel & Meister · EMNLP 2024
- **정리**: 단어 앞에 공백이 붙는 토크나이저에서는 흔한 계산법이 단어 확률을 틀리게 구하며, 다음 단어의 시작 공백까지 고려한 보정이 필요함을 보였다.
- **분석**: 작은 구현 차이가 서프라이절 값을 체계적으로 바꾼다. 재현성·검증에 직접 영향.
- **아이디어**: ① 어절 서프라이절 계산에 공백 보정 적용 여부를 결과 파일 메타데이터에 기록 ② 보정 전후 차이를 검증 단계에서 비교 ③ 한국어 SentencePiece(▁ 표시) 모델에서 같은 문제가 생기는지 점검

### 15. Psychometric Predictive Power of Large Language Models
Kuribayashi, Oseki, Baldwin · Findings of NAACL 2024
- **정리**: 지시조정 모델이 같은 크기의 베이스 모델보다 읽기시간 예측력이 낮은 경우가 많고, 프롬프트로 이를 쉽게 보완하기 어렵다고 보고했다.
- **분석**: 우리가 쓸 모델(지시조정 버전 다수)에 직접 해당. 모델 버전 선택이 결과를 좌우한다.
- **아이디어**: ① 서프라이절 측정은 기본적으로 베이스 모델 사용, 지시조정 모델은 비교군으로만 ② 계획서에 모델 버전(base/instruct)을 필수 항목으로 추가 ③ 한국어 모델의 베이스 버전 공개 여부를 LM Researcher가 사전 확인
