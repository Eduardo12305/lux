---
name: plan
description: "Planejamento de tarefas multi-step com milestones e delegacao"
version: 1.0.0
author: lux-core
platforms: [linux, macos]
metadata:
  lux:
    tags: [planning, project, organization]
    category: productivity
    requires_toolsets: [tasks]
    use_count: 0
---

# Planejamento de Tarefas

## Quando Usar
Quando o usuario pede para planejar algo complexo com multiplas etapas, ou quando uma tarefa exige divisao em subtarefas com dependencias.

## Pre-requisitos
- Toolset `tasks` ativo

## Procedimento

### 1. Analise o pedido
Identifique o objetivo final, restricoes de tempo, recursos necessarios e dependencias.

### 2. Quebre em milestones
Divida em 3-5 milestones claros, cada um com criterio de conclusao verificavel.

### 3. Crie tarefas no TODO.md
Use `task_create` para cada acao concreta. Agrupe por milestone no titulo.

### 4. Apresente o plano
Liste milestones, tarefas por milestone, e proximo passo imediato.

### 5. Execute e atualize
Conforme avanca, use `task_complete` para marcar concluidas. Se surgirem bloqueios, replaneje.

## Pitfalls
- Planejar demais sem executar: depois de 5 tasks criadas, COMECE a executar
- Tasks muito vagas: use verbos de acao (implementar, configurar, testar)
- Dependencias nao mapeadas: pergunte "o que precisa estar pronto antes disso?"

## Verificacao
- `task_list` mostra todas as tasks com milestones claros
- Proximo passo imediato esta definido
