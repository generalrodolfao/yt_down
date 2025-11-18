from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp
import os
import re
from pathlib import Path
import json
import whisper
import subprocess
import shutil
from datetime import timedelta

app = Flask(__name__)
CORS(app)  # Permite requisições de qualquer origem (útil para desenvolvimento)

# Pasta para salvar os downloads
DOWNLOAD_FOLDER = Path(__file__).parent / "downloads"
DOWNLOAD_FOLDER.mkdir(exist_ok=True)

LESSONS_FOLDER_NAME = "assuntos"
VIDEO_EXTENSIONS = ['.mp4', '.webm', '.mkv', '.m4a', '.mp3']
SUBTITLE_LANGS = ['pt', 'pt-BR', 'pt-PT']

# Opções comuns do yt-dlp para evitar erro 403 e detecção de bot
def get_common_opts():
    """Retorna opções comuns do yt-dlp, incluindo cookies se disponível"""
    opts = {
        'quiet': False,
        'no_warnings': False,
        'extract_flat': False,
        # User agent mais recente
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'referer': 'https://www.youtube.com/',
        # Headers mais completos e atualizados
        'headers': {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9,pt;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Sec-Ch-Ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
            'Cache-Control': 'max-age=0',
        },
        # Opções adicionais para evitar 403 e detecção
        'no_check_certificate': False,
        'prefer_insecure': False,
        'socket_timeout': 30,
        'retries': 10,
        'fragment_retries': 10,
        'file_access_retries': 3,
        # Opções para evitar detecção de bot
        'sleep_requests': 1,  # Pausa entre requisições
        'sleep_interval': 1,  # Pausa entre downloads
        'max_sleep_interval': 5,
    }
    
    # Tenta usar cookies se disponível (via variável de ambiente ou arquivo)
    cookies_path = os.getenv('YOUTUBE_COOKIES', None)
    if cookies_path and os.path.exists(cookies_path):
        opts['cookiefile'] = cookies_path
    elif os.path.exists('cookies.txt'):
        opts['cookiefile'] = 'cookies.txt'
    
    return opts

