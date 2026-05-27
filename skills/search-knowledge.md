---
name: search-knowledge
description: "Busca inteligente: web + FTS5 historico + Qdrant semantico combinados"
version: 1.0.0
author: lux-core
platforms: [linux, macos]
metadata:
  lux:
    tags: [search, research, knowledge]
    category: productivity
    requires_toolsets: [web, memory_tools]
    use_count: 0
---

# Busca de Conhecimento

## Quando Usar
Quando o usuario pergunta algo que voce nao sabe, precisa de informacao atualizada, ou quer encontrar algo discutido em sessoes anteriores.

## Pre-requisitos
- Toolset `web` e `memory_tools` ativos

## Procedimento

### 1. Verificar memoria local primeiro
Use `session_search` para buscar em sessoes anteriores. Muitas vezes o usuario ja discutiu o topico antes.

### 2. Buscar na web
Use `web_search` com termos especificos. Prefira SearXNG local (mais privado).

### 3. Buscar documentacao tecnica
Use `web_fetch` para carregar paginas de documentacao relevantes.

### 4. Sintetizar resposta
Combine resultados de todas as fontes. Cite fonte (URL ou sessao) quando relevante.

### 5. Salvar conhecimento
Se a informacao for util no futuro, use `memory` para persistir.

## Exemplos
```
Usuario: "Qual a sintaxe do async/await em Rust?"
→ session_search("Rust async await")  # ja discutimos?
→ web_search("Rust async await syntax 2025")
→ Resposta combinando fontes
```
