# Backend Developer 학습 노트 — 최근 3년 논문 15편

- 학습일: 2026-11-07 · 담당: Backend Developer (백엔드 개발자)
- 교차 영역: 언어모델 실험의 재현 가능한 구현(확률 계산, 평가 하네스, 효율적 추론, 코드 에이전트·연구 재현 벤치마크)
- 기간: 2023-11 ~ 2026-11 게재 기준 (프리프린트가 더 이른 논문은 표시)
- 읽기 범위: 초록·공개 본문·웹 검색으로 확인한 내용 기준. 원문 전체 정독은 아니며, 수치는 확인된 것만 적었다.

<!-- DIGEST START -->
## 핵심 요약
- 단어 확률 계산에는 앞 공백 토큰 같은 미묘한 구현 함정이 있고, 이것이 심리측정 결과를 체계적으로 바꾼다.
- 재현 가능한 평가는 프롬프트·정규화·토큰화·버전을 모두 기록하는 하네스 수준의 관리가 필요하다.
- 맥북 같은 제한 환경에서는 가중치 양자화(AWQ 등)와 효율적 어텐션이 실용적이지만, 결과에 미치는 영향을 측정해야 한다.
- 코드 에이전트는 저장소 수준 작업에서 발전했지만, 연구 재현(PaperBench, CORE-Bench)에서는 아직 성공률이 낮다. 사람 검토와 테스트가 필수다.
- 프로그램적 프롬프트 구성(DSPy)처럼 LLM 호출을 모듈로 다루면 파이프라인 관리가 쉬워진다.

> 주의: 아래 관계절 관련 제안은 2026-11-06 에이전트 점검용 가상 시나리오에서 나온 것이다. 사용자의 실제 실험 주제·계획으로 확인되지 않았다.

## 향후 연구·연구실 운영에 적용할 후보 아이디어
1. 서프라이절 코드에 공백 보정 옵션과 단위 테스트(알려진 예제의 확률 합 검사)를 넣는다.
2. 실행마다 모델 해시·토크나이저 버전·양자화·라이브러리 버전·시드를 run_manifest에 자동 기록한다.
3. 같은 문항을 두 백엔드(HF transformers vs llama.cpp)로 계산해 차이를 자동 비교하는 검증 스크립트를 둔다.
4. 에이전트가 쓴 코드는 반드시 테스트를 실행해 통과를 확인한 뒤 "검증됨"이라고 쓴다.
5. 분석 코드는 결과 스키마를 code/README.md에 문서화한다.
<!-- DIGEST END -->

## 논문별 노트

### 1. Lessons from the Trenches on Reproducible Evaluation of Language Models
Biderman 외 · arXiv 2405.14782, 2024
- **정리**: lm-evaluation-harness 운영 경험을 바탕으로 평가 재현성을 해치는 요인(프롬프트 세부, 정규화, 토큰화)과 모범 사례를 정리했다.
- **분석**: 평가 코드를 직접 짜기보다 검증된 하네스를 쓰고 설정을 모두 공개하라는 실무 지침.
- **아이디어**: ① 보조 벤치마크는 lm-evaluation-harness로 실행하고 설정 파일을 결과와 함께 저장 ② 정규화 방식(길이 보정 등)을 매니페스트에 기록 ③ 하네스 버전 고정

### 2. Leading Whitespaces of Language Models' Subword Vocabulary Pose a Confound for Calculating Word Probabilities
Oh & Schuler · EMNLP 2024
- **정리**: 단어 앞 공백이 같은 토큰에 붙는 어휘 구조 때문에 일반적인 단어 확률 계산이 왜곡되며, 이를 바로잡는 계산법을 제시했다.
- **분석**: 우리 서프라이절 코드에 직접 영향을 준다. Pimentel & Meister(2024)와 같은 문제를 다룬다.
- **아이디어**: ① 공백 보정 계산을 옵션으로 구현하고 기본값으로 ② 보정 전후 서프라이절 차이 리포트 자동 생성 ③ SentencePiece(▁) 한국어 모델에 같은 보정 적용 테스트

