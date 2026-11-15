import importlib.util
import os
from pathlib import Path

import pytest


module_path = Path(os.environ.get("SURPRISAL_MODULE", "surprisal_utils.py"))
spec = importlib.util.spec_from_file_location("surprisal_utils_under_test", module_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_one_word_includes_final_word():
    assert module.word_surprisal([-2.0 * __import__("math").log(2)], [0]) == pytest.approx([2.0])


def test_subwords_are_summed_for_each_word():
    import math

    assert module.word_surprisal([-math.log(2), -2 * math.log(2), -3 * math.log(2)], [0, 0, 1]) == pytest.approx([3.0, 3.0])


def test_mean_uses_all_words():
    import math

    assert module.mean_surprisal([-math.log(2), -3 * math.log(2)], [0, 1]) == pytest.approx(2.0)


def test_empty_input():
    assert module.word_surprisal([], []) == []
    assert module.mean_surprisal([], []) == 0.0


def test_mismatched_lengths():
    with pytest.raises(ValueError, match="길이가 다릅니다"):
        module.word_surprisal([-1.0], [])
