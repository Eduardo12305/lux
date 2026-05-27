---
name: deploy-docker
description: "Deploy de container Docker local ou remoto via SSH"
version: 1.0.0
author: lux-core
platforms: [linux, macos]
metadata:
  lux:
    tags: [docker, deploy, devops]
    category: infrastructure
    requires_toolsets: [terminal]
    use_count: 0
---

# Deploy Docker

## Quando Usar
Deploy de imagens Docker em ambientes locais ou remotos.

## Pre-requisitos
- Docker instalado e rodando (`docker info`)
- Se remoto: SSH configurado para o host alvo
- Toolset `terminal` ativo

## Procedimento

### 1. Verificar estado atual
```bash
docker ps -a | grep {container_name}
docker images | grep {image_name}
```

### 2. Build da imagem
```bash
docker build -t {image_name}:{tag} .
```

### 3. Teste local (opcional)
```bash
docker run --rm -p {port}:{port} {image_name}:{tag}
curl http://localhost:{port}/health
```

### 4. Push para registry (se aplicavel)
```bash
docker tag {image_name}:{tag} {registry}/{image_name}:{tag}
docker push {registry}/{image_name}:{tag}
```

### 5. Deploy
Local:
```bash
docker stop {container_name} 2>/dev/null
docker rm {container_name} 2>/dev/null
docker run -d --name {container_name} --restart=unless-stopped -p {port}:{port} {image_name}:{tag}
```

Remoto via SSH:
```bash
ssh {host} "docker pull {image} && docker stop {container} 2>/dev/null; docker rm {container} 2>/dev/null; docker run -d --name {container} --restart=unless-stopped -p {port}:{port} {image}"
```

### 6. Verificar
```bash
docker ps | grep {container_name}
curl http://{host}:{port}/health
docker logs {container_name} --tail 20
```

## Pitfalls
- Permission denied: `sudo usermod -aG docker $USER` + relogin
- Porta ocupada: `lsof -i :{port}` para ver o que esta usando
- Registry HTTP inseguro: adicionar em `/etc/docker/daemon.json`
