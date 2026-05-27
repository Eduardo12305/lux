# lux/main.py
# Módulo: Entry Point
# Dependências: todos os modulos
# Status: IMPLEMENTADO
# Notas: Composition root + DI + Auth + StartupCoordinator (GAP 9) + ProcessLauncher (GAP 11)

from __future__ import annotations

import argparse
import asyncio
import getpass
import logging
import os
import sys
from typing import Optional

from lux.agent.agent import AIAgent
from lux.agent.state import Channel, UserProfile, UserRole
from lux.config import get_config
from lux.gateway.auth import AuthManager
from lux.interfaces.hermes_cli.auth import AuthCommands
from lux.memory.manager import MemoryManager
from lux.models.llama_client import LlamaClient
from lux.models.manager import ModelManager
from lux.models.vram_guard import VRAMGuard
from lux.prompt.assembler import PromptAssembler
from lux.prompt.soul import SoulLoader
from lux.skills.manager import SkillManager
from lux.tools.approval import ApprovalSystem
from lux.tools.implementations.calendar import CalendarCreateTool, CalendarReadTool, ReminderCancelTool, ReminderListTool, ReminderSetTool
from lux.tools.implementations.desktop import (
    ClipboardReadTool, ClipboardWriteTool, FindOnScreenTool,
    KeyboardPressTool, KeyboardTypeTool, MouseClickTool, MouseMoveTool,
    ScreenReadTool, ScreenshotTool, WindowFocusTool, WindowListTool,
)
from lux.tools.implementations.email import EmailListTool, EmailReadTool, EmailSendTool
from lux.tools.implementations.email_classifier import EmailQueryTool
from lux.tools.implementations.file_watcher import FileQueryTool
from lux.tools.implementations.filesystem import FileReadTool, FileWriteTool
from lux.tools.implementations.git import GitBranchTool, GitCommitTool, GitDiffTool, GitLogTool, GitPullTool, GitPushTool, GitStatusTool
from lux.tools.implementations.memory_tools import MemoryTool, SessionSearchTool
from lux.tools.implementations.orchestrator import (
    OrchestratorCancelTool, OrchestratorStatusTool, RunTaskTool,
)
from lux.tools.implementations.skills_tools import SkillCreateTool, SkillsListTool, SkillViewTool
from lux.tools.implementations.subagent import DelegateTaskTool, TodoTool
from lux.tools.implementations.system import StatusCheckTool
from lux.tools.implementations.tasks import TaskCompleteTool, TaskCreateTool, TaskListTool, TaskUpdateTool
from lux.tools.implementations.terminal import ShellRunTool
from lux.tools.implementations.web import WebFetchTool, WebSearchTool
from lux.tools.implementations.workflow_tools import (
    WorkflowCreateTool, WorkflowDeleteTool, WorkflowListTool,
    WorkflowToggleTool, WorkflowViewTool,
)
from lux.tools.registry import ToolRegistry
from lux.voice.pipeline import VoicePipeline, VoicePipelineState
from lux.voice.stt import STTEngine
from lux.voice.tts import TTSEngine
from lux.voice.vad import VADDetector
from lux.interfaces.voice_ui import VoiceUI
from lux.voice.interactive import VoiceMode

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _register_tools(registry: ToolRegistry):
    registry.register(ShellRunTool())
    registry.register(FileReadTool())
    registry.register(FileWriteTool())
    registry.register(MemoryTool())
    registry.register(SessionSearchTool())
    registry.register(StatusCheckTool())
    registry.register(SkillsListTool())
    registry.register(SkillViewTool())
    registry.register(SkillCreateTool())
    registry.register(TaskCreateTool())
    registry.register(TaskListTool())
    registry.register(TaskCompleteTool())
    registry.register(TaskUpdateTool())
    registry.register(WebSearchTool())
    registry.register(WebFetchTool())
    registry.register(GitStatusTool())
    registry.register(GitDiffTool())
    registry.register(GitLogTool())
    registry.register(GitCommitTool())
    registry.register(GitPushTool())
    registry.register(GitPullTool())
    registry.register(GitBranchTool())
    registry.register(CalendarReadTool())
    registry.register(CalendarCreateTool())
    registry.register(ReminderListTool())
    registry.register(ReminderSetTool())
    registry.register(ReminderCancelTool())
    registry.register(EmailListTool())
    registry.register(EmailReadTool())
    registry.register(EmailSendTool())
    registry.register(EmailQueryTool())
    registry.register(DelegateTaskTool())
    registry.register(TodoTool())
    registry.register(ScreenshotTool())
    registry.register(ScreenReadTool())
    registry.register(MouseClickTool())
    registry.register(MouseMoveTool())
    registry.register(KeyboardTypeTool())
    registry.register(KeyboardPressTool())
    registry.register(WindowListTool())
    registry.register(WindowFocusTool())
    registry.register(ClipboardReadTool())
    registry.register(ClipboardWriteTool())
    registry.register(FindOnScreenTool())
    registry.register(RunTaskTool())
    registry.register(OrchestratorStatusTool())
    registry.register(OrchestratorCancelTool())
    registry.register(FileQueryTool())
    registry.register(WorkflowListTool())
    registry.register(WorkflowViewTool())
    registry.register(WorkflowCreateTool())
    registry.register(WorkflowToggleTool())
    registry.register(WorkflowDeleteTool())


