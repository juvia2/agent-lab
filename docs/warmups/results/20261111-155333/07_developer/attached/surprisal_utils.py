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
    # 수정: 마지막 단어의 누적값도 반환에 포함한다.
    if current is not None:
        out.append(acc)
    return out


def mean_surprisal(token_logprobs, word_ids):
    """문장의 단어 평균 surprisal(bit)."""
    s = word_surprisal(token_logprobs, word_ids)
    return sum(s) / len(s) if s else 0.0
