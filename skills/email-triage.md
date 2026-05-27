---
name: email-triage
description: "Triagem de emails: lista nao lidos, identifica urgentes, responde"
version: 1.0.0
author: lux-core
platforms: [linux, macos]
metadata:
  lux:
    tags: [email, productivity, communication]
    category: productivity
    requires_toolsets: [email]
    use_count: 0
---

# Triagem de Email

## Quando Usar
Quando o usuario pede para verificar emails, identificar urgentes, ou responder mensagens.

## Pre-requisitos
- Toolset `email` ativo
- Email configurado no `.env` (LUX_EMAIL_*)

## Procedimento

### 1. Listar nao lidos
Use `email_list` com `unread_only=true`. Limite a 20 para nao sobrecarregar.

### 2. Identificar urgentes
Criterios de urgencia:
- Remetente e contato frequente (verificar MEMORY.md)
- Palavras-chave: "urgente", "hoje", "prazo", "reuniao"
- Data: enviado ha mais de 24h sem resposta
- Assunto menciona projeto ativo (verificar contexto)

### 3. Classificar
- ⚠️ Urgente: requer acao hoje
- 📝 Importante: requer acao esta semana
- 📰 Informativo: newsletter, notificacao
- 🗑 Lixo: spam, promocao

### 4. Sugerir acoes
Para cada urgente, sugira resposta. Use `email_read` para ver o corpo completo antes de responder.

### 5. Responder (com confirmacao)
Use `email_send` APENAS apos confirmacao explicita do usuario.
NUNCA envie email sem o usuario revisar o conteudo.

## Pitfalls
- Enviar sem revisao do usuario → sempre peca confirmacao
- Responder email antigo sem contexto → leia a thread completa
- Classificar como urgente sem verificar → confirme com o usuario
