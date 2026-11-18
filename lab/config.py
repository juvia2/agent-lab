from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _int(name: str, default: int | None) -> int | None:
    v = os.environ.get(name, "").strip()
    return int(v) if v else default


# 역할별 모델 우선순위. 앞이 막히면(한도·로그인·꺼짐) 다음으로 넘어간다. 형식: 백엔드[/모델], 쉼표로 구분.
# 백엔드: claude(구독 CLI) · codex(구독 CLI) · gemini(구독 CLI) · local(OpenAI 호환 로컬 서버) · api(토큰 과금, 기본 제외)
DEFAULT_ROUTES = {
    "director": "claude/sonnet, gemini, local",
    "linguist": "claude/opus, gemini, codex",
    "cogsci": "claude/opus, gemini, codex",
    "lm": "claude/opus, gemini, codex",
    "statistician": "claude/opus, gemini, codex",
    "corpus": "local, claude/sonnet, gemini",
    "developer": "codex, claude/sonnet, local",
    "practitioner": "local, gemini, claude/sonnet",
    "documenter": "local, claude/sonnet, gemini",
    "tester": "claude/opus, codex, gemini",
    "default": "claude/sonnet, gemini, codex, local",
}


def load_routes() -> dict:
    from .backends import parse_route
    out = {}
    for role, spec in DEFAULT_ROUTES.items():
        out[role] = parse_route(os.environ.get(f"ROUTE_{role.upper()}", spec))
        if any(name == "hermes" for name, _ in out[role]):
            if role != "practitioner" or len(out[role]) != 1:
                raise ValueError("Hermes는 ROUTE_PRACTITIONER=hermes 단독 경로에서만 허용됩니다")
    return out


def _discord_id(name: str) -> int | None:
    v = os.environ.get(name, "").strip()
    if not v:
        return None
    if not v.isdigit():
        raise SystemExit(
            f"{name} 에는 숫자 ID 를 넣어야 합니다(지금 값: {v!r}). 사용자 이름(@아이디)이 아닙니다.\n"
            "디스코드 설정 → 고급 → 개발자 모드 켜기 → 내 프로필(또는 서버 아이콘) 우클릭 → ID 복사 (18~19자리 숫자)")
    return int(v)