async def _run_cli(workdir: str | None = None):
    config = get_config()
    logger.info("Lux v1.0.0 iniciando...")

    work_context = None
    if workdir:
        workdir = os.path.realpath(workdir)
        work_context = f"Diretorio de trabalho atual do usuario: `{workdir}`\nUse este diretorio como contexto padrao para operacoes de arquivo e codigo."
        logger.info("Contexto de diretorio: %s", workdir)

    llama = LlamaClient()
    vram = VRAMGuard()
    model_mgr = ModelManager(llama_client=llama, vram_guard=vram)
    memory_mgr = MemoryManager()
    skill_mgr = SkillManager()
    tool_registry = ToolRegistry()
    _register_tools(tool_registry)
    approval = ApprovalSystem()
    auth_mgr = AuthManager(session_db=memory_mgr.session_db)
    auth_cmds = AuthCommands(auth_mgr)

    user_profile = await _cli_auth_flow(auth_mgr)

    voice = VoicePipeline(
        vad=VADDetector(),
        stt=STTEngine(),
        tts=TTSEngine(),
    )
    voice.mode = VoiceMode.PUSH
    voice_active = False

    soul_loader = SoulLoader()
    prompt_assembler = PromptAssembler(
        skill_list_provider=skill_mgr,
        tool_schema_provider=tool_registry,
        soul_loader=soul_loader,
    )

    agent = AIAgent(
        user_id=user_profile.user_id,
        user_profile=user_profile,
        channel=Channel.CLI,
        model_manager=model_mgr,
        memory_manager=memory_mgr,
        skill_manager=skill_mgr,
        tool_registry=tool_registry,
        approval_system=approval,
        prompt_assembler=prompt_assembler,
    )

    # Workflow Engine + File Watcher (background, não bloqueiam)
    from lux.workflows.runner import WorkflowRunner
    from lux.tools.implementations.file_watcher import DirectoryScanner, FileWatcher

    workflow_runner = WorkflowRunner()
    workflow_runner.set_agent(agent)
    workflow_runner.set_memory_manager(memory_mgr)
    await workflow_runner.start()

    file_watcher = FileWatcher(scanner=DirectoryScanner())
    file_watcher.set_memory_manager(memory_mgr)
    await file_watcher.start()

    try:
        from lux.interfaces.cli import LuxTUI
        from lux.interfaces.hermes_cli.main import run_tui
        await run_tui(agent, user_profile, work_context)
    except ImportError:
        await _run_simple_cli(agent, user_profile, llama, work_context)

    await agent.close()
    await voice.shutdown()
    await workflow_runner.stop()
    await file_watcher.stop()
    await auth_mgr.close()


