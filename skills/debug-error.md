---
name: debug-error
description: "Diagnostico e correcao de erros: stack trace, logs, root cause"
version: 1.0.0
author: lux-core
platforms: [linux, macos]
metadata:
  lux:
    tags: [debugging, troubleshooting, errors]
    category: development
    requires_toolsets: [terminal]
    use_count: 0
---

# Debug de Erros

## Quando Usar
Quando o usuario reporta um erro, stack trace, comportamento inesperado, ou falha em build/teste.

## Pre-requisitos
- Toolset `terminal` ativo

## Procedimento

### 1. Coletar informacao
- Stack trace completo
- Arquivo e linha do erro
- O que estava fazendo quando ocorreu
- Ambiente (SO, versoes, config)

### 2. Reproduzir
```bash
# execute o comando que falhou
# capture saida completa
```

### 3. Analisar root cause
- Leia o arquivo e linha do erro
- Trace a logica de tras pra frente
- Verifique se e: logica, tipo, performance, race condition

### 4. Corrigir
- Patch minimo (nao refatorar alem do necessario)
- Explicar a correcao
- Verificar se nao quebrou outros testes

### 5. Prevenir
- Sugerir teste que teria capturado o bug
- Sugerir melhoria de validacao/contrato

## Padroes comuns
| Erro | Causa provavel |
|------|---------------|
| `KeyError` / `undefined` | Chave/dict sem validacao |
| `TypeError: NoneType` | Retorno None nao tratado |
| `Connection refused` | Servico offline ou porta errada |
| `import error` | Dependencia faltando ou circular |
| Timeout | Operacao bloqueante no event loop |
