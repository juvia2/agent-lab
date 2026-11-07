# Report Writer 학습 노트 — 최근 3년 논문 15편

- 학습일: 2026-11-07 · 담당: Report Writer (서류화·보고 담당)
- 교차 영역: 과학 글쓰기·보고 기준, 출처 기반 생성과 사실 검증, LLM의 과학 문헌 종합
- 기간: 2023-11 ~ 2026-11 게재 기준 (프리프린트가 더 이른 논문은 표시)
- 읽기 범위: 초록·공개 본문·웹 검색으로 확인한 내용 기준. 원문 전체 정독은 아니며, 수치는 확인된 것만 적었다.

<!-- DIGEST START -->
## 핵심 요약
- LLM이 수정한 과학 글과 심사 의견이 빠르게 늘고 있으며, 획일화·근거 없는 일반화 위험이 지적된다.
- ML 기반 과학과 LLM 연구에는 합의된 보고 기준(REFORMS, TRIPOD-LLM)이 생겼다. 데이터·모델·평가·한계 보고 항목이 구체적이다.
- 인용과 함께 생성하게 하면 검증 가능성이 높아지지만, 인용이 실제로 주장을 뒷받침하는지는 별도로 확인해야 한다.
- 원자적 사실 단위로 쪼개 근거 문서와 대조하는 사실 검증(FActScore, MiniCheck)이 효과적이다.
- 문헌 검색 기반 에이전트(PaperQA2, OpenScholar)는 문헌 종합에서 강하지만, 인용 정확도 점검이 필수다.

> 주의: 아래 관계절 관련 제안은 2026-11-06 에이전트 점검용 가상 시나리오에서 나온 것이다. 사용자의 실제 실험 주제·계획으로 확인되지 않았다.

## 향후 연구·연구실 운영에 적용할 후보 아이디어
1. 보고서 모든 수치 문장에 출처 파일 경로를 붙이고, 검증 단계에서 문장 단위로 대조한다.
2. 보고서 템플릿에 REFORMS·TRIPOD-LLM에서 우리 연구에 맞는 항목(모델 버전, 프롬프트, 데이터 출처, 오염 점검, 한계)을 추가한다.
3. 보고서를 원자적 주장으로 쪼개 결과 파일과 대조하는 자동 점검을 QA Verifier와 함께 만든다.
4. 결론 문장은 데이터가 지지하는 범위로 제한하고, 일반화 문장은 별도 "추측" 표시를 한다.
5. 노션 기록에도 같은 출처 표기 규칙을 적용한다.
<!-- DIGEST END -->

## 논문별 노트

### 1. Mapping the Increasing Use of LLMs in Scientific Papers
Liang 외 · COLM 2024
- **정리**: 대규모 논문 말뭉치에서 LLM이 수정한 문장 비율을 추정해, 특히 컴퓨터과학 분야에서 빠르게 늘고 있음을 보였다.
- **분석**: 우리 보고서도 LLM이 쓰는 만큼, 문체 획일화와 과장 표현을 경계해야 한다.
- **아이디어**: ① 보고서 상투 표현 목록(과장 형용사 등)을 금지어로 관리 ② 작성 모델과 백엔드를 보고서 부록에 기록 ③ 사람 검토 여부를 표시

### 2. Can large language models provide useful feedback on research papers? A large-scale empirical analysis
Liang 외 · NEJM AI 1, 2024
- **정리**: GPT-4의 논문 피드백이 사람 심사자 의견과 상당히 겹치고 많은 연구자가 유용하다고 평가했지만, 구체성·깊이는 부족했다.
- **분석**: LLM 검토는 보조로 유용하지만 대체는 아니다.
- **아이디어**: ① 보고서 초안에 자동 자기 검토 단계 추가(검증 담당 전) ② 피드백의 구체성 기준(어느 문장, 어떤 근거) 설정 ③ 연구자 최종 검토 항목 명시

