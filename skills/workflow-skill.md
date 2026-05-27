---
name: workflow-skill
description: "Criação, atualização e gerenciamento de workflows autônomos. Use esta skill SEMPRE antes de criar, modificar ou remover qualquer workflow."
version: 1.0.0
author: lux-core
platforms: [linux]
metadata:
  lux:
    tags: [workflow, automation, cron, scheduling]
    category: productivity
    requires_toolsets: [terminal]
    use_count: 0
---

# Workflow Skill

> Skill de criação, atualização e gerenciamento de workflows autônomos do agente LUX.

---

## 1. QUANDO USAR ESTA SKILL

O agente **sempre** consulta esta skill antes de qualquer ação relacionada a workflows. Ative-a quando detectar qualquer um dos seguintes sinais na mensagem do usuário:

### Gatilhos de criação
| Padrão detectado | Exemplo real |
|---|---|
| Recorrência temporal | "todo dia", "toda segunda", "nos dias úteis", "às 8h", "toda semana" |
| Automação de tarefa | "quero que você faça X automaticamente", "toda vez que Y acontecer" |
| Monitoramento contínuo | "me avise quando", "fique de olho em", "monitore" |
| Ação disparada por evento | "quando eu disser X, faça Y", "ao abrir o projeto, toque" |
| Rotina declarada | "minha rotina é", "crie uma automação que" |

### Gatilhos de atualização
| Padrão detectado | Exemplo real |
|---|---|
| Modificar workflow existente | "adicione também o site X", "mude o horário para 9h" |
| Estender comportamento | "além disso, me mande um resumo", "use também o Canaltech" |
| Corrigir automação | "o workflow de notícias está errado, corrija para" |

### Gatilhos de remoção
| Padrão detectado | Exemplo real |
|---|---|
| Exclusão explícita | "delete o workflow X", "remova a automação de notícias" |
| Desativação | "pause o workflow de backup", "desative por enquanto" |

### Quando NÃO criar workflow
- Tarefas únicas sem recorrência ("pesquise as notícias de hoje")
- Ações imediatas já satisfeitas por skills existentes
- Usuário claramente testando ou fazendo pergunta hipotética ("e se eu quisesse...")

---

## 2. PROTOCOLO DE DECISÃO (fluxo interno)

```
mensagem recebida
      │
      ▼
[1] Há intenção de automação recorrente ou evento?
      │ NÃO → responder normalmente, sem workflow
      │ SIM ↓
[2] Já existe workflow semelhante? (chamar workflow_list)
      │ SIM → perguntar: "Encontrei o workflow X. Deseja atualizá-lo?"
      │ NÃO ↓
[3] A tarefa envolve ação sensível ou irreversível?
      (abrir apps, deletar arquivos, postar conteúdo, gastar dinheiro)
      │ SIM → solicitar confirmação antes de criar
      │ NÃO ↓
[4] Gerar YAML internamente → validar schema → chamar workflow_create
[5] Confirmar ao usuário com resumo do que foi criado
```

**Regra de ouro:** O agente nunca cria um workflow em silêncio absoluto. Sempre informa o que foi criado, com qual trigger e qual ação — em no máximo 2 linhas.

---

## 3. SCHEMA YAML COMPLETO

```yaml
# ~/.lux/workflows/<nome-descritivo>.yaml

name: string                    # identificador legível, kebab-case
description: string             # o que este workflow faz (1 linha)
version: "1.0"
enabled: true

trigger:
  type: schedule | event | manual | voice_command
  
  # Se type = schedule:
  cron: "0 8 * * 1-5"          # padrão cron (min hora dia mês dia_semana)
  timezone: "America/Recife"    # sempre definir fuso
  
  # Se type = event:
  event: file_created | file_modified | task_completed | keyword_detected
  watch_path: /home/user/Documentos   # para eventos de arquivo
  pattern: "*.py"                      # glob opcional
  
  # Se type = voice_command:
  phrase: "inicie o último projeto"    # frase exata ou aproximada
  confirmation_required: true          # solicita confirmação antes de executar

steps:
  - id: step_1
    name: string                # nome legível do passo
    skill: string               # nome da skill a usar (ver seção 5)
    params:
      # parâmetros específicos da skill
    timeout: 60                 # segundos (padrão 120, mínimo 10)
    on_error: continue | abort | notify
    output_var: string          # variável para capturar saída deste step

  - id: step_2
    name: string
    skill: string
    params:
      input: "{{step_1.output}}"  # referência a output anterior
    depends_on: step_1            # garante ordem de execução

notify:
  on_success:
    message: "{{workflow.name}} concluído: {{last_step.summary}}"
    channel: chat | desktop | both
  on_failure:
    message: "Erro no workflow {{workflow.name}}: {{error.message}}"
    channel: chat

metadata:
  created_at: ISO-8601
  updated_at: ISO-8601
  created_by: agent | user
  tags: [lista, de, tags]
```

