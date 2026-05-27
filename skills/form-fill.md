---
name: form-fill
description: "Preencher formularios na tela usando screenshot + OCR + keyboard_type"
version: 1.0.0
author: lux-core
platforms: [linux]
metadata:
  lux:
    tags: [desktop, forms, automation]
    category: productivity
    requires_toolsets: [desktop]
    use_count: 0
---

# Form Fill

## Quando Usar
Preencher formularios web ou de aplicacao automaticamente, lendo os campos via OCR.

## Pre-requisitos
- Toolset `desktop` ativo
- Formulario visivel na tela

## Procedimento

### 1. Identificar campos via OCR
```bash
screen_read    # le todos os textos da tela
# ou
find_on_screen --text "Nome"    # encontra campo especifico
```

### 2. Clicar no campo
```bash
mouse_click --x {x} --y {y}
```

### 3. Preencher
```bash
keyboard_type --text "valor" --clear_first True
keyboard_press --keys "Tab"     # proximo campo
```

### 4. Repetir para cada campo

### 5. Submeter
```bash
find_on_screen --text "Enviar"  # encontra botao
mouse_click --x {x} --y {y}    # clica
```

## Pitfalls
- Campos dinamicos podem mudar de posicao entre sessoes
- OCR pode errar em fontes pequenas: faca screenshot com zoom se necessario
- Sempre confirme com o usuario antes de submeter
