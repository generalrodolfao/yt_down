# Como usar Cookies do YouTube para evitar detecção de bot

O YouTube pode bloquear requisições do yt-dlp detectando que é um bot. Para resolver isso, você pode usar cookies do seu navegador.

## Método 1: Usando extensão do navegador (Mais fácil)

### Chrome/Edge/Brave:
1. Instale a extensão: [Get cookies.txt LOCALLY](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)
2. Acesse https://www.youtube.com
3. Faça login na sua conta do YouTube
4. Clique no ícone da extensão
5. Clique em "Export" para baixar o arquivo `cookies.txt`
6. Coloque o arquivo na raiz do projeto (mesmo diretório do `app.py`)

### Firefox:
1. Instale a extensão: [cookies.txt](https://addons.mozilla.org/en-US/firefox/addon/cookies-txt/)
2. Acesse https://www.youtube.com
3. Faça login na sua conta do YouTube
4. Clique no ícone da extensão
5. Clique em "Export" para baixar o arquivo `cookies.txt`
6. Coloque o arquivo na raiz do projeto

## Método 2: Usando yt-dlp diretamente

```bash
# Exportar cookies do navegador Chrome
yt-dlp --cookies-from-browser chrome --cookies cookies.txt "https://www.youtube.com"

# Ou do Firefox
yt-dlp --cookies-from-browser firefox --cookies cookies.txt "https://www.youtube.com"
```

## Método 3: Manual (copiar do navegador)

1. Abra o YouTube no navegador e faça login
2. Abra as ferramentas de desenvolvedor (F12)
3. Vá para a aba "Application" (Chrome) ou "Storage" (Firefox)
4. Encontre "Cookies" → "https://www.youtube.com"
5. Copie os cookies importantes (principalmente `__Secure-3PSID`, `__Secure-3PAPISID`, etc.)
6. Crie um arquivo `cookies.txt` no formato Netscape:
```
# Netscape HTTP Cookie File
.youtube.com	TRUE	/	TRUE	1735689600	__Secure-3PSID	valor_do_cookie
```

## Usando no projeto

### Localmente:
1. Coloque o arquivo `cookies.txt` na raiz do projeto
2. O código detectará automaticamente e usará

### No Docker/VPS:
1. Coloque o arquivo `cookies.txt` na raiz do projeto antes do build
2. Ou use variável de ambiente:
```bash
export YOUTUBE_COOKIES=/caminho/para/cookies.txt
```

### No docker-compose.yml:
```yaml
services:
  yt-downloader:
    environment:
      - YOUTUBE_COOKIES=/app/cookies.txt
    volumes:
      - ./cookies.txt:/app/cookies.txt:ro  # Monta como read-only
```

## Importante

- ⚠️ **Nunca compartilhe seu arquivo cookies.txt** - ele contém suas credenciais de sessão
- ⚠️ Adicione `cookies.txt` ao `.gitignore` para não versionar
- ⚠️ Os cookies expiram, você precisará atualizar periodicamente
- ✅ Cookies ajudam muito a evitar detecção de bot
- ✅ Funciona melhor quando você está logado em uma conta do YouTube

## Verificar se está funcionando

Se os cookies estiverem sendo usados, você verá nos logs do yt-dlp que não há mais o erro "Sign in to confirm you're not a bot".