---

## 4. EXEMPLOS COMPLETOS DE WORKFLOWS

### 4.1 — Briefing diário de tecnologia

**Trigger do usuário:** *"Todo dia útil às 8h me atualize com as últimas notícias de tecnologia. Use sites como Novadigital e Canaltech, e também fontes em inglês."*

**Ação do agente:** Verificar se existe workflow de notícias → não existe → criar diretamente (sem confirmação, pois é tarefa informativa, não destrutiva).

```yaml
name: briefing-tecnologia-diario
description: Pesquisa, resume e entrega as principais notícias de tecnologia dos dias úteis
version: "1.0"
enabled: true

trigger:
  type: schedule
  cron: "0 8 * * 1-5"
  timezone: "America/Recife"

steps:
  - id: coleta_pt
    name: Coletar notícias PT-BR
    skill: web_search
    params:
      sources:
        - "https://novadigital.com.br"
        - "https://canaltech.com.br"
        - "https://tecnoblog.net"
      query: "últimas notícias tecnologia"
      max_results: 10
      since: "24h"
    timeout: 45
    on_error: continue
    output_var: noticias_pt

  - id: coleta_en
    name: Coletar notícias EN
    skill: web_search
    params:
      sources:
        - "https://techcrunch.com"
        - "https://theverge.com"
        - "https://arstechnica.com"
      query: "latest tech news"
      max_results: 10
      since: "24h"
    timeout: 45
    on_error: continue
    output_var: noticias_en

  - id: resumir
    name: Resumir e priorizar
    skill: summarize
    params:
      inputs:
        - "{{coleta_pt.output}}"
        - "{{coleta_en.output}}"
      format: |
        Retorne JSON com:
        {
          "destaques": [ { "titulo": "", "fonte": "", "resumo": "", "link": "" } ],
          "tendencias": ["lista de temas em alta"],
          "nota_do_agente": "observação breve sobre o dia em tecnologia"
        }
        Máximo 5 destaques, priorizando relevância e novidade.
      max_tokens: 800
    depends_on: [coleta_pt, coleta_en]
    output_var: briefing

  - id: entregar
    name: Entregar briefing ao usuário
    skill: notify
    params:
      template: briefing_tecnologia
      data: "{{resumir.output}}"
      intro: "☀️ Seu briefing de tecnologia de hoje:"
    depends_on: resumir

notify:
  on_success:
    message: "Briefing de tecnologia entregue."
    channel: chat
  on_failure:
    message: "Não consegui gerar o briefing hoje: {{error.message}}"
    channel: chat

metadata:
  created_by: agent
  tags: [noticias, tecnologia, diario]
```

---

### 4.2 — Atualizar workflow existente com novas fontes

**Trigger do usuário:** *"No workflow de notícias, adicione o Wired e o MIT Technology Review como fontes em inglês."*

**Ação do agente:**
1. Chamar `workflow_list` → identificar `briefing-tecnologia-diario`
2. Chamar `workflow_view` → obter YAML atual
3. Editar apenas o step `coleta_en`, adicionando as fontes
4. Chamar `workflow_create` com o YAML atualizado (sobrescreve)
5. Confirmar: *"Adicionei Wired e MIT Technology Review ao workflow de notícias. As novas fontes entram em vigor a partir do próximo ciclo."*

