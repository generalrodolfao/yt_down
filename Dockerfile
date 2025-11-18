FROM python:3.11-slim

# Instala dependências do sistema (ffmpeg, ffprobe, etc)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

# Define diretório de trabalho
WORKDIR /app

# Copia requirements e instala dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install gunicorn

# Copia código da aplicação
COPY . .

# Cria diretório para downloads
RUN mkdir -p downloads

# Cria diretório para cookies (opcional, pode ser montado via volume)
RUN mkdir -p /app/cookies

# Expõe porta
EXPOSE 5002

# Comando para produção (usando gunicorn)
CMD ["gunicorn", "--bind", "0.0.0.0:5002", "--workers", "2", "--timeout", "300", "--access-logfile", "-", "--error-logfile", "-", "app:app"]

