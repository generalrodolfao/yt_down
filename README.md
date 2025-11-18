# YouTube Downloader

Sistema web para baixar vídeos e playlists do YouTube com interface moderna usando Materialize CSS.

## Funcionalidades

- 📥 Download de vídeos individuais do YouTube
- 📚 Download de playlists completas do YouTube
- 🎬 Visualização de informações do vídeo/playlist antes do download
- 🎨 Interface moderna com Materialize CSS
- 📋 Lista de vídeos baixados
- ⚙️ Seleção de qualidade do vídeo
- 🔒 Proteção contra erro 403 (Forbidden) com headers personalizados

## Instalação

1. Instale as dependências:
```bash
pip3 install -r requirements.txt
```

## Uso

1. Inicie o servidor:
```bash
python3 app.py
```

2. Acesse no navegador:
```
http://localhost:5002
```

3. Cole a URL do vídeo ou playlist do YouTube e clique em "Obter Informações"

4. Escolha a qualidade desejada e clique em "Baixar Vídeo" ou "Baixar Playlist"

## Estrutura

- `app.py` - Servidor Flask com as rotas da API
- `templates/index.html` - Interface web
- `downloads/` - Pasta onde os vídeos são salvos (criada automaticamente)
  - Vídeos individuais são salvos diretamente na pasta
  - Playlists são salvas em subpastas com o nome da playlist

## Notas

- Os vídeos são salvos na pasta `downloads/` dentro do projeto
- Playlists são organizadas em subpastas com o nome da playlist
- O sistema suporta diferentes qualidades de vídeo
- A interface é responsiva e funciona em dispositivos móveis
- O sistema inclui proteções contra erro 403 usando headers e user-agent personalizados

# yt_down