@dataclass
class Config:
    lab_home: Path
    anthropic_api_key: str | None
    discord_token: str | None
    discord_owner_id: int | None
    discord_guild_id: int | None
    intake_channel: str
    report_channel: str
    perf_channel: str             # 에이전트 성능 향상(학습·테스트) 리포트 전용. 연구 진행 채널과 분리
    test_channel: str             # 봇 접속·권한·개발 점검 전용
    adhoc_channel: str            # 실험과 무관한 단건 의뢰(담당자에게 직접 질의·잡무)
    reading_channel: str          # 논문 리딩(전원 리딩 리포트·튜터 과외·연구 지향 누적, lab/reading.py)
    reading_dirs: tuple           # #논문리딩에서 경로로 받을 수 있는 맥 폴더(READING_DIRS, 쉼표 구분)
    reading_parallel: int         # 리딩 리포트 동시 작성 수(구독 한도 보호)
    adhoc_timeout_min: int        # 의뢰 1건의 명령 실행 상한(분). 넘는 일은 #실험요청으로
    adhoc_read_dirs: tuple        # 의뢰에서 읽기 전용으로 열람 가능한 맥 폴더(쉼표 구분 .env ADHOC_READ_DIRS)
    learn_threshold: int          # 같은 학습 후보가 이 횟수만큼 쌓이면 연구자 확인 요청
    model_director: str
    model_thinker: str
    model_runner: str
    sandbox_backend: str          # docker | host
    docker_image: str
    sandbox_cpus: str
    sandbox_memory: str
    max_concurrent: int
    token_budget: int             # 실험 1건당 입력+출력 토큰 상한
    run_timeout_min: int          # run_command 1회 상한
    approval_runtime_min: int     # 이 시간을 넘길 것으로 예상되면 승인 필요
    network_policy: str           # ask | allow | deny
    max_agent_turns: int
    routes: dict                  # 역할 → [(백엔드, 모델|None), ...] 우선순위
    claude_bin: str
    codex_bin: str
    gemini_bin: str
    hermes_bin: str
    hermes_profile: str
    hermes_provider: str
    cli_timeout_min: int          # CLI 1회 호출 상한
    keep_api_keys: bool           # False 면 CLI 호출 때 *_API_KEY 환경변수를 지워 구독 로그인만 쓰게 한다
    local_base_url: str
    local_model: str
    local_api_key: str
    light_approval: str = "button"        # 재집계·점검 명령 경량 승인: button(연구자 버튼) | auto(기록만 남기고 자동 승인)
    light_approval_timeout_min: int = 60  # 경량 승인 대기 상한(분). 넘으면 실행하지 않고 남은 일로 넘긴다
    sandbox_threads: int = 1              # 샌드박스 OMP/MKL/OPENBLAS 스레드 기본값(재현성·CPU 과점 방지)

    @classmethod
    def from_env(cls) -> "Config":
        e = os.environ.get
        home = Path(e("LAB_HOME") or ROOT / "workspace").expanduser().resolve()
        return cls(
            lab_home=home,
            anthropic_api_key=e("ANTHROPIC_API_KEY") or None,
            discord_token=e("DISCORD_TOKEN") or None,
            discord_owner_id=_discord_id("DISCORD_OWNER_ID"),
            discord_guild_id=_discord_id("DISCORD_GUILD_ID"),
            intake_channel=e("INTAKE_CHANNEL", "실험진행"),
            report_channel=e("REPORT_CHANNEL", "results-산출물"),
            perf_channel=e("PERF_CHANNEL", "성능고도화"),
            test_channel=e("TEST_CHANNEL", "봇점검"),
            adhoc_channel=e("ADHOC_CHANNEL", "의뢰"),
            reading_channel=e("READING_CHANNEL", "논문리딩"),
            reading_dirs=tuple(Path(x.strip()).expanduser().resolve()
                               for x in e("READING_DIRS", "~/Documents,~/Downloads,~/Desktop").split(",") if x.strip()),
            reading_parallel=_int("READING_PARALLEL", 3) or 3,
            adhoc_timeout_min=_int("ADHOC_TIMEOUT_MIN", 10) or 10,
            adhoc_read_dirs=tuple(Path(x.strip()).expanduser().resolve()
                                  for x in e("ADHOC_READ_DIRS", "").split(",") if x.strip()),
            learn_threshold=_int("LEARN_THRESHOLD", 3) or 3,
            model_director=e("MODEL_DIRECTOR", "claude-sonnet-5-5"),
            model_thinker=e("MODEL_THINKER", "claude-opus-5-5"),
            model_runner=e("MODEL_RUNNER", "claude-sonnet-5-5"),
            sandbox_backend=e("SANDBOX_BACKEND", "docker"),
            docker_image=e("DOCKER_IMAGE", "research-lab-sandbox:latest"),
            sandbox_cpus=e("SANDBOX_CPUS", "4"),
            sandbox_memory=e("SANDBOX_MEMORY", "10g"),
            max_concurrent=_int("MAX_CONCURRENT", 1) or 1,
            token_budget=_int("TOKEN_BUDGET_PER_EXPERIMENT", 3_000_000) or 3_000_000,
            run_timeout_min=_int("RUN_TIMEOUT_MIN", 120) or 120,
            approval_runtime_min=_int("APPROVAL_RUNTIME_MIN", 60) or 60,
            network_policy=e("NETWORK_POLICY", "ask"),
            max_agent_turns=_int("MAX_AGENT_TURNS", 60) or 60,
            routes=load_routes(),
            claude_bin=e("CLAUDE_BIN", "claude"),
            codex_bin=e("CODEX_BIN", "codex"),
            gemini_bin=e("GEMINI_BIN", "gemini"),
            hermes_bin=e("HERMES_BIN", str(Path.home() / ".local/bin/hermes")),
            hermes_profile=e("HERMES_PROFILE", "research-lab-coordinator"),
            hermes_provider=e("HERMES_PROVIDER", ""),
            cli_timeout_min=_int("CLI_TIMEOUT_MIN", 20) or 20,
            keep_api_keys=e("KEEP_API_KEYS", "0") == "1",
            local_base_url=e("LOCAL_BASE_URL", "http://localhost:11434/v1"),
            local_model=e("LOCAL_MODEL", ""),
            local_api_key=e("LOCAL_API_KEY", ""),
            light_approval=e("LIGHT_APPROVAL", "button"),
            light_approval_timeout_min=_int("LIGHT_APPROVAL_TIMEOUT_MIN", 60) or 60,
            sandbox_threads=_int("SANDBOX_THREADS", 1) or 1,
        )

    # --- 경로 ---
    @property
    def experiments_dir(self) -> Path:
        return self.lab_home / "experiments"

    @property
    def notebook_dir(self) -> Path:
        return self.lab_home / "notebook"

    @property
    def data_dir(self) -> Path:
        return self.lab_home / "data"

    @property
    def hf_cache_dir(self) -> Path:
        return self.lab_home / "hf_cache"

    @property
    def adhoc_dir(self) -> Path:
        return self.lab_home / "adhoc"

    @property
    def learning_dir(self) -> Path:
        return self.lab_home / "learning"

    @property
    def memory_dir(self) -> Path:
        return self.lab_home / "memory"

    @property
    def ledger_path(self) -> Path:
        return self.lab_home / "ledger.db"

    def ensure_dirs(self) -> None:
        for d in (self.experiments_dir, self.notebook_dir, self.data_dir, self.hf_cache_dir,
                  self.adhoc_dir, self.learning_dir, self.memory_dir):
            d.mkdir(parents=True, exist_ok=True)
