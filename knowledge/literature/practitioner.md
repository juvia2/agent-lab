# Experiment Coordinator 학습 노트 — 최근 3년 논문 15편

- 학습일: 2026-11-07 · 담당: Experiment Coordinator (실험 실무 담당)
- 교차 영역: 언어모델 대상 언어·인지 실험의 측정 프로토콜 설계(확률 vs 프롬프트, 과제 요구, 강건성, 문맥 효과)
- 기간: 2023-11 ~ 2026-11 게재 기준 (프리프린트가 더 이른 논문은 표시)
- 읽기 범위: 초록·공개 본문·웹 검색으로 확인한 내용 기준. 원문 전체 정독은 아니며, 수치는 확인된 것만 적었다.

<!-- DIGEST START -->
## 핵심 요약
- 확률 직접 측정이 프롬프트 질의보다 언어 지식을 더 잘 드러내며, 지시조정 모델에서는 첫 토큰 확률과 텍스트 답이 어긋날 수 있다.
- 과제 요구(메타언어적 질문, 형식 맞추기)가 작은 모델의 능력을 가린다. 측정 방식이 결론을 바꾼다.
- 선택지 순서·기호, 템플릿의 사소한 변경, 정보 위치가 성능을 크게 흔든다. 변형 조건으로 강건성을 확인해야 한다.
- 인지 평가는 대조 조건, 자극 변형, 인간 기준선, 사전 등록 같은 실험심리학 원칙을 따라야 한다.
- LLM 결과는 학습 목표(다음 단어 예측)의 흔적을 띠므로, 출력 확률이 높은 형식과 낮은 형식을 비교하는 설계가 유용하다.

> 주의: 아래 관계절 관련 제안은 2026-11-06 에이전트 점검용 가상 시나리오에서 나온 것이다. 사용자의 실제 실험 주제·계획으로 확인되지 않았다.

## 향후 연구·연구실 운영에 적용할 후보 아이디어
1. 계획서에 측정 방식을 "확률 직접 측정(기본) / 프롬프트(보조)"로 명시하고, 둘을 섞어 결론 내리지 않는다.
2. 모든 실험에 변형 조건(어휘 교체, 어순 변형, 문맥 프레임 변경)을 일정 비율 포함해 강건성을 함께 보고한다.
3. 베이스 모델을 기본으로 하고, 지시조정 모델은 비교군으로 둔다.
4. 실행 전 소규모 시험 실행으로 토큰 경계·확률 계산을 확인하는 단계를 필수로 한다.
5. 인간 기준선 데이터(공개 데이터 또는 파일럿)를 계획 단계에서 확정한다.
<!-- DIGEST END -->

## 논문별 노트

### 1. Prompting is not a substitute for probability measurements in large language models
Hu & Levy · EMNLP 2023 (2023-12)
- **정리**: 메타언어적 프롬프트("이 문장이 문법적인가?")로 얻은 판단은 모델 내부 확률로 직접 측정한 것보다 언어 지식을 덜 드러내며, 둘의 일치도도 낮을 수 있다.
- **분석**: 우리 연구실의 기본 측정 원칙(확률 직접 측정)의 핵심 근거.
- **아이디어**: ① 계획서 템플릿에 "측정 방식" 필수 항목 추가 ② 프롬프트 판단을 쓸 경우 확률 측정과 일치도를 함께 보고 ③ 결론은 확률 측정 결과 위주로

### 2. Auxiliary task demands mask the capabilities of smaller language models
Hu & Frank · COLM 2024
- **정리**: 평가 과제에 부가적 요구(형식 맞추기, 메타언어적 판단)가 있으면 작은 모델의 능력이 과소평가되며, 요구가 적은 측정에서는 차이가 줄어든다고 보였다.
- **분석**: 모델 크기 비교 결론이 측정 방식에 좌우된다는 근거. 발달심리학의 과제 요구 개념을 차용했다.
- **아이디어**: ① 크기별 모델 비교 시 과제 요구가 가장 낮은 측정(서프라이절)을 주 지표로 ② 과제 요구를 높인 조건을 보조로 넣어 차이를 보고 ③ "작은 모델은 못한다" 결론 전 측정 방식 재확인

