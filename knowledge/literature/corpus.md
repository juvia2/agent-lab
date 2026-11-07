# Corpus & Data Engineer 학습 노트 — 최근 3년 논문 15편

- 학습일: 2026-11-07 · 담당: Corpus & Data Engineer (코퍼스·데이터 전문가)
- 교차 영역: 한국어 토큰화·형태소, 사전학습 데이터 구성과 오염, 한국어 평가 자원, LLM 기반 자극·규범 생성
- 기간: 2023-11 ~ 2026-11 게재 기준 (프리프린트가 더 이른 논문은 표시)
- 읽기 범위: 초록·공개 본문·웹 검색으로 확인한 내용 기준. 원문 전체 정독은 아니며, 수치는 확인된 것만 적었다.

<!-- DIGEST START -->
## 핵심 요약
- 한국어 토큰화는 형태소 기반·자모 기반 등 언어 구조를 반영한 방식이 빈도 기반 BPE보다 효율·성능 면에서 유리하다는 결과가 쌓이고 있다.
- 평가 오염은 흔하며, 생성 기반 탐지(시간 여행), 확률 기반 탐지(Min-K% Prob), 데이터 검색 도구(WIMBD)로 점검할 수 있다.
- 공개 사전학습 데이터(Dolma, FineWeb, FineWeb2)는 정제 과정이 문서화돼 있어 자극 오염 점검과 빈도 추정에 활용할 수 있다.
- 한국어 평가 자원은 번역형에서 한국어 고유형(CLIcK, HAE-RAE, KMMLU, KoBALT)으로 이동 중이다.
- LLM으로 심리언어학 규범(친숙도 등)을 추정하는 방법이 유효성을 보이지만, 사람 평정으로 보정·검증해야 한다.

> 주의: 아래 관계절 관련 제안은 2026-11-06 에이전트 점검용 가상 시나리오에서 나온 것이다. 사용자의 실제 실험 주제·계획으로 확인되지 않았다.

## 향후 연구·연구실 운영에 적용할 후보 아이디어
1. 자극 문장마다 Min-K% Prob와 공개 코퍼스 n-gram 검색으로 오염 위험을 점검하고 결과를 CSV 열로 남긴다.
2. 모델별 어절-토큰 정렬표를 자동 생성하고, 형태소 경계와 토큰 경계 불일치 문항을 표시한다.
3. 빈도는 공개 코퍼스(FineWeb2 한국어 부분 등)와 국립국어원 자원을 함께 써서 출처별로 기록한다.
4. LLM 생성 자극·규범은 무작위 표본을 원어민이 검수하고, 검수 비율과 통과율을 보고한다.
5. 유명 예문은 쓰지 않고 새 문장을 만든다.
<!-- DIGEST END -->

## 논문별 노트

### 1. Morpheme Matters: Morpheme-Based Subword Tokenization for Korean Language Models
Lee, Park, Cho, Lee · EACL 2026 (Short)
- **정리**: 어절 사이·어절 안 분절을 모두 다루는 형태소 기반 하위어 토큰화(MoB)를 제안했고, 입력당 토큰 수가 줄고 한국어 과제 성능이 대체로 개선됐다.
- **분석**: 한국어 형태 구조를 토큰화에 반영하면 효율과 성능이 같이 좋아질 수 있음을 보여 준다.
- **아이디어**: ① 형태소 분석 결과와 모델 토큰의 정렬 지표를 자극 메타데이터로 계산 ② 형태소 경계 정렬 여부를 문항 수준 변수로 기록 ③ 토큰화 방식이 다른 모델 간 비교 시 이 지표로 층화

### 2. Jamo-Level Subword Tokenization in Low-Resource Korean Machine Translation
Lee, Cognetta, Moon, Okazaki · LoResMT 2025
- **정리**: 한글 음절을 자모로 분해한 뒤 BPE를 적용하면 저자원·제한 어휘 조건에서 음절·바이트 기반보다 번역 성능이 좋았다.
- **분석**: 음절 수가 많은 한국어에서 어휘 효율을 높이는 대안. 다만 우리가 쓰는 사전학습 모델의 토크나이저는 바꿀 수 없다.
- **아이디어**: ① 소형 모델 직접 학습 실험 시 자모 BPE를 후보로 ② 자모 단위 확률을 어절 서프라이절로 합산하는 코드 준비 ③ 토크나이저 비교 실험 아이디어로 LM Researcher와 공유