async def _run_simple_cli(agent, user_profile, llama, work_context):
    """Fallback: CLI com input() simples."""
    print("╔══════════════════════════════════════════╗")
    print(f"║   Lux v1.0.0 — {user_profile.display_name:28s} ║")
    print("║   /help para comandos  |  /quit para sair║")
    print("╚══════════════════════════════════════════╝")
    print()

    while True:
        try:
            user_input = input("> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nAte logo!")
            break
        if not user_input:
            continue
        if user_input in ("/quit", "/exit", "/q"):
            print("Ate logo!")
            break
        print()
        response = await agent.run_conversation(
            user_message=user_input,
            system_message=work_context if work_context else None,
        )
        print(response.final_response)
        work_context = None
        print()

        if not user_input:
            continue
        if user_input in ("/quit", "/exit", "/q"):
            print("Ate logo!")
            break
        if user_input == "/desktop":
            print("Abrindo interface desktop...")
            try:
                from lux.interfaces.desktop_ui import LuxDesktopApp
                desktop = LuxDesktopApp(agent=agent, user_profile=user_profile, work_context=work_context)
                await desktop.run_async()
            except ImportError:
                print("Flet nao instalado. Execute: pip install flet")
            continue
        if user_input == "/help":
            print("Comandos: /quit, /help, /status, /memory, /skills, /doctor")
            print("Auth: /login, /register <user> [display], /users, /whitelist <platform>")
            print("Voz: /voice, /listen, /voice-stop, /voice-status, /voice-mode <off|wake|interactive|push>")
            print("Gateway: /gateway setup <telegram|discord>, /gateway status, /gateway disconnect <platform>")
            print("Desktop: /desktop — abrir interface grafica")
            if workdir:
                print(f"Contexto: {workdir}")
            continue
        if user_input == "/status":
            print(f"Lux v1.0.0 | Usuario: {user_profile.username} | Role: {user_profile.role.value}")
            continue
        if user_input == "/doctor":
            print("Health check:")
            main_ok = await llama.health_check("main")
            aux_ok = await llama.health_check("aux")
            print(f"  llama-server (14B): {'OK' if main_ok else 'FALHA'}")
            print(f"  llama-server (1.7B): {'OK' if aux_ok else 'FALHA'}")
            continue
        if user_input.startswith("/register "):
            parts = user_input.split(maxsplit=2)
            username = parts[1] if len(parts) > 1 else ""
            display = parts[2] if len(parts) > 2 else ""
            if username:
                password = getpass.getpass("Senha: ")
                confirm = getpass.getpass("Confirmar senha: ")
                if password == confirm:
                    result = await auth_cmds.register(username, password, display)
                else:
                    result = "Senhas nao conferem."
                print(result)
            continue
        if user_input.startswith("/login "):
            parts = user_input.split(maxsplit=1)
            if len(parts) >= 2:
                result = await auth_cmds.login(parts[1])
                print(result)
            continue
        if user_input == "/users":
            result = await auth_cmds.list_users()
            print(result)
            continue
        if user_input.startswith("/whitelist "):
            parts = user_input.split(maxsplit=1)
            platform = parts[1] if len(parts) > 1 else "cli"
            result = await auth_cmds.whitelist_show(platform)
            print(result)
            continue
        if user_input == "/voice":
            print("[Voz] Modos: /listen (push-to-talk), /voice-stop, /voice-status")
            print(f"[Voz] Status: {voice.state.name}, modo: {voice.mode.name}")
            continue
        if user_input == "/voice-status":
            print(f"[Voz] Estado: {voice.state.name}")
            print(f"[Voz] Modo: {voice.mode.name}")
            print(f"[Voz] STT carregado: {voice._stt.is_loaded}")
            print(f"[Voz] Falando: {voice.is_speaking}")
            continue
        if user_input == "/listen":
            voice_active = True
            voice.reset()
            print("[Voz] Push-to-talk ativo. Pressione Enter para falar.")
            print("[Voz] Fale algo... (silencio para parar)")

            transcript = await voice.listen_once()
            if transcript and transcript.strip() and transcript not in (
                "[STT indisponivel]", "[sem fala detectada]", "[erro na transcricao]"
            ):
                print(f"[Voz] ✓ Transcrito: \"{transcript}\"\n")
                user_input = transcript.strip()
            else:
                print(f"[Voz] Nada detectado.")
                voice_active = False
                continue
        if user_input == "/voice-full":
            voice_active = True
            voice_ui = VoiceUI()
            voice_ui.clear()
            voice.reset()
            await _voice_interactive_loop(agent, voice, voice_ui, work_context)
            voice_active = False
            voice_ui.clear()
            continue
        if user_input == "/voice-stop":
            voice.stop()
            print("[Voz] Parado. STT descarregado.")
            voice_active = False
            continue
        if user_input.startswith("/voice-mode"):
            parts = user_input.split(maxsplit=2)
            new_mode = parts[1] if len(parts) > 1 else "status"
            try:
                vm = VoiceMode(new_mode)
                voice.mode = vm
                voice_active = vm != VoiceMode.OFF
                print(f"[Voz] Modo alterado para: {vm.value}")
                if vm == VoiceMode.OFF:
                    voice.stop()
            except ValueError:
                print("[Voz] Modos: off, wake, interactive, push")
            continue
        if user_input.startswith("/gateway"):
            from lux.gateway.setup import (
                setup_telegram, setup_discord,
                gateway_status, gateway_disconnect,
            )
            parts = user_input.split(maxsplit=3)
            if len(parts) >= 3 and parts[1] == "setup":
                platform = parts[2]
                if platform == "telegram":
                    setup_telegram()
                elif platform == "discord":
                    setup_discord()
                else:
                    print(f"Plataforma desconhecida: {platform}")
            elif len(parts) >= 3 and parts[1] == "disconnect":
                print(gateway_disconnect(parts[2]))
            elif user_input == "/gateway" or (len(parts) >= 2 and parts[1] == "status"):
                print(gateway_status())
            else:
                print("Uso: /gateway [status|setup <telegram|discord>|disconnect <platform>]")
            continue

        print()
        response = await agent.run_conversation(
            user_message=user_input,
            system_message=work_context if work_context else None,
        )
        print(response.final_response)
        work_context = None
        print()

    await agent.close()
    await voice.shutdown()
    await auth_mgr.close()