### 3. FlashAttention-2: Faster Attention with Better Parallelism and Work Partitioning
Dao · ICLR 2024
- **정리**: GPU 메모리 계층을 고려한 작업 분할로 어텐션 계산 속도와 메모리 효율을 크게 높였다.
- **분석**: 주로 CUDA GPU용이며 맥 MPS에서는 그대로 쓰기 어렵다. 맥에서는 대안(SDPA 등)을 확인해야 한다.
- **아이디어**: ① 맥 MPS에서 사용 가능한 어텐션 구현 확인 후 설정 ② 어텐션 구현이 수치 결과를 바꾸는지 작은 테스트 ③ 긴 맥락 실험의 메모리 예산 계산에 반영

### 4. AWQ: Activation-aware Weight Quantization for On-Device LLM Compression and Acceleration
Lin 외 · MLSys 2024
- **정리**: 활성값 크기를 고려해 중요한 가중치를 보호하면서 4비트 양자화하는 방법으로, 기기 내 추론을 가능하게 했다.
- **분석**: 맥북 로컬 실행에 실용적이지만, 확률 분포 미세 변화가 서프라이절에 영향을 줄 수 있다.
- **아이디어**: ① 양자화 방식(AWQ/GGUF)을 매니페스트에 기록 ② FP16 대비 서프라이절 차이 자동 측정 스크립트 ③ 핵심 분석은 차이가 작을 때만 양자화 모델 사용

### 5. GQA: Training Generalized Multi-Query Transformer Models from Multi-Head Checkpoints
Ainslie 외 · EMNLP 2023 (2023-12)
- **정리**: 키·값 헤드를 그룹으로 공유해 추론 메모리와 속도를 개선하면서 품질 손실을 줄이는 방법을 제시했다.
- **분석**: 최근 모델 다수가 채택한 구조라 메모리 추정에 반영해야 한다.
- **아이디어**: ① 모델별 KV 캐시 메모리 계산에 GQA 구조 반영 ② 배치 크기 자동 결정 로직 개선 ③ 메모리 표 갱신

### 6. SWE-bench: Can Language Models Resolve Real-World GitHub Issues?
Jimenez 외 · ICLR 2024
- **정리**: 실제 GitHub 이슈를 해결하는 패치를 만들고 테스트로 검증하는 저장소 수준 코딩 벤치마크를 제시했다.
- **분석**: "테스트 통과"를 성공 기준으로 삼는 설계가 우리 코드 검증 원칙과 같다.
- **아이디어**: ① 가상 점검 시나리오 코드도 수정 시 테스트 통과를 완료 조건으로 ② 이슈-패치-테스트 형식으로 수정 기록 ③ Codex 백엔드 사용 시 테스트 실행 필수

### 7. SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering
Yang 외 · NeurIPS 2024
- **정리**: 에이전트 전용 명령 인터페이스(파일 보기·편집·검색)를 설계하면 코딩 에이전트 성능이 크게 오른다는 것을 보였다.
- **분석**: 도구 인터페이스 설계가 에이전트 성능을 좌우한다. 우리 Toolbox 설계에 참고할 수 있다.
- **아이디어**: ① Toolbox의 파일 읽기 도구에 줄 범위·검색 기능 개선 검토 ② 도구 출력 길이 제한과 요약 방식 점검 ③ 편집 후 자동 문법 검사 단계 추가

### 8. OpenHands: An Open Platform for AI Software Developers as Generalist Agents
Wang 외 · ICLR 2025
- **정리**: 코드 실행 샌드박스, 브라우저, 다중 에이전트를 갖춘 공개 개발 에이전트 플랫폼을 제시했다.
- **분석**: 도커 샌드박스 + 도구 호출 구조가 우리 연구실 구조와 비슷해 설계 비교 대상이 된다.
- **아이디어**: ① 샌드박스 자원 제한·네트워크 정책 설정을 비교 점검 ② 에이전트 작업 로그 형식 참고 ③ 실패 복구(재시도) 패턴 비교

### 9. PaperBench: Evaluating AI's Ability to Replicate AI Research
Starace 외 · ICML 2025
- **정리**: 논문을 처음부터 재현하는 과제를 세부 채점 기준으로 평가하는 벤치마크로, 최고 에이전트도 사람 연구자보다 크게 낮았다.
- **분석**: 연구 구현 자동화의 현재 한계를 보여 준다. 우리 연구실도 사람 검토가 필요한 이유.
- **아이디어**: ① 실험 구현을 세부 채점 항목(루브릭)으로 쪼개 진행률을 측정 ② QA Verifier가 루브릭 기반 검증 ③ 실패 지점 통계를 학습 레이어에 기록

