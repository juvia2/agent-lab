# 연구 에이전트·Hermes·세컨드 브레인 저장소 조사

조사일: 2026-11-08. 범위: 공개 GitHub 저장소의 README·문서와 현재 연구실 코드 비교. 아래 평가는 **이 연구실에 대한 적합성 판단**이며, 저장소 자체의 성능 우열을 입증한 벤치마크가 아니다. 설치·클론·실험 데이터 전송은 이번 조사에서 하지 않았다.

## 현재 연구실에서 먼저 해결할 문제

- `lab/notebook.py`는 완료 실험 요약 Markdown에 대한 단어 일치 검색이다. 원본 파일 경로, 검증 상태, 자료 등급, 결정의 변경 이력을 검색 결과에 싣지 않는다.
- `lab/director.py`의 연구실장은 연구노트 검색·실험 파일 읽기를 할 수 있으나, 출처가 붙은 기억 검색과 연구자 결정의 제안·확정 흐름이 없다.
- `lab/backends.py`의 `HermesBackend`는 전용 프로필을 한 턴씩 호출한다. `lab/tools.py`의 도구 권한과 기존 승인 절차는 통과하지만, 실험 명세 `protocol.json`, 실행 인자·산출물 manifest 대조, 자료 등급별 전송 차단은 미구현이다. 실제 기본 경로는 아직 Hermes가 아니다.
- `lab/agents.py`는 역할별 문헌 DIGEST를 프롬프트에 자동 추가한다. 연구자 원안과 외부 문헌을 분리하는 출처 정책이 먼저 필요하다.

## 추천 저장소와 적용 위치