### 3. Improving Korean NLP Tasks with Linguistically Informed Subword Tokenization and Sub-character Decomposition
Jeon, Yang, Kim, Lim · arXiv 2311.03928, 2023-11
- **정리**: 형태소 유형 정보와 하위 문자 분해를 결합한 토큰화로 특히 한국어 문법성 판단(NIKL-CoLA) 성능이 좋아졌다.
- **분석**: 문법 현상에 형태 정보가 중요하다는 점을 보여 주며, 우리 관계절 연구와 연결된다.
- **아이디어**: ① 관계절 관형형 어미(-는/-은/-을)가 토큰 경계에서 분리되는지 모델별 점검 ② 어미 분리 여부에 따라 서프라이절 차이를 층화 분석 ③ NIKL-CoLA를 보조 평가로 검토

### 4. NLP Evaluation in trouble: On the Need to Measure LLM Data Contamination for each Benchmark
Sainz 외 · Findings of EMNLP 2023 (2023-12)
- **정리**: 평가 데이터가 사전학습에 섞이는 오염이 널리 퍼져 있으며 벤치마크마다 오염을 측정·보고해야 한다고 주장했다.
- **분석**: 오염 점검을 실험 절차의 기본 단계로 만들어야 할 이유.
- **아이디어**: ① 자극 세트마다 오염 점검 결과를 보고서 부록에 포함 ② 공개 자극을 재사용할 때 특히 주의 ③ 오염 의심 문항은 분석에서 분리해 민감도 분석

### 5. Time Travel in LLMs: Tracing Data Contamination in Large Language Models
Golchin & Surdeanu · ICLR 2024
- **정리**: 데이터셋 이름·분할 정보를 주고 문항의 앞부분으로 나머지를 생성하게 해, 정확히 재현되는지로 오염을 탐지하는 방법을 제안했다.
- **분석**: 블랙박스 모델에도 쓸 수 있지만, 지시조정 모델에 의존하는 방법이라 베이스 모델에는 적용이 다르다.
- **아이디어**: ① 공개 자극 재사용 시 생성 기반 오염 점검 ② 점검 프롬프트를 표준화해 스크립트로 ③ 결과를 QA Verifier와 공유

### 6. Detecting Pretraining Data from Large Language Models
Shi 외 · ICLR 2024
- **정리**: 토큰 확률 중 가장 낮은 k%의 평균(Min-K% Prob)으로 특정 텍스트가 사전학습 데이터에 포함됐는지 추정하는 방법을 제안했다.
- **분석**: 이미 서프라이절을 계산하는 우리 파이프라인에 거의 추가 비용 없이 붙일 수 있다.
- **아이디어**: ① 서프라이절 계산과 함께 Min-K% 점수를 자동 산출 ② 조건 간 Min-K% 분포 차이를 균형 검정 ③ 기준선으로 새로 만든 문장 집합과 비교

### 7. Dolma: an Open Corpus of Three Trillion Tokens for Language Model Pretraining Research
Soldaini 외 · ACL 2024
- **정리**: 3조 토큰 규모의 공개 사전학습 코퍼스와 정제·중복 제거·필터링 과정을 문서화해 공개했다.
- **분석**: OLMo 학습 데이터라 해당 모델의 오염을 직접 확인할 수 있다. 한국어 비중은 낮다.
- **아이디어**: ① OLMo 대조 실험 시 자극 문장 n-gram 검색 ② 정제 파이프라인 문서화 방식을 우리 데이터 처리 기록에 참고 ③ 한국어 자원으로는 부적합함을 명시

### 8. The FineWeb Datasets: Decanting the Web for the Finest Text Data at Scale
Penedo 외 · NeurIPS 2024 Datasets and Benchmarks
- **정리**: 대규모 웹 데이터를 단계별로 정제한 공개 데이터셋과, 정제 결정마다 소형 모델로 효과를 검증한 절차를 공개했다.
- **분석**: 데이터 처리 결정을 실험으로 검증하는 방법론이 핵심.
- **아이디어**: ① 데이터 전처리 선택(정규화, 필터)의 영향을 작은 실험으로 확인하는 습관 ② 처리 단계별 로그 남기기 ③ 영어 대조 빈도 자원으로 활용

