import wave

import pytest

from scripts.stage_first_stt_pilot import stage


def test_stage_verifies_audio_pair_and_preserves_existing_copy(tmp_path):
    source, dest = tmp_path / "source", tmp_path / "dest"
    source.mkdir()
    wav = source / "KsponSpeech_000001.wav"
    with wave.open(str(wav), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b"\x00\x00")
    (source / "KsponSpeech_000001.txt").write_text("검토 전사", encoding="utf-8")

    result = stage(source, dest)
    assert result["clips"][0]["files"]["wav"]["file"] == wav.name
    assert (dest / wav.name).read_bytes() == wav.read_bytes()
    assert stage(source, dest) == result

    (dest / wav.name).write_bytes(b"changed")
    with pytest.raises(ValueError, match="differs"):
        stage(source, dest)
