"""연구실 공용 유틸리티. 각 실험의 code/ 폴더에 복사되어 샌드박스 안에서 import 한다.

    from lab_utils import set_seed, write_manifest, bootstrap_ci, paired_permutation_test, holm
"""
from __future__ import annotations

import hashlib
import importlib.metadata as md
import json
import platform
import random
import sys
import time
from pathlib import Path

_TRACKED = ["numpy", "scipy", "pandas", "scikit-learn", "statsmodels", "torch",
            "transformers", "datasets", "tokenizers", "matplotlib"]


def set_seed(seed: int) -> int:
    """python / numpy / torch 의 시드를 한 번에 고정한다."""
    random.seed(seed)
    try:
        import numpy as np
        np.random.seed(seed)
    except Exception:
        pass
    try:
        import torch
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    except Exception:
        pass
    return seed


def file_sha256(path: str | Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def write_manifest(path: str | Path = "results/run_manifest.json", *, seed=None,
                   data_files: list[str] | None = None, **extra) -> dict:
    """재현에 필요한 실행 정보를 기록한다."""
    versions = {}
    for pkg in _TRACKED:
        try:
            versions[pkg] = md.version(pkg)
        except md.PackageNotFoundError:
            pass
    manifest = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "argv": sys.argv,
        "seed": seed,
        "packages": versions,
        "data_sha256": {f: file_sha256(f) for f in (data_files or []) if Path(f).exists()},
    }
    manifest.update(extra)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def bootstrap_ci(values, stat=None, n_boot: int = 10000, alpha: float = 0.05, seed: int = 0):
    """부트스트랩 백분위 신뢰구간. 반환: (추정치, 하한, 상한)"""
    import numpy as np
    x = np.asarray(values, dtype=float)
    stat = stat or np.mean
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(x), size=(n_boot, len(x)))
    boots = np.array([stat(x[i]) for i in idx])
    lo, hi = np.percentile(boots, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return float(stat(x)), float(lo), float(hi)


def paired_permutation_test(a, b, n_perm: int = 10000, seed: int = 0) -> dict:
    """짝지은 표본의 부호 뒤집기 순열검정(양측). 반환: 평균차, p값, Cohen's dz"""
    import numpy as np
    d = np.asarray(a, dtype=float) - np.asarray(b, dtype=float)
    rng = np.random.default_rng(seed)
    obs = abs(d.mean())
    signs = rng.choice([-1.0, 1.0], size=(n_perm, len(d)))
    perm = np.abs((signs * d).mean(axis=1))
    p = (np.sum(perm >= obs) + 1) / (n_perm + 1)
    sd = d.std(ddof=1) if len(d) > 1 else float("nan")
    return {"mean_diff": float(d.mean()), "p": float(p),
            "cohens_dz": float(d.mean() / sd) if sd and sd == sd and sd > 0 else None, "n": int(len(d))}


def holm(pvals: list[float]) -> list[float]:
    """Holm-Bonferroni 보정 p값 (입력 순서 유지)."""
    m = len(pvals)
    order = sorted(range(m), key=lambda i: pvals[i])
    adj = [0.0] * m
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, (m - rank) * pvals[i])
        adj[i] = min(1.0, running)
    return adj
