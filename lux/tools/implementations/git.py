# lux/tools/implementations/git.py
import subprocess
from pathlib import Path
from lux.agent.state import AgentState, ToolResult
from lux.tools.base import Tool


def _run_git(args: list[str], cwd: str | None = None) -> tuple[int, str, str]:
    try:
        r = subprocess.run(
            ["git"] + args, capture_output=True, text=True, cwd=cwd, timeout=30,
        )
        return r.returncode, r.stdout, r.stderr
    except FileNotFoundError:
        return -1, "", "git nao encontrado no PATH"
    except subprocess.TimeoutExpired:
        return -1, "", "timeout (30s)"


def _git_dir(state: AgentState) -> str:
    return str(Path.cwd())


class GitStatusTool(Tool):
    name = "git_status"
    description = "Mostra o status do repositorio git"
    parameters_schema = {"type": "object", "properties": {}}

    def execute(self, args: dict, state: AgentState) -> ToolResult:
        code, out, err = _run_git(["status", "--porcelain"], _git_dir(state))
        if code != 0:
            return ToolResult.failure(err or "Erro ao executar git status")
        return ToolResult.ok(out.strip() or "Working tree limpo.")


class GitDiffTool(Tool):
    name = "git_diff"
    description = "Mostra diff do working tree ou staged"
    parameters_schema = {
        "type": "object",
        "properties": {
            "staged": {"type": "boolean", "description": "Mostrar diff staged", "default": False},
        },
    }

    def execute(self, args: dict, state: AgentState) -> ToolResult:
        cmd = ["diff", "--staged"] if args.get("staged") else ["diff"]
        code, out, err = _run_git(cmd, _git_dir(state))
        if code != 0:
            return ToolResult.failure(err or "Erro ao executar git diff")
        return ToolResult.ok(out.strip()[:5000] or "Sem alteracoes.")


class GitLogTool(Tool):
    name = "git_log"
    description = "Mostra historico de commits"
    parameters_schema = {
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "description": "Numero de commits", "default": 20},
        },
    }

    def execute(self, args: dict, state: AgentState) -> ToolResult:
        n = args.get("limit", 20)
        code, out, err = _run_git(["log", "--oneline", f"-n{n}"], _git_dir(state))
        if code != 0:
            return ToolResult.failure(err or "Erro ao executar git log")
        return ToolResult.ok(out.strip() or "Sem commits.")


class GitBranchTool(Tool):
    name = "git_branch"
    description = "Lista branches do repositorio"
    parameters_schema = {"type": "object", "properties": {}}

    def execute(self, args: dict, state: AgentState) -> ToolResult:
        code, out, err = _run_git(["branch", "-a"], _git_dir(state))
        if code != 0:
            return ToolResult.failure(err or "Erro ao executar git branch")
        return ToolResult.ok(out.strip() or "Nenhuma branch.")


class GitCommitTool(Tool):
    name = "git_commit"
    description = "Cria um commit com as alteracoes"
    parameters_schema = {
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "Mensagem do commit"},
            "files": {"type": "array", "items": {"type": "string"}, "description": "Arquivos a commitar (vazio = todos)"},
        },
        "required": ["message"],
    }

    def execute(self, args: dict, state: AgentState) -> ToolResult:
        msg = args.get("message", "")
        files = args.get("files", [])
        cwd = _git_dir(state)

        if files:
            code, _, err = _run_git(["add"] + files, cwd)
            if code != 0:
                return ToolResult.failure(err or "Erro ao adicionar arquivos")
        else:
            _run_git(["add", "-A"], cwd)

        code, out, err = _run_git(["commit", "-m", msg], cwd)
        if code != 0:
            return ToolResult.failure(err or out or "Erro ao commitar")
        return ToolResult.ok(out.strip() or "Commit criado.")


class GitPushTool(Tool):
    name = "git_push"
    description = "Push para remote"
    parameters_schema = {
        "type": "object",
        "properties": {
            "remote": {"type": "string", "description": "Remote", "default": "origin"},
            "branch": {"type": "string", "description": "Branch"},
        },
    }

    def execute(self, args: dict, state: AgentState) -> ToolResult:
        remote = args.get("remote", "origin")
        branch = args.get("branch", "")
        cmd = ["push", remote]
        if branch:
            cmd.append(branch)
        code, out, err = _run_git(cmd, _git_dir(state))
        if code != 0:
            return ToolResult.failure(err or out or "Push falhou.")
        return ToolResult.ok(out.strip() or "Push concluido.")


class GitPullTool(Tool):
    name = "git_pull"
    description = "Pull do remote"
    parameters_schema = {
        "type": "object",
        "properties": {
            "remote": {"type": "string", "description": "Remote", "default": "origin"},
            "branch": {"type": "string", "description": "Branch"},
        },
    }

    def execute(self, args: dict, state: AgentState) -> ToolResult:
        remote = args.get("remote", "origin")
        branch = args.get("branch", "")
        cmd = ["pull", remote]
        if branch:
            cmd.append(branch)
        code, out, err = _run_git(cmd, _git_dir(state))
        if code != 0:
            return ToolResult.failure(err or out or "Pull falhou.")
        return ToolResult.ok(out.strip() or "Pull concluido.")