### 3. Log Probabilities Are a Reliable Estimate of Semantic Plausibility in Base and Instruction-Tuned Language Models
Kauf, Chersoni, Lenci, Fedorenko, Ivanova · BlackboxNLP 2024
- **정리**: 의미적 개연성 판단에서 로그확률이 프롬프트 응답보다 신뢰할 만하며, 지시조정 모델에서도 그런 경향이 유지됐다.
- **분석**: 확률 측정 원칙을 의미 영역과 지시조정 모델까지 확장해 준다.
- **아이디어**: ① 자극 개연성 통제에 모델 로그확률을 보조 지표로 사용 ② 지시조정 모델도 확률 측정이면 비교군으로 쓸 수 있음 ③ 개연성과 문법성 효과를 분리하는 설계

### 4. How to evaluate the cognitive abilities of LLMs
Ivanova · Nature Human Behaviour 9, 2025
- **정리**: LLM 인지 평가를 설계·해석할 때 고려할 방법론 14가지(자극 오염, 과제 요구, 대조 조건, 인간 비교 등)를 제시했다.
- **분석**: 가상 점검 시나리오 계획 체크리스트로 바로 옮길 수 있는 실무 지침.
- **아이디어**: ① 14개 항목을 계획서 점검표로 변환 ② QA Verifier의 계획 준수 점검에 연동 ③ 각 실험 보고서에 해당 항목 충족 여부 표기

### 5. Elements of World Knowledge (EWoK): A Cognition-Inspired Framework for Evaluating Basic World Knowledge in Language Models
Ivanova 외 · arXiv 2405.09605, 2024
- **정리**: 인지과학의 핵심 지식 영역을 바탕으로 최소대립 문맥 쌍을 템플릿으로 생성해 세계 지식을 평가하는 틀을 제시했다.
- **분석**: 템플릿 기반 생성 + 최소대립 + 여러 측정 방식 비교라는 설계가 우리 자극 생성에 그대로 쓸 수 있다.
- **아이디어**: ① 자극 생성을 "개념-템플릿-어휘 채우기" 3단계로 구조화 ② 같은 문항을 로그확률·프롬프트 두 방식으로 측정 ③ 템플릿 파일을 버전 관리

### 6. A foundation model to predict and capture human cognition
Binz 외 · Nature, 2025
- **정리**: 대규모 인간 행동 실험 데이터로 LLM을 미세조정한 Centaur가 여러 실험의 인간 선택을 예측하고 일부 새로운 과제로 일반화했다고 보고했다.
- **분석**: 인간 데이터 예측을 목표로 학습시킨 모델의 가능성과 한계(메커니즘 설명은 별개)를 동시에 보여 준다.
- **아이디어**: ① 인간 행동 예측과 인지 이론 검증을 구분하는 문구를 해석 지침에 추가 ② 공개 행동 데이터 형식을 참고해 우리 결과 파일 스키마 정리 ③ 인간 데이터 예측 실험은 별도 트랙으로

### 7. Can language models handle recursively nested grammatical structures? A case study on comparing models and humans
Lampinen · Computational Linguistics 50, 2024
- **정리**: 중첩 구조 처리에서 모델과 인간을 비교할 때, 인간은 연습·지시를 받는데 모델은 그렇지 않은 등 조건 불일치가 결론을 왜곡할 수 있으며, 몇 개 예시를 주면 모델 성능이 크게 달라짐을 보였다.
- **분석**: 모델-인간 비교의 공정성 문제를 정면으로 다룬다.
- **아이디어**: ① 인간 실험 조건(연습 문항, 지시)을 모델 조건에 대응시키는 표를 계획서에 포함 ② 맥락 예시 유무를 조건으로 넣어 비교 ③ 비교 불공정 요소를 한계 절에 명시

### 8. Embers of autoregression show how large language models are shaped by the problem they are trained to solve
McCoy, Yao, Friedman, Hardy, Griffiths · PNAS 121, 2024
- **정리**: 같은 과제라도 출력이 학습 분포에서 확률이 높을 때 LLM 정확도가 높고, 낮으면 떨어진다는 것을 여러 과제에서 보였다.
- **분석**: 결과 해석 시 출력 확률·빈도 효과를 대안 설명으로 고려해야 한다.
- **아이디어**: ① 관계절 조건 간 핵어·동사 빈도를 맞춰 확률 차이에 의한 착시 방지 ② 고빈도/저빈도 변형 조건을 추가 ③ 결과 해석에 "학습 목표의 흔적" 가능성 점검 항목 추가

