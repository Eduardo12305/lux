---
name: code-review
description: "Revisao de codigo: analisa PR, sugere melhorias, verifica convencoes"
version: 1.0.0
author: lux-core
platforms: [linux, macos]
metadata:
  lux:
    tags: [code-review, quality, collaboration]
    category: development
    requires_toolsets: [terminal, git]
    use_count: 0
---

# Code Review

## Quando Usar
Quando o usuario pede para revisar um PR, analisar codigo, verificar qualidade, ou sugerir melhorias.

## Pre-requisitos
- Toolset `git` e `terminal` ativos

## Procedimento

### 1. Obter o codigo
```bash
git fetch origin pull/{PR_NUMBER}/head:pr-review
git checkout pr-review
git diff main...pr-review --stat
```

### 2. Checklist de revisao
- [ ] O codigo compila?
- [ ] Testes passam?
- [ ] Cobre os casos de borda?
- [ ] Nomes de variaveis/funcoes sao claros?
- [ ] Segue as convencoes do projeto (ver AGENTS.md)?
- [ ] Tem tratamento de erros adequado?
- [ ] Nao introduz duplicacao?
- [ ] Mudancas estao no escopo certo?

### 3. Rodar verificacoes
```bash
# build e testes (linguagem detectada do contexto)
cargo build && cargo test        # Rust
npm run build && npm test        # Node
python -m pytest                 # Python
```

### 4. Apresentar revisao
Formato:
```
## Revisao do PR #{N}
**Resumo:** [1-2 linhas]
**Arquivos:** [lista dos modificados]
### Pontos fortes
- ...
### Sugestoes
- ...
### Bloqueios (se houver)
- ...
```

## Pitfalls
- Revisar sem contexto: leia AGENTS.md/.lux.md do repositorio primeiro
- Sugestoes vagas: seja especifico (linha, arquivo, sugestao concreta)
- Nao verificar se builda: SEMPRE execute build/testes antes de aprovar
