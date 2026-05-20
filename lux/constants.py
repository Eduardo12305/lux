# lux/constants.py
# Módulo: Core
# Dependências: nenhuma
# Status: IMPLEMENTADO

from __future__ import annotations

from pathlib import Path

LUX_HOME: Path = Path("~/.lux/").expanduser()
LUX_HOME.mkdir(parents=True, exist_ok=True)

MEMORIES_DIR: Path = LUX_HOME / "memories"
MEMORIES_DIR.mkdir(parents=True, exist_ok=True)

SESSIONS_DB_PATH: Path = LUX_HOME / "sessions.db"

SKILLS_DIR: Path = LUX_HOME / "skills"
SKILLS_DIR.mkdir(parents=True, exist_ok=True)

SKILLS_BACKUPS_DIR: Path = SKILLS_DIR / ".backups"
SKILLS_BACKUPS_DIR.mkdir(parents=True, exist_ok=True)

CHECKPOINTS_DIR: Path = LUX_HOME / "checkpoints"
CHECKPOINTS_DIR.mkdir(parents=True, exist_ok=True)

PLUGINS_DIR: Path = LUX_HOME / "plugins"
PLUGINS_DIR.mkdir(parents=True, exist_ok=True)

CRON_DIR: Path = LUX_HOME / "cron"
CRON_DIR.mkdir(parents=True, exist_ok=True)

CRON_JOBS_FILE: Path = CRON_DIR / "jobs.json"
CRON_JOBS_FILE.parent.mkdir(parents=True, exist_ok=True)

SOUL_PATH: Path = LUX_HOME / "SOUL.md"

GLOBAL_CONTEXT_PATH: Path = LUX_HOME / "global-context.md"

TRAJECTORIES_DIR: Path = LUX_HOME / "trajectories"
TRAJECTORIES_DIR.mkdir(parents=True, exist_ok=True)

AUDIT_LOG_PATH: Path = LUX_HOME / "audit.log"

MEMORY_MD_LIMIT_CHARS: int = 2200
USER_MD_LIMIT_CHARS: int = 1375
MEMORY_ENTRY_SEPARATOR: str = "\u00a7"
MEMORY_ENTRY_SEPARATOR_VISIBLE: str = "\u00a7"

DEFAULT_MAX_ITERATIONS: int = 50
DEFAULT_CTX_SIZE: int = 8192
DEFAULT_PARALLEL_SLOTS_MAIN: int = 2
DEFAULT_PARALLEL_SLOTS_AUX: int = 4
DEFAULT_COMPRESSION_THRESHOLD_CLI: float = 0.50
DEFAULT_COMPRESSION_THRESHOLD_GATEWAY: float = 0.85
DEFAULT_PROTECT_LAST_N: int = 20

DEFAULT_VRAM_BUDGET_GB: float = 14.5
DEFAULT_GPU_BACKEND: str = "rocm"

LLAMA_MAIN_PORT: int = 8080
LLAMA_AUX_PORT: int = 8081

QDRANT_DEFAULT_PORT: int = 6333
REDIS_DEFAULT_PORT: int = 6379

WHISPER_INACTIVITY_TIMEOUT: float = 60.0
WHISPER_VRAM_GB: float = 0.5

SKILL_CREATION_THRESHOLD: int = 5
SKILL_MAX_BACKUPS: int = 5
SKILL_SIMILARITY_THRESHOLD: float = 0.8

NUDGE_AT_CONTEXT_PCT: float = 0.60
NUDGE_AT_TURNS: int = 30