### 9. Clever Hans or Neural Theory of Mind? Stress Testing Social Reasoning in Large Language Models
Shapira 외 · EACL 2024
- **정리**: 여러 마음이론 과제에서 LLM이 보이는 성공이 작은 변형에 쉽게 무너져, 얕은 휴리스틱에 의존할 가능성이 크다고 보였다.
- **분석**: 변형 검사(stress test)를 설계 단계에 넣어야 하는 이유.
- **아이디어**: ① 모든 자극 세트에 적대적 변형 하위 세트 포함 ② 원본-변형 성능 차이를 강건성 지표로 보고 ③ 변형 생성 규칙을 Linguist와 정의

### 10. Do LLMs Exhibit Human-like Response Biases? A Case Study in Survey Design
Tjuatja, Chen, Wu, Talwalkar, Neubig · TACL 12, 2024
- **정리**: 설문 문구 변화에 대한 인간의 반응 편향을 LLM이 일관되게 재현하지 않으며, 인간에게는 영향이 없는 변화에도 민감하다고 보고했다.
- **분석**: LLM을 인간 참가자 대리로 쓰는 실험의 한계를 보여 준다.
- **아이디어**: ① LLM 응답을 인간 대리로 쓰는 설계는 피함 ② 문구 변형 민감도를 보조 결과로 보고 ③ 인간과 모델의 반응 차이를 해석 대상으로 다룸

### 11. "My Answer is C": First-Token Probabilities Do Not Match Text Answers in Instruction-Tuned Language Models
Wang 외 · Findings of ACL 2024
- **정리**: 지시조정 모델에서 선택지의 첫 토큰 확률로 정한 답과 실제 생성 텍스트 답이 자주 어긋남을 보였다.
- **분석**: 확률 측정과 생성 측정이 같은 것을 재는지 늘 확인해야 한다.
- **아이디어**: ① 객관식 보조 평가에서 두 방식 일치율 보고 ② 확률 측정 시 전체 문장 확률을 기본으로 ③ 지시조정 모델 사용 시 주의 문구 추가

### 12. Large Language Models Are Not Robust Multiple Choice Selectors
Zheng, Zhou, Meng, Zhou, Huang · ICLR 2024
- **정리**: LLM은 특정 선택지 기호를 선호하는 편향이 있어 선택지 순서를 바꾸면 답이 달라지며, 이를 보정하는 방법을 제안했다.
- **분석**: 객관식 형식 결과를 해석할 때 위치 편향 통제가 필요하다.
- **아이디어**: ① 선택지 순서 순환(counterbalancing) 적용 ② 위치별 선택 비율을 점검 ③ 가능하면 객관식 대신 확률 비교 사용

### 13. GSM-Symbolic: Understanding the Limitations of Mathematical Reasoning in Large Language Models
Mirzadeh 외 · ICLR 2025
- **정리**: 수학 문제의 이름·숫자만 바꾼 템플릿 변형에서도 성능이 흔들리고, 무관한 문장을 넣으면 크게 떨어짐을 보였다.
- **분석**: 템플릿 변형으로 암기·패턴 매칭을 진단하는 설계는 언어 실험에도 적용 가능하다.
- **아이디어**: ① 관계절 템플릿의 어휘만 바꾼 변형 세트로 성능 분포 측정 ② 무관한 수식어 삽입 조건을 방해 조건으로 ③ 분포의 분산을 결과에 보고

### 14. Lost in the Middle: How Language Models Use Long Contexts
Liu 외 · TACL 12, 2024
- **정리**: 긴 문맥에서 정보가 처음이나 끝에 있을 때보다 가운데 있을 때 모델 성능이 크게 떨어짐을 보였다.
- **분석**: 문맥 프레임을 길게 쓰는 실험에서 위치 효과가 교란 요인이 될 수 있다.
- **아이디어**: ① 문맥 문장 길이와 목표 문장 위치를 조건 간 동일하게 ② 담화 맥락 실험에서 위치를 균형화 ③ 문맥 길이를 메타데이터로 기록

### 15. Using Computational Models to Test Syntactic Learnability
Wilcox, Futrell, Levy · Linguistic Inquiry 55, 2024
- **정리**: 언어모델을 학습가능성 검증 도구로 써서, 섬 제약 같은 구문 일반화가 입력에서 학습 가능한지 평가하는 방법과 결과를 제시했다.
- **분석**: LM 실험이 언어학 이론 질문에 답하려면 어떤 설계가 필요한지 보여 주는 모범 사례.
- **아이디어**: ① 관계절 실험에 "학습가능성" 질문 형식으로 가설을 적는 방식 도입 ② 필러-공백 의존을 측정하는 wh-효과 계산법을 한국어 관계절에 응용 ③ 2×2 상호작용 설계를 기본 틀로