**Modificação cirúrgica no YAML:**
```yaml
# step coleta_en após atualização:
  - id: coleta_en
    name: Coletar notícias EN
    skill: web_search
    params:
      sources:
        - "https://techcrunch.com"
        - "https://theverge.com"
        - "https://arstechnica.com"
        - "https://wired.com"                        # ← adicionado
        - "https://technologyreview.com"             # ← adicionado
      query: "latest tech news"
      max_results: 12                                # ← ajustado
      since: "24h"
```

---

### 4.3 — Workflow com confirmação obrigatória

**Trigger do usuário:** *"Crie um workflow que toda vez que eu disser 'inicie o último projeto', ele abra o último projeto e toque a playlist de rap no Spotify."*

**Ação do agente:** Detecta ação sensível (abrir app externo + controlar Spotify) → solicita confirmação antes de criar.

**Resposta do agente antes de criar:**
```
Entendido. Vou criar uma automação com o seguinte comportamento:

  Gatilho   → quando você disser "inicie o último projeto"
  Passo 1   → abrir o projeto mais recente no seu editor
  Passo 2   → iniciar a playlist de rap no Spotify

Confirma? (sim / não / ajustar)
```

**Após confirmação, criar:**
```yaml
name: iniciar-ultimo-projeto
description: Abre o projeto mais recente e toca playlist de rap no Spotify
version: "1.0"
enabled: true

trigger:
  type: voice_command
  phrase: "inicie o último projeto"
  confirmation_required: false   # confirmação já foi feita na criação
  fuzzy_match: true              # aceita variações como "abra meu último projeto"

steps:
  - id: detectar_projeto
    name: Detectar projeto mais recente
    skill: directory_scan
    params:
      path: "{{env.LUX_WATCH_DIRS}}"
      sort_by: last_modified
      filter: [".git", "package.json", "pyproject.toml", "*.code-workspace"]
      depth: 3
      return: last_modified_root
    timeout: 15
    on_error: abort
    output_var: ultimo_projeto

  - id: abrir_editor
    name: Abrir projeto no editor
    skill: shell_exec
    params:
      command: "code '{{detectar_projeto.output.path}}'"
      confirm_before_run: false
    depends_on: detectar_projeto
    timeout: 20
    on_error: notify

  - id: spotify_play
    name: Tocar playlist de rap
    skill: spotify
    params:
      action: play_playlist
      query: "rap"
      strategy: liked_first   # prefere playlists salvas antes de buscar
    depends_on: detectar_projeto
    timeout: 15
    on_error: notify
    output_var: spotify_result

  - id: confirmar
    name: Confirmar ao usuário
    skill: notify
    params:
      message: >
        Tudo pronto. Abri **{{detectar_projeto.output.name}}** no editor
        e coloquei **{{spotify_play.output.playlist_name}}** no Spotify. 🎧
      channel: chat
    depends_on: [abrir_editor, spotify_play]

notify:
  on_failure:
    message: "Não consegui iniciar o projeto: {{error.message}}"
    channel: chat

metadata:
  created_by: agent
  tags: [projeto, spotify, produtividade]
  requires_confirmation_to_create: true
```

---

## 5. SKILLS DISPONÍVEIS PARA STEPS

| Skill | Função | Params principais |
|---|---|---|
| `web_search` | Pesquisa web com filtro de fontes e janela de tempo | `sources`, `query`, `since`, `max_results` |
| `summarize` | Resume e estrutura conteúdo via LLM | `inputs`, `format`, `max_tokens` |
| `notify` | Envia mensagem ao usuário | `message`, `channel`, `template` |
| `directory_scan` | Escaneia diretórios do sistema | `path`, `sort_by`, `filter`, `depth` |
| `shell_exec` | Executa comando shell | `command`, `confirm_before_run` |
| `spotify` | Controla Spotify | `action`, `query`, `strategy` |
| `file_ops` | Copia, move, comprime arquivos | `action`, `source`, `dest` |
| `git_ops` | Operações git | `action`, `repo_path` |
| `http_request` | Requisição HTTP genérica | `url`, `method`, `headers`, `body` |
| `write_file` | Escreve resultado em arquivo | `path`, `content`, `format` |

---

## 6. REFERÊNCIA DE EXPRESSÕES CRON

