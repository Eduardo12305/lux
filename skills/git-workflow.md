---
name: git-workflow
description: "Fluxo completo de Git: branch, commit, PR, merge"
version: 1.0.0
author: lux-core
platforms: [linux, macos]
metadata:
  lux:
    tags: [git, version-control, collaboration]
    category: development
    requires_toolsets: [git, terminal]
    use_count: 0
---

# Git Workflow

## Quando Usar
Operacoes Git: criar branches, commitar, push, revisar PRs, resolver conflitos.

## Pre-requisitos
- Git instalado e configurado
- Toolset `git` e `terminal` ativos

## Procedimento

### Iniciar nova feature
```bash
git checkout -b feat/nome-da-feature
```

### Commitar alteracoes
```bash
git status                    # ver o que mudou
git add {arquivos}            # stage
git commit -m "feat: resumo"  # commit com conventional commit
```

### Atualizar com main
```bash
git checkout main
git pull
git checkout feat/nome
git merge main                # ou rebase
```

### Push e PR
```bash
git push -u origin feat/nome
```

### Revisar PR de outro
```bash
git fetch origin pull/{PR_NUMBER}/head:pr-{PR_NUMBER}
git checkout pr-{PR_NUMBER}
# revisar arquivos
git diff main...pr-{PR_NUMBER}
```

## Conventional Commits
- `feat:` nova funcionalidade
- `fix:` correcao de bug
- `chore:` manutencao, deps
- `docs:` documentacao
- `test:` testes
- `refactor:` refatoracao sem mudanca de comportamento

## Pitfalls
- Push rejeitado (non-fast-forward): precisa dar pull primeiro
- Conflito de merge: resolver manualmente, `git add`, `git commit`
- Commit em branch errada: `git stash` + `git checkout branch_correta` + `git stash pop`