### 9. FineWeb2: One Pipeline to Scale Them All — Adapting Pre-Training Data Processing to Every Language
Penedo 외 · arXiv 2506.20920, 2025
- **정리**: 언어별로 정제 파이프라인을 조정해 수많은 언어의 공개 웹 데이터를 구축했다.
- **분석**: 한국어 웹 텍스트를 공개 자원으로 얻을 수 있어 빈도 추정과 오염 점검에 쓸 수 있다.
- **아이디어**: ① 한국어 부분으로 어절·형태소 빈도표 구축(네트워크 승인 필요) ② 국립국어원 자원과 빈도 상관 확인 ③ 장르 편향(웹)을 한계로 기록

### 10. What's In My Big Data?
Elazar 외 · ICLR 2024
- **정리**: 대형 코퍼스의 내용·중복·오염·민감 정보를 검색·집계하는 도구와 분석을 공개했다.
- **분석**: 코퍼스 감사 도구로 우리 오염 점검의 실무 기반이 된다.
- **아이디어**: ① 자극 문장 정확 일치 검색 절차 마련 ② 코퍼스별 검색 결과를 표준 형식으로 저장 ③ 문서 단위 중복 비율도 함께 확인

### 11. A Pretrainer's Guide to Training Data: Measuring the Effects of Data Age, Domain Coverage, Quality, & Toxicity
Longpre 외 · NAACL 2024
- **정리**: 데이터 시기, 도메인 구성, 품질·유해성 필터가 모델 행동에 주는 영향을 체계적으로 측정했다.
- **분석**: 필터링 선택이 특정 언어 현상 분포를 바꿀 수 있다는 점이 우리에게 중요하다.
- **아이디어**: ① 모델별 학습 데이터 시기를 기록해 신조어·최신 표현 자극 회피 ② 도메인(문어/구어) 차이를 자극 설계에 반영 ③ 필터링이 구어체 구문을 줄였을 가능성을 해석에 고려

### 12. CLIcK: A Benchmark Dataset of Cultural and Linguistic Intelligence in Korean
Kim, Suk, Oh, Yoo, Thorne, Oh · LREC-COLING 2024
- **정리**: 한국어 문화·언어 지식을 묻는 1,995개 문항을 공식 시험 등에서 구성해 한국어 LLM의 한계를 평가했다.
- **분석**: 언어 지식 하위 영역이 있어 모델의 한국어 기초 능력 사전 점검에 쓸 수 있다.
- **아이디어**: ① 실험 전 모델 한국어 능력 기초 점검용으로 일부 사용 ② 언어 영역 점수와 가상 점검 시나리오 결과의 상관 확인 ③ 문항 출처(시험) 특성상 오염 가능성 기록

### 13. KMMLU: Measuring Massive Multitask Language Understanding in Korean
Son 외 · NAACL 2025
- **정리**: 번역이 아닌 한국 시험 문제로 구성한 대규모 다분야 한국어 평가셋을 만들었다.
- **분석**: 지식 중심 평가라 형식적 언어 능력과는 다르지만, 모델 선택 시 한국어 전반 능력 지표로 참고할 수 있다.
- **아이디어**: ① 모델 카드에 공개된 KMMLU 점수 기록 ② 지식 점수와 문법 실험 결과가 다를 수 있음을 해석에 반영 ③ 가상 점검 시나리오에 직접 쓰지는 않음

### 14. HAE-RAE Bench: Evaluation of Korean Knowledge in Language Models
Son 외 · LREC-COLING 2024
- **정리**: 한국어 어휘·문화·역사 지식 등 한국어 고유 지식을 평가하는 벤치마크를 제시했다.
- **분석**: 어휘 관련 하위 과제가 있어 어휘 지식 차이를 모델 비교 시 참고할 수 있다.
- **아이디어**: ① 어휘 하위 점수를 모델 비교의 공변량 후보로 ② 한국어 고유형 평가 목록을 자원 문서에 정리 ③ 오염 위험 기록

### 15. Can large language models help augment English psycholinguistic datasets?
Trott · Behavior Research Methods 56, 2024
- **정리**: GPT-4가 생성한 단어 규범(친숙도, 구체성 등)이 인간 규범과 높은 상관을 보이며 데이터셋 확장에 쓸 수 있지만 일부 차원에서는 차이가 있다고 보고했다.
- **분석**: 한국어 규범 자료가 부족한 우리에게 유용하지만, 한국어에서도 같은 타당성이 있는지는 별도 검증이 필요하다.
- **아이디어**: ① 관계절 명사의 친숙도·구체성을 LLM으로 추정하고 일부를 원어민 평정으로 검증 ② 검증 결과에 따라 사용 범위 결정 ③ Statistician과 PPI 방식 보정 협의