async def _cli_auth_flow(auth_mgr: AuthManager) -> UserProfile:
    from lux.auth.first_run import FirstRunWizard
    from lux.auth.password import PasswordAuthenticator

    wizard = FirstRunWizard(auth_mgr._db)
    is_first = await wizard.is_first_run()

    if is_first:
        profile = await wizard.run_wizard()
        if profile:
            return profile

    print("╔══════════════════════════════════════════╗")
    print("║   Lux — Autenticacao Local             ║")
    print("╚══════════════════════════════════════════╝")
    print()
    print("[1] Entrar como admin local")
    print("[2] Login")
    print("[3] Registrar novo usuario")
    print()

    choice = input("Opcao [1]: ").strip() or "1"

    match choice:
        case "1":
            return await auth_mgr._authorize_cli("local")
        case "2":
            username = input("Username: ").strip()
            password = getpass.getpass("Senha: ")
            pw_auth = PasswordAuthenticator(auth_mgr._db)
            profile, status = await pw_auth.authenticate(username, password)
            if profile:
                return profile
            print("Credenciais invalidas. Usando admin local.")
            return await auth_mgr._authorize_cli("local")
        case "3":
            username = input("Username: ").strip()
            display = input("Display name: ").strip()
            password = getpass.getpass("Senha: ")
            confirm = getpass.getpass("Confirmar senha: ")
            if password != confirm:
                print("Senhas nao conferem. Usando admin local.")
                return await auth_mgr._authorize_cli("local")
            p = await auth_mgr.register_user(username, password, display)
            if p:
                return p
            print("Registro falhou. Usando admin local.")
            return await auth_mgr._authorize_cli("local")
        case _:
            return await auth_mgr._authorize_cli("local")


async def _run_gateway():
    from lux.gateway.platforms.telegram import TelegramAdapter
    from lux.gateway.platforms.discord import DiscordAdapter
    from lux.gateway.runner import GatewayRunner

    logger.info("Lux Gateway iniciando...")
    runner = GatewayRunner()

    telegram = TelegramAdapter(runner)
    discord = DiscordAdapter(runner)

    config = get_config()
    tasks = []

    if config.telegram_token:
        tasks.append(asyncio.create_task(telegram.start(), name="telegram"))
        logger.info("Plataforma Telegram ativada")
    else:
        logger.info("Telegram desabilitado (sem token)")

    if config.discord_token:
        tasks.append(asyncio.create_task(discord.start(), name="discord"))
        logger.info("Plataforma Discord ativada")
    else:
        logger.info("Discord desabilitado (sem token)")

    if not tasks:
        print("Gateway: Nenhuma plataforma configurada.")
        print("Defina LUX_TELEGRAM_TOKEN e/ou LUX_DISCORD_TOKEN no .env")
        return

    print("Gateway online. Plataformas ativas:")
    if config.telegram_token:
        print("  📱 Telegram")
    if config.discord_token:
        print("  🎮 Discord")

    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        pass
    finally:
        await telegram.stop()
        await discord.stop()
        await runner.stop()


