import math

import pytest

from surprisal_utils import mean_surprisal, word_surprisal


def test_single_word_includes_final_word():
    assert word_surprisal([-math.log(2)], [0]) == pytest.approx([1.0])


def test_subword_surprisals_sum_by_word():
    logprobs = [-math.log(2), -math.log(4), -math.log(8)]
    assert word_surprisal(logprobs, [0, 0, 1]) == pytest.approx([3.0, 3.0])


def test_last_word_with_multiple_subwords():
    logprobs = [-math.log(2), -math.log(2), -math.log(4)]
    assert word_surprisal(logprobs, [0, 1, 1]) == pytest.approx([1.0, 3.0])


def test_word_ids_need_not_start_at_zero():
    logprobs = [-math.log(2), -math.log(2), -math.log(4)]
    assert word_surprisal(logprobs, [3, 3, 4]) == pytest.approx([2.0, 2.0])


def test_output_length_equals_number_of_words():
    logprobs = [-1.0] * 5
    assert len(word_surprisal(logprobs, [0, 0, 1, 2, 2])) == 3


def test_mean_surprisal_uses_all_words():
    logprobs = [-math.log(2), -math.log(8)]
    assert mean_surprisal(logprobs, [0, 1]) == pytest.approx(2.0)


def test_empty_input():
    assert word_surprisal([], []) == []
    assert mean_surprisal([], []) == 0.0


def test_mismatched_lengths_raise_value_error():
    with pytest.raises(ValueError, match='길이가 다릅니다'):
        word_surprisal([-1.0], [])