### 3. Monitoring AI-Modified Content at Scale: A Case Study on the Impact of ChatGPT on AI Conference Peer Reviews
Liang 외 · ICML 2024
- **정리**: AI 학회 심사 의견 중 LLM이 상당 부분 수정한 비율을 추정하고, 마감 직전·확신도 낮은 심사에서 더 많이 나타남을 보였다.
- **분석**: 시간 압박 상황에서 LLM 의존이 커진다는 점은 우리 자동 보고에도 시사점이 있다.
- **아이디어**: ① 급하게 만든 보고서일수록 검증 단계를 생략하지 않는 규칙 ② 보고서 생성 시간과 검증 통과율을 학습 레이어에 기록 ③ 확신도 낮은 문장은 별도 표시

### 4. Can LLMs Generate Novel Research Ideas? A Large-Scale Human Study with 100+ NLP Researchers
Si, Yang, Hashimoto · ICLR 2025
- **정리**: LLM이 낸 연구 아이디어가 사람 전문가 아이디어보다 참신성 점수는 높았지만 실현 가능성은 약간 낮았다고 보고했다.
- **분석**: "다음 결정" 절에 LLM이 제안하는 후속 연구는 참신하지만 실현성 점검이 필요하다.
- **아이디어**: ① 보고서 "다음 단계" 제안에 실현 가능성(자원·시간) 평가를 붙임 ② 아이디어는 전문가 에이전트 검토 후에만 제시 ③ 연구자 선택 결과를 학습 레이어에 기록

### 5. REFORMS: Consensus-based Recommendations for Machine-learning-based Science
Kapoor 외 · Science Advances 10, 2024
- **정리**: ML 기반 과학 연구의 오류·누수를 줄이기 위한 합의 기반 보고 체크리스트(연구 목표, 데이터, 전처리, 모델, 평가, 재현성 등)를 제시했다.
- **분석**: 우리 보고서 구조 점검에 바로 쓸 수 있는 표준.
- **아이디어**: ① 보고서 부록에 REFORMS 항목별 충족 여부 표 ② 데이터 누수(자극 오염) 항목을 필수로 ③ QA Verifier 점검 목록과 통합

### 6. The TRIPOD-LLM reporting guideline for studies using large language models
Gallifant 외 · Nature Medicine 31, 2025
- **정리**: LLM을 사용하는 연구의 보고 기준으로, 모델 버전·프롬프트·평가 설계·인간 감독·한계 등 보고 항목을 정리했다.
- **분석**: 의료 분야용이지만 LLM 사용 보고 항목은 우리 연구에 그대로 적용 가능하다.
- **아이디어**: ① 모델 버전·날짜·접근 방식(API/로컬)·프롬프트 전문을 부록에 기록 ② 사람 감독 단계(승인, 검증) 서술 ③ 보고서 템플릿에 항목 추가

### 7. Enabling Large Language Models to Generate Text with Citations
Gao, Yen, Yu, Chen · EMNLP 2023 (2023-12)
- **정리**: 인용과 함께 답을 생성하는 과제(ALCE)를 만들고, 인용 재현율·정밀도로 인용 품질을 자동 평가하는 방법을 제시했다.
- **분석**: 인용이 있다는 것과 인용이 주장을 뒷받침한다는 것은 다르다.
- **아이디어**: ① 보고서 수치 문장마다 결과 파일 인용 필수 ② 인용 정밀도(인용 파일이 실제 그 수치를 담는지) 자동 점검 ③ 인용 없는 수치 문장을 오류로 처리

### 8. OpenScholar: Synthesizing Scientific Literature with Retrieval-augmented LMs
Asai 외 · arXiv 2411.14199, 2024
- **정리**: 대규모 공개 논문 데이터로 검색 증강 생성을 해 과학 문헌을 인용과 함께 종합하는 모델을 제시하고, 인용 환각이 일반 LLM보다 적다고 보고했다.
- **분석**: 문헌 조사 기능을 추가할 때 참고할 구조.
- **아이디어**: ① 보고서 배경 절의 선행연구 인용은 검색으로 확인된 문헌만 ② 인용 문헌의 실재 확인 단계 ③ 향후 문헌 조사원 에이전트 설계 시 참고

### 9. AutoSurvey: Large Language Models Can Automatically Write Surveys
Wang 외 · NeurIPS 2024
- **정리**: 검색·개요 작성·병렬 절 작성·통합·평가 단계로 서베이 논문을 자동 작성하는 파이프라인을 제시했다.
- **분석**: 긴 문서를 단계적으로 쓰는 구조가 우리 보고서 작성에도 유효하다.
- **아이디어**: ① 보고서를 개요 → 절별 작성 → 통합 → 검증 단계로 ② 절별로 담당 전문가 해석을 연결 ③ 통합 단계에서 중복·모순 점검

