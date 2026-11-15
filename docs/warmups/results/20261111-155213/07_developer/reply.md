문서화된 동작과 다른 점을 테스트로 재현했습니다. 원본은 마지막 단어의 surprisal을 결과에 넣지 않아 단어 목록과 평균이 잘못 계산됩니다. 마지막 단어를 추가하도록 고쳤고, 원본에서는 관련 테스트가 실패하며 수정본에서는 전체 테스트가 통과했습니다.

수정한 [모듈](surprisal_utils.py), [pytest 테스트](tests/test_surprisal_utils.py), [실행 로그](execution.log)를 첨부했습니다.