### 10. CORE-Bench: Fostering the Credibility of Published Research Through a Computational Reproducibility Agent Benchmark
Siegel 외 · TMLR 2025
- **정리**: 공개된 논문 코드로 결과를 재현하는 과제에서 에이전트 성능을 측정해, 환경 설정·의존성 문제가 주요 실패 원인임을 보였다.
- **분석**: 재현성 실패의 상당 부분이 환경 문제라는 점이 우리 도커 이미지 관리의 중요성을 뒷받침한다.
- **아이디어**: ① 의존성 버전을 잠금 파일로 고정 ② 실험마다 환경 스냅샷(이미지 태그) 기록 ③ 재현 스크립트(run.sh) 자동 생성

### 11. MLE-bench: Evaluating Machine Learning Agents on Machine Learning Engineering
Chan 외 · ICLR 2025
- **정리**: Kaggle 대회 과제로 머신러닝 엔지니어링 에이전트를 평가했고, 자원·시간 제한과 디버깅이 성능에 큰 영향을 준다고 보고했다.
- **분석**: 실행 시간 예산과 반복 시도 관리가 핵심. 우리 실행 시간 승인 게이트와 연결된다.
- **아이디어**: ① 실행 시간 추정과 실제 시간 비교 로그 ② 시간 초과 패턴을 분석해 추정 개선 ③ 작은 시험 실행 단계 의무화

### 12. MLAgentBench: Evaluating Language Agents on Machine Learning Experimentation
Huang, Vora, Liang, Leskovec · ICML 2024
- **정리**: 연구 과제(모델 개선 실험)를 에이전트가 계획·실행·분석하는 능력을 평가했고, 장기 과제에서 계획 유지와 환각이 문제였다.
- **분석**: 실험 실행 에이전트의 실패 유형이 우리 실무 담당·개발자 역할에 직접 해당한다.
- **아이디어**: ① 긴 작업은 중간 저장·진행 보고 단계로 쪼갬 ② 결과 수치는 반드시 파일에서 읽어 인용(환각 방지) ③ 실패 사례를 피드백 로그로 축적

### 13. Is Your Code Generated by ChatGPT Really Correct? Rigorous Evaluation of LLMs for Code Generation
Liu, Xia, Wang, Zhang · NeurIPS 2023 (2023-12)
- **정리**: 기존 코드 벤치마크의 테스트가 부족해 틀린 코드가 통과되는 문제를 보이고, 테스트를 대폭 늘린 EvalPlus를 제시했다.
- **분석**: "테스트 통과=정답"은 테스트가 충분할 때만 성립한다.
- **아이디어**: ① 서프라이절 계산 코드에 경계값 테스트(빈 문자열, 특수문자, 긴 어절) 추가 ② 어절 합산 결과를 토큰 확률 합과 대조하는 속성 테스트 ③ 테스트 커버리지 측정

### 14. LiveCodeBench: Holistic and Contamination Free Evaluation of Large Language Models for Code
Jain 외 · ICLR 2025
- **정리**: 시간 순으로 새 문제를 수집해 오염 없는 코드 평가를 지속적으로 수행하는 벤치마크를 제시했다.
- **분석**: 시간 기준 오염 회피 방법은 자극 설계에도 응용 가능하다.
- **아이디어**: ① 모델 학습 마감일 이후 텍스트로 만든 자극을 오염 대조군으로 ② 자극 생성일을 메타데이터로 기록 ③ Corpus & Data Engineer와 오염 점검 공유

### 15. DSPy: Compiling Declarative Language Model Calls into Self-Improving Pipelines
Khattab 외 · ICLR 2024
- **정리**: LLM 호출을 선언적 모듈로 구성하고, 평가 지표에 맞춰 프롬프트·예시를 자동 최적화하는 프레임워크를 제시했다.
- **분석**: 에이전트 프롬프트를 코드처럼 관리하는 방법. 다만 자동 최적화는 과적합 위험이 있다.
- **아이디어**: ① 에이전트 역할 프롬프트를 버전 관리하고 변경 시 테스트 ② 학습 레이어의 자동 반영 규칙을 프롬프트 모듈 단위로 적용 ③ 자동 최적화는 검증 세트 분리 후에만
