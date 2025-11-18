#!/bin/bash
# deploy.sh - Script de deploy automatizado

set -e

echo "🚀 Iniciando deploy do YouTube Downloader..."

# Verifica se Docker está instalado
if ! command -v docker &> /dev/null; then
    echo "❌ Docker não encontrado. Instalando..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
    echo "✅ Docker instalado. Você pode precisar fazer logout/login para usar Docker sem sudo."
fi

# Verifica se Docker Compose está instalado
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose não encontrado. Instalando..."
    sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
fi

# Cria diretório de downloads se não existir
mkdir -p downloads

# Build e start
echo "🔨 Fazendo build da imagem..."
docker-compose build

echo "🛑 Parando containers existentes (se houver)..."
docker-compose down || true

echo "🚀 Iniciando containers..."
docker-compose up -d

echo "⏳ Aguardando container iniciar..."
sleep 5

# Verifica se está rodando
if docker-compose ps | grep -q "Up"; then
    echo "✅ Deploy concluído com sucesso!"
    echo ""
    echo "📡 Acesse: http://localhost:5002"
    echo "📋 Ver logs: docker-compose logs -f"
    echo "🛑 Parar: docker-compose down"
    echo "🔄 Reiniciar: docker-compose restart"
else
    echo "❌ Erro ao iniciar container. Verifique os logs:"
    docker-compose logs
    exit 1
fi

