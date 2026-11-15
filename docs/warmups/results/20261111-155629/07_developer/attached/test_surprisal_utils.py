"""문서화된 단어 surprisal 동작의 회귀 테스트."""
import importlib.util
import math
import os
from pathlib import Path

import pytest


module_path = Path(os.environ.get("SURPRISAL_MODULE", "surprisal_utils.py"))
spec = importlib.util.spec_from_file_location("surprisal_utils_under_test", module_path)
surprisal = importlib.util.module_from_spec(spec)
spec.loader.exec_module(surprisal)


def test_subword_surprisal_is_summed_per_word_including_final_word():
    logprobs = [-math.log(2), -math.log(4), -math.log(8)]
    assert surprisal.word_surprisal(logprobs, [0, 0, 1]) == pytest.approx([3.0, 3.0])


def test_single_word_is_returned():
    assert surprisal.word_surprisal([-math.log(2)], [0]) == pytest.approx([1.0])


def test_mean_is_over_words():
    logprobs = [-math.log(2), -math.log(4), -math.log(16)]
    assert surprisal.mean_surprisal(logprobs, [0, 0, 1]) == pytest.approx(3.5)


def test_empty_input():
    assert surprisal.word_surprisal([], []) == []
    assert surprisal.mean_surprisal([], []) == 0.0


def test_mismatched_lengths_raise_value_error():
    with pytest.raises(ValueError, match="길이가 다릅니다"):
        surprisal.word_surprisal([-math.log(2)], [])