| Intenção do usuário | Cron |
|---|---|
| "todo dia às 8h" | `0 8 * * *` |
| "dias úteis às 8h" | `0 8 * * 1-5` |
| "toda segunda às 9h" | `0 9 * * 1` |
| "toda hora" | `0 * * * *` |
| "toda semana, sexta às 18h" | `0 18 * * 5` |
| "primeiro dia do mês" | `0 9 1 * *` |
| "duas vezes ao dia" | `0 8,18 * * *` |

---

## 7. REGRAS DE CONFIRMAÇÃO

```
CRIAR sem confirmação quando:
  ✓ Tarefa é informativa (notícias, resumos, relatórios)
  ✓ Tarefa é backup/cópia (reversível)
  ✓ Não envolve apps externos, dinheiro ou postagem

CRIAR com confirmação quando:
  ✗ Abre aplicativos externos (editor, Spotify, browser)
  ✗ Executa comandos shell
  ✗ Envolve envio (e-mail, mensagens, redes sociais)
  ✗ Modifica ou deleta arquivos
  ✗ Acessa APIs externas com escrita

ATUALIZAR sem confirmação quando:
  ✓ Alteração é aditiva (adicionar fontes, mudar horário)
  ✓ Usuário especificou exatamente o que mudar

ATUALIZAR com confirmação quando:
  ✗ Alteração muda comportamento central do workflow
  ✗ Remove steps existentes

DELETAR: sempre confirmar, nunca silencioso.
```

---

## 8. FORMATO DE RESPOSTA AO USUÁRIO

### Após criar workflow
```
Workflow criado: **{nome}**
Vai rodar {descrição do trigger} e {ação resumida em 1 linha}.
```

### Após atualizar workflow
```
Workflow **{nome}** atualizado.
{O que mudou em 1 linha.} Próxima execução: {data/horário se aplicável}.
```

### Pedindo confirmação
```
Vou criar uma automação com o seguinte comportamento:

  Gatilho → {trigger em linguagem natural}
  {step 1 resumido}
  {step 2 resumido}
  ...

Confirma? (sim / não / ajustar)
```

### Ao deletar
```
Tem certeza que quer remover o workflow **{nome}**?
{Descrição do que ele faz.} Um backup será salvo em ~/.lux/workflows/.trash/
```

---

## 9. ERROS COMUNS E COMO TRATAR

| Situação | Comportamento |
|---|---|
| Skill referenciada não existe | Abortar criação, informar ao usuário quais skills estão disponíveis |
| YAML inválido após geração | Tentar corrigir automaticamente (1 retry), senão informar o erro |
| Workflow com mesmo nome já existe | Perguntar: atualizar existente ou criar novo com nome diferente? |
| Step com timeout excedido | Executar `on_error` do step; o agente continua respondendo normalmente |
| Frase de voice_command ambígua | Listar workflows que poderiam corresponder, pedir que o usuário escolha |
| `workflow_delete` sem backup | NUNCA deletar sem backup. Sempre salvar em `.trash/` com timestamp |

---

## 10. VARIÁVEIS DE AMBIENTE E CONTEXTO

```
{{env.LUX_WATCH_DIRS}}     → diretórios monitorados (do .env)
{{env.HOME}}               → home do usuário
{{user.name}}              → nome do usuário
{{workflow.name}}          → nome do workflow atual
{{workflow.last_run}}      → timestamp da última execução
{{step_id.output}}         → saída de um step anterior
{{error.message}}          → mensagem de erro (em handlers on_error)
{{date.today}}             → data atual YYYY-MM-DD
{{date.weekday}}           → dia da semana em português
```

---

## 11. FILOSOFIA DO AGENTE

> O agente não pergunta o que não precisa perguntar.  
> O agente não cria o que o usuário não pediu.  
> O agente confirma apenas quando a ação tem peso.  
> O agente informa, sem encher de texto desnecessário.

Workflows rodam **em background**, sem travar a conversa. O usuário nunca deve sentir que o agente "travou" criando uma automação — a resposta chega imediatamente, e o workflow roda por conta própria.

Se um workflow falha, o agente notifica com contexto suficiente para o usuário entender o que ocorreu — sem stack traces, sem jargão técnico.

---

*Versão 1.0 — LUX Workflow Agent*
