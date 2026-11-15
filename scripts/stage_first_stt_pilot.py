"""Stage the first STT project's five reviewed P clips for a local data pilot."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import wave
from pathlib import Path

DEST = Path(__file__).resolve().parent.parent / "workspace/data/stt_pilot"


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def stage(source: Path, dest: Path = DEST) -> dict:
    source = source.resolve()
    if not source.is_dir():
        raise ValueError(f"sample directory missing: {source}")
    clips = sorted(source.glob("KsponSpeech_*.wav"))
    if not clips:
        raise ValueError("no reviewed WAV clips found")
    if dest.resolve() == source or source in dest.resolve().parents:
        raise ValueError("destination must be separate from the source")
    dest.mkdir(parents=True, exist_ok=True)
    rows = []
    for wav in clips:
        txt = wav.with_suffix(".txt")
        if not txt.is_file():
            raise ValueError(f"missing transcript: {txt.name}")
        with wave.open(str(wav), "rb") as audio:
            if audio.getnframes() == 0:
                raise ValueError(f"empty audio: {wav.name}")
            audio_meta = {"sample_rate": audio.getframerate(), "channels": audio.getnchannels(),
                          "frames": audio.getnframes()}
        if not txt.read_text(encoding="utf-8-sig").strip():
            raise ValueError(f"empty transcript: {txt.name}")
        files = {}
        for original in (wav, txt):
            staged = dest / original.name
            source_hash = digest(original)
            if staged.exists() and digest(staged) != source_hash:
                raise ValueError(f"staged file differs: {staged.name}")
            if not staged.exists():
                shutil.copy2(original, staged)
            if digest(staged) != source_hash:
                raise RuntimeError(f"copy verification failed: {staged.name}")
            files[original.suffix.lstrip(".")] = {"file": original.name, "sha256": source_hash,
                                                    "bytes": original.stat().st_size}
        rows.append({"clip_id": wav.stem, "files": files, "audio": audio_meta})
    manifest = {"purpose": "local data integrity pilot; not final test set", "source": str(source),
                "clips": rows}
    (dest / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="AIHub_KsponSpeech_검토샘플 folder")
    args = parser.parse_args()
    print(f"staged {len(stage(args.source)['clips'])} clip pairs in {DEST}")