### 10. MiniCheck: Efficient Fact-Checking of LLMs on Grounding Documents
Tang, Laban, Durrett · EMNLP 2024
- **정리**: 문장이 근거 문서로 뒷받침되는지 판단하는 작은 사실 검증 모델을 만들어, 큰 모델에 가까운 성능을 훨씬 낮은 비용으로 얻었다.
- **분석**: 로컬에서 돌릴 수 있는 검증기라 과금 없는 우리 환경에 적합할 수 있다.
- **아이디어**: ① 보고서 문장과 결과 파일·해석 메모의 일치를 로컬 검증기로 점검 ② 불일치 문장을 검증 담당에게 자동 전달 ③ 로컬 실행 가능성 확인

### 11. FActScore: Fine-grained Atomic Evaluation of Factual Precision in Long Form Text Generation
Min 외 · EMNLP 2023 (2023-12)
- **정리**: 긴 생성문을 원자적 사실로 쪼개 각 사실이 지식원으로 뒷받침되는 비율을 측정하는 방법을 제시했다.
- **분석**: 보고서 검증을 문장보다 작은 단위로 하면 오류를 놓치지 않는다.
- **아이디어**: ① 결과 절을 원자적 주장 목록으로 변환해 검증 ② 사실 정밀도를 보고서 품질 지표로 기록 ③ 학습 레이어에서 개선 추적

### 12. A Survey on Hallucination in Large Language Models: Principles, Taxonomy, Challenges, and Open Questions
Huang 외 · ACM TOIS, 2025 (arXiv 2311.05232)
- **정리**: LLM 환각을 사실성·충실성 유형으로 분류하고 원인과 탐지·완화 방법을 정리했다.
- **분석**: 보고서 오류 유형 분류 체계로 쓸 수 있다.
- **아이디어**: ① 검증 지적을 환각 유형(수치 조작, 출처 불일치, 과잉 일반화)으로 분류 ② 유형별 빈도를 학습 레이어에 기록 ③ 자주 나오는 유형에 맞춘 작성 규칙 추가

### 13. PaperQA: Retrieval-Augmented Generative Agent for Scientific Research
Lála 외 · arXiv 2312.07559, 2023-12
- **정리**: 논문 검색·관련 단락 수집·답변 생성을 에이전트로 수행해 과학 질의에 인용과 함께 답하는 시스템을 제시했다.
- **분석**: 질문에 답할 때 근거 단락을 먼저 모으는 구조가 우리 질의응답(디스코드)에도 맞는다.
- **아이디어**: ① 팀원 봇 답변도 실험 파일 근거를 먼저 읽고 답하게 하는 규칙 유지 ② 답변에 근거 파일 경로 표시 ③ 근거가 없으면 모른다고 답하기

### 14. Language agents achieve superhuman synthesis of scientific knowledge
Skarlinski 외 · arXiv 2409.13740, 2024
- **정리**: PaperQA2가 문헌 검색·요약·모순 탐지 과제에서 전문가 수준 이상의 성능을 보였다고 보고했다.
- **분석**: 문헌 종합 자동화의 가능성. 다만 평가 과제 설계에 따라 결과가 달라질 수 있다.
- **아이디어**: ① 선행연구 간 모순 탐지를 보고서 논의 절에 활용 ② 우리 결과와 선행연구가 어긋나는 지점을 명시하는 절 추가 ③ 문헌 조사원 추가 시 기준선으로

### 15. The Widespread Adoption of Large Language Model-Assisted Writing Across Society
Liang 외 · Patterns (Cell Press), 2025 (arXiv 2502.09747)
- **정리**: 기업 보도자료, 민원, 채용 공고 등 여러 영역에서 LLM 보조 글쓰기가 빠르게 확산됐음을 추정했다.
- **분석**: 글쓰기 보조가 일상화될수록 출처·책임 표시가 중요해진다.
- **아이디어**: ① 보고서에 "자동 작성 · 사람 검토 여부" 표시 ② 연구자가 수정한 부분과 자동 작성 부분 구분 기록 ③ 노션 기록에도 같은 표시
