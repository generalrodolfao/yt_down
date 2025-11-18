# Guia de Deploy - YouTube Downloader para VPS

## Pré-requisitos

- VPS com Ubuntu 20.04+ ou Debian 11+
- Acesso SSH à VPS
- Docker e Docker Compose instalados
- Domínio configurado (opcional, para usar com Nginx)

## Passo 1: Preparar a VPS

### 1.1 Conectar via SSH
```bash
ssh usuario@seu-ip-vps
```

### 1.2 Atualizar sistema
```bash
sudo apt update && sudo apt upgrade -y
```

### 1.3 Instalar Docker
```bash
# Instalar Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Adicionar usuário ao grupo docker
sudo usermod -aG docker $USER

# Instalar Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Verificar instalação
docker --version
docker-compose --version
```

### 1.4 Criar diretório do projeto
```bash
mkdir -p ~/yt-downloader
cd ~/yt-downloader
```

## Passo 2: Enviar código para VPS

### Opção A: Usando Git (recomendado)
```bash
# Na sua máquina local, inicialize git se ainda não tiver
cd /Users/rodolfobarbosa/projetos/yt_down
git init
git add .
git commit -m "Initial commit"

# Na VPS
cd ~/yt-downloader
git clone <seu-repositorio> .
# OU se já tiver o código local, use scp:
```

### Opção B: Usando SCP (do seu Mac)
```bash
# Do seu Mac, envie os arquivos
scp -r /Users/rodolfobarbosa/projetos/yt_down/* usuario@seu-ip-vps:~/yt-downloader/
```

### Opção C: Usando rsync (mais eficiente)
```bash
rsync -avz --exclude 'downloads' --exclude '__pycache__' \
  /Users/rodolfobarbosa/projetos/yt_down/ \
  usuario@seu-ip-vps:~/yt-downloader/
```

## Passo 3: Configurar projeto na VPS

### 3.1 Criar estrutura de diretórios
```bash
cd ~/yt-downloader
mkdir -p downloads
```

### 3.2 Configurar Cookies (Recomendado para evitar detecção de bot)
Se você está tendo problemas com "Sign in to confirm you're not a bot", configure cookies:

1. **Exporte cookies do seu navegador** (veja `COOKIES.md` para instruções detalhadas)
2. **Coloque o arquivo `cookies.txt` na raiz do projeto**
3. **Descomente a linha de cookies no `docker-compose.yml`**:
```yaml
volumes:
  - ./cookies.txt:/app/cookies.txt:ro
```

**Importante:** Nunca compartilhe seu arquivo `cookies.txt` - ele contém suas credenciais!

### 3.3 Ajustar configurações (opcional)
Se quiser mudar a porta, edite `docker-compose.yml`:
```yaml
ports:
  - "8080:5002"  # Mude 8080 para a porta desejada
```

## Passo 4: Build e iniciar container

### 4.1 Build da imagem
```bash
cd ~/yt-downloader
docker-compose build
```

### 4.2 Iniciar container
```bash
docker-compose up -d
```

### 4.3 Verificar logs
```bash
docker-compose logs -f
```

### 4.4 Verificar se está rodando
```bash
docker-compose ps
curl http://localhost:5002
```

## Passo 5: Configurar Nginx (Reverso Proxy - Opcional mas Recomendado)

### 5.1 Instalar Nginx
```bash
sudo apt install nginx -y
```

### 5.2 Criar configuração
```bash
sudo nano /etc/nginx/sites-available/yt-downloader
```

Adicione:
```nginx
server {
    listen 80;
    server_name seu-dominio.com;  # Ou IP da VPS

    client_max_body_size 10G;  # Para uploads grandes

    location / {
        proxy_pass http://localhost:5002;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
        
        # Timeouts para processamento longo
        proxy_connect_timeout 600s;
        proxy_send_timeout 600s;
        proxy_read_timeout 600s;
    }
}
```

### 5.3 Ativar site
```bash
sudo ln -s /etc/nginx/sites-available/yt-downloader /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### 5.4 Configurar SSL com Let's Encrypt (se tiver domínio)
```bash
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d seu-dominio.com
```

## Passo 6: Configurar Firewall

```bash
# Permitir SSH
sudo ufw allow 22/tcp

# Permitir HTTP/HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Se não usar Nginx, permitir porta direta
sudo ufw allow 5002/tcp

# Ativar firewall
sudo ufw enable
```

## Passo 7: Manutenção

### Ver logs
```bash
docker-compose logs -f yt-downloader
```

### Reiniciar container
```bash
docker-compose restart
```

### Parar container
```bash
docker-compose down
```

### Atualizar código
```bash
# Se usar Git
cd ~/yt-downloader
git pull
docker-compose build
docker-compose up -d
```

### Backup dos downloads
```bash
# Criar backup
tar -czf backup-downloads-$(date +%Y%m%d).tar.gz downloads/

# Restaurar backup
tar -xzf backup-downloads-YYYYMMDD.tar.gz
```

## Passo 8: Monitoramento (Opcional)

### Instalar htop para monitorar recursos
```bash
sudo apt install htop -y
htop
```

### Ver uso de disco
```bash
df -h
du -sh downloads/
```

## Troubleshooting

### Container não inicia
```bash
docker-compose logs yt-downloader
docker-compose ps
```

### Erro de permissão
```bash
sudo chown -R $USER:$USER downloads/
```

### Porta já em uso
```bash
sudo lsof -i :5002
# Mude a porta no docker-compose.yml
```

### Sem espaço em disco
```bash
# Limpar imagens Docker não usadas
docker system prune -a

# Verificar espaço
df -h
```

## Variáveis de Ambiente (Opcional)

Crie arquivo `.env`:
```bash
nano .env
```

Adicione:
```
FLASK_ENV=production
PORT=5002
```

E atualize `docker-compose.yml`:
```yaml
env_file:
  - .env
```

## Acesso

- Com Nginx: `http://seu-dominio.com` ou `https://seu-dominio.com`
- Sem Nginx: `http://seu-ip-vps:5002`

## Comandos Úteis

```bash
# Ver status
docker-compose ps

# Ver logs em tempo real
docker-compose logs -f

# Parar tudo
docker-compose down

# Reiniciar
docker-compose restart

# Rebuild após mudanças
docker-compose build --no-cache
docker-compose up -d
```

