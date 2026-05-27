---
name: browser-control
description: "Controle de browser via ferramentas de desktop: abrir URL, navegar, copiar texto"
version: 1.0.0
author: lux-core
platforms: [linux]
metadata:
  lux:
    tags: [browser, desktop, web]
    category: productivity
    requires_toolsets: [desktop, terminal]
    use_count: 0
---

# Browser Control

## Quando Usar
Quando precisar interagir com paginas web via browser (abrir URLs, navegar entre abas, copiar conteudo da pagina).

## Pre-requisitos
- Toolset `desktop` ativo
- Browser aberto e visivel
- xdotool, xclip instalados

## Procedimento

### 1. Focar o browser
```bash
# Listar janelas
window_list

# Focar browser (Chrome/Firefox)
window_focus --title "Google Chrome"
# ou
window_focus --title "Firefox"
```

### 2. Abrir URL (barra de endereco)
```bash
keyboard_press --keys "ctrl+l"     # foca barra de endereco
keyboard_type --text "https://github.com" --delay_ms 30
keyboard_press --keys "Return"
```

### 3. Navegar na pagina
```bash
keyboard_press --keys "Page_Down"   # scroll down
keyboard_press --keys "ctrl+f"      # buscar na pagina
keyboard_type --text "termo" --delay_ms 50
keyboard_press --keys "Escape"      # fechar busca
```

### 4. Copiar texto da pagina
```bash
keyboard_press --keys "ctrl+a"     # selecionar tudo
keyboard_press --keys "ctrl+c"     # copiar
clipboard_read                     # ler conteudo copiado
```

### 5. Fechar aba
```bash
keyboard_press --keys "ctrl+w"
```

## Pitfalls
- Browser em tela cheia pode esconder a barra de endereco: use F11 antes
- Focus stealing: se outra janela roubar foco, refoque com window_focus