def get_video_info(url):
    """Obtém informações do vídeo ou playlist sem baixar"""
    ydl_opts = {
        **get_common_opts(),
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,  # Extrai informações completas
        'listsubtitles': True,  # Lista legendas disponíveis
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # Verifica legendas disponíveis
            available_subtitles = {}
            if 'subtitles' in info:
                available_subtitles = info.get('subtitles', {})
            if 'automatic_captions' in info:
                auto_captions = info.get('automatic_captions', {})
                # Mescla legendas automáticas
                for lang, formats in auto_captions.items():
                    if lang not in available_subtitles:
                        available_subtitles[lang] = formats
            
            # Verifica se tem português
            has_portuguese = any(lang.startswith('pt') for lang in available_subtitles.keys())
            
            # Verifica se é uma playlist
            if 'entries' in info and info.get('_type') == 'playlist':
                # É uma playlist
                entries = list(info.get('entries', []))
                # Remove entradas None
                entries = [e for e in entries if e is not None]
                
                return {
                    'is_playlist': True,
                    'title': info.get('title', 'Playlist sem título'),
                    'uploader': info.get('uploader', 'Desconhecido'),
                    'playlist_count': len(entries),
                    'thumbnail': info.get('thumbnail', ''),
                    'has_subtitles': has_portuguese,
                    'available_subtitle_langs': list(available_subtitles.keys()),
                    'entries': [
                        {
                            'id': entry.get('id', ''),
                            'title': entry.get('title', 'Sem título'),
                            'duration': entry.get('duration', 0),
                            'url': entry.get('url', ''),
                        }
                        for entry in entries[:10]  # Limita a 10 para preview
                    ]
                }
            else:
                # É um vídeo único
                return {
                    'is_playlist': False,
                    'title': info.get('title', 'Sem título'),
                    'duration': info.get('duration', 0),
                    'thumbnail': info.get('thumbnail', ''),
                    'uploader': info.get('uploader', 'Desconhecido'),
                    'view_count': info.get('view_count', 0),
                    'has_subtitles': has_portuguese,
                    'available_subtitle_langs': list(available_subtitles.keys()),
                }
    except Exception as e:
        return {'error': str(e)}

def download_video(url, quality='best', is_playlist=False, download_subtitles=False):
    """Baixa o vídeo ou playlist do YouTube com fallback para evitar 403"""
    # Se a URL tem parâmetro list= mas is_playlist é False, remove o parâmetro list
    if not is_playlist and 'list=' in url:
        # Remove o parâmetro list da URL para baixar apenas o vídeo
        url = re.sub(r'[?&]list=[^&]*', '', url)
        # Limpa caracteres duplicados
        url = url.replace('?&', '?').replace('&&', '&')
        if url.endswith('&') or url.endswith('?'):
            url = url[:-1]
    
    if is_playlist:
        output_path = DOWNLOAD_FOLDER / "%(playlist_title)s" / "%(title)s.%(ext)s"
        subtitle_path = DOWNLOAD_FOLDER / "%(playlist_title)s" / "%(title)s.%(ext)s"
    else:
        output_path = DOWNLOAD_FOLDER / "%(title)s.%(ext)s"
        subtitle_path = DOWNLOAD_FOLDER / "%(title)s.%(ext)s"
    
    # Simplifica o formato para evitar problemas de merge que podem travar
    format_selector = quality
    if quality == 'best':
        # Tenta formatos simples primeiro (sem merge)
        format_selector = 'best[ext=mp4]/best[height<=720]/best'
    elif quality == 'worst':
        format_selector = 'worst'
    elif quality == 'bestvideo+bestaudio':
        format_selector = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
    
    # Estratégias diferentes para tentar evitar 403 e detecção de bot
    # Ordem: mais modernos primeiro (menos detecção)
    strategies = [
        {
            'name': 'mweb_client',
            'extractor_args': {
                'youtube': {
                    'player_client': ['mweb'],
                    'player_skip': ['webpage', 'configs'],
                }
            }
        },
        {
            'name': 'android_embedded',
            'extractor_args': {
                'youtube': {
                    'player_client': ['android_embedded'],
                    'player_skip': ['webpage', 'configs'],
                }
            }
        },
        {
            'name': 'android',
            'extractor_args': {
                'youtube': {
                    'player_client': ['android'],
                    'player_skip': ['webpage', 'configs'],
                }
            }
        },
        {
            'name': 'ios',
            'extractor_args': {
                'youtube': {
                    'player_client': ['ios'],
                    'player_skip': ['webpage', 'configs'],
                }
            }
        },
        {
            'name': 'web',
            'extractor_args': {
                'youtube': {
                    'player_client': ['web'],
                }
            }
        },
    ]
    
    downloaded_files = []
    last_error = None
    
    # Tenta cada estratégia
    for strategy_idx, strategy in enumerate(strategies, 1):
        try:
            ydl_opts = {
                **get_common_opts(),
                'format': format_selector,
                'outtmpl': str(output_path),
                'quiet': False,
                'no_warnings': False,
                'merge_output_format': 'mp4',
                'extractor_args': strategy['extractor_args'],
                'progress_hooks': [],  # Pode adicionar hooks de progresso aqui
            }
            
            # Configura download de legendas/transcrições em português
            if download_subtitles:
                ydl_opts['writesubtitles'] = True
                ydl_opts['writeautomaticsub'] = True  # Inclui transcrições automáticas
                ydl_opts['subtitleslangs'] = ['pt', 'pt-BR', 'pt-PT']  # Português em várias variantes
                ydl_opts['subtitlesformat'] = 'vtt'  # Formato WebVTT
                # O yt-dlp adiciona automaticamente .{lang}.vtt ao nome do arquivo
            
            # Se for playlist, não limita quantidade
            if is_playlist:
                ydl_opts['noplaylist'] = False
            else:
                ydl_opts['noplaylist'] = True
            
            print(f"Tentando estratégia {strategy_idx}/{len(strategies)}: {strategy['name']}")
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                
                if 'entries' in info and info.get('entries'):
                    # Playlist baixada
                    subtitle_files = []
                    for entry in info.get('entries', []):
                        if entry:
                            filename = ydl.prepare_filename(entry)
                            # Verifica se o arquivo existe (pode ter extensão diferente)
                            base_filename = os.path.splitext(filename)[0]
                            video_file = None
                            for ext in ['.mp4', '.webm', '.mkv', '.m4a']:
                                test_file = base_filename + ext
                                if os.path.exists(test_file):
                                    video_file = test_file
                                    break
                            
                            if video_file:
                                file_info = {
                                    'filename': os.path.basename(video_file),
                                    'path': video_file,
                                    'title': entry.get('title', 'Sem título')
                                }
                                
                                # Verifica se há arquivo de legenda
                                if download_subtitles:
                                    for lang in ['pt', 'pt-BR', 'pt-PT']:
                                        subtitle_file = base_filename + f'.{lang}.vtt'
                                        if os.path.exists(subtitle_file):
                                            file_info['subtitle'] = os.path.basename(subtitle_file)
                                            subtitle_files.append(subtitle_file)
                                            break
                                
                                downloaded_files.append(file_info)
                    
                    return {
                        'success': True,
                        'is_playlist': True,
                        'files': downloaded_files,
                        'count': len(downloaded_files),
                        'playlist_title': info.get('title', 'Playlist'),
                        'subtitles_downloaded': len(subtitle_files) > 0
                    }
                else:
                    # Vídeo único baixado
                    filename = ydl.prepare_filename(info)
                    # Verifica se o arquivo existe (pode ter extensão diferente)
                    base_filename = os.path.splitext(filename)[0]
                    actual_file = None
                    for ext in ['.mp4', '.webm', '.mkv', '.m4a']:
                        test_file = base_filename + ext
                        if os.path.exists(test_file):
                            actual_file = test_file
                            break
                    
                    if not actual_file:
                        # Se não encontrou o arquivo, tenta o nome original
                        if os.path.exists(filename):
                            actual_file = filename
                        else:
                            raise Exception(f"Arquivo não encontrado após download: {filename}")
                    
                    result = {
                        'success': True,
                        'is_playlist': False,
                        'filename': os.path.basename(actual_file),
                        'path': actual_file,
                        'title': info.get('title', 'Sem título')
                    }
                    
                    # Verifica se há arquivo de legenda
                    subtitle_file_path = None
                    if download_subtitles:
                        for lang in ['pt', 'pt-BR', 'pt-PT']:
                            subtitle_file = base_filename + f'.{lang}.vtt'
                            if os.path.exists(subtitle_file):
                                result['subtitle'] = os.path.basename(subtitle_file)
                                result['subtitles_downloaded'] = True
                                subtitle_file_path = subtitle_file
                                break
                        if 'subtitles_downloaded' not in result:
                            result['subtitles_downloaded'] = False
                    
                    # Cria reels automaticamente se tiver legendas
                    if subtitle_file_path and download_subtitles:
                        try:
                            print(f"Criando reels automaticamente para {actual_file}...")
                            segments = parse_vtt_file(Path(subtitle_file_path))
                            if segments:
                                viral_moments = analyze_viral_moments(segments, 15, 60)
                                if viral_moments:
                                    clips_folder = Path(actual_file).parent / f"{Path(actual_file).stem}_reels"
                                    clips = create_video_clips(Path(actual_file), viral_moments, clips_folder)
                                    if clips:
                                        result['reels_created'] = True
                                        result['reels_count'] = len(clips)
                                        result['reels_folder'] = clips_folder.name
                        except Exception as e:
                            print(f"Erro ao criar reels automaticamente: {e}")
                            result['reels_created'] = False
                    
                    return result
        except Exception as e:
            error_str = str(e)
            last_error = error_str
            print(f"Erro na estratégia {strategy['name']}: {error_str}")
            # Se não for erro 403, retorna imediatamente
            if '403' not in error_str and 'Forbidden' not in error_str:
                return {
                    'success': False,
                    'error': error_str
                }
            # Se for 403, continua para próxima estratégia
            continue
    
    # Se todas as estratégias falharam
    return {
        'success': False,
        'error': f'Erro após tentar todas as estratégias. Último erro: {last_error}'
    }

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/info', methods=['POST'])
def get_info():
    try:
        data = request.get_json() or {}
        url = data.get('url', '')
        
        if not url:
            return jsonify({'error': 'URL não fornecida'}), 400
        
        info = get_video_info(url)
        return jsonify(info)
    except Exception as e:
        return jsonify({'error': f'Erro ao processar requisição: {str(e)}'}), 500

@app.route('/api/download', methods=['POST'])
def download():
    data = request.get_json()
    url = data.get('url', '')
    quality = data.get('quality', 'best')
    is_playlist = data.get('is_playlist', False)
    download_subtitles = data.get('download_subtitles', False)
    
    if not url:
        return jsonify({'error': 'URL não fornecida'}), 400
    
    try:
        result = download_video(url, quality, is_playlist, download_subtitles)
        
        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/download-file/<path:filename>')
def download_file(filename):
    # Suporta arquivos em subpastas (para playlists)
    file_path = DOWNLOAD_FOLDER / filename
    # Verifica se o arquivo está dentro da pasta de downloads (segurança)
    try:
        file_path.resolve().relative_to(DOWNLOAD_FOLDER.resolve())
    except ValueError:
        return jsonify({'error': 'Acesso negado'}), 403
    
    if file_path.exists() and file_path.is_file():
        return send_file(str(file_path), as_attachment=True)
    return jsonify({'error': 'Arquivo não encontrado'}), 404

@app.route('/api/download-subtitles', methods=['POST'])
def download_subtitles_only():
    """Baixa apenas as legendas de um vídeo já baixado"""
    data = request.get_json()
    video_url = data.get('url', '')
    video_filename = data.get('filename', '')
    
    if not video_url:
        return jsonify({'error': 'URL do vídeo não fornecida'}), 400
    
    try:
        # Encontra o arquivo de vídeo
        video_path = None
        if video_filename:
            # Procura o arquivo na pasta de downloads
            for file in DOWNLOAD_FOLDER.rglob(video_filename):
                if file.is_file() and file.suffix in ['.mp4', '.webm', '.mkv', '.m4a']:
                    video_path = file
                    break
        
        if not video_path:
            return jsonify({'error': 'Arquivo de vídeo não encontrado'}), 404
        
        # Define o caminho para a legenda (mesmo nome do vídeo, extensão .vtt)
        base_name = video_path.stem
        subtitle_path = video_path.parent / f"{base_name}.%(lang)s.vtt"
        
        ydl_opts = {
            **get_common_opts(),
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitleslangs': ['pt', 'pt-BR', 'pt-PT'],
            'subtitlesformat': 'vtt',
            'skip_download': True,  # Não baixa o vídeo, apenas legendas
            'outtmpl': str(subtitle_path),
            'quiet': False,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            
            # Verifica se a legenda foi baixada
            downloaded_subtitles = []
            for lang in ['pt', 'pt-BR', 'pt-PT']:
                subtitle_file = video_path.parent / f"{base_name}.{lang}.vtt"
                if subtitle_file.exists():
                    downloaded_subtitles.append({
                        'filename': subtitle_file.name,
                        'path': str(subtitle_file),
                        'lang': lang
                    })
            
            if downloaded_subtitles:
                return jsonify({
                    'success': True,
                    'subtitles': downloaded_subtitles,
                    'count': len(downloaded_subtitles)
                })
            else:
                return jsonify({
                    'success': False,
                    'error': 'Legendas em português não disponíveis para este vídeo'
                }), 400
                
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/transcribe-video', methods=['POST'])
def transcribe_video():
    """Transcreve um vídeo usando Whisper"""
    data = request.get_json()
    video_filename = data.get('filename', '')
    model_size = data.get('model', 'base')  # tiny, base, small, medium, large
    
    if not video_filename:
        return jsonify({'error': 'Nome do arquivo não fornecido'}), 400
    
    try:
        # Encontra o arquivo de vídeo
        video_path = None
        for file in DOWNLOAD_FOLDER.rglob(video_filename):
            if file.is_file() and file.suffix in ['.mp4', '.webm', '.mkv', '.m4a', '.mp3']:
                video_path = file
                break
        
        if not video_path:
            return jsonify({'error': 'Arquivo de vídeo não encontrado'}), 404
        
        # Verifica se já existe transcrição
        transcript_path = video_path.parent / f"{video_path.stem}_whisper.txt"
        if transcript_path.exists():
            return jsonify({
                'success': True,
                'message': 'Transcrição já existe',
                'filename': transcript_path.name,
                'path': str(transcript_path),
                'text': transcript_path.read_text(encoding='utf-8')[:500] + '...' if transcript_path.stat().st_size > 500 else transcript_path.read_text(encoding='utf-8')
            })
        
        # Carrega o modelo Whisper
        print(f"Carregando modelo Whisper: {model_size}")
        model = whisper.load_model(model_size)
        
        # Encontra o ffmpeg
        ffmpeg_path = shutil.which('ffmpeg')
        if not ffmpeg_path:
            return jsonify({
                'success': False,
                'error': 'ffmpeg não encontrado. Por favor, instale o ffmpeg.'
            }), 400
        
        # Extrai áudio do vídeo se necessário
        audio_path = None
        if video_path.suffix in ['.mp4', '.webm', '.mkv']:
            # Precisa extrair áudio
            audio_path = video_path.parent / f"{video_path.stem}_temp_audio.wav"
            print(f"Extraindo áudio de {video_path.name}...")
            result = subprocess.run([
                ffmpeg_path, '-i', str(video_path),
                '-ar', '16000',  # Taxa de amostragem para Whisper
                '-ac', '1',  # Mono
                '-y',  # Sobrescrever se existir
                str(audio_path)
            ], capture_output=True, check=True)
        else:
            # Já é um arquivo de áudio
            audio_path = video_path
        
        # Transcreve o áudio
        print(f"Transcrevendo {audio_path.name}...")
        result = model.transcribe(
            str(audio_path),
            language='pt',  # Português
            task='transcribe'
        )
        
        # Salva a transcrição em texto
        transcript_text = result['text']
        transcript_path.write_text(transcript_text, encoding='utf-8')
        
        # Salva também em formato VTT para uso com timeline
        vtt_path = video_path.parent / f"{video_path.stem}.pt.vtt"
        whisper_result_to_vtt(result, vtt_path)
        
        # Remove arquivo temporário de áudio se foi criado
        if audio_path != video_path and audio_path.exists():
            audio_path.unlink()
        
        return jsonify({
            'success': True,
            'message': 'Transcrição concluída',
            'filename': transcript_path.name,
            'vtt_filename': vtt_path.name,
            'path': str(transcript_path),
            'vtt_path': str(vtt_path),
            'text': transcript_text[:1000] + '...' if len(transcript_text) > 1000 else transcript_text,
            'full_length': len(transcript_text)
        })
        
    except subprocess.CalledProcessError as e:
        return jsonify({
            'success': False,
            'error': f'Erro ao extrair áudio: {e.stderr.decode() if e.stderr else str(e)}'
        }), 400
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/api/list-downloads')
def list_downloads():
    """Lista todos os vídeos e transcrições baixados"""
    files = []
    # Lista arquivos na pasta principal
    for file in DOWNLOAD_FOLDER.iterdir():
        if file.is_file() and file.suffix in ['.mp4', '.webm', '.mkv', '.m4a', '.mp3', '.vtt', '.txt']:
            file_type = 'subtitle' if file.suffix == '.vtt' else ('transcript' if file.suffix == '.txt' and '_whisper' in file.name else 'video')
            files.append({
                'name': file.name,
                'size': file.stat().st_size,
                'path': str(file),
                'type': file_type
            })
    
    # Lista arquivos em subpastas (playlists e reels)
    for subfolder in DOWNLOAD_FOLDER.iterdir():
        if subfolder.is_dir():
            # Se for pasta de reels, marca como reel
            is_reels_folder = subfolder.name.endswith('_reels')
            for file in subfolder.iterdir():
                if file.is_file() and file.suffix in ['.mp4', '.webm', '.mkv', '.m4a', '.mp3', '.vtt', '.txt']:
                    if is_reels_folder:
                        file_type = 'reel'
                    else:
                        file_type = 'subtitle' if file.suffix == '.vtt' else ('transcript' if file.suffix == '.txt' and '_whisper' in file.name else 'video')
                    files.append({
                        'name': f"{subfolder.name}/{file.name}",
                        'size': file.stat().st_size,
                        'path': str(file),
                        'type': file_type
                    })
    
    return jsonify({'files': files})

@app.route('/api/list-courses')
def list_courses():
    try:
        courses = list_course_directories()
        return jsonify({'success': True, 'courses': courses})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/course-videos', methods=['POST'])
def course_videos():
    data = request.get_json()
    course_name = data.get('course')
    if not course_name:
        return jsonify({'success': False, 'error': 'Curso não informado'}), 400
    try:
        course_path = resolve_course_path(course_name)
        videos = gather_course_videos(course_path)
        return jsonify({
            'success': True,
            'course': course_name,
            'videos': videos,
            'lessons_folder': LESSONS_FOLDER_NAME,
            'lessons_exists': (course_path / LESSONS_FOLDER_NAME).exists()
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/video-timeline', methods=['POST'])
def video_timeline():
    data = request.get_json()
    course_name = data.get('course')
    filename = data.get('filename')
    if not course_name or not filename:
        return jsonify({'success': False, 'error': 'Curso e vídeo são obrigatórios'}), 400
    try:
        _, video_path = resolve_video_path(course_name, filename)
        subtitle_path = find_subtitle_for_video(video_path)
        if not subtitle_path:
            return jsonify({
                'success': False,
                'error': 'Nenhum arquivo de legenda encontrado para este vídeo. Baixe ou transcreva primeiro.'
            }), 404
        segments = parse_vtt_file(subtitle_path)
        if not segments:
            return jsonify({
                'success': False,
                'error': 'Não foi possível extrair a transcrição para gerar a linha do tempo.'
            }), 400
        formatted_segments = [
            {
                'start_seconds': round(seg['start'], 2),
                'end_seconds': round(seg['end'], 2),
                'start': seconds_to_hhmmss(seg['start']),
                'end': seconds_to_hhmmss(seg['end']),
                'text': seg['text']
            }
            for seg in segments
        ]
        return jsonify({
            'success': True,
            'segments': formatted_segments,
            'subtitle': subtitle_path.name,
            'duration': get_video_duration(video_path)
        })
    except (ValueError, FileNotFoundError) as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': f'Erro ao gerar linha do tempo: {e}'}), 400

@app.route('/api/create-lessons', methods=['POST'])
def create_lessons():
    data = request.get_json()
    course_name = data.get('course')
    filename = data.get('filename')
    lessons = data.get('lessons', [])
    if not course_name or not filename:
        return jsonify({'success': False, 'error': 'Curso e vídeo são obrigatórios'}), 400
    if not lessons:
        return jsonify({'success': False, 'error': 'Nenhuma aula foi enviada'}), 400
    ffmpeg_path = shutil.which('ffmpeg')
    if not ffmpeg_path:
        return jsonify({'success': False, 'error': 'ffmpeg não encontrado no sistema'}), 400
    try:
        course_path, video_path = resolve_video_path(course_name, filename)
        lessons_folder = course_path / LESSONS_FOLDER_NAME
        lessons_folder.mkdir(exist_ok=True)
        existing_count = len([
            f for f in lessons_folder.glob('*')
            if f.is_file() and f.suffix in VIDEO_EXTENSIONS
        ])
        sequence = existing_count + 1
        created_lessons = []
        for lesson in lessons:
            title = lesson.get('title', f'Aula {sequence}')
            start = lesson.get('start')
            end = lesson.get('end')
            if not start or not end:
                raise ValueError(f'Defina início e fim para a aula "{title}"')
            start_seconds = hhmmss_to_seconds(start)
            end_seconds = hhmmss_to_seconds(end)
            if end_seconds <= start_seconds:
                raise ValueError(f'O fim da aula "{title}" deve ser maior que o início')
            duration = round(end_seconds - start_seconds, 2)
            safe_title = sanitize_filename(title)
            output_filename = f"{sequence:02d} - {safe_title}{video_path.suffix}"
            clip_path = lessons_folder / output_filename
            cmd = [
                ffmpeg_path,
                '-ss', str(start_seconds),
                '-i', str(video_path),
                '-t', str(duration),
                '-c', 'copy',
                '-avoid_negative_ts', 'make_zero',
                '-y',
                str(clip_path)
            ]
            try:
                subprocess.run(cmd, capture_output=True, check=True)
            except subprocess.CalledProcessError as e:
                raise RuntimeError(f'Erro ao criar aula "{title}": {e.stderr.decode() if e.stderr else str(e)}')
            created_lessons.append({
                'title': title,
                'filename': output_filename,
                'duration': duration
            })
            sequence += 1
        return jsonify({
            'success': True,
            'message': f'{len(created_lessons)} aulas criadas em "{LESSONS_FOLDER_NAME}"',
            'lessons_folder': LESSONS_FOLDER_NAME,
            'created': created_lessons
        })
    except (ValueError, FileNotFoundError) as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': f'Erro ao criar aulas: {e}'}), 400


def parse_vtt_file(vtt_path):
    """Parseia um arquivo VTT e retorna lista de segmentos com timestamps"""
    segments = []
    with open(vtt_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Regex para capturar timestamps e texto
    pattern = r'(\d{2}:\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}\.\d{3})\s*\n(.*?)(?=\n\d{2}:\d{2}:\d{2}|$)'
    matches = re.finditer(pattern, content, re.DOTALL | re.MULTILINE)
    
    for match in matches:
        start_time = match.group(1)
        end_time = match.group(2)
        text = match.group(3).strip().replace('\n', ' ')
        
        # Converte tempo para segundos
        def time_to_seconds(time_str):
            parts = time_str.split(':')
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = float(parts[2])
            return hours * 3600 + minutes * 60 + seconds
        
        segments.append({
            'start': time_to_seconds(start_time),
            'end': time_to_seconds(end_time),
            'text': text,
            'duration': time_to_seconds(end_time) - time_to_seconds(start_time)
        })
    
    return segments

def analyze_viral_moments(segments, min_duration=15, max_duration=60):
    """Analisa segmentos e identifica momentos virais usando heurísticas"""
    viral_keywords = [
        'incrível', 'surpreendente', 'você sabia', 'dica', 'segredo',
        'nunca mais', 'pare de', 'como fazer', 'tutorial', 'passo a passo',
        'atenção', 'importante', 'cuidado', 'alerta', 'não faça',
        'melhor', 'pior', 'top', 'ranking', 'lista',
        'mistério', 'revelação', 'descoberta', 'novidade',
        'truque', 'hack', 'macete', 'jeito fácil',
        'pergunta', 'resposta', 'explicação', 'entenda',
        'motivação', 'inspiração', 'sucesso', 'conquista',
        'erro', 'evite', 'não cometa', 'cuidado com'
    ]
    
    # Palavras que indicam início de tópico importante
    topic_starters = ['olha só', 'sabe o que', 'quer saber', 'vou te mostrar',
                     'preste atenção', 'escuta isso', 'imagina', 'pensa comigo']
    
    viral_moments = []
    
    # Agrupa segmentos consecutivos
    current_group = []
    current_start = None
    current_text = []
    
    for i, segment in enumerate(segments):
        text_lower = segment['text'].lower()
        
        # Verifica se tem palavras-chave virais
        has_viral_keyword = any(keyword in text_lower for keyword in viral_keywords)
        has_topic_starter = any(starter in text_lower for starter in topic_starters)
        
        # Pontuação de viralidade
        score = 0
        if has_viral_keyword:
            score += 2
        if has_topic_starter:
            score += 3
        if '?' in segment['text']:  # Perguntas são engajadoras
            score += 1
        if len(segment['text']) > 50:  # Conteúdo mais completo
            score += 1
        if segment['duration'] > 3:  # Momento mais longo pode ser importante
            score += 1
        
        # Se tem pontuação alta ou é início de tópico, adiciona ao grupo
        if score >= 2 or has_topic_starter:
            if current_start is None:
                current_start = segment['start']
            current_group.append(segment)
            current_text.append(segment['text'])
        else:
            # Finaliza grupo se tiver duração adequada
            if current_group and current_start is not None:
                group_duration = current_group[-1]['end'] - current_start
                if min_duration <= group_duration <= max_duration:
                    viral_moments.append({
                        'start': current_start,
                        'end': current_group[-1]['end'],
                        'duration': group_duration,
                        'text': ' '.join(current_text),
                        'score': sum(1 for s in current_group if any(kw in s['text'].lower() for kw in viral_keywords))
                    })
            current_group = []
            current_start = None
            current_text = []
    
    # Finaliza último grupo se existir
    if current_group and current_start is not None:
        group_duration = current_group[-1]['end'] - current_start
        if min_duration <= group_duration <= max_duration:
            viral_moments.append({
                'start': current_start,
                'end': current_group[-1]['end'],
                'duration': group_duration,
                'text': ' '.join(current_text),
                'score': sum(1 for s in current_group if any(kw in s['text'].lower() for kw in viral_keywords))
            })
    
    # Ordena por score e retorna top momentos
    viral_moments.sort(key=lambda x: x['score'], reverse=True)
    return viral_moments[:10]  # Retorna top 10 momentos

def create_video_clips(video_path, viral_moments, output_folder):
    """Cria cortes de vídeo usando ffmpeg"""
    ffmpeg_path = shutil.which('ffmpeg')
    if not ffmpeg_path:
        raise Exception('ffmpeg não encontrado')
    
    clips = []
    output_folder.mkdir(exist_ok=True)
    
    for i, moment in enumerate(viral_moments, 1):
        start_time = moment['start']
        duration = moment['duration']
        
        # Nome do arquivo
        clip_name = f"clip_{i:02d}_{int(start_time)}s.mp4"
        clip_path = output_folder / clip_name
        
        # Comando ffmpeg para cortar
        cmd = [
            ffmpeg_path,
            '-i', str(video_path),
            '-ss', str(start_time),
            '-t', str(duration),
            '-c', 'copy',  # Copy codec para ser mais rápido
            '-avoid_negative_ts', 'make_zero',
            '-y',
            str(clip_path)
        ]
        
        try:
            subprocess.run(cmd, capture_output=True, check=True)
            clips.append({
                'filename': clip_name,
                'path': str(clip_path),
                'start': start_time,
                'duration': duration,
                'text': moment['text'][:100] + '...' if len(moment['text']) > 100 else moment['text']
            })
        except subprocess.CalledProcessError as e:
            print(f"Erro ao criar clip {i}: {e.stderr.decode() if e.stderr else str(e)}")
            continue
    
    return clips

def sanitize_filename(name):
    """Sanitiza nomes para uso em arquivos"""
    sanitized = re.sub(r'[^A-Za-z0-9 _\-]+', '', name).strip()
    return sanitized or 'aula'

def whisper_result_to_vtt(whisper_result, output_path):
    """Converte resultado do Whisper para formato VTT"""
    vtt_content = "WEBVTT\n\n"
    
    for segment in whisper_result.get('segments', []):
        start = segment.get('start', 0)
        end = segment.get('end', 0)
        text = segment.get('text', '').strip()
        
        if not text:
            continue
        
        # Formata timestamps no formato VTT (HH:MM:SS.mmm)
        def format_timestamp(seconds):
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = seconds % 60
            return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"
        
        vtt_content += f"{format_timestamp(start)} --> {format_timestamp(end)}\n"
        vtt_content += f"{text}\n\n"
    
    output_path.write_text(vtt_content, encoding='utf-8')
    return output_path

def hhmmss_to_seconds(timestamp):
    """Converte string hh:mm:ss(.ms) para segundos"""
    if not timestamp:
        raise ValueError('Timestamp vazio')
    parts = timestamp.strip().split(':')
    parts = [p.strip() for p in parts if p.strip() != '']
    if len(parts) == 1:
        seconds = float(parts[0])
    elif len(parts) == 2:
        minutes = int(parts[0])
        seconds = float(parts[1])
        seconds += minutes * 60
    elif len(parts) == 3:
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = float(parts[2])
        seconds += minutes * 60 + hours * 3600
    else:
        raise ValueError('Formato de tempo inválido. Use HH:MM:SS')
    return round(seconds, 3)

def seconds_to_hhmmss(seconds):
    """Converte segundos em string HH:MM:SS"""
    seconds = float(seconds)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:06.3f}".rstrip('0').rstrip('.')
    return f"{minutes:02d}:{secs:05.2f}".rstrip('0').rstrip('.')

def resolve_course_path(course_name):
    """Valida e retorna caminho completo do curso"""
    root_path = DOWNLOAD_FOLDER.resolve()
    course_path = (root_path / course_name).resolve()
    try:
        course_path.relative_to(root_path)
    except ValueError:
        raise ValueError('Curso inválido')
    if not course_path.exists() or not course_path.is_dir():
        raise FileNotFoundError('Pasta do curso não encontrada')
    return course_path

def list_course_directories():
    """Retorna diretórios considerados cursos"""
    courses = []
    for folder in DOWNLOAD_FOLDER.iterdir():
        if folder.is_dir() and not folder.name.endswith('_reels'):
            video_files = list(folder.rglob('*'))
            video_files = [f for f in video_files if f.is_file() and f.suffix in VIDEO_EXTENSIONS]
            if video_files:
                lessons_folder = folder / LESSONS_FOLDER_NAME
                courses.append({
                    'name': folder.name,
                    'video_count': len(video_files),
                    'has_lessons': lessons_folder.exists(),
                    'lessons_count': len(list(lessons_folder.glob('*'))) if lessons_folder.exists() else 0
                })
    courses.sort(key=lambda c: c['name'].lower())
    return courses

def get_video_duration(video_path):
    """Obtém duração do vídeo usando ffprobe"""
    ffprobe_path = shutil.which('ffprobe')
    if not ffprobe_path:
        return None
    try:
        result = subprocess.run(
            [
                ffprobe_path,
                '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                str(video_path)
            ],
            capture_output=True,
            text=True,
            check=True
        )
        duration = float(result.stdout.strip())
        return round(duration, 2)
    except Exception:
        return None

def find_subtitle_for_video(video_path):
    """Localiza arquivo de legenda correspondente a um vídeo"""
    base_name = video_path.stem
    for lang in SUBTITLE_LANGS:
        subtitle_path = video_path.parent / f"{base_name}.{lang}.vtt"
        if subtitle_path.exists():
            return subtitle_path
    # fallback: qualquer vtt
    generic_subtitle = video_path.parent / f"{base_name}.vtt"
    if generic_subtitle.exists():
        return generic_subtitle
    return None

def gather_course_videos(course_path):
    videos = []
    for file in course_path.iterdir():
        if file.is_file() and file.suffix in VIDEO_EXTENSIONS:
            duration = get_video_duration(file)
            subtitle = find_subtitle_for_video(file)
            videos.append({
                'name': file.name,
                'size': file.stat().st_size,
                'duration': duration,
                'has_subtitles': subtitle is not None
            })
    videos.sort(key=lambda v: v['name'].lower())
    return videos

def resolve_video_path(course_name, filename):
    """Retorna caminho absoluto do vídeo dentro do curso"""
    course_path = resolve_course_path(course_name)
    video_path = (course_path / filename).resolve()
    try:
        video_path.relative_to(course_path)
    except ValueError:
        raise ValueError('Arquivo inválido')
    if not video_path.exists() or not video_path.is_file():
        raise FileNotFoundError('Arquivo de vídeo não encontrado')
    if video_path.suffix not in VIDEO_EXTENSIONS:
        raise ValueError('Arquivo selecionado não é um vídeo suportado')
    return course_path, video_path

@app.route('/api/transcribe-course', methods=['POST'])
def transcribe_course():
    """Transcreve todos os vídeos de um curso que não têm legendas"""
    data = request.get_json()
    course_name = data.get('course', '')
    model_size = data.get('model', 'base')
    force_reprocess = data.get('force', False)
    
    if not course_name:
        return jsonify({'success': False, 'error': 'Nome do curso não fornecido'}), 400
    
    try:
        course_path = resolve_course_path(course_name)
        videos = gather_course_videos(course_path)
        
        # Filtra vídeos sem legendas
        videos_to_transcribe = [
            v for v in videos 
            if not v['has_subtitles'] or force_reprocess
        ]
        
        if not videos_to_transcribe:
            return jsonify({
                'success': True,
                'message': 'Todos os vídeos já têm legendas',
                'processed': 0,
                'total': len(videos)
            })
        
        # Carrega modelo Whisper uma vez
        print(f"Carregando modelo Whisper: {model_size}")
        model = whisper.load_model(model_size)
        
        ffmpeg_path = shutil.which('ffmpeg')
        if not ffmpeg_path:
            return jsonify({
                'success': False,
                'error': 'ffmpeg não encontrado'
            }), 400
        
        processed = []
        errors = []
        
        for video_info in videos_to_transcribe:
            video_path = course_path / video_info['name']
            try:
                # Extrai áudio
                audio_path = course_path / f"{video_path.stem}_temp_audio.wav"
                print(f"Extraindo áudio de {video_path.name}...")
                subprocess.run([
                    ffmpeg_path, '-i', str(video_path),
                    '-ar', '16000',
                    '-ac', '1',
                    '-y',
                    str(audio_path)
                ], capture_output=True, check=True)
                
                # Transcreve
                print(f"Transcrevendo {video_path.name}...")
                result = model.transcribe(
                    str(audio_path),
                    language='pt',
                    task='transcribe'
                )
                
                # Salva VTT
                vtt_path = course_path / f"{video_path.stem}.pt.vtt"
                whisper_result_to_vtt(result, vtt_path)
                
                # Salva texto também
                txt_path = course_path / f"{video_path.stem}_whisper.txt"
                txt_path.write_text(result['text'], encoding='utf-8')
                
                # Remove áudio temporário
                if audio_path.exists():
                    audio_path.unlink()
                
                processed.append({
                    'video': video_info['name'],
                    'vtt_file': vtt_path.name
                })
                
            except Exception as e:
                errors.append({
                    'video': video_info['name'],
                    'error': str(e)
                })
                # Remove áudio temporário em caso de erro
                audio_path = course_path / f"{video_path.stem}_temp_audio.wav"
                if audio_path.exists():
                    audio_path.unlink()
        
        return jsonify({
            'success': True,
            'message': f'{len(processed)} vídeo(s) transcrito(s) com sucesso',
            'processed': len(processed),
            'errors': len(errors),
            'total': len(videos),
            'details': {
                'processed': processed,
                'errors': errors
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/api/transcribe-all-courses', methods=['POST'])
def transcribe_all_courses():
    """Transcreve todos os vídeos de todos os cursos que não têm legendas"""
    data = request.get_json()
    model_size = data.get('model', 'base')
    force_reprocess = data.get('force', False)
    
    try:
        courses = list_course_directories()
        if not courses:
            return jsonify({
                'success': True,
                'message': 'Nenhum curso encontrado',
                'processed': 0
            })
        
        # Carrega modelo Whisper uma vez
        print(f"Carregando modelo Whisper: {model_size}")
        model = whisper.load_model(model_size)
        
        ffmpeg_path = shutil.which('ffmpeg')
        if not ffmpeg_path:
            return jsonify({
                'success': False,
                'error': 'ffmpeg não encontrado'
            }), 400
        
        total_processed = 0
        total_errors = 0
        course_results = []
        
        for course in courses:
            course_path = resolve_course_path(course['name'])
            videos = gather_course_videos(course_path)
            videos_to_transcribe = [
                v for v in videos 
                if not v['has_subtitles'] or force_reprocess
            ]
            
            if not videos_to_transcribe:
                continue
            
            course_processed = 0
            course_errors = []
            
            for video_info in videos_to_transcribe:
                video_path = course_path / video_info['name']
                try:
                    # Extrai áudio
                    audio_path = course_path / f"{video_path.stem}_temp_audio.wav"
                    subprocess.run([
                        ffmpeg_path, '-i', str(video_path),
                        '-ar', '16000',
                        '-ac', '1',
                        '-y',
                        str(audio_path)
                    ], capture_output=True, check=True)
                    
                    # Transcreve
                    result = model.transcribe(
                        str(audio_path),
                        language='pt',
                        task='transcribe'
                    )
                    
                    # Salva VTT
                    vtt_path = course_path / f"{video_path.stem}.pt.vtt"
                    whisper_result_to_vtt(result, vtt_path)
                    
                    # Salva texto
                    txt_path = course_path / f"{video_path.stem}_whisper.txt"
                    txt_path.write_text(result['text'], encoding='utf-8')
                    
                    # Remove áudio temporário
                    if audio_path.exists():
                        audio_path.unlink()
                    
                    course_processed += 1
                    total_processed += 1
                    
                except Exception as e:
                    course_errors.append({
                        'video': video_info['name'],
                        'error': str(e)
                    })
                    total_errors += 1
                    # Remove áudio temporário
                    audio_path = course_path / f"{video_path.stem}_temp_audio.wav"
                    if audio_path.exists():
                        audio_path.unlink()
            
            if course_processed > 0 or course_errors:
                course_results.append({
                    'course': course['name'],
                    'processed': course_processed,
                    'errors': len(course_errors),
                    'error_details': course_errors
                })
        
        return jsonify({
            'success': True,
            'message': f'{total_processed} vídeo(s) transcrito(s) em {len(course_results)} curso(s)',
            'total_processed': total_processed,
            'total_errors': total_errors,
            'courses': course_results
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/api/create-reels', methods=['POST'])
def create_reels():
    """Cria cortes virais de um vídeo usando legendas"""
    data = request.get_json()
    video_filename = data.get('filename', '')
    min_duration = data.get('min_duration', 15)
    max_duration = data.get('max_duration', 60)
    
    if not video_filename:
        return jsonify({'error': 'Nome do arquivo não fornecido'}), 400
    
    try:
        # Encontra o arquivo de vídeo
        video_path = None
        for file in DOWNLOAD_FOLDER.rglob(video_filename):
            if file.is_file() and file.suffix in ['.mp4', '.webm', '.mkv', '.m4a']:
                video_path = file
                break
        
        if not video_path:
            return jsonify({'error': 'Arquivo de vídeo não encontrado'}), 404
        
        # Procura arquivo de legenda
        subtitle_path = None
        base_name = video_path.stem
        for lang in ['pt', 'pt-BR', 'pt-PT']:
            test_path = video_path.parent / f"{base_name}.{lang}.vtt"
            if test_path.exists():
                subtitle_path = test_path
                break
        
        if not subtitle_path:
            return jsonify({
                'success': False,
                'error': 'Arquivo de legenda não encontrado. Baixe as legendas primeiro.'
            }), 400
        
        # Parseia legendas
        print(f"Parseando legendas de {subtitle_path.name}...")
        segments = parse_vtt_file(subtitle_path)
        
        if not segments:
            return jsonify({
                'success': False,
                'error': 'Não foi possível extrair segmentos das legendas'
            }), 400
        
        # Analisa momentos virais
        print(f"Analisando {len(segments)} segmentos para momentos virais...")
        viral_moments = analyze_viral_moments(segments, min_duration, max_duration)
        
        if not viral_moments:
            return jsonify({
                'success': False,
                'error': 'Nenhum momento viral identificado nas legendas'
            }), 400
        
        # Cria pasta para os cortes
        clips_folder = video_path.parent / f"{base_name}_reels"
        
        # Cria os cortes
        print(f"Criando {len(viral_moments)} cortes...")
        clips = create_video_clips(video_path, viral_moments, clips_folder)
        
        if not clips:
            return jsonify({
                'success': False,
                'error': 'Erro ao criar os cortes de vídeo'
            }), 400
        
        return jsonify({
            'success': True,
            'message': f'{len(clips)} cortes criados com sucesso',
            'clips_folder': clips_folder.name,
            'clips': clips,
            'count': len(clips)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5002)

