---
name: system-health
description: "Diagnostico do sistema: VRAM, processos, logs,性能"
version: 1.0.0
author: lux-core
platforms: [linux]
metadata:
  lux:
    tags: [system, monitoring, diagnostics]
    category: system
    requires_toolsets: [system, terminal]
    use_count: 0
---

# System Health

## Quando Usar
Quando o usuario pede status do sistema, diagnostico de性能, ou algo parece lento/travado.

## Pre-requisitos
- Toolset `system` e `terminal` ativos

## Procedimento

### 1. VRAM e GPU
```bash
rocm-smi --showmeminfo vram 2>/dev/null || nvidia-smi
```

### 2. Processos pesados
```bash
ps aux --sort=-%mem | head -10
```

### 3. Disco
```bash
df -h /
```

### 4. Servicos Lux
Verificar se llama-server (14B e 1.7B), Qdrant e Redis estao rodando.

### 5. Logs recentes
```bash
tail -50 ~/.lux/logs/llama_main.log
```

### 6. Sugestoes
- VRAM > 90%: sugerir fechar apps ou reduzir contexto
- Disco < 5GB: sugerir limpeza
- Processos zumbis: sugerir kill
