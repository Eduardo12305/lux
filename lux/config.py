# lux/config.py
# Módulo: Core
# Dependências: constants.py
# Status: IMPLEMENTADO
# Notas: pydantic-settings para todas as variáveis de ambiente do Lux

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from lux.constants import (
    DEFAULT_COMPRESSION_THRESHOLD_CLI,
    DEFAULT_COMPRESSION_THRESHOLD_GATEWAY,
    DEFAULT_CTX_SIZE,
    DEFAULT_GPU_BACKEND,
    DEFAULT_MAX_ITERATIONS,
    DEFAULT_PARALLEL_SLOTS_AUX,
    DEFAULT_PARALLEL_SLOTS_MAIN,
    DEFAULT_PROTECT_LAST_N,
    DEFAULT_VRAM_BUDGET_GB,
    LUX_HOME,
    MEMORIES_DIR,
    MEMORY_MD_LIMIT_CHARS,
    SKILL_CREATION_THRESHOLD,
    SKILLS_DIR,
    USER_MD_LIMIT_CHARS,
)


class LuxConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="LUX_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )

    # ── Hardware ──────────────────────────────────────────────
    vram_budget_gb: float = Field(
        default=DEFAULT_VRAM_BUDGET_GB,
        description="Orçamento máximo de VRAM em GB",
    )
    gpu_backend: str = Field(
        default=DEFAULT_GPU_BACKEND,
        description="Backend GPU: rocm | cuda | cpu",
    )

    # ── Modelos ───────────────────────────────────────────────
    main_model_path: Path = Field(
        default=Path("/models/Qwen3-14B-Instruct-Q4_K_M.gguf"),
        description="Caminho para o modelo principal Qwen3-14B",
    )
    aux_model_path: Path = Field(
        default=Path("/models/Qwen3-1.7B-Instruct-Q4_K_M.gguf"),
        description="Caminho para o modelo auxiliar Qwen3-1.7B",
    )
    whisper_model: str = Field(
        default="small",
        description="Tamanho do modelo Whisper: tiny | base | small | medium",
    )
    piper_voice: str = Field(
        default="pt_BR-faber-medium",
        description="Voz padrão do Piper TTS",
    )
    llama_main_url: str = Field(
        default="http://127.0.0.1:8080",
        description="URL do llama-server para o modelo principal",
    )
    llama_aux_url: str = Field(
        default="http://127.0.0.1:8081",
        description="URL do llama-server para o modelo auxiliar",
    )

    # ── Omni (MiniCPM-o 4.5 unificado) ────────────────────────
    omni_model_path: str = Field(
        default="~/.lux/models/minicpm-o-4_5-gguf/MiniCPM-o-4_5-Q4_K_M.gguf",
        description="Caminho para MiniCPM-o 4.5 GGUF",
    )
    omni_binary_path: str = Field(
        default="llama-omni-cli",
        description="Caminho para binário llama-omni-cli",
    )
    omni_ref_audio_path: str = Field(
        default="",
        description="Áudio de referência para voice cloning (opcional)",
    )
    omni_gfx_override: str = Field(
        default="12.0.1",
        description="HSA_OVERRIDE_GFX_VERSION para gfx1201",
    )
    omni_vram_layers: int = Field(
        default=-1,
        description="-1 = offload todas camadas para GPU",
    )

    # ── Serviços ──────────────────────────────────────────────
    qdrant_url: str = Field(
        default="http://localhost:6333",
        description="URL do Qdrant",
    )
    redis_url: str = Field(
        default="redis://localhost:6379",
        description="URL do Redis (opcional, para gateway)",
    )

    # ── Sessão e Contexto ─────────────────────────────────────
    ctx_size: int = Field(
        default=DEFAULT_CTX_SIZE,
        description="Tamanho do contexto em tokens",
    )
    parallel_slots_main: int = Field(
        default=DEFAULT_PARALLEL_SLOTS_MAIN,
        description="Slots paralelos do llama-server principal",
    )
    parallel_slots_aux: int = Field(
        default=DEFAULT_PARALLEL_SLOTS_AUX,
        description="Slots paralelos do llama-server auxiliar",
    )
    max_iterations: int = Field(
        default=DEFAULT_MAX_ITERATIONS,
        description="Número máximo de iterações do agent loop",
    )
    compression_threshold: float = Field(
        default=DEFAULT_COMPRESSION_THRESHOLD_CLI,
        description="Threshold de compressão: 0.50 (CLI) ou 0.85 (gateway)",
    )
    protect_last_n: int = Field(
        default=DEFAULT_PROTECT_LAST_N,
        description="Número de mensagens preservadas na compressão",
    )

    # ── Memória ───────────────────────────────────────────────
    memory_md_limit: int = Field(
        default=MEMORY_MD_LIMIT_CHARS,
        description="Limite de caracteres do MEMORY.md",
    )
    user_md_limit: int = Field(
        default=USER_MD_LIMIT_CHARS,
        description="Limite de caracteres do USER.md",
    )
    memories_dir: Path = Field(
        default=MEMORIES_DIR,
        description="Diretório de arquivos de memória",
    )

    # ── Skills ────────────────────────────────────────────────
    skills_dir: Path = Field(
        default=SKILLS_DIR,
        description="Diretório de skills do usuário",
    )
    auto_create_skills: bool = Field(
        default=True,
        description="Permite criação autônoma de skills",
    )
    skill_creation_threshold: int = Field(
        default=SKILL_CREATION_THRESHOLD,
        description="Mínimo de tool calls para sugerir criação de skill",
    )

    # ── Voz ───────────────────────────────────────────────────
    voice_default: bool = Field(
        default=False,
        description="Voz habilitada por padrão",
    )
    listening_mode: str = Field(
        default="push_to_talk",
        description="Modo de escuta: off | wake_word | push_to_talk | always_on",
    )
    # ── Wake Word ──────────────────────────────────────────────
    wake_word: str = Field(
        default="arkana",
        description="Palavra de ativação (wake word). 'arkana' é sempre mantida como reserva.",
    )
    wakeword_model_dir: str = Field(
        default="~/.lux/models/wakeword",
        description="Diretório com modelos .onnx da wake word",
    )
    wakeword_threshold: float = Field(
        default=0.5,
        description="Threshold de deteccao (0.0-1.0). Mais alto = menos falsos positivos",
    )
    wakeword_cooldown_s: float = Field(
        default=2.0,
        description="Segundos minimos entre deteccoes consecutivas",
    )
    wakeword_min_rms: float = Field(
        default=0.002,
        description="RMS minimo de energia para processar a wake word",
    )
    stt_language: str = Field(
        default="pt",
        description="Idioma para STT (Whisper)",
    )

    # ── Proatividade ──────────────────────────────────────────
    proactivity_enabled: bool = Field(
        default=True,
        description="Habilita triggers proativos",
    )
    proactivity_poll_interval: int = Field(
        default=30,
        description="Intervalo de polling dos triggers em segundos",
    )

    # ── Segurança ─────────────────────────────────────────────
    jwt_secret: str = Field(
        default="",
        description="Segredo JWT para API server",
    )
    session_expire_hours: int = Field(
        default=24,
        description="Horas até expiração de sessão",
    )
    enable_dangerous_tools: bool = Field(
        default=False,
        description="Habilita ferramentas perigosas (apenas admin)",
    )

    # ── Processos Gerenciados ─────────────────────────────────
    managed_processes: bool = Field(
        default=True,
        description="Lux gerencia o ciclo de vida do llama-server (GAP 11)",
    )
    llama_server_bin: str = Field(
        default="llama-server",
        description="Caminho para o binário llama-server",
    )

    # ── Interfaces ────────────────────────────────────────────
    gradio_enabled: bool = Field(
        default=False,
        description="Habilita WebUI Gradio",
    )
    gradio_port: int = Field(
        default=7860,
        description="Porta da WebUI Gradio",
    )
    acp_enabled: bool = Field(
        default=False,
        description="Habilita servidor ACP para IDEs",
    )
    acp_port: int = Field(
        default=3284,
        description="Porta do servidor ACP",
    )

    # ── Gateway (opcional) ────────────────────────────────────
    telegram_token: str = Field(default="", description="Token do bot Telegram")
    discord_token: str = Field(default="", description="Token do bot Discord")
    discord_channel_ids: str = Field(default="", description="IDs de canais Discord")
    slack_bot_token: str = Field(default="", description="Token do bot Slack")
    slack_app_token: str = Field(default="", description="Token de app Slack")
    email_imap_host: str = Field(default="", description="Host IMAP para e-mail")
    email_smtp_host: str = Field(default="", description="Host SMTP para e-mail")
    email_address: str = Field(default="", description="Endereço de e-mail")
    email_password: str = Field(default="", description="Senha do e-mail")
    searxng_url: str = Field(
        default="http://localhost:8888",
        description="URL do SearXNG local",
    )

    # ── Diretórios Monitorados (Módulo 1 - File Watcher) ───────
    watch_dirs: str = Field(
        default="",
        description="Diretórios monitorados (separados por vírgula)",
    )
    reindex_interval: int = Field(
        default=30,
        description="Intervalo de reindexação automática em minutos",
    )
    accepted_extensions: str = Field(
        default=".md,.txt,.py,.json,.yaml,.yml,.toml,.cfg,.ini,.env,.sh,.js,.ts,.html,.css,.rs,.go,.java,.c,.cpp,.h",
        description="Extensões de arquivo aceitas para indexação",
    )
    dir_max_depth: int = Field(
        default=3,
        description="Profundidade máxima de leitura de subpastas",
    )
    file_watcher_enabled: bool = Field(
        default=True,
        description="Habilita monitoramento de diretórios em tempo real",
    )

    # ── E-mail Inteligente (Módulo 2 - Email Classifier) ──────
    email_provider: str = Field(
        default="imap",
        description="Provider de e-mail: gmail | outlook | imap",
    )
    email_fetch_limit: int = Field(
        default=50,
        description="Quantidade de e-mails recentes para carregar",
    )
    email_interests: str = Field(
        default="",
        description="Categorias de interesse: nome1:kw1,kw2; nome2:kw3,kw4",
    )
    email_classifier_enabled: bool = Field(
        default=False,
        description="Habilita classificador de e-mails",
    )

    # ── Workflow Engine (Módulo 3) ────────────────────────────
    workflows_enabled: bool = Field(
        default=True,
        description="Habilita motor de workflows automáticos",
    )
    workflow_dir: Path = Field(
        default=LUX_HOME / "workflows",
        description="Diretório com arquivos .yaml de workflow",
    )

    # ── Lux Home ──────────────────────────────────────────────
    lux_home: Path = Field(
        default=LUX_HOME,
        description="Diretório raiz do Lux (~/.lux/)",
    )


_config_instance: Optional[LuxConfig] = None


def get_config() -> LuxConfig:
    global _config_instance
    if _config_instance is None:
        _config_instance = LuxConfig()
    return _config_instance


def reload_config() -> LuxConfig:
    global _config_instance
    _config_instance = LuxConfig()
    return _config_instance