def main():
    parser = argparse.ArgumentParser(description="Lux — Assistente Pessoal Local")
    parser.add_argument("--gateway", action="store_true", help="Iniciar em modo gateway")
    parser.add_argument("--doctor", action="store_true", help="Executar diagnostico")
    parser.add_argument("--version", action="store_true", help="Mostrar versao")
    parser.add_argument("--workdir", type=str, default=os.getcwd(), help="Diretorio de trabalho (contexto para codigo, default: diretorio atual)")
    parser.add_argument("--desktop", action="store_true", help="Iniciar interface desktop (Flet)")
    parser.add_argument("--voice", action="store_true", help="Iniciar direto no modo voz interativo (MiniCPM-o)")
    args = parser.parse_args()

    if args.version:
        print("Lux v1.0.0")
        return

    if args.doctor:
        asyncio.run(_run_doctor())
        return

    voice_active = args.voice or os.environ.get("LUX_ENABLE_OMNI", "").lower() == "true"

    if args.gateway:
        asyncio.run(_run_gateway())
    elif args.desktop:
        asyncio.run(_run_desktop(workdir=args.workdir))
    elif voice_active:
        asyncio.run(_run_voice(workdir=args.workdir))
    else:
        asyncio.run(_run_cli(workdir=args.workdir))


async def _run_voice(workdir: str | None = None):
    """Modo voz contínuo com MiniCPM-o 4.5 e roteamento para Qwen3-14B + tools."""
    config = get_config()
    logger.info("Lux Voice Mode iniciando...")

    # --- Infraestrutura compartilhada (agent + tools) ---
    llama = LlamaClient()
    memory_mgr = MemoryManager()
    skill_mgr = SkillManager()
    tool_registry = ToolRegistry()
    _register_tools(tool_registry)
    approval = ApprovalSystem()
    auth_mgr = AuthManager(session_db=memory_mgr.session_db)
    user_profile = await auth_mgr._authorize_cli("local")

    model_mgr = ModelManager(llama_client=llama)

    soul_loader = SoulLoader()
    prompt_assembler = PromptAssembler(
        skill_list_provider=skill_mgr,
        tool_schema_provider=tool_registry,
        soul_loader=soul_loader,
    )

    agent = AIAgent(
        user_id=user_profile.user_id,
        user_profile=user_profile,
        channel=Channel.CLI,
        model_manager=model_mgr,
        memory_manager=memory_mgr,
        skill_manager=skill_mgr,
        tool_registry=tool_registry,
        approval_system=approval,
        prompt_assembler=prompt_assembler,
    )
    # --- Fim infraestrutura ---

    from lux.voice.interactive import InteractiveListener, VoiceMode
    from lux.voice.omni_engine import OmniEngine
    from lux.voice.wake_word import WakeWordDetector
    from lux.voice.vad import VADDetector

    vram_layers = getattr(config, "omni_vram_layers", -1)
    gfx = getattr(config, "omni_gfx_override", "12.0.1")

    omni = OmniEngine(gfx_override=gfx, vram_layers=vram_layers)
    wake = WakeWordDetector.get_instance()
    wake.load()

    wake_word = wake.activation_word
    print("╔══════════════════════════════════════════╗")
    print("║   Lux Voice Mode — MiniCPM-o 4.5        ║")
    print(f"║   {user_profile.display_name or user_profile.username:36s} ║")
    if wake.is_available:
        print(f"║   Fale '{wake_word}' para ativar..." + " " * (16 - len(wake_word)) + "  ║")
    else:
        print("║   Fale para ativar..." + " " * 19 + "  ║")
    print("║   Ctrl+C para sair                       ║")
    print("╚══════════════════════════════════════════╝")
    print()

    listener = InteractiveListener(vad=VADDetector(), wake=wake)
    listener.mode = VoiceMode.WAKE if wake.is_available else VoiceMode.INTERACTIVE
    listener._active = True

    try:
        await listener.run_omni_continuous(omni, agent=agent)
    except KeyboardInterrupt:
        print("\nEncerrando...")
    finally:
        await omni.stop()
        await agent.close()
        await auth_mgr.close()


