"""샌드박스: 에이전트가 쓴 코드를 격리해서 실행한다.

docker 백엔드(기본): 컨테이너 안에서 실행, 기본 네트워크 차단, 실험 폴더만 쓰기 가능.
host 백엔드: 맥에서 직접 실행(MPS GPU 사용 가능). 격리가 없으므로 계획 단계에서 반드시 연구자 승인을 받는다.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RunResult:
    exit_code: int
    output: str
    timed_out: bool
    seconds: float


class Sandbox:
    def __init__(self, cfg):
        self.cfg = cfg

    # 테스트 가능하도록 순수 함수로 분리
    def docker_args(self, exp_id: str, exp_dir: Path, command: str, network: bool) -> list[str]:
        c = self.cfg
        args = ["docker", "run", "--rm", "--name", f"lab-{exp_id.lower()}",
                "--cpus", str(c.sandbox_cpus), "--memory", str(c.sandbox_memory),
                "--pids-limit", "1024",
                "--network", "bridge" if network else "none",
                "-v", f"{exp_dir}:/work",
                "-v", f"{c.data_dir}:/data:ro",
                "-v", f"{c.hf_cache_dir}:/hf_cache",
                "-e", "HF_HOME=/hf_cache", "-e", "PYTHONUNBUFFERED=1",
                "-e", "TOKENIZERS_PARALLELISM=false",
                "-w", "/work", c.docker_image, "bash", "-lc", command]
        return args

    def run(self, exp_id: str, exp_dir: Path, command: str, *, timeout_s: int, network: bool,
            host: bool = False) -> RunResult:
        start = time.time()
        if self.cfg.sandbox_backend == "docker" and not host:
            argv = self.docker_args(exp_id, exp_dir, command, network)
            env = None
            cwd = None
        else:
            argv = ["bash", "-lc", command]
            env = dict(os.environ, HF_HOME=str(self.cfg.hf_cache_dir), PYTHONUNBUFFERED="1",
                       TOKENIZERS_PARALLELISM="false", LAB_DATA=str(self.cfg.data_dir))
            venv_bin = self.cfg.lab_home / "host-venv" / "bin"
            if venv_bin.is_dir():                      # MPS 용 파이썬 환경이 있으면 우선 사용
                env["PATH"] = f"{venv_bin}{os.pathsep}{env.get('PATH', '')}"
            cwd = str(exp_dir)
        try:
            p = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True,
                               timeout=timeout_s, errors="replace")
            out = (p.stdout or "") + (("\n[stderr]\n" + p.stderr) if p.stderr else "")
            if (p.returncode != 0 and argv[0] == "docker" and "Cannot connect to the Docker daemon" in out
                    and try_start_colima()):          # 잠자기·재부팅 뒤 도커가 꺼진 경우 한 번 복구
                p = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True,
                                   timeout=timeout_s, errors="replace")
                out = (p.stdout or "") + (("\n[stderr]\n" + p.stderr) if p.stderr else "")
            return RunResult(p.returncode, out, False, time.time() - start)
        except subprocess.TimeoutExpired as e:
            self.kill(exp_id)
            def _s(x):
                return x.decode("utf-8", "replace") if isinstance(x, bytes) else (x or "")
            out = _s(e.stdout) + (("\n[stderr]\n" + _s(e.stderr)) if e.stderr else "")
            return RunResult(124, out + f"\n[시간 초과: {timeout_s}초]", True, time.time() - start)
        except FileNotFoundError as e:
            return RunResult(127, f"실행 파일을 찾지 못함: {e}", False, time.time() - start)

    def kill(self, exp_id: str) -> None:
        if self.cfg.sandbox_backend == "docker" and shutil.which("docker"):
            subprocess.run(["docker", "rm", "-f", f"lab-{exp_id.lower()}"], capture_output=True)


def docker_ready() -> bool:
    if not shutil.which("docker"):
        return False
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=20).returncode == 0
    except Exception:
        return False


def try_start_colima() -> bool:
    """도커 데몬이 꺼져 있으면 colima 를 시작해 본다(재부팅 후 자동 복구용)."""
    if not shutil.which("colima"):
        return False
    try:
        subprocess.run(["colima", "start"], capture_output=True, timeout=300)
    except Exception:
        return False
    return docker_ready()