| 우선순위 | 저장소 | 가져올 부분 | 적용 대상·방식 | 적합성과 한계 |
|---|---|---|---|---|
| 1 | [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) (MIT) | 프로필별 기억·스킬, `memory.write_approval`, `skills.write_approval`, 도구 집합 제한 | 기존 `HermesBackend`와 `research-lab-coordinator` 프로필 유지. 실무 담당의 재사용 절차를 검토 대기 스킬로 제안하고, `Toolbox` 호출만 허용 | 이미 설치·연결되어 가장 낮은 통합 비용. 프로필은 상태 분리일 뿐 파일시스템 샌드박스가 아니며, 승인된 실험 명세보다 기억·스킬이 우선해서는 안 됨. [기억 승인](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/memory.md), [스킬 승인](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/skills.md), [프로필 경계](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/profiles.md) |
| 1 | [Future-House/paper-qa](https://github.com/Future-House/paper-qa) (Apache-2.0) | 논문 원문 검색 → 증거 수집 → 인용된 답변, 충돌 탐색, 로컬 인덱스 | 별도 문헌 검색 계층을 만들고 언어학·인지과학·LM·통계·코퍼스 전문가의 **외부 문헌 전용** 도구에 시범 적용. DOI·페이지·인용 구간을 별도 근거 레코드에 저장 | 문헌 근거에 직접 맞는다. 기본 설정이 외부 OpenAI 모델·임베딩을 쓰므로 미공개 요청·내부 실험 기록을 그대로 넣으면 안 된다. 로컬 임베딩과 허용된 모델을 명시하고, 외부 문헌 색인과 내부 기억 색인을 분리. `lab/learning.py`는 검색 엔진이 아니라 학습 완료 보고 큐다. [설정과 검색](https://github.com/Future-House/paper-qa#readme) |
| 1 | [SakanaAI/AI-Scientist-v3](https://github.com/SakanaAI/AI-Scientist-v3) (Apache-2.0) | 실행별 고정 스냅샷, 단계별 산출물, 봉인된 최종 평가, baseline·ablation 기록 | `lab/pipeline.py`의 계획 승인 후 `protocol.json` 해시·코드·실행 인자를 묶은 run snapshot 생성. `lab/sandbox.py` 실행 결과를 독립 검증 담당이 재계산하고 `run_manifest.json`과 대조 | 실험 재현성과 결과 오염 방지에 직접적. 전체 자동 아이디어→논문 루프는 연구자의 설계 승인 경계와 맞지 않으므로 복제하지 않는다. [파이프라인](https://github.com/SakanaAI/AI-Scientist-v3#how-it-works) |
| 2 | [letta-ai/letta-code](https://github.com/letta-ai/letta-code) (Apache-2.0) | 짧은 상시 기억, 원본을 찾는 장기 기억, 기억 변경 이력, 절차 스킬을 구분하는 구조 | 연구실장에만 `연구자 확인 선호·현재 결정`의 짧은 상시 맥락을 둔다. 과거 실험·대화는 로컬 원본 경로와 해시를 가진 검색 인덱스로 조회. 기억 변경은 제안→연구자 확정 | 세컨드 브레인 정보 배치에 유용. Letta 전체 런타임으로 바꾸면 기존 Discord·승인·도구 구조가 중복된다. 기본 Cloud 경로·Git 동기화는 미공개 자료 정책 확인 전 사용하지 않는다. 옛 [`letta-ai/letta`](https://github.com/letta-ai/letta)는 현재 코드가 `letta-code`로 이동했음을 안내한다. [현재 기능](https://github.com/letta-ai/letta-code#feature-overview) |
| 2 이후 | [getzep/graphiti](https://github.com/getzep/graphiti) (Apache-2.0) | 변경 전후 사실의 유효 기간, 원본 episode 연결, 키워드·의미·관계 혼합 검색 | 연구실장 결정 이력이 복잡해진 뒤에만 검토. 먼저 SQLite 기반 인덱스에서 `source_path`, `sha256`, `valid_from/to`, `verification_status`, `classification`을 구현하고 검색 평가를 수행 | 결정 충돌·수정에는 좋은 모델. Graphiti는 그래프 DB와 LLM·임베딩 제공자가 필요한 별도 서비스여서 현재 규모에는 운영 비용이 크다. 기본 OpenAI 경로를 그대로 쓰지 않는다. [구조·요구사항](https://github.com/getzep/graphiti#readme) |
| 선택 참고 | [stanford-oval/storm](https://github.com/stanford-oval/storm) (MIT) | 여러 관점에서 질문 만들기, 질문→근거→개요의 문헌 조사 절차 | 문헌 조사 요청에서 전문가들이 서로 다른 반례·방법 질문을 만드는 **프롬프트 패턴**만 실험. 최종 연구 질문·가설은 연구자가 정한다 | 체계적인 배경 조사에 유용하지만 공개 웹 기반 자동 보고서가 연구자 원안과 섞일 수 있고 모델 호출이 늘어난다. [설계](https://github.com/stanford-oval/storm#readme) |

### 보류 후보

[hncpyj/research-agent-lab](https://github.com/hncpyj/research-agent-lab)은 승인된 과학적 의도와 구현·실행·보고를 연결하는 `Protocol Before Code` 개념이 현재 P0 문제와 가깝다. 다만 저장소가 스스로 연구 프로토타입이라고 밝히며 PolyForm Noncommercial 라이선스를 사용한다. **설계 개념과 검증 항목을 참고**하고, 코드 복사는 별도 라이선스 검토 뒤에만 한다. [아키텍처·라이선스](https://github.com/hncpyj/research-agent-lab#readme)

## 에이전트별 적용

| 현재 역할 | 추가할 능력 | 경계 |
|---|---|---|
| 연구실장 | 로컬 연구 기억 검색, 원본 열람, 결정 제안; 답변마다 `연구자 결정 / 실험 관측 / 외부 문헌 / AI 제안`, 경로·검증 상태 표시 | 과거 기억은 새 지시를 덮지 않고 승인 도구도 갖지 않음 |
| Hermes 실무 담당 | 승인된 명세·해시를 입력으로 받아 계획·실행, 변경 필요 시 `request_change`; 검토된 절차 스킬 재사용 | 모델 자체 기억이나 자유 셸 명령으로 조건·시드·지표 변경 불가 |
| 5인 자문 전문가 | PaperQA2를 통한 허용된 외부 문헌 질의, 반례와 근거 구간 반환 | 내부 자료를 문헌 색인으로 보내지 않음. 자문은 연구자 원안과 별도 표시 |
| 개발 담당 | 승인된 명세와 구현의 일치 검사, 실행 설정 파일 생성 | 과학적 설계를 임의 보정하지 않음 |
| 검증 담당 | 독립 재계산, baseline·ablation·manifest·보고 수치 확인 | 실무 담당의 요약만으로 통과 판정하지 않음 |
| 문서 담당 | 근거 ID→원본 경로·실행 ID 연결표와 주장별 증거 표 작성 | 출처 없는 단정과 미검증 결과의 확정 표현 금지 |

## 구현 순서와 통과 기준

1. **P0 자료 경계:** 실험·자료 등급, 허용 모델·게시 경로를 정의하고 모델 호출 직전·폴백·Discord 게시 전에 강제한다. 외부 문헌 DIGEST 자동 주입은 등급별 허용으로 바꾼다. 가짜 미공개 아이디어를 이용한 누출 테스트가 0건이어야 한다.
2. **P0 승인 명세:** `protocol.json`을 승인 시 해시로 고정하고, 본 실행 명령을 구조화된 명세에서 생성한다. `run_manifest.json`을 명세·코드·데이터 체크섬과 대조한다. 인자 변경·재시도·산출물 변조 테스트에서 모두 차단되어야 한다.
3. **P1 문헌 근거:** 외부 공개 문헌만 별도 색인에 넣어 PaperQA2의 검색·인용 결과를 현재 키워드 방식과 비교한다. DOI·페이지·인용 구간 정확도와 허위 인용 건수를 확인하고, 외부 LLM/임베딩 전송 정책을 별도로 확인한다.
4. **P1 연구실장 기억:** 원본 `workspace/`와 로컬 인덱스를 연결한다. 출처 경로·해시·날짜·검증 상태·자료 등급 필터와 한국어 검색을 먼저 만들고, 충분한 규모가 될 때만 Graphiti를 검토한다. 충돌하는 과거 결정과 실패 실험도 찾을 수 있어야 한다.
5. **P2 Hermes 그림자 계획:** 같은 공개·가상 요청으로 기존 실무 담당과 Hermes의 계획을 비교한다. 의도 보존, 필수 조건 누락, 부당한 변경, 비용·시간을 기록한 뒤 제한된 실행으로 확장한다.

**복제 방침:** 지금은 어느 저장소도 통째로 클론해 파이프라인에 넣지 않는다. 현재 Python·SQLite·Discord·Toolbox 기반 구조와 승인 책임을 유지하고, 작은 인터페이스와 검증 가능한 산출물 단위로 도입한다. 실제 코드 복사 시에는 해당 커밋·라이선스·변경 내용을 기록한다.

## 상세 설계: 어디에, 어떻게, 왜

### 1. Hermes Agent: 실험 실무 담당의 제한된 실행 엔진

**현재 위치.** `lab/pipeline.py`의 `_phase_plan()`과 `_phase_execute()`가 `practitioner`를 호출한다. `lab/backends.py`의 `HermesBackend`는 이미 전용 프로필의 한 턴 응답을 기존 도구 호출 형식으로 변환한다. 실제 실행은 `lab/tools.py`의 `Toolbox`가 맡고, 현재 `ROUTE_PRACTITIONER` 기본 경로는 Hermes가 아니다.

**필요한 이유.** 실무 담당에게는 자문을 계획으로 통합하고 실행 오류를 보고하는 연속성이 유용하다. Hermes의 프로필 기억과 스킬은 반복되는 *절차*를 축적할 수 있다. 그러나 과거에 성공한 절차가 새 실험의 조건·표본·지표를 자동으로 정하는 근거가 되면 승인된 연구 질문이 바뀐다. 따라서 Hermes의 학습 대상은 “로그를 확인하는 순서, 재시도 전 점검표” 같은 조작 절차로 한정한다. [Hermes 기억·스킬 쓰기 승인](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/memory.md), [스킬 승인](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/skills.md).

**연결 방법.** `_phase_plan()`에는 연구자 요청서, 자문 메모, 검색된 과거 사례의 출처만 전달한다. `_phase_execute()`에는 승인된 `protocol.json` 버전·해시, 허용 실행 진입점, 결과 파일 규약을 전달한다. 실무 담당의 도구 목록에서 본 실행용 자유 형식 `run_command`를 구조화된 `run_approved_protocol`로 교체하고, 그 도구가 명세에서 명령을 생성한다. 변경이 필요하면 이미 있는 `request_change`로 멈춘다. 승인 후에는 새 명세 버전을 발행한다. Hermes 스킬 쓰기는 현재처럼 승인 대기로 두고, 재현 가능한 절차만 활성화한다.

**완료 판정.** 공개·가상 데이터의 동일 요청서로 기존 실무 담당과 Hermes 계획을 비교한다. 필수 조건 누락·무단 변경·불필요한 도구 호출·재시도 성공률과 비용을 기록한다. 승인 전 실행과 승인 명세와 다른 인자를 모두 차단해야 실제 경로를 전환한다. Hermes 프로필은 상태를 분리하지만 파일시스템 접근 제한 수단은 아니라는 [공식 설명](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/profiles.md)을 도구 권한 설계에 반영한다.

### 2. PaperQA2: 전문가의 외부 문헌 근거 검색

**현재 위치.** `knowledge/literature/<role>.md`의 DIGEST는 `lab/agents.py`에서 역할 프롬프트에 자동 붙는다. 자문 결과는 `lab/pipeline.py`의 `_phase_consult()`가 `notes/consult_<role>.md`로 받는다. `lab/learning.py`는 학습 완료 보고 큐이며 논문 검색 기능은 없다. 팀원 직접 대화는 `lab/team.py`의 읽기 도구만 사용한다.

**필요한 이유.** 현재 DIGEST는 요약과 원문 근거 사이의 연결이 약하다. 예를 들어 언어학 담당이 선행 연구의 조작 정의를, 통계 담당이 효과 크기와 분석 조건을 제시할 때 논문·페이지·구간을 함께 보존해야 검증 담당이 다시 확인할 수 있다. PaperQA2의 문서 검색·증거 수집·답변 흐름이 여기에 맞는다. [PaperQA2 README](https://github.com/Future-House/paper-qa#readme).

**연결 방법.** 공개 논문만 담은 `literature_index`를 별도로 만들고 `search_literature(query, role, k)`라는 읽기 전용 연구실 도구를 제공한다. 반환값은 최소 `paper_id/DOI`, 제목, 출처 파일, 페이지·구간, 검색된 문장, 인용 식별자, 색인 버전을 포함한다. 자문 메모에는 그 식별자를 붙이고, 계획 통합 시 `연구자 지정 / 외부 근거 / 전문가 제안`을 분리한다. 현재 `literature_digest(role)`의 자동 주입은 검색 요청 또는 실험별 문헌 허용 정책에 따른 주입으로 바꾼다. 팀원 봇에 연결할 때도 같은 자료 등급 검사를 적용한다.

**모델 경계.** PaperQA2의 기본 모델·임베딩은 OpenAI 경로다. 로컬 임베딩을 지원하지만 그것만 바꿔서는 요약·질의 모델의 외부 호출이 사라지지 않는다. 색인 입력, 질의 문장, 검색 구간 각각에 등급 검사를 적용한다. 내부 요청서의 미공개 가설을 그대로 검색 질의로 보내지 않는다. [기본 설정과 로컬 임베딩](https://github.com/Future-House/paper-qa#readme).

**완료 판정.** 공개 논문 20~30편과 연구자가 직접 만든 질의 세트로 현재 DIGEST 방식과 비교한다. 문헌 발견률, DOI·페이지 정확도, 인용 문장 지지율, 반례 발견률, 질의당 비용·시간을 측정한다. 자료 누출 테스트를 먼저 통과한다.

### 3. AI-Scientist-v3: 실행 기록과 독립 평가의 구조

**현재 위치.** `_phase_plan()`은 `plan.md`와 `plan.json`을 저장하고 연구자 승인을 기다린다. `_phase_execute()`는 실행 전후 요청서·계획·코드 해시를 비교한다. `run_command`는 여전히 자유 형식 명령을 받고, 실행이 어떤 데이터·조건·시드로 이뤄졌는지 검증 가능한 manifest가 없다. 이후 분석·해석·보고·검증 단계가 진행된다.

**필요한 이유.** 코드 파일이 바뀌지 않아도 실행 인자 하나로 실제 실험은 바뀔 수 있다. AI-Scientist-v3가 사용하는 실행별 고정 task snapshot, 단계별 결과 보관, 분리된 최종 평가 방식은 이 빈틈을 메우는 설계 참고가 된다. 해당 저장소는 실험·ablation·최종 평가를 실행별 폴더에 보관하고 단계를 격리한다. [파이프라인 설명](https://github.com/SakanaAI/AI-Scientist-v3#how-it-works).

**연결 방법.** 승인 시 `protocol.json`을 생성해 연구 질문, 데이터 체크섬, 모델 버전, 조건, 표본·시드, 지표, 제외 기준, 분석법을 고정한다. 개발 담당의 `finish_build.entrypoints`는 이 명세와 일치하는지 검증하고, 실무 담당은 허용된 진입점·인자만 실행한다. 실행 래퍼가 `run_manifest.json`에 명세 해시, 코드·데이터 해시, 실제 명령, 환경, 시드, 시작·종료 시각, 출력 파일 해시를 기록한다. 검증 담당은 원자료를 별도 읽기 경로에서 재계산하고 보고서의 수치와 비교한다. baseline·ablation은 연구자가 계획에서 지정한 경우에만 수행한다.

**완료 판정.** 시드·조건·데이터 파일·지표를 바꾼 가짜 실행이 모두 명세 불일치로 중단되고, 같은 명세의 재실행은 결과와 로그를 추적할 수 있어야 한다. 연구자 승인 없이 자동 아이디어 탐색이나 승자 선택을 시작하지 않는다.

### 4. Letta Code: 연구실장 기억을 나누는 방법

**현재 위치.** 연구실장 `lab/director.py`는 `search_notebook`과 실험 파일 읽기를 제공하지만, `lab/notebook.py`의 결과는 완료 요약 앞부분만 반환한다. 연구자 결정, 실험 관측, 모델 제안의 경계와 오래된 결정의 수정 상태는 저장·검색되지 않는다.

**필요한 이유.** 매번 모든 기록을 프롬프트에 넣으면 오래된 지시와 새 지시가 섞이고 비용도 증가한다. Letta Code는 상시 기억과 필요할 때 검색하는 기억·메시지 이력을 구분하고 기억 변경 이력을 관리한다. 이 **기억 계층 구조**를 연구실장에 맞춰 적용한다. [현재 Letta Code 기능](https://github.com/letta-ai/letta-code#feature-overview).

**연결 방법.** 연구자가 확인한 지속적 선호와 현재 유효한 결정만 짧은 상시 맥락으로 `director_system()`에 넣는다. 나머지는 `workspace/experiments/`와 `workspace/notebook/` 원본을 가리키는 로컬 SQLite 검색 인덱스에 저장한다. `lab/director.py`에 `search_research_memory`, `read_source`, `propose_decision`을 만들고, 결정 확정은 연구자 입력에서만 처리한다. 검색 결과에는 `source_path`, 해시, 실험 ID, 자료 등급, 검증 상태를 포함한다. `lab/team.py`의 팀원 직접 대화에는 자신의 권한 범위에 맞는 읽기 결과만 제공한다.

**운영 경계.** Letta 런타임 자체를 붙이면 현재 Discord 봇·모델 라우팅·승인 관리와 겹친다. Letta Code는 Cloud가 기본 선택지이고 기억 저장소 동기화 기능이 있으므로 미공개 기록을 다루는 지금은 로컬 구조만 참고한다. [현재 소스와 로컬/Cloud 선택](https://github.com/letta-ai/letta-code#readme).

**완료 판정.** 연구실장이 과거 결정의 원본을 찾고, 실패·미검증 실험을 성공으로 설명하지 않으며, 연구자의 새 지시가 과거 기억과 충돌할 때 충돌을 밝히는지 평가한다. 출처 없는 수치 진술은 0건이어야 한다.

### 5. Graphiti: 결정과 사실의 시간 이력이 복잡해질 때

**현재 위치.** `lab/ledger.py`의 `events`는 실험의 상태 변화를 시간순 기록하지만, “이 분석 기준은 언제부터 유효했는가”, “어떤 원본이 이 판단을 뒷받침했는가”를 질의하는 기억 모델은 아니다. `lab/notebook.py`의 검색도 단어 일치다.

**필요한 이유.** 연구자의 방법 선호·용어 정의·실험 결론은 수정될 수 있다. Graphiti의 episode→사실→유효 기간 구조와 하이브리드 검색은 과거 판단을 지우지 않으면서 현재 유효한 판단을 찾는 문제에 맞는다. [Graphiti 데이터 모델](https://github.com/getzep/graphiti#readme).

**연결 방법.** 먼저 SQLite에 `memory_sources`, `memory_facts`, `decision_revisions` 수준의 작은 스키마를 만든다. 각 사실은 원본 파일·해시와 자료 등급, `valid_from/to`, 검증 상태를 가진다. 연구실장이 원본을 열지 않고도 사실을 확정하지 않게 한다. 단어/한국어 문자 n-gram 검색에서 필요한 사례가 충분히 쌓였는데도 결정 연결 질의가 실패할 때 Graphiti로 같은 테스트 세트를 평가한다.

**도입 조건.** Graphiti는 자체 서비스·그래프 DB와 LLM·임베딩 설정이 필요하다. 현재 소규모 연구실에서는 인프라 부담이 검색 품질 이득보다 클 수 있다. 기본 외부 모델 경로는 자료 정책을 통과해야 한다. [요구사항](https://github.com/getzep/graphiti#installation).

### 6. STORM: 배경 조사에서 빠뜨린 관점 찾기

**현재 위치.** 다섯 전문가가 `_phase_consult()`에서 각자 자문하고, 실무 담당이 `_phase_plan()`에서 이를 통합한다. 현재는 질문 탐색의 범위·반례 조사 여부를 구조적으로 확인하지 않는다.

**필요한 이유.** STORM은 여러 관점의 질문을 만든 뒤 근거를 찾고 개요로 묶는다. 여기서는 자동 보고서 생성보다 **질문 생성 순서**가 유용하다. 언어학 담당은 조작 정의, 인지과학 담당은 메커니즘 대안, LM 담당은 모델 혼입, 통계 담당은 교란·검정력, 코퍼스 담당은 표본 편향을 질문으로 제출하게 한다. [STORM의 관점별 질문 설계](https://github.com/stanford-oval/storm#readme).

**연결 방법.** 자문 메모 스키마에 `unanswered_questions`, `counter_evidence`를 추가하거나 메모 본문의 고정 섹션으로 시작한다. 실무 담당 계획에는 “답한 질문 / 확인 전 질문 / 연구자 결정 필요”를 표시한다. 공개 문헌 검색은 PaperQA2 계층을 사용한다. 외부 웹에서 수집한 문구는 출처가 붙은 자료로만 다루고 연구자의 지시로 해석하지 않는다.

**완료 판정.** 작은 공개 주제 두세 개에서 기존 자문 대비 새로 발견한 중요한 반례·교란 수와 불필요한 질문·모델 호출 비용을 비교한다. 유의미한 누락 감소가 없으면 도입하지 않는다.

### 7. ResearchAgentLab: 승인된 의도와 결과를 잇는 통제 설계 참고

**현재 위치.** 현재 계획 승인과 `request_change`는 존재하지만, 승인된 질문→명세→코드→실제 실행→보고 주장 사이의 기계적 연결이 약하다.

**필요한 이유.** 이 저장소의 `Protocol Before Code`는 과학적 의도 충실성, 방법론 검토, 구현 검증, 실행 증거, 주장 수용을 별도로 본다. 이는 현재 P0 작업의 검증 항목을 정리하는 데 직접 유용하다. [연구 프로토타입의 설계 설명](https://github.com/hncpyj/research-agent-lab#readme).

**연결 방법.** 구현 코드를 복사하기보다 체크리스트를 `lab/pipeline.py` 상태 전환에 매핑한다: 계획 승인 전 의도 충실성·방법 검토, 실행 전 명세·코드 해시 확인, 실행 후 manifest·원자료 확인, 보고 전 주장별 증거 확인. 판정 결과는 `lab/ledger.py` 이벤트와 실험 폴더의 검증 파일에 남긴다.

**채택 한계.** 프로젝트는 연구 프로토타입이며 PolyForm Noncommercial 1.0.0을 명시한다. 코드 복사·재배포를 결정할 때는 사용 목적과 라이선스를 따로 검토해야 한다. [라이선스 설명](https://github.com/hncpyj/research-agent-lab#license).