async def _run_doctor():
    print("Lux Doctor — Diagnostico do Sistema")
    print("=" * 40)
    config = get_config()
    print(f"Lux Home: {config.lux_home}")
    print(f"VRAM Budget: {config.vram_budget_gb}GB")
    print(f"GPU Backend: {config.gpu_backend}")

    llama = LlamaClient()
    main_ok = await llama.health_check("main")
    aux_ok = await llama.health_check("aux")
    print(f"llama-server (14B): {'OK' if main_ok else 'FALHA — verifique se o servidor esta rodando'}")
    print(f"llama-server (1.7B): {'OK' if aux_ok else 'FALHA — verifique se o servidor esta rodando'}")
    await llama.close()


async def _run_desktop(workdir: str | None = None):
    config = get_config()
    logger.info("Lux Desktop iniciando...")

    work_context = None
    if workdir:
        workdir = os.path.realpath(workdir)
        work_context = f"Diretorio: {workdir}"

    llama = LlamaClient()
    vram = VRAMGuard()
    model_mgr = ModelManager(llama_client=llama, vram_guard=vram)
    memory_mgr = MemoryManager()
    skill_mgr = SkillManager()
    tool_registry = ToolRegistry()
    _register_tools(tool_registry)
    approval = ApprovalSystem()
    auth_mgr = AuthManager(session_db=memory_mgr.session_db)
    user_profile = await auth_mgr._authorize_cli("local")

    soul_loader = SoulLoader()
    prompt_assembler = PromptAssembler(
        skill_list_provider=skill_mgr,
        tool_schema_provider=tool_registry,
        soul_loader=soul_loader,
    )

    agent = AIAgent(
        user_id=user_profile.user_id,
        user_profile=user_profile,
        channel=Channel.CLI,
        model_manager=model_mgr,
        memory_manager=memory_mgr,
        skill_manager=skill_mgr,
        tool_registry=tool_registry,
        approval_system=approval,
        prompt_assembler=prompt_assembler,
    )

    from lux.interfaces.desktop_ui import LuxDesktopApp
    app = LuxDesktopApp(agent=agent, user_profile=user_profile, work_context=work_context)
    await app.run_async()
    await agent.close()
    await auth_mgr.close()


def gateway_main():
    asyncio.run(_run_gateway())


async def _voice_interactive_loop(agent, voice, voice_ui, work_context):
    """Loop interativo de voz: push-to-talk → transcreve → LLM → TTS."""
    voice_ui.set_state(VoicePipelineState.IDLE)

    ui_task = asyncio.create_task(
        voice_ui.rich_render_loop(voice, asyncio.Event())
    )

    try:
        while True:
            voice_ui.set_state(VoicePipelineState.IDLE)
            input("Pressione Enter para falar (ou 'q' + Enter para sair): ")

            voice_ui.set_state(VoicePipelineState.LISTENING)
            transcript = await voice.listen_once()

            if not transcript or transcript in (
                "[STT indisponivel]", "[sem fala detectada]", "[erro na transcricao]"
            ):
                continue

            voice_ui.on_transcript(transcript)
            voice_ui.set_state(VoicePipelineState.PROCESSING)

            response = await agent.run_conversation(
                user_message=transcript.strip(),
                system_message=work_context if work_context else None,
            )
            work_context = None

            voice_ui.on_tts(response.final_response[:120])
            voice_ui.set_state(VoicePipelineState.SPEAKING)
            print(f"\n🤖 {response.final_response}\n")
            voice_ui.set_state(VoicePipelineState.IDLE)

    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        voice.stop()
        ui_task.cancel()
        try:
            await ui_task
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    main()
