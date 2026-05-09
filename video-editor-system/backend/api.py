#!/usr/bin/env python3
"""
Flask API server for video editing system
Provides REST API for video processing
"""

import os
import sys
import json
import uuid
import time
import threading
import unicodedata
import re
import requests as _http
from difflib import SequenceMatcher
import subprocess
from datetime import datetime
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
from werkzeug.exceptions import HTTPException
from pathlib import Path

# Add backend directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main import VideoEditorSystem
from utils import ensure_directory_exists, get_file_size, format_time


# ── Persistent Gemini rate limiter (module-level, survives across requests) ──
#
# Free-tier limit: 10 RPM per key.
# We enforce a MINIMUM INTERVAL of 6.5 s between consecutive calls on the
# same key — this is slightly more than 60/10 = 6 s and prevents bursts.
# With N keys the effective throughput is N × ~9 RPM with zero 429s.
#
# All state is module-level so it persists between back-to-back requests.
# A fresh request never hammers keys that are still cooling down from the
# previous translation job.

_gem_lock: threading.Lock       = threading.Lock()
_gem_last_used:  dict[str, float] = {}   # api_key → time of last dispatched call
_gem_blocked:    dict[str, float] = {}   # api_key → unblock_at (epoch seconds)
_GEM_RPM          = 10
_GEM_MIN_INTERVAL = 60.0 / _GEM_RPM + 0.5   # 6.5 s between calls on same key


def _gem_acquire(keys: list[str]) -> str:
    """Block until a key slot is available; return the chosen key.

    For each key in order:
      1. Skip if blocked by a 429 window.
      2. Skip if used too recently (< _GEM_MIN_INTERVAL ago).
      3. Otherwise claim it: record last-used time and return.

    If no key is ready, sleep EXACTLY until the soonest key becomes
    available (not a fixed poll interval), then retry.
    """
    while True:
        soonest_wait = _GEM_MIN_INTERVAL   # upper bound for sleep
        with _gem_lock:
            now = time.time()
            for key in keys:
                unblock = _gem_blocked.get(key, 0)
                if now < unblock:
                    soonest_wait = min(soonest_wait, unblock - now)
                    continue
                available_at = _gem_last_used.get(key, 0) + _GEM_MIN_INTERVAL
                if now >= available_at:
                    _gem_last_used[key] = now
                    return key
                soonest_wait = min(soonest_wait, available_at - now)
        time.sleep(soonest_wait + 0.05)   # wake up just after the slot opens


def _gem_block(key: str, seconds: int) -> None:
    """Mark key as rate-limited for `seconds` seconds.  Called on 429."""
    with _gem_lock:
        _gem_blocked[key] = time.time() + seconds
        # Also push last_used forward so the interval check honours the block
        _gem_last_used[key] = time.time() + seconds


def _gem_parse_retry(text: str) -> int:
    """Extract retry delay from a Gemini 429 response body.

    Tries all known formats:
      "retryDelay": "13s"               – JSON error details
      retry_delay { seconds: 13 }       – proto-text in message string
      "seconds": 13                     – bare JSON int
      Retry in 13 / retry after 13      – human-readable fallback
    """
    m = (re.search(r'"retryDelay":\s*"(\d+)', text) or
         re.search(r'retry_delay\s*\{[^}]*seconds:\s*(\d+)', text, re.DOTALL) or
         re.search(r'"seconds":\s*(\d+)', text) or
         re.search(r'(?:retry in|retry after)\s*(\d+)', text, re.IGNORECASE) or
         re.search(r'(\d+)\s*s(?:ec|econds)?\b', text))
    return min(int(m.group(1)) + 2, 90) if m else 20


def _gem_key_label(key: str) -> str:
    """Return a short, safe display label for a Gemini API key.
    Shows first 4 + last 4 chars so you can tell keys apart in the terminal
    without exposing the full secret.  Example: AIza…Xk7m
    """
    if not key or len(key) < 10:
        return '???'
    return f'{key[:4]}…{key[-4:]}'


def _gem_all_keys() -> list[str]:
    """Return every unique, non-empty Gemini API key from Config (deduplicated).

    Priority: dedicated translate keys first (so they're preferred over shared
    keys); then shared keys so the user gets maximum throughput from whatever
    they've configured in Settings.
    """
    from config import Config
    raw = [
        Config.get_gemini_translate_1_key(),
        Config.get_gemini_translate_2_key(),
        Config.get_gemini_api_key(),
        Config.get_director_gemini_api_key(),
        Config.get_gemini_image_api_key(),
    ]
    return list(dict.fromkeys(k for k in raw if k))


def _gem_call_sdk(keys: list[str], model_name: str,
                  generation_config: dict, prompt_text: str,
                  retries: int = 6) -> str:
    """Call Gemini via the Python SDK with full rate-limiting and 429 retry.

    Uses _gem_acquire() to enforce the per-key minimum interval so calls are
    naturally spaced and never burst.  On ResourceExhausted (429) the key is
    blocked via _gem_block() and the call is retried with a different key.

    Returns the response text string.
    """
    import google.generativeai as genai
    try:
        from google.api_core.exceptions import ResourceExhausted
    except ImportError:
        ResourceExhausted = Exception  # safety fallback

    last_err = None
    for attempt in range(retries):
        key = _gem_acquire(keys)
        try:
            genai.configure(api_key=key)
            model = genai.GenerativeModel(
                model_name=model_name,
                generation_config=generation_config,
            )
            response = model.generate_content(prompt_text)
            return response.text
        except ResourceExhausted as e:
            err_str = str(e)
            delay = _gem_parse_retry(err_str)
            print(f'   ⏳ 429 on key …{key[-6:]} — blocking {delay}s '
                  f'(attempt {attempt + 1}/{retries})')
            _gem_block(key, delay)
            last_err = e
        except Exception:
            raise
    raise RuntimeError(f'Gemini SDK: all {retries} retries exhausted. '
                       f'Last error: {last_err}')


# Initialize Flask app
app = Flask(__name__, static_folder='../frontend', static_url_path='')
CORS(app)  # Enable CORS for frontend


@app.errorhandler(Exception)
def handle_unexpected_error(err):
    """Ensure API endpoints always return JSON even on unexpected exceptions."""
    if request.path.startswith('/api/'):
        if isinstance(err, HTTPException):
            return jsonify({
                'success': False,
                'error': err.description or str(err)
            }), err.code or 500
        return jsonify({
            'success': False,
            'error': str(err)
        }), 500
    raise err

# Configuration
UPLOAD_FOLDER = 'uploads'
TEMP_FOLDER = 'temp'
OUTPUT_FOLDER = 'output'
MAX_UPLOAD_SIZE = 5 * 1024 * 1024 * 1024  # 5GB

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_UPLOAD_SIZE

# Ensure directories exist
ensure_directory_exists(UPLOAD_FOLDER)
ensure_directory_exists(TEMP_FOLDER)
ensure_directory_exists(OUTPUT_FOLDER)

# Allowed file extensions
ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'mov', 'avi', 'mkv', 'webm', 'flv'}
ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'jfif', 'png', 'bmp', 'gif', 'tiff', 'webp'}
ALLOWED_AUDIO_EXTENSIONS = {'mp3', 'wav', 'aac', 'm4a', 'ogg', 'flac'}

# Global processing state (in production, use Redis or database)
processing_jobs = {}


def allowed_file(filename, file_type):
    """Check if file extension is allowed"""
    if '.' not in filename:
        return False

    ext = filename.rsplit('.', 1)[1].lower()

    if file_type == 'video':
        return ext in ALLOWED_VIDEO_EXTENSIONS
    elif file_type == 'image':
        return ext in ALLOWED_IMAGE_EXTENSIONS
    elif file_type == 'audio':
        return ext in ALLOWED_AUDIO_EXTENSIONS

    return False


@app.route('/')
def index():
    """Serve frontend"""
    return send_from_directory(app.static_folder, 'index.html')


@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint with FFmpeg verification"""
    # Check FFmpeg availability
    ffmpeg_available = False
    ffmpeg_version = 'not installed'
    ffprobe_available = False

    try:
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            ffmpeg_available = True
            # Extract version from first line
            first_line = result.stdout.split('\n')[0]
            ffmpeg_version = first_line.split(' ')[2] if len(first_line.split(' ')) > 2 else 'unknown'
    except:
        pass

    try:
        result = subprocess.run(['ffprobe', '-version'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            ffprobe_available = True
    except:
        pass

    status = 'healthy' if (ffmpeg_available and ffprobe_available) else 'degraded'

    return jsonify({
        'status': status,
        'service': 'Video Editor API',
        'version': '1.0.0',
        'ffmpeg': {
            'available': ffmpeg_available,
            'version': ffmpeg_version
        },
        'ffprobe': {
            'available': ffprobe_available
        }
    })


@app.route('/api/upload', methods=['POST'])
def upload_file():
    """
    Upload a file (video, image, or audio)

    Request:
        - file: File data
        - type: 'video', 'image', or 'audio'

    Response:
        {
            'success': true,
            'file_id': 'unique-id',
            'filename': 'uploaded_filename.mp4',
            'size': '1.5 MB',
            'type': 'video'
        }
    """
    try:
        # Check if file is in request
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400

        file = request.files['file']

        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        file_type = request.form.get('type', '').lower()

        if file_type not in ['video', 'image', 'audio']:
            return jsonify({'error': 'Invalid file type. Must be video, image, or audio'}), 400

        # Validate file extension
        if not allowed_file(file.filename, file_type):
            return jsonify({'error': f'Invalid file format for {file_type}'}), 400

        # Generate unique file ID
        file_id = str(uuid.uuid4())
        filename = secure_filename(file.filename)
        file_ext = filename.rsplit('.', 1)[1].lower()
        unique_filename = f"{file_id}.{file_ext}"

        # Save file
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(file_path)

        # Get file info
        file_size = get_file_size(file_path)

        return jsonify({
            'success': True,
            'file_id': file_id,
            'filename': filename,
            'unique_filename': unique_filename,
            'path': file_path,
            'size': file_size,
            'type': file_type
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# Chunked upload — supports very large files (5GB, 12GB, …) by assembling
# client-side chunks. Each chunk is small enough to fit under MAX_CONTENT_LENGTH
# and keeps memory pressure low.
# ─────────────────────────────────────────────────────────────────────────────
CHUNK_UPLOAD_DIR = os.path.join(TEMP_FOLDER, 'chunks')
ensure_directory_exists(CHUNK_UPLOAD_DIR)


@app.route('/api/upload/chunk', methods=['POST'])
def upload_chunk():
    """
    Receive one chunk of a large upload. When the final chunk arrives,
    assemble all chunks into a single file under UPLOAD_FOLDER and respond
    with the same shape as /api/upload.

    Form fields:
        upload_id:    opaque id chosen by client (8..64 [A-Za-z0-9_-])
        chunk_index:  int, 0-based
        total_chunks: int
        filename:     original file name (used for extension only)
        type:         'video' | 'image' | 'audio'
        file:         chunk bytes
    """
    try:
        upload_id = (request.form.get('upload_id') or '').strip()
        if not re.match(r'^[A-Za-z0-9_-]{8,64}$', upload_id):
            return jsonify({'error': 'invalid upload_id'}), 400

        try:
            chunk_index = int(request.form.get('chunk_index', -1))
            total_chunks = int(request.form.get('total_chunks', 0))
        except ValueError:
            return jsonify({'error': 'chunk_index/total_chunks must be integers'}), 400

        if chunk_index < 0 or total_chunks <= 0 or chunk_index >= total_chunks:
            return jsonify({'error': 'invalid chunk_index/total_chunks'}), 400

        filename = request.form.get('filename', '')
        file_type = (request.form.get('type') or '').lower()
        if file_type not in ('video', 'image', 'audio'):
            return jsonify({'error': 'Invalid file type'}), 400
        if not allowed_file(filename, file_type):
            return jsonify({'error': f'Invalid file format for {file_type}'}), 400

        if 'file' not in request.files:
            return jsonify({'error': 'No chunk data'}), 400
        chunk = request.files['file']

        chunk_dir = os.path.join(CHUNK_UPLOAD_DIR, upload_id)
        ensure_directory_exists(chunk_dir)
        chunk_path = os.path.join(chunk_dir, f'chunk_{chunk_index:06d}.part')
        chunk.save(chunk_path)

        received = sorted(f for f in os.listdir(chunk_dir) if f.startswith('chunk_'))
        if len(received) < total_chunks:
            return jsonify({
                'success': True,
                'complete': False,
                'chunks_received': len(received),
                'total_chunks': total_chunks,
            })

        # All chunks present — assemble
        file_id = str(uuid.uuid4())
        sfn = secure_filename(filename) or f'{file_id}.bin'
        file_ext = sfn.rsplit('.', 1)[1].lower() if '.' in sfn else 'bin'
        unique_filename = f'{file_id}.{file_ext}'
        final_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)

        BUF = 4 * 1024 * 1024  # 4 MB streaming buffer — keeps RAM low
        with open(final_path, 'wb') as outf:
            for name in received:
                p = os.path.join(chunk_dir, name)
                with open(p, 'rb') as inf:
                    while True:
                        buf = inf.read(BUF)
                        if not buf:
                            break
                        outf.write(buf)

        for name in received:
            try: os.remove(os.path.join(chunk_dir, name))
            except Exception: pass
        try: os.rmdir(chunk_dir)
        except Exception: pass

        return jsonify({
            'success': True,
            'complete': True,
            'file_id': file_id,
            'filename': sfn,
            'unique_filename': unique_filename,
            'path': final_path,
            'size': get_file_size(final_path),
            'type': file_type,
            'chunks_received': len(received),
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/upload/chunk-abort', methods=['POST'])
def upload_chunk_abort():
    """Cancel an in-progress chunked upload and remove any partial chunks."""
    try:
        upload_id = (request.form.get('upload_id') or '').strip()
        if not re.match(r'^[A-Za-z0-9_-]{8,64}$', upload_id):
            return jsonify({'error': 'invalid upload_id'}), 400
        chunk_dir = os.path.join(CHUNK_UPLOAD_DIR, upload_id)
        if os.path.isdir(chunk_dir):
            for name in os.listdir(chunk_dir):
                try: os.remove(os.path.join(chunk_dir, name))
                except Exception: pass
            try: os.rmdir(chunk_dir)
            except Exception: pass
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/process', methods=['POST'])
def process_video():
    """
    Process video project - ULTRA OPTIMIZED (No Captions)

    Request JSON:
        {
            'visual_media': [
                {'rank': 1, 'type': 'video', 'file_id': '...'},
                {'rank': 2, 'type': 'image', 'file_id': '...'}
            ],
            'audio_files': [
                {'rank': 1, 'file_id': '...'}
            ],
            'output_filename': 'my_video.mp4',  # optional
            'mute_videos': false  # optional - if true, removes audio from uploaded videos
        }

    Response:
        {
            'success': true,
            'job_id': 'unique-job-id',
            'status': 'processing'
        }
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'No data provided'}), 400

        visual_media = data.get('visual_media', [])
        audio_files = data.get('audio_files', [])
        output_filename = data.get('output_filename')
        mute_videos = data.get('mute_videos', False)

        if not visual_media:
            return jsonify({'error': 'No visual media provided'}), 400

        if not audio_files:
            return jsonify({'error': 'No audio files provided'}), 400

        # Convert file IDs to paths
        for item in visual_media:
            file_id = item.get('file_id')
            if not file_id:
                return jsonify({'error': 'Missing file_id in visual_media'}), 400

            # Find file with this ID
            file_ext = _find_uploaded_file(file_id)
            if not file_ext:
                return jsonify({'error': f'File not found: {file_id}'}), 404

            item['path'] = os.path.join(app.config['UPLOAD_FOLDER'], f"{file_id}.{file_ext}")

        for item in audio_files:
            file_id = item.get('file_id')
            if not file_id:
                return jsonify({'error': 'Missing file_id in audio_files'}), 400

            # Find file with this ID
            file_ext = _find_uploaded_file(file_id)
            if not file_ext:
                return jsonify({'error': f'File not found: {file_id}'}), 404

            item['path'] = os.path.join(app.config['UPLOAD_FOLDER'], f"{file_id}.{file_ext}")

        # Generate job ID
        job_id = str(uuid.uuid4())

        # Store job info
        processing_jobs[job_id] = {
            'status': 'processing',
            'progress': 0,
            'message': 'Starting processing...'
        }

        # Process video (in production, use background task queue like Celery)
        try:
            editor = VideoEditorSystem(
                temp_dir=TEMP_FOLDER,
                output_dir=OUTPUT_FOLDER,
                verbose=True
            )

            result = editor.process_video_project(
                visual_media=visual_media,
                audio_files=audio_files,
                output_filename=output_filename,
                mute_videos=mute_videos,
                cleanup_temp=True
            )

            # Update job status
            processing_jobs[job_id] = {
                'status': 'completed',
                'progress': 100,
                'message': 'Processing complete',
                'result': result
            }

            return jsonify({
                'success': True,
                'job_id': job_id,
                'status': 'completed',
                'result': result
            })

        except Exception as e:
            processing_jobs[job_id] = {
                'status': 'failed',
                'progress': 0,
                'message': str(e)
            }

            return jsonify({
                'success': False,
                'job_id': job_id,
                'error': str(e)
            }), 500

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/job/<job_id>', methods=['GET'])
def get_job_status(job_id):
    """
    Get processing job status

    Response:
        {
            'status': 'processing' | 'completed' | 'failed',
            'progress': 0-100,
            'message': '...',
            'result': {...}  # if completed
        }
    """
    if job_id not in processing_jobs:
        return jsonify({'error': 'Job not found'}), 404

    return jsonify(processing_jobs[job_id])


@app.route('/api/download/<path:filename>', methods=['GET'])
def download_file(filename):
    """Download output file with debug logging"""
    try:
        filepath = os.path.join(OUTPUT_FOLDER, filename)

        print(f"\n{'='*60}")
        print(f"📥 DOWNLOAD REQUEST")
        print(f"{'='*60}")
        print(f"Filename: {filename}")
        print(f"Full path: {filepath}")
        print(f"OUTPUT_FOLDER: {OUTPUT_FOLDER}")
        print(f"Current dir: {os.getcwd()}")
        print(f"File exists: {os.path.exists(filepath)}")

        if os.path.exists(filepath):
            file_size = os.path.getsize(filepath)
            print(f"File size: {file_size:,} bytes")
            print(f"File readable: {os.access(filepath, os.R_OK)}")
            print(f"✅ Sending file...")
        else:
            print(f"❌ File not found!")
            # List files in output directory
            if os.path.exists(OUTPUT_FOLDER):
                files = os.listdir(OUTPUT_FOLDER)
                print(f"\nFiles in {OUTPUT_FOLDER}:")
                for f in files:
                    print(f"  - {f}")

        print(f"{'='*60}\n")

        # Determine mimetype based on file extension
        if filename.endswith('.txt'):
            mimetype = 'text/plain'
        elif filename.endswith('.mp4'):
            mimetype = 'video/mp4'
        elif filename.endswith('.mp3'):
            mimetype = 'audio/mpeg'
        elif filename.endswith('.wav'):
            mimetype = 'audio/wav'
        elif filename.endswith('.m4a'):
            mimetype = 'audio/mp4'
        else:
            mimetype = None

        return send_from_directory(
            OUTPUT_FOLDER,
            filename,
            as_attachment=True,
            mimetype=mimetype
        )

    except FileNotFoundError as e:
        print(f"❌ FileNotFoundError: {e}")
        return jsonify({'error': 'File not found'}), 404
    except Exception as e:
        print(f"❌ Download error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/cache/<path:filepath>', methods=['GET'])
def serve_cache_file(filepath):
    """Serve cached files (generated images, etc.)"""
    try:
        cache_base = Path('cache')
        full_path = cache_base / filepath

        # Security: Ensure path doesn't escape cache directory
        if not str(full_path.resolve()).startswith(str(cache_base.resolve())):
            return jsonify({'error': 'Invalid path'}), 403

        if full_path.exists() and full_path.is_file():
            # Determine mimetype
            if filepath.endswith(('.jpg', '.jpeg')):
                mimetype = 'image/jpeg'
            elif filepath.endswith('.png'):
                mimetype = 'image/png'
            elif filepath.endswith('.webp'):
                mimetype = 'image/webp'
            else:
                mimetype = None

            return send_file(str(full_path), mimetype=mimetype)
        else:
            return jsonify({'error': 'File not found'}), 404

    except Exception as e:
        print(f"❌ Cache serve error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/output', methods=['GET'])
@app.route('/output/', methods=['GET'])
def show_output_directory():
    """Show all files in output directory with download links"""
    try:
        from flask import render_template_string

        # Get all files in output directory
        files = []
        output_path = os.path.abspath(OUTPUT_FOLDER)

        if os.path.exists(output_path):
            for filename in os.listdir(output_path):
                filepath = os.path.join(output_path, filename)
                if os.path.isfile(filepath):
                    file_size = os.path.getsize(filepath)
                    file_size_mb = file_size / (1024 * 1024)

                    # Get file modification time
                    import time
                    mtime = os.path.getmtime(filepath)
                    mod_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(mtime))

                    files.append({
                        'name': filename,
                        'size': f"{file_size_mb:.2f} MB",
                        'modified': mod_time,
                        'download_url': f"/api/download/{filename}"
                    })

        # Sort by modification time (newest first)
        files.sort(key=lambda x: x['modified'], reverse=True)

        # HTML template
        html = '''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Output Files - Video Editor System</title>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                * {
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }
                body {
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    padding: 20px;
                }
                .container {
                    max-width: 1200px;
                    margin: 0 auto;
                    background: white;
                    border-radius: 12px;
                    box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                    overflow: hidden;
                }
                .header {
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 30px;
                    text-align: center;
                }
                .header h1 {
                    font-size: 2em;
                    margin-bottom: 10px;
                }
                .header p {
                    opacity: 0.9;
                    font-size: 1.1em;
                }
                .content {
                    padding: 30px;
                }
                .stats {
                    background: #f8f9fa;
                    padding: 20px;
                    border-radius: 8px;
                    margin-bottom: 30px;
                    display: flex;
                    justify-content: space-around;
                    text-align: center;
                }
                .stat-item {
                    flex: 1;
                }
                .stat-value {
                    font-size: 2em;
                    font-weight: bold;
                    color: #667eea;
                }
                .stat-label {
                    color: #666;
                    margin-top: 5px;
                }
                table {
                    width: 100%;
                    border-collapse: collapse;
                    margin-top: 20px;
                }
                th {
                    background: #667eea;
                    color: white;
                    padding: 15px;
                    text-align: left;
                    font-weight: 600;
                    font-size: 0.95em;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                }
                td {
                    padding: 15px;
                    border-bottom: 1px solid #e0e0e0;
                }
                tr:hover {
                    background-color: #f8f9fa;
                }
                tr:last-child td {
                    border-bottom: none;
                }
                .download-btn {
                    background: #667eea;
                    color: white;
                    padding: 8px 20px;
                    border-radius: 6px;
                    text-decoration: none;
                    display: inline-block;
                    transition: all 0.3s;
                    font-weight: 500;
                }
                .download-btn:hover {
                    background: #764ba2;
                    transform: translateY(-2px);
                    box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
                }
                .no-files {
                    text-align: center;
                    padding: 60px 20px;
                    color: #666;
                }
                .no-files-icon {
                    font-size: 4em;
                    margin-bottom: 20px;
                }
                .filename {
                    font-weight: 500;
                    color: #333;
                    font-family: 'Courier New', monospace;
                }
                .back-link {
                    display: inline-block;
                    margin-top: 20px;
                    color: #667eea;
                    text-decoration: none;
                    font-weight: 500;
                }
                .back-link:hover {
                    text-decoration: underline;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📁 Output Files</h1>
                    <p>Video Editor System - Generated Videos</p>
                </div>

                <div class="content">
                    {% if files %}
                    <div class="stats">
                        <div class="stat-item">
                            <div class="stat-value">{{ files|length }}</div>
                            <div class="stat-label">Total Files</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-value">{{ "%.2f"|format(files|sum(attribute='size')|replace(' MB', '')|float) }} MB</div>
                            <div class="stat-label">Total Size</div>
                        </div>
                    </div>

                    <table>
                        <thead>
                            <tr>
                                <th>Filename</th>
                                <th>Size</th>
                                <th>Modified</th>
                                <th>Action</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for file in files %}
                            <tr>
                                <td><span class="filename">{{ file.name }}</span></td>
                                <td>{{ file.size }}</td>
                                <td>{{ file.modified }}</td>
                                <td><a href="{{ file.download_url }}" class="download-btn">📥 Download</a></td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                    {% else %}
                    <div class="no-files">
                        <div class="no-files-icon">📂</div>
                        <h2>No files found</h2>
                        <p>Output directory is empty. Generate some videos to see them here!</p>
                    </div>
                    {% endif %}

                    <a href="/" class="back-link">← Back to Video Editor</a>
                </div>
            </div>
        </body>
        </html>
        '''

        return render_template_string(html, files=files)

    except Exception as e:
        return f"<h1>Error</h1><p>{str(e)}</p>", 500


@app.route('/api/files', methods=['GET'])
def list_uploaded_files():
    """List all uploaded files"""
    try:
        files = []

        for filename in os.listdir(app.config['UPLOAD_FOLDER']):
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

            if os.path.isfile(file_path):
                file_id = filename.rsplit('.', 1)[0]
                file_ext = filename.rsplit('.', 1)[1].lower()

                # Determine file type
                if file_ext in ALLOWED_VIDEO_EXTENSIONS:
                    file_type = 'video'
                elif file_ext in ALLOWED_IMAGE_EXTENSIONS:
                    file_type = 'image'
                elif file_ext in ALLOWED_AUDIO_EXTENSIONS:
                    file_type = 'audio'
                else:
                    continue

                files.append({
                    'file_id': file_id,
                    'filename': filename,
                    'type': file_type,
                    'size': get_file_size(file_path)
                })

        return jsonify({'files': files})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


def _find_uploaded_file(file_id):
    """Find uploaded file by ID and return extension"""
    for filename in os.listdir(app.config['UPLOAD_FOLDER']):
        if filename.startswith(file_id + '.'):
            return filename.rsplit('.', 1)[1].lower()
    return None


# =============================================================================
# AI VIDEO GENERATOR ROUTES
# =============================================================================

@app.route('/api/niches', methods=['GET', 'POST'])
def manage_niches():
    """Get all niches or create new niche"""
    from niche_manager import NicheManager

    try:
        if request.method == 'GET':
            niches = NicheManager.get_all_niches()
            return jsonify({'niches': niches})

        elif request.method == 'POST':
            data = request.get_json()

            if not data:
                return jsonify({'error': 'No data provided'}), 400

            name = data.get('name')
            language = data.get('language')
            writing_guidelines = data.get('writing_guidelines')

            if not name or not language or not writing_guidelines:
                return jsonify({'error': 'Missing required fields: name, language, writing_guidelines'}), 400

            niche = NicheManager.create_niche(name, language, writing_guidelines)

            return jsonify({
                'success': True,
                'niche': niche
            }), 201

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/niches/<niche_id>', methods=['GET', 'PUT', 'DELETE'])
def manage_niche(niche_id):
    """Get, update, or delete specific niche by ID"""
    from niche_manager import NicheManager

    try:
        if request.method == 'GET':
            niche = NicheManager.get_niche(niche_id)

            if not niche:
                return jsonify({'error': 'Niche not found'}), 404

            return jsonify({'niche': niche})

        elif request.method == 'PUT':
            data = request.get_json()
            if not data:
                return jsonify({'error': 'No data provided'}), 400

            name = data.get('name')
            language = data.get('language')
            writing_guidelines = data.get('writing_guidelines')

            updated = NicheManager.update_niche(
                niche_id=niche_id,
                name=name,
                language=language,
                writing_guidelines=writing_guidelines
            )

            if not updated:
                return jsonify({'error': 'Niche not found'}), 404

            return jsonify({'success': True, 'niche': updated})

        elif request.method == 'DELETE':
            success = NicheManager.delete_niche(niche_id)

            if success:
                return jsonify({'success': True, 'message': 'Niche deleted'})
            else:
                return jsonify({'error': 'Niche not found'}), 404

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/image-styles', methods=['GET', 'POST'])
def manage_image_styles():
    """Get all image styles or create new style"""
    from image_style_manager import ImageStyleManager

    try:
        if request.method == 'GET':
            styles = ImageStyleManager.get_all_styles()
            return jsonify({'styles': styles})

        elif request.method == 'POST':
            data = request.get_json()

            if not data:
                return jsonify({'error': 'No data provided'}), 400

            name = data.get('name')
            prompts = data.get('prompts')

            if not name or not prompts:
                return jsonify({'error': 'Missing required fields: name, prompts'}), 400

            if not isinstance(prompts, list) or len(prompts) != 6:
                return jsonify({'error': 'prompts must be an array of exactly 6 strings'}), 400

            style = ImageStyleManager.create_style(name, prompts)

            return jsonify({
                'success': True,
                'style': style
            }), 201

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/image-styles/<style_id>', methods=['GET', 'DELETE'])
def manage_image_style(style_id):
    """Get or delete specific image style by ID"""
    from image_style_manager import ImageStyleManager

    try:
        if request.method == 'GET':
            style = ImageStyleManager.get_style(style_id)

            if not style:
                return jsonify({'error': 'Image style not found'}), 404

            return jsonify({'style': style})

        elif request.method == 'DELETE':
            success = ImageStyleManager.delete_style(style_id)

            if success:
                return jsonify({'success': True, 'message': 'Image style deleted'})
            else:
                return jsonify({'error': 'Image style not found'}), 404

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/generate-title', methods=['POST'])
def generate_title_route():
    """Generate AI title using Gemini"""
    from title_generator import TitleGenerator
    from config import Config
    from niche_manager import NicheManager

    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'No data provided'}), 400

        topic = data.get('topic')
        niche_id = data.get('niche_id')
        count = data.get('count', 1)  # Default 1 title

        if not topic or not niche_id:
            return jsonify({'error': 'Missing required fields: topic, niche_id'}), 400

        # Validate count (1-5)
        if not isinstance(count, int) or count < 1 or count > 5:
            return jsonify({'error': 'Count must be an integer between 1 and 5'}), 400

        # Validate API key
        errors = Config.validate_api_keys()
        if any('GEMINI' in e for e in errors):
            return jsonify({'error': 'Gemini API key not configured'}), 500

        # Validate niche exists
        niche = NicheManager.get_niche(niche_id)
        if not niche:
            return jsonify({'error': 'Niche not found'}), 404

        # Generate title(s)
        generator = TitleGenerator()
        titles = generator.generate_title(topic, niche_id, count=count, verbose=True)

        # Return single title or array based on count
        if count == 1:
            return jsonify({
                'success': True,
                'title': titles,
                'niche': niche['name'],
                'language': niche['language']
            })
        else:
            return jsonify({
                'success': True,
                'titles': titles,
                'count': len(titles),
                'niche': niche['name'],
                'language': niche['language']
            })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/generate-script', methods=['POST'])
def generate_script():
    """
    Generate AI script using 3-CHUNK ARCHITECTURE

    API CALLS PER REQUEST:
    - 3 chunks (one API call each) = 3 total calls
    - Rate limit safe: 20 calls/min ÷ 3 = 6-7 videos/min max
    """
    from script_generator_3chunk import ScriptGenerator3Chunk
    from config import Config
    from niche_manager import NicheManager
    from datetime import datetime
    import os
    import time

    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'No data provided'}), 400

        title    = data.get('title')
        niche_id = data.get('niche_id')
        length   = data.get('length', Config.DEFAULT_SCRIPT_LENGTH)
        provider = data.get('provider', 'gemini')   # "gemini" | "claude"

        if not title or not niche_id:
            return jsonify({'error': 'Missing required fields: title, niche_id'}), 400

        # Validate length
        if not Config.validate_script_length(length):
            return jsonify({
                'error': f'Invalid length. Must be between {Config.MIN_SCRIPT_LENGTH} and {Config.MAX_SCRIPT_LENGTH} characters'
            }), 400

        # Validate API key for chosen provider
        if provider == 'claude':
            if not Config.get_claude_api_key():
                return jsonify({'error': 'Claude API key not configured. Add it in Settings → Claude API.'}), 500
        else:
            errors = Config.validate_api_keys()
            if any('GEMINI' in e for e in errors):
                return jsonify({'error': 'Gemini API key not configured'}), 500

        # Get niche info
        niche = NicheManager.get_niche(niche_id)
        if not niche:
            return jsonify({'error': 'Niche not found'}), 404

        # Generate script using 3-CHUNK architecture
        print(f"\n🎬 Starting 3-chunk script generation...")
        print(f"   API calls: 3 (one per chunk)")
        generator = ScriptGenerator3Chunk()
        result = generator.generate_script(title, niche_id, length=length, verbose=True, provider=provider)

        # SAVE SCRIPT TO FILE - Use OUTPUT_FOLDER directly (same as videos)
        timestamp = int(time.time())
        script_filename = f"script_{timestamp}.txt"
        script_path = os.path.join(OUTPUT_FOLDER, script_filename)

        print(f"\n📝 Saving script to: {script_path}")

        # Write ONLY the raw script text (NO HEADERS)
        # ENGINEERING FIX: Headers break TTS processing and add noise
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(result['script'])

        print(f"✅ Script saved successfully! (raw text only, no headers)")
        print(f"   File: {script_filename}")
        print(f"   Size: {os.path.getsize(script_path):,} bytes")

        return jsonify({
            'success': True,
            'script': result['script'],
            'script_file': script_path,
            'script_filename': script_filename,
            'length': result['stats']['chars'],
            'words': result['stats']['words'],
            'chunks_used': result['chunks_used'],
            'time': result['stats']['time'],
            'validation': result['validation']
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# =============================================================================
# BATCH SCRIPT GENERATION
# =============================================================================

_batch_jobs = {}   # job_id -> {titles, total, completed, results, status}
_batch_lock = threading.Lock()


def _generate_single_script(title, niche_id, length, provider, index, job_id):
    """Thread worker — generates one script. Runs in background thread."""
    result = {
        'index': index,
        'title': title,
        'niche_id': niche_id,
        'length': length,
        'engine': provider,
        'status': 'running',
        'error': None,
        'script': None,
        'chars': 0,
        'words': 0,
        'time': 0,
        'chunks': 0,
        'filename': None,
    }
    try:
        from script_generator_3chunk import ScriptGenerator3Chunk
        import time as _time

        t0 = _time.time()
        gen = ScriptGenerator3Chunk()
        out = gen.generate_script(title, niche_id, length=length, verbose=False, provider=provider)

        # Save script to file
        timestamp = int(t0)
        safe_title = re.sub(r'[^\w\-_.]', '_', title)[:50]
        filename = f"batch_{job_id}_{index}_{timestamp}.txt"
        filepath = os.path.join(OUTPUT_FOLDER, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(out['script'])

        result.update({
            'status': 'done',
            'script': out['script'],
            'chars': out['stats']['chars'],
            'words': out['stats']['words'],
            'time': round(_time.time() - t0, 1),
            'chunks': out['chunks_used'],
            'filename': filename,
        })
    except Exception as e:
        result.update({'status': 'failed', 'error': str(e)})

    # Mark as completed in shared dict
    with _batch_lock:
        _batch_jobs[job_id]['completed'] += 1
        _batch_jobs[job_id]['results'][index] = result
        _batch_jobs[job_id]['progress_pct'] = int(
            _batch_jobs[job_id]['completed'] / _batch_jobs[job_id]['total'] * 100
        )

    print(f"   [{job_id[:8]}] Script {index+1}/{_batch_jobs[job_id]['total']} ({title[:40]}) → {result['status']}")


@app.route('/api/batch-generate-scripts', methods=['POST'])
def batch_generate_scripts():
    """
    Generate multiple scripts — each with its own niche, length, and engine.
    Each title is processed independently with its own settings.

    POST body:
    {
      "titles": ["Title 1", "Title 2", ...],
      "titles_niches": ["niche_id_1", "niche_id_2", ...],
      "titles_lengths": [60000, 100000, ...],
      "titles_engines": ["gemini", "claude", ...],
      "parallel": false,       // false = one-by-one with delay (safe)
      "delay_seconds": 5,
    }
    """
    from config import Config

    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        raw_titles       = data.get('titles', [])
        titles_niches    = data.get('titles_niches', [])
        titles_lengths   = data.get('titles_lengths', [])
        titles_engines   = data.get('titles_engines', [])
        parallel         = data.get('parallel', False)
        delay_seconds    = int(data.get('delay_seconds', 5))

        # Parse titles
        if isinstance(raw_titles, str):
            titles = [t.strip() for t in raw_titles.replace('\n', ',').split(',') if t.strip()]
        else:
            titles = [t.strip() for t in raw_titles if t.strip()]

        if not titles:
            return jsonify({'error': 'No titles provided'}), 400

        # Validate all rows have niche + length
        for i, title in enumerate(titles):
            nid   = titles_niches[i] if i < len(titles_niches) else None
            nlen  = titles_lengths[i] if i < len(titles_lengths) else Config.DEFAULT_SCRIPT_LENGTH
            neng  = titles_engines[i] if i < len(titles_engines) else 'gemini'

            if not nid:
                return jsonify({'error': f'Missing niche for title: "{title}"'}), 400
            niche = NicheManager.get_niche(nid)
            if not niche:
                return jsonify({'error': f'Niche not found for title: "{title}"'}), 404
            if not Config.validate_script_length(nlen):
                return jsonify({
                    'error': f'Invalid length {nlen} for title: "{title}". '
                              f'Must be between {Config.MIN_SCRIPT_LENGTH} and {Config.MAX_SCRIPT_LENGTH}.'
                }), 400

        has_gemini = bool(Config.get_gemini_api_key())
        has_claude = bool(Config.get_claude_api_key())
        if not has_gemini and not has_claude:
            return jsonify({'error': 'No API key configured (Gemini or Claude)'}), 500

        # Build full per-title data list
        titles_full = []
        for i, title in enumerate(titles):
            nid  = titles_niches[i] if i < len(titles_niches) else None
            nlen = titles_lengths[i] if i < len(titles_lengths) else Config.DEFAULT_SCRIPT_LENGTH
            neng = titles_engines[i].lower() if i < len(titles_engines) else 'gemini'

            # Fallback to available engine if chosen engine not available
            if neng == 'claude' and not has_claude:
                neng = 'gemini'
            elif neng == 'gemini' and not has_gemini:
                neng = 'claude'

            titles_full.append({'index': i, 'title': title, 'niche_id': nid, 'length': nlen, 'engine': neng})

        job_id = str(uuid.uuid4())
        total  = len(titles_full)
        gemini_count = sum(1 for t in titles_full if t['engine'] == 'gemini')
        claude_count = sum(1 for t in titles_full if t['engine'] == 'claude')

        engine_note = f"Gemini {gemini_count} + Claude {claude_count}"

        _batch_jobs[job_id] = {
            'titles': titles,
            'titles_full': titles_full,
            'total': total,
            'completed': 0,
            'results': {},
            'status': 'running',
            'progress_pct': 0,
            'engine_note': engine_note,
            'delay_seconds': delay_seconds,
        }

        print(f"\n🚀 Batch job {job_id[:8]} — {total} scripts — {engine_note} — {delay_seconds}s delay")

        # Fire all threads simultaneously — Gemini + Claude both work at same time
        for item in titles_full:
            t = threading.Thread(
                target=_generate_single_script,
                args=(item['title'], item['niche_id'], item['length'], item['engine'],
                      item['index'], job_id)
            )
            t.daemon = True
            t.start()

        return jsonify({
            'success': True,
            'job_id': job_id,
            'total': total,
            'engines': engine_note,
            'message': f'Batch started — {total} scripts queued. {delay_seconds}s delay between each.'
        }), 202

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/batch-status/<job_id>', methods=['GET'])
def batch_status(job_id):
    """Poll batch job status and results."""
    try:
        with _batch_lock:
            if job_id not in _batch_jobs:
                return jsonify({'error': 'Job not found'}), 404
            job = _batch_jobs[job_id]

            if job['completed'] >= job['total'] and job['status'] == 'running':
                job['status'] = 'done'

            return jsonify({
                'job_id': job_id,
                'status': job['status'],
                'total': job['total'],
                'completed': job['completed'],
                'progress_pct': job['progress_pct'],
                'engine_note': job['engine_note'],
                'results': job['results'],
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/translate-script', methods=['POST'])
def translate_script():
    """
    High-quality parallel translation engine.

    Architecture:
    - Raw REST API calls — fully thread-safe (no genai global state)
    - All languages translated in parallel (one thread per language)
    - Chunks within each language processed in parallel (max 3 concurrent)
    - Shared sliding-window rate limiter across both keys (10 RPM per key)
    - Paragraph-boundary chunking + ±1-paragraph context window per chunk
    - Auto-retry reading retry_delay from 429 errors

    Quality:
    - No parenthetical glosses (enforced via prompt + post-processing strip)
    - Idiomatic transition words, natural rhetorical questions
    - Long sentences split for spoken flow
    - Context window prevents sentence-fragment artifacts
    - Consecutive duplicate paragraph detection + removal
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from config import Config

    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        script = data.get('script', '').strip()
        languages = data.get('languages', [])

        if not script:
            return jsonify({'error': 'Script is required'}), 400
        if not languages:
            return jsonify({'error': 'At least one language is required'}), 400

        # Translation uses ONLY its dedicated keys (Translate 1 + Translate 2).
        # No fallback to Script Writer / Auto Images / Image keys — each feature
        # must use its own dedicated API key to keep rate limits fully isolated.
        _candidate_keys = [
            Config.get_gemini_translate_1_key(),
            Config.get_gemini_translate_2_key(),
        ]
        keys = list(dict.fromkeys(k for k in _candidate_keys if k))
        if not keys:
            return jsonify({'error': 'No Translation API key configured. Add Translation Key 1 in Settings → Google Gemini AI → Translation Keys.'}), 500
        print(f'🔑 Translation using {len(keys)} dedicated key(s)')

        LANG_NAMES = {
            'fr': 'French (français)',
            'es': 'Spanish (español)',
            'de': 'German (Deutsch)',
            'en': 'English',
            'pt': 'Portuguese (português)',
            'it': 'Italian (italiano)',
            'nl': 'Dutch (Nederlands)',
            'pl': 'Polish (polski)',
            'ru': 'Russian (русский)',
            'ar': 'Arabic (العربية)',
            'zh': 'Chinese (中文)',
            'ja': 'Japanese (日本語)',
            'ko': 'Korean (한국어)',
            'tr': 'Turkish (Türkçe)',
            'hi': 'Hindi (हिन्दी)',
        }

        # Per-language guide: natural discourse markers used IN the target language.
        # These are injected into the prompt so the model knows what "natural" means
        # for each specific language — not just generic "be idiomatic" advice.
        DISCOURSE_GUIDE: dict = {
            'fr': {
                'attention':   'Écoutez, Regardez, Tenez, Voilà',
                'transition':  'Du coup, En fait, D\'ailleurs, Par contre, Bref, Maintenant',
                'opener':      'C\'est simple :, La réalité c\'est que..., Ce qu\'il faut comprendre c\'est..., Voici ce que...',
                'rhetorical':  'Vous voyez ?, C\'est pas génial ça ?, Incroyable non ?',
            },
            'es': {
                'attention':   'Mira, Escucha, Fíjate, Oye, Resulta que',
                'transition':  'O sea, De hecho, Además, Sin embargo, Es decir, A ver',
                'opener':      'Aquí está la clave:, La verdad es que..., Y es que..., Lo que pasa es que...',
                'rhetorical':  '¿Lo ves?, ¿Te das cuenta?, ¿A que no lo sabías?',
            },
            'de': {
                'attention':   'Schau mal, Hör zu, Also, Pass mal auf, Weißt du was',
                'transition':  'Eigentlich, Jedenfalls, Außerdem, Nämlich, Übrigens, Dabei',
                'opener':      'Darum geht\'s:, Die Wahrheit ist:, So funktioniert das:, Und hier ist der Punkt:',
                'rhetorical':  'Weißt du warum?, Kannst du dir das vorstellen?, Klingt das nicht verrückt?',
            },
            'en': {
                'attention':   'Look, Listen, Here\'s the thing, Now, Right,',
                'transition':  'Actually, Basically, The thing is, On top of that, By the way',
                'opener':      'Here\'s the deal:, The truth is:, Here\'s the kicker:, And this is key:',
                'rhetorical':  'Can you believe that?, Right?, Doesn\'t that blow your mind?',
            },
            'pt': {
                'attention':   'Olha, Veja bem, Escuta, Sabe o que é',
                'transition':  'Na verdade, Aliás, Além disso, Inclusive, Então',
                'opener':      'Veja bem:, A verdade é que..., E é aí que..., O ponto é:',
                'rhetorical':  'Acredita nisso?, Entende?, Incrível, não é?',
            },
            'it': {
                'attention':   'Guarda, Senti, Ecco, Sai cosa',
                'transition':  'Infatti, Quindi, Comunque, Tra l\'altro, In realtà',
                'opener':      'Ecco il punto:, La verità è che..., Ed è qui che...',
                'rhetorical':  'Ci credi?, Capisci?, Non è incredibile?',
            },
            'nl': {
                'attention':   'Kijk, Luister, Weet je wat, Oké dus',
                'transition':  'Eigenlijk, Bovendien, Trouwens, Kortom, Maar goed',
                'opener':      'Hier is het punt:, De waarheid is:, En dit is cruciaal:',
                'rhetorical':  'Kun je het geloven?, Toch?, Is dat niet gek?',
            },
            'pl': {
                'attention':   'Słuchaj, Patrz, Wiesz co, No to słuchaj',
                'transition':  'Właściwie, Poza tym, Zresztą, Tak czy inaczej, W każdym razie',
                'opener':      'Oto o co chodzi:, Prawda jest taka:, I tu jest clou:',
                'rhetorical':  'Wierzysz w to?, No nie?, Czy to nie niesamowite?',
            },
            'tr': {
                'attention':   'Bak, Dinle, Şimdi, Şunu söyleyeyim',
                'transition':  'Aslında, Üstelik, Zaten, Yani, Neyse',
                'opener':      'İşte mesele şu:, Gerçek şu ki:, Ve işte bu noktada:',
                'rhetorical':  'İnanabiliyor musun?, Değil mi?, Bu çılgınca değil mi?',
            },
        }
        MODEL      = 'gemini-2.5-flash'
        GEMINI_URL = f'https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent'
        MAX_TOKENS = 8192
        CHUNK_CHARS = 3500   # paragraph-safe max; output ~20 % larger = ~4 200 → fine

        # ── REST call — uses module-level rate limiter (persists across requests) ─
        def gemini_call(prompt, retries=6):
            """Send one translation request.

            On 429: marks the offending key as blocked for the retry delay so ALL
            threads automatically avoid it — no manual sleeping in caller code.
            Re-acquires immediately (acquire() will block until a key is free).
            On network error: exponential back-off, max 4×.
            """
            body = {
                'contents': [{'parts': [{'text': prompt}]}],
                'generationConfig': {
                    'temperature': 0.3,
                    'maxOutputTokens': MAX_TOKENS,
                    'topP': 0.95,
                },
            }
            for attempt in range(retries):
                api_key = _gem_acquire(keys)   # blocks until a key slot is free
                try:
                    r = _http.post(GEMINI_URL, json=body, params={'key': api_key}, timeout=90)
                    if r.status_code == 429:
                        wait = _gem_parse_retry(r.text)
                        print(f'   ⏳ 429 on key …{api_key[-6:]} — blocked {wait}s '
                              f'(attempt {attempt+1}/{retries})')
                        _gem_block(api_key, wait)   # mark key; acquire() will skip it
                        continue                     # re-acquire immediately (no sleep here)
                    r.raise_for_status()
                    return r.json()['candidates'][0]['content']['parts'][0]['text'].strip()
                except (_http.exceptions.Timeout, _http.exceptions.ConnectionError) as e:
                    if attempt < retries - 1:
                        time.sleep(min(4 ** attempt, 30))
                    else:
                        raise
            raise RuntimeError(f'Gemini call failed after {retries} attempts')

        # ── Paragraph-boundary chunking ─────────────────────────────────────────
        def smart_chunks(text):
            pieces = re.split(r'(\n{2,})', text)   # keep separators
            chunks, cur = [], ''
            for piece in pieces:
                if len(cur) + len(piece) > CHUNK_CHARS and cur.strip():
                    chunks.append(cur.strip())
                    cur = '' if re.match(r'^\n+$', piece) else piece
                else:
                    cur += piece
            if cur.strip():
                chunks.append(cur.strip())
            return chunks or [text]

        # ── Unicode-aware normaliser (works for ALL scripts) ──────────────────
        def tnorm(s: str) -> str:
            """Normalise text for duplicate comparison across any language.

            NFKD decomposition splits accented chars → base + combining mark
            (é → e + combining acute) so French/German/Spanish/Polish etc.
            compare correctly even with accent variation.  \w in the final
            sub matches Unicode word chars, so CJK/Arabic/Cyrillic are kept.
            """
            s = unicodedata.normalize('NFKD', s.strip())
            s = ''.join(c for c in s if not unicodedata.combining(c))
            s = s.lower()
            s = re.sub(r'\s+', ' ', s)
            s = re.sub(r'[^\w\s]', '', s)
            return s

        def tsimilar(a: str, b: str, threshold: float = 0.88) -> bool:
            """True if two normalised strings are ≥ threshold similar."""
            if not a or not b:
                return False
            if min(len(a), len(b)) / max(len(a), len(b)) < 0.7:
                return False
            return SequenceMatcher(None, a, b).ratio() >= threshold

        # ── Overlap-aware chunk joiner ─────────────────────────────────────────
        def join_chunks(parts):
            """Join translated chunks, trimming line-level overlap at boundaries."""
            if not parts:
                return ''
            result = parts[0]
            for part in parts[1:]:
                if not part:
                    continue
                r_lines = [l for l in result.splitlines() if l.strip()]
                p_lines = [l for l in part.splitlines()   if l.strip()]
                overlap = 0
                for n in range(min(6, len(r_lines), len(p_lines)), 0, -1):
                    if [tnorm(l) for l in r_lines[-n:]] == [tnorm(l) for l in p_lines[:n]]:
                        overlap = n
                        break
                if overlap:
                    trimmed = part
                    for _ in range(overlap):
                        nl = trimmed.find('\n')
                        trimmed = trimmed[nl + 1:].lstrip('\n') if nl != -1 else ''
                    result = result.rstrip('\n') + '\n\n' + trimmed
                else:
                    result = result.rstrip('\n') + '\n\n' + part
            return result

        # ── Post-processing ────────────────────────────────────────────────────
        def postprocess(text):
            # Strip parenthetical glosses
            text = re.sub(
                r'(?<=\w)\s*\([^()\n]{1,60}\)(?=[^\w(]|$)',
                lambda m: '' if not re.search(r'[!?,.]', m.group()) else m.group(),
                text,
            )
            # Dedup: exact normalised match + near-duplicate similarity check
            paras = re.split(r'\n{2,}', text)
            seen_norm: list = []
            seen_exact: set = set()
            deduped = []
            for p in paras:
                n = tnorm(p)
                if not n:
                    continue
                if n in seen_exact:
                    continue
                if any(tsimilar(n, prev) for prev in seen_norm):
                    continue
                seen_exact.add(n)
                seen_norm.append(n)
                deduped.append(p)
            return '\n\n'.join(deduped)

        # ── Single chunk translation ───────────────────────────────────────────
        def translate_chunk(chunk, prev_ctx, next_ctx, lang_code, lang_name, idx, total):
            # Build context block
            ctx = ''
            if prev_ctx:
                ctx += f'[PRECEDING CONTEXT — read-only, do NOT output]:\n{prev_ctx[-400:]}\n\n'
            if next_ctx:
                ctx += f'[FOLLOWING CONTEXT — read-only, do NOT output]:\n{next_ctx[:400]}\n\n'

            # Pull language-specific discourse guide, fall back to English
            dg = DISCOURSE_GUIDE.get(lang_code, DISCOURSE_GUIDE['en'])

            prompt = (
                f'You are an expert professional translator specialising in spoken video scripts.\n'
                f'Translate the [TEXT] section below into {lang_name}.\n\n'
                f'STRICT RULES — follow every single rule, no exceptions:\n\n'

                f'1. OUTPUT ONLY the translated text — no preamble, no notes, no headings, '
                f'no section labels.\n\n'

                f'2. NO PARENTHETICALS — never add parenthetical explanations, '
                f'original-language terms, or any annotation in parentheses.\n\n'

                f'3. DISCOURSE MARKERS & RHETORICAL OPENERS — CRITICAL:\n'
                f'   Openers like "Here", "Ici", "Aquí", "Hier", "Now,", "So,", "Look,", '
                f'"Right,", "Voilà,", "Also,", "Schau mal," and any similar word used to '
                f'open or punctuate a sentence are RHETORICAL FUNCTIONS, not literal words.\n'
                f'   → Translate their COMMUNICATIVE FUNCTION, not their literal meaning.\n'
                f'   → Ask yourself: "What would a native {lang_name} video-script writer '
                f'say here to create the same energy and effect?"\n'
                f'   → In {lang_name}, natural attention-getters are: {dg["attention"]}\n'
                f'   → In {lang_name}, natural rhetorical openers are: {dg["opener"]}\n'
                f'   → In {lang_name}, natural rhetorical questions are: {dg["rhetorical"]}\n\n'

                f'4. TRANSITION WORDS — connectors (however, therefore, meanwhile, besides, '
                f'actually, basically, anyway…) must use the most natural, colloquially correct '
                f'{lang_name} equivalent.\n'
                f'   → In {lang_name}, natural connectors are: {dg["transition"]}\n'
                f'   → Never use a word-for-word calque of the source-language connector.\n\n'

                f'5. RHETORICAL QUESTIONS — must sound punchy and completely native in '
                f'{lang_name}. Restructure the sentence if needed; do not translate literally.\n\n'

                f'6. SENTENCE LENGTH — split any sentence over ~25 words into shorter '
                f'sentences for natural spoken rhythm.\n\n'

                f'7. STRUCTURE — preserve paragraph breaks and blank lines exactly as in the source.\n\n'

                f'8. CONTEXT SECTIONS — if present above, they are read-only references '
                f'for continuity. Do NOT include them in your output.\n\n'

                f'{ctx}'
                f'[TEXT]:\n{chunk}'
            )
            result = gemini_call(prompt)
            print(f'   ✅ [{lang_name}] chunk {idx+1}/{total}: {len(result):,} chars')
            return idx, result

        # ── Single flat work queue — all languages × all chunks ───────────────
        # One ThreadPoolExecutor for everything.  max_workers = len(keys) so at
        # most N threads compete for N keys; _gem_acquire() spaces them out via
        # the per-key minimum interval (6.5 s) — no bursts, no 429s.
        chunks_src = smart_chunks(script)
        n_chunks   = len(chunks_src)
        print(f'📝 {len(languages)} language(s) × {n_chunks} chunk(s) '
              f'= {len(languages) * n_chunks} task(s) — {len(keys)} key(s) available')

        # task = (lang_code, lang_name, chunk_text, idx, prev_ctx, next_ctx)
        tasks = []
        for lang_code in languages:
            lang_name = LANG_NAMES.get(lang_code, lang_code)
            print(f'🌍 [{lang_code}] queued — {n_chunks} chunk(s), {len(script):,} chars')
            for i, chunk in enumerate(chunks_src):
                tasks.append((
                    lang_code, lang_name, chunk, i,
                    chunks_src[i - 1] if i > 0         else '',
                    chunks_src[i + 1] if i < n_chunks - 1 else '',
                ))

        # Accumulate translated parts indexed by (lang_code, chunk_idx)
        translated: dict[tuple, str] = {}
        chunk_errors: dict[str, str] = {}

        def run_task(task):
            lang_code, lang_name, chunk, idx, prev_ctx, next_ctx = task
            _, text = translate_chunk(chunk, prev_ctx, next_ctx,
                                      lang_code, lang_name, idx, n_chunks)
            return (lang_code, idx), text

        with ThreadPoolExecutor(max_workers=len(keys)) as ex:
            futs = {ex.submit(run_task, t): t for t in tasks}
            for f in as_completed(futs):
                task = futs[f]
                lang_code = task[0]
                try:
                    key, text = f.result()
                    translated[key] = text
                except Exception as e:
                    chunk_errors[lang_code] = str(e)
                    print(f'   ❌ [{lang_code}] chunk {task[3]+1} failed: {e}')

        # Assemble per-language results in original chunk order
        results, errors = {}, {}
        for lang_code in languages:
            if lang_code in chunk_errors and not any(
                    k[0] == lang_code for k in translated):
                errors[lang_code] = chunk_errors[lang_code]
                continue
            parts = [translated.get((lang_code, i), '') for i in range(n_chunks)]
            joined = postprocess(join_chunks(parts))
            print(f'✅ [{lang_code}] done: {len(joined):,} chars')
            results[lang_code] = joined

        return jsonify({'success': True, 'translations': results, 'errors': errors})

    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/generate-image-prompts', methods=['POST'])
def generate_image_prompts_route():
    """Generate image prompts from script using Gemini + Image Formula (NEW SYSTEM)"""
    from image_prompts_generator import generate_image_prompts
    from settings_manager import SettingsManager

    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'No data provided'}), 400

        script = data.get('script')
        count = data.get('count', 6)  # Default to 6 images
        style = data.get('style', '')  # Optional: image style (e.g., "hand draw cartoon")

        if not script:
            return jsonify({'error': 'Missing required field: script'}), 400

        # Validate count (3-30)
        if not isinstance(count, int) or count < 3 or count > 30:
            return jsonify({'error': 'Count must be an integer between 3 and 30'}), 400

        # Get Gemini API key from settings
        gemini_api_key = SettingsManager.get_api_key('gemini')
        if not gemini_api_key:
            return jsonify({'error': 'Gemini API key not configured in settings'}), 500

        # Load image formula from settings
        image_formula = SettingsManager.load_formula('image')

        # Generate prompts with style
        prompts = generate_image_prompts(
            script_text=script,
            image_formula=image_formula,
            count=count,
            gemini_api_key=gemini_api_key,
            style=style,
            verbose=True
        )

        return jsonify({
            'success': True,
            'prompts': prompts,
            'count': len(prompts)
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/fetch-stock', methods=['POST'])
def fetch_stock_route():
    """Fetch stock footage/photos from Pexels (NEW SYSTEM)"""
    from stock_footage import fetch_and_download_stock, extract_keywords_from_script
    from settings_manager import SettingsManager

    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'No data provided'}), 400

        query_or_script = data.get('query') or data.get('script')
        count = data.get('count', 5)
        media_type = data.get('media_type', 'both')  # 'videos', 'photos', or 'both'
        auto_extract = data.get('auto_extract', True)

        if not query_or_script:
            return jsonify({'error': 'Missing required field: query or script'}), 400

        # Validate media_type
        if media_type not in ['videos', 'photos', 'both']:
            return jsonify({'error': 'media_type must be: videos, photos, or both'}), 400

        # Validate count (1-20)
        if not isinstance(count, int) or count < 1 or count > 20:
            return jsonify({'error': 'Count must be an integer between 1 and 20'}), 400

        # Get Pexels API key from settings
        pexels_api_key = SettingsManager.get_api_key('pexels')
        if not pexels_api_key:
            return jsonify({'error': 'Pexels API key not configured in settings'}), 500

        # Fetch and download
        result = fetch_and_download_stock(
            api_key=pexels_api_key,
            query_or_script=query_or_script,
            count=count,
            media_type=media_type,
            auto_extract=auto_extract,
            output_dir='output/stock'
        )

        return jsonify({
            'success': True,
            'query': result['query'],
            'media_info': result['media_info'],
            'downloaded_paths': result['downloaded_paths'],
            'count': result['count']
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/extract-keywords', methods=['POST'])
def extract_keywords_route():
    """Extract keywords from script for stock search"""
    from stock_footage import extract_keywords_from_script

    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'No data provided'}), 400

        script = data.get('script')
        max_keywords = data.get('max_keywords', 5)

        if not script:
            return jsonify({'error': 'Missing required field: script'}), 400

        # Extract keywords
        keywords = extract_keywords_from_script(script, max_keywords=max_keywords)

        return jsonify({
            'success': True,
            'keywords': keywords,
            'query': ' '.join(keywords)
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/generate-images', methods=['POST'])
def generate_images():
    """Generate AI images using Replicate"""
    from image_generator import ImageGenerator
    from config import Config

    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'No data provided'}), 400

        title = data.get('title')
        script = data.get('script')
        style_id = data.get('style_id')
        count = data.get('count', 6)  # Default to 6 if not specified

        if not title or not script or not style_id:
            return jsonify({'error': 'Missing required fields: title, script, style_id'}), 400

        # Handle "default" style_id - use first available style
        if style_id == 'default':
            from image_style_manager import ImageStyleManager
            styles = ImageStyleManager.get_all_styles()
            if not styles or len(styles) == 0:
                return jsonify({'error': 'No image styles available. Server initialization may have failed.'}), 500
            style_id = styles[0]['id']
            print(f"   Using default style: {styles[0]['name']} ({style_id})")

        # Validate API key
        errors = Config.validate_api_keys()
        if any('REPLICATE' in e for e in errors):
            return jsonify({'error': 'Replicate API token not configured'}), 500

        # Generate images with user-specified count
        generator = ImageGenerator()
        image_urls = generator.generate_images(title, script, style_id, count=count)

        return jsonify({
            'success': True,
            'image_urls': image_urls,
            'count': len(image_urls)
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/process-ai-video', methods=['POST'])
def process_ai_video():
    """
    Process AI-generated video from images and audio files

    Request JSON:
        {
            'title': 'Video Title',
            'image_urls': ['url1', 'url2', ...],  # 6 image URLs
            'audio_files': [
                {'rank': 1, 'file_id': '...'},
                {'rank': 2, 'file_id': '...'}
            ],
            'output_filename': 'my_video.mp4',  # optional
            'niche_id': 'uuid',  # for tracking
            'style_id': 'uuid',  # for tracking
            'script': 'generated script text'  # for tracking
        }

    Response:
        {
            'success': true,
            'job_id': 'unique-job-id',
            'status': 'completed',
            'result': {...}
        }
    """
    from database import VideoDatabase

    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'No data provided'}), 400

        title = data.get('title')
        image_urls = data.get('image_urls', [])
        audio_files = data.get('audio_files', [])
        output_filename = data.get('output_filename')
        niche_id = data.get('niche_id')
        style_id = data.get('style_id')
        script = data.get('script', '')

        if not title:
            return jsonify({'error': 'Missing title'}), 400

        if not image_urls or len(image_urls) != 6:
            return jsonify({'error': 'Must provide exactly 6 image URLs'}), 400

        if not audio_files:
            return jsonify({'error': 'No audio files provided'}), 400

        # Convert file IDs to paths
        audio_paths = []
        for item in audio_files:
            file_id = item.get('file_id')
            if not file_id:
                return jsonify({'error': 'Missing file_id in audio_files'}), 400

            # Find file with this ID
            file_ext = _find_uploaded_file(file_id)
            if not file_ext:
                return jsonify({'error': f'Audio file not found: {file_id}'}), 404

            audio_paths.append(os.path.join(app.config['UPLOAD_FOLDER'], f"{file_id}.{file_ext}"))

        # Generate job ID
        job_id = str(uuid.uuid4())

        # Store job info
        processing_jobs[job_id] = {
            'status': 'processing',
            'progress': 0,
            'message': 'Starting AI video processing...'
        }

        # Process video
        try:
            editor = VideoEditorSystem(
                temp_dir=TEMP_FOLDER,
                output_dir=OUTPUT_FOLDER,
                verbose=True
            )

            result = editor.process_ai_generated_video(
                title=title,
                image_urls=image_urls,
                audio_paths=audio_paths,
                output_filename=output_filename,
                cleanup_temp=True
            )

            # Save to video database
            if niche_id and style_id:
                VideoDatabase.create(
                    title=title,
                    niche_id=niche_id,
                    style_id=style_id,
                    script=script,
                    image_urls=image_urls,
                    audio_paths=audio_paths,
                    output_path=result['output_path']
                )

            # Update job status
            processing_jobs[job_id] = {
                'status': 'completed',
                'progress': 100,
                'message': 'AI video processing complete',
                'result': result
            }

            return jsonify({
                'success': True,
                'job_id': job_id,
                'status': 'completed',
                'result': result
            })

        except Exception as e:
            processing_jobs[job_id] = {
                'status': 'failed',
                'progress': 0,
                'message': str(e)
            }

            return jsonify({
                'success': False,
                'job_id': job_id,
                'error': str(e)
            }), 500

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/process-final-video', methods=['POST'])
def process_final_video_route():
    """Process all media into final video (NEW SYSTEM)"""
    from video_processor import process_final_video
    import time

    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'No data provided'}), 400

        title = data.get('title', 'video')
        media_items = data.get('media_items', [])
        audio_files = data.get('audio_files', [])
        quality = data.get('quality', '1080')

        if not media_items:
            return jsonify({'error': 'No media items provided'}), 400

        if not audio_files:
            return jsonify({'error': 'No audio files provided'}), 400

        # Validate quality
        if quality not in ['720', '1080']:
            return jsonify({'error': 'Quality must be 720 or 1080'}), 400

        # Safe filename
        safe_title = re.sub(r'[^a-z0-9]', '_', title.lower())[:50]
        timestamp = int(time.time())
        output_filename = f"{safe_title}_{timestamp}.mp4"
        output_path = os.path.join(OUTPUT_FOLDER, output_filename)

        # Process video
        result = process_final_video(
            media_items=media_items,
            audio_files=audio_files,
            output_path=output_path,
            quality=quality,
            verbose=True
        )

        return jsonify({
            'success': True,
            'output_filename': output_filename,
            **result
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/videos/recent', methods=['GET'])
def get_recent_videos():
    """Get recent AI-generated videos"""
    from database import VideoDatabase

    try:
        limit = request.args.get('limit', 10, type=int)
        videos = VideoDatabase.get_recent(limit)

        return jsonify({'videos': videos})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# =============================================================================
# API CONFIGURATION ROUTES
# =============================================================================

@app.route('/api/config', methods=['GET'])
def get_api_config():
    """Get API configuration status (without exposing actual keys)"""
    from config import Config

    try:
        status = Config.get_api_config_status()
        return jsonify(status)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/config', methods=['POST'])
def save_api_config():
    """Save API configuration"""
    from config import Config

    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'No data provided'}), 400

        gemini_key = data.get('gemini_api_key')
        director_gemini_key = data.get('director_gemini_key')
        gemini_image_key = data.get('gemini_image_key')
        replicate_token = data.get('replicate_api_token')
        inworld_key = data.get('inworld_api_key')
        inworld_secret = data.get('inworld_api_secret')

        if not gemini_key and not director_gemini_key and not gemini_image_key and not replicate_token and not inworld_key and not inworld_secret:
            return jsonify({'error': 'At least one API key must be provided'}), 400

        # Save configuration
        Config.save_api_config(
            gemini_key=gemini_key,
            director_gemini_key=director_gemini_key,
            gemini_image_key=gemini_image_key,
            replicate_token=replicate_token,
            inworld_key=inworld_key,
            inworld_secret=inworld_secret
        )

        return jsonify({
            'success': True,
            'message': 'API configuration saved successfully'
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/config', methods=['DELETE'])
def clear_api_config():
    """Clear all API configuration"""
    from config import Config

    try:
        Config.clear_api_config()
        return jsonify({
            'success': True,
            'message': 'API configuration cleared'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/config/test', methods=['GET'])
def test_api_config():
    """Test API connections"""
    from config import Config
    import google.generativeai as genai

    results = {
        'gemini_ok': False,
        'replicate_ok': False
    }

    # Test Gemini
    try:
        gemini_key = Config.get_gemini_api_key()
        if gemini_key:
            genai.configure(api_key=gemini_key)
            # Try to list models to test connection
            list(genai.list_models())
            results['gemini_ok'] = True
    except:
        pass

    # Test Replicate
    try:
        replicate_token = Config.get_replicate_api_token()
        if replicate_token:
            import replicate
            import os
            os.environ['REPLICATE_API_TOKEN'] = replicate_token
            # Simple test - will work if token is valid
            results['replicate_ok'] = True
    except:
        pass

    return jsonify(results)


# =============================================================================
# SETTINGS MANAGEMENT ROUTES (NEW)
# =============================================================================

@app.route('/api/settings', methods=['GET'])
def get_settings():
    """Get all settings including API keys status, formulas, and voice settings"""
    from settings_manager import SettingsManager

    try:
        summary = SettingsManager.get_settings_summary()
        return jsonify({
            'success': True,
            'settings': summary
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/settings/api-keys', methods=['GET'])
def get_api_keys_status():
    """Get API keys status (for debugging)"""
    from settings_manager import SettingsManager

    try:
        settings = SettingsManager.load_settings()
        api_keys = settings.get('api_keys', {})

        # Return masked keys (show first 4 chars only)
        def mask_key(key):
            if not key or len(key) == 0:
                return ''
            if len(key) <= 8:
                return '***'
            return key[:4] + '***' + key[-4:]

        return jsonify({
            'success': True,
            'api_keys': {
                'gemini': mask_key(api_keys.get('gemini', '')),
                'director_gemini': mask_key(api_keys.get('director_gemini', '')),
                'replicate': mask_key(api_keys.get('replicate', '')),
                'inworld': mask_key(api_keys.get('inworld', '')),
                'inworld_secret': mask_key(api_keys.get('inworld_secret', '')),
                'pexels': mask_key(api_keys.get('pexels', '')),
                'pixabay': mask_key(api_keys.get('pixabay', '')),
                'claude_key': mask_key(api_keys.get('claude_api_key', ''))
            },
            'settings_file': str(SettingsManager.SETTINGS_FILE),
            'file_exists': SettingsManager.SETTINGS_FILE.exists()
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/settings/api-keys', methods=['POST'])
def save_api_keys():
    """Save API keys (Script Writer Gemini, Director Gemini, Replicate, Inworld AI Key+Secret, Pexels, Pixabay)"""
    from settings_manager import SettingsManager

    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'No data provided'}), 400

        gemini = data.get('gemini')
        director_gemini = data.get('director_gemini')
        gemini_image = data.get('gemini_image')
        replicate = data.get('replicate')
        inworld = data.get('inworld')
        inworld_secret = data.get('inworld_secret')
        pexels = data.get('pexels')
        pixabay = data.get('pixabay')
        unsplash = data.get('unsplash')
        brave_search  = data.get('brave_search')
        serper        = data.get('serper')
        google_search = data.get('google_search')
        videvo        = data.get('videvo')
        coverr        = data.get('coverr')
        gemini_translate_1 = data.get('gemini_translate_1')
        gemini_translate_2 = data.get('gemini_translate_2')
        gemini_prompts     = data.get('gemini_prompts')
        gemini_seo         = data.get('gemini_seo')
        claude_key         = data.get('claude_key')

        # Debug: Log what keys we received (show length not actual value)
        print("\n🔑 Received API keys:")
        print(f"   Gemini: {'SET (' + str(len(gemini)) + ' chars)' if gemini else 'NOT SET'}")
        print(f"   Director Gemini: {'SET (' + str(len(director_gemini)) + ' chars)' if director_gemini else 'NOT SET'}")
        print(f"   Gemini Image: {'SET (' + str(len(gemini_image)) + ' chars)' if gemini_image else 'NOT SET'}")
        print(f"   Replicate: {'SET (' + str(len(replicate)) + ' chars)' if replicate else 'NOT SET'}")
        print(f"   Inworld: {'SET (' + str(len(inworld)) + ' chars)' if inworld else 'NOT SET'}")
        print(f"   Inworld Secret: {'SET (' + str(len(inworld_secret)) + ' chars)' if inworld_secret else 'NOT SET'}")
        print(f"   Pexels: {'SET (' + str(len(pexels)) + ' chars)' if pexels else 'NOT SET'}")
        print(f"   Pixabay: {'SET (' + str(len(pixabay)) + ' chars)' if pixabay else 'NOT SET'}")
        print(f"   Unsplash: {'SET (' + str(len(unsplash)) + ' chars)' if unsplash else 'NOT SET'}")
        print(f"   Translate 1: {'SET (' + str(len(gemini_translate_1)) + ' chars)' if gemini_translate_1 else 'NOT SET'}")
        print(f"   Translate 2: {'SET (' + str(len(gemini_translate_2)) + ' chars)' if gemini_translate_2 else 'NOT SET'}")
        print(f"   Prompts Gen: {'SET (' + str(len(gemini_prompts)) + ' chars)' if gemini_prompts else 'NOT SET'}")
        print(f"   SEO Gen: {'SET (' + str(len(gemini_seo)) + ' chars)' if gemini_seo else 'NOT SET'}")

        # Save API keys (each feature uses its own dedicated key)
        settings = SettingsManager.save_api_keys(
            gemini=gemini,
            director_gemini=director_gemini,
            gemini_image=gemini_image,
            replicate=replicate,
            inworld=inworld,
            inworld_secret=inworld_secret,
            pexels=pexels,
            pixabay=pixabay,
            unsplash=unsplash,
            brave_search=brave_search,
            serper=serper,
            google_search=google_search,
            videvo=videvo,
            coverr=coverr,
            gemini_translate_1=gemini_translate_1,
            gemini_translate_2=gemini_translate_2,
            gemini_prompts=gemini_prompts,
            gemini_seo=gemini_seo,
            claude_key=claude_key
        )

        # Get validation status
        validation = SettingsManager.validate_api_keys()

        return jsonify({
            'success': True,
            'message': 'API keys saved successfully',
            'validation': validation
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/settings/formulas', methods=['POST'])
def save_formulas():
    """Save generation formulas (title, script, image)"""
    from settings_manager import SettingsManager

    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'No data provided'}), 400

        title_formula       = data.get('title_formula')
        script_formula      = data.get('script_formula')
        image_formula       = data.get('image_formula')
        auto_images_formula = data.get('auto_images_formula')

        # Save formulas
        success = SettingsManager.save_formulas(
            title_formula=title_formula,
            script_formula=script_formula,
            image_formula=image_formula,
            auto_images_formula=auto_images_formula,
        )

        if success:
            return jsonify({
                'success': True,
                'message': 'Formulas saved successfully'
            })
        else:
            return jsonify({'error': 'Failed to save formulas'}), 500

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/settings/formulas/<formula_type>', methods=['GET'])
def get_formula(formula_type):
    """Get a specific formula (title, script, or image)"""
    from settings_manager import SettingsManager

    try:
        if formula_type not in ['title', 'script', 'image', 'auto_images']:
            return jsonify({'error': 'Invalid formula type. Must be: title, script, image, or auto_images'}), 400

        formula = SettingsManager.load_formula(formula_type)

        return jsonify({
            'success': True,
            'formula_type': formula_type,
            'formula': formula
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/settings/formulas/<formula_type>/reset', methods=['POST'])
def reset_formula(formula_type):
    """Delete saved formula file so it falls back to the built-in default."""
    from settings_manager import SettingsManager
    file_map = {
        'title':       SettingsManager.TITLE_FORMULA_FILE,
        'script':      SettingsManager.SCRIPT_FORMULA_FILE,
        'image':       SettingsManager.IMAGE_FORMULA_FILE,
        'auto_images': SettingsManager.AUTO_IMAGES_FORMULA_FILE,
    }
    if formula_type not in file_map:
        return jsonify({'error': 'Invalid formula type'}), 400
    try:
        f = file_map[formula_type]
        if f.exists():
            f.unlink()
        default = SettingsManager.load_formula(formula_type)
        return jsonify({'success': True, 'formula': default})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/settings/formula-guide/download', methods=['GET'])
def download_formula_guide():
    """Download the complete formula writing tutorial as a TXT file"""
    from flask import Response

    guide = """================================================================
GUIDE COMPLET — COMMENT ÉCRIRE UNE FORMULE DE NICHE
Pour le Générateur de Scripts IA
Version 1.0
================================================================

Ce guide t'apprend à écrire une formule de niche complète
pour n'importe quel sujet : trading, story, horreur, éducation,
motivation, finance personnelle, crypto, développement personnel, etc.

La formule que tu écris devient la LOI ABSOLUE du générateur.
L'IA l'exécutera exactement dans l'ordre que tu définis.


================================================================
PARTIE 1 — QU'EST-CE QU'UNE FORMULE DE NICHE ?
================================================================

Une formule de niche est un document texte qui définit :

1. QUI tu es quand tu écris (la voix, le personnage narrateur)
2. POUR QUI tu écris (le public exact, ses douleurs, son niveau)
3. COMMENT tu écris (le style, le rythme, les lois d'écriture)
4. DANS QUEL ORDRE tu écris (la structure obligatoire du script)
5. CE QUE TU VENDS (le produit, comment le présenter, les promotions)
6. CE QUI EST INTERDIT (les phrases mortes, les patterns à éviter)

Sans formule = scripts génériques.
Avec une bonne formule = scripts impossibles à distinguer d'un humain expert.


================================================================
PARTIE 2 — STRUCTURE OBLIGATOIRE D'UNE FORMULE DE NICHE
================================================================

Une formule complète contient ces 8 sections dans cet ordre :

SECTION 1 — IDENTITÉ DU SCRIPTEUR
SECTION 2 — LE PUBLIC CIBLE
SECTION 3 — LA VOIX ET LE TON
SECTION 4 — LES LOIS DE RYTHME
SECTION 5 — LES LOIS D'ÉCRITURE
SECTION 6 — LA STRUCTURE DU SCRIPT (ordre des parties)
SECTION 7 — LES RÈGLES DE CHAQUE PARTIE
SECTION 8 — LES INTERDITS ABSOLUS

Chaque section est expliquée ci-dessous avec instructions
et exemples concrets que tu peux adapter à ta niche.


================================================================
SECTION 1 — IDENTITÉ DU SCRIPTEUR
================================================================

Définit QUI parle. Pas un personnage fictif — une identité crédible
qui a vécu ce que le public vit. La voix doit venir de l'intérieur,
pas de l'extérieur.

QUESTIONS À RÉPONDRE :
- Quelle est l'expérience vécue qui donne de la crédibilité ?
- Est-ce que cette voix enseigne ou témoigne ?
- Quel est le rapport de cette voix au public : pair, mentor, survivant ?
- Quelles sont les 3 qualités uniques de cette voix ?

EXEMPLE (niche trading psychologie) :
  Tu n'es pas un gourou. Tu es quelqu'un qui est passé exactement
  par où ces traders passent. Les nuits à fixer un écran rouge.
  Les règles brisées encore et encore malgré la connaissance.
  Ta voix a trois qualités : Clarté. Vérité. Respect.
  Jamais condescendant. Jamais énergie artificielle.

EXEMPLE (niche développement personnel) :
  Tu n'es pas un coach. Tu es quelqu'un qui a tout reconstruit
  après un échec complet. Tu parles depuis la reconstruction,
  pas depuis le sommet. Ta voix a trois qualités : honnêteté brute,
  précision pratique, humour sombre. Jamais de positivité forcée.

EXEMPLE (niche histoire/mystère) :
  Tu es le narrateur qui sait tout mais révèle au compte-gouttes.
  Tu contrôles le rythme de l'information. Tu sais exactement
  quand tendre et quand relâcher. Ta voix est froide, précise,
  fascinante. Jamais dramatique. Jamais de sensationnalisme vide.

TEMPLATE À REMPLIR :
  Tu n'es pas [rôle générique].
  Tu es quelqu'un qui [expérience vécue spécifique].
  Tu parles depuis [position crédible].
  Ta voix a trois qualités : [qualité 1]. [qualité 2]. [qualité 3].
  Jamais [ce que tu refuses absolument].
  Jamais [deuxième refus].


================================================================
SECTION 2 — LE PUBLIC CIBLE
================================================================

Définit QUI écoute. Plus tu es précis, plus le script résonne.
Un public vague produit un script vague.

QUESTIONS À RÉPONDRE :
- Quel âge approximatif ? Quelle situation de vie ?
- Quel niveau d'expertise dans le domaine ?
- Quelles sont leurs 3 douleurs principales ?
- Qu'ont-ils déjà essayé sans succès ?
- Quel est le détail émotionnel qui change tout ?
  (le moment précis où ils souffrent le plus)

EXEMPLE (trading) :
  Traders particuliers. Forex, crypto, actions.
  Entre 6 mois et 3 ans d'expérience.
  Assez de connaissances pour être dangereux.
  Ils ont lu les livres. Suivi les formations.
  Ils répètent les mêmes erreurs depuis des mois.
  Le détail qui change tout : à 23h devant un écran rouge,
  seuls, honteux d'avoir encore brisé leurs règles.

EXEMPLE (fitness/perte de poids) :
  Adultes 25-45 ans. Emplois sédentaires. Familles.
  Ont essayé 3 à 5 régimes différents.
  Perdent du poids puis reprennent tout dans les 6 mois.
  Savent ce qu'il faut faire mais ne le font pas.
  Le détail qui change tout : le lundi matin dans le miroir,
  la promesse qu'ils se font et qu'ils savent déjà qu'ils vont briser.

TEMPLATE À REMPLIR :
  [Profil démographique précis].
  [Niveau d'expérience dans le domaine].
  [Ce qu'ils savent faire / Ce qui leur manque].
  [Ce qu'ils ont déjà essayé sans résultat].
  Le détail qui change tout : [moment émotionnel précis et privé].


================================================================
SECTION 3 — LA VOIX ET LE TON
================================================================

Définit COMMENT sonne la voix. Chaque adjectif doit être opposé
à son contraire pour être utile.

FORMAT OBLIGATOIRE :
  [Adjectif positif] sans être [son excès négatif].
  Exemple : "Directe sans être brutale."
  Exemple : "Intime sans être molle."
  Exemple : "Précise sans être froide."

LISTE D'OPPOSÉS UTILES :
  Direct / Brutal
  Intime / Mou
  Précis / Froid
  Autoritaire / Arrogant
  Passionné / Hystérique
  Calme / Endormi
  Urgence / Manipulation
  Profond / Prétentieux
  Simple / Simplet
  Émotionnel / Mélodramatique

TEST DE LA VOIX :
  Si tu retires tout l'enseignement — le spectateur se sent-il compris ?
  Si tu retires toute l'émotion — a-t-il appris quelque chose de concret ?
  Les deux ensemble = la voix est juste.

TEMPLATE À REMPLIR :
  Cette voix est [adjectif] sans être [excès].
  [Adjectif] sans être [excès].
  [Adjectif] sans être [excès].
  Chaque phrase sonne comme quelqu'un qui parle à une vraie personne
  dans la même pièce. Pas à une caméra. À lui. Directement.


================================================================
SECTION 4 — LES LOIS DE RYTHME
================================================================

C'est la règle la plus importante. Elle s'applique à chaque paragraphe.

LA LOI DU RYTHME VIVANT :
  Chaque paragraphe suit ce schéma :
  — Phrase courte percutante (maximum 8 mots) pour ouvrir
  — Une ou deux phrases longues (15 à 20 mots) pour développer
  — Phrase courte mémorable (maximum 8 mots) pour fermer

RYTHME MORT (interdit) :
  "Tu perds. Tu souffres. Tu recommences. Tu te promets."
  Ce rythme haché tue l'écoute. Signal d'un script générique.

RYTHME VIVANT (obligatoire) :
  "Tu perds. Mais ce n'est pas la perte qui te détruit vraiment —
  c'est la promesse que tu te fais juste après, celle que tu sais
  déjà que tu vas briser. C'est ce cycle-là. Pas le marché."

RÈGLE DE VÉRIFICATION :
  Avant de livrer chaque paragraphe — vérifie ce rythme.
  Si deux phrases courtes se suivent sans phrase longue — réécris.

NOTE POUR TOUTES LES NICHES :
  Cette loi du rythme vivant s'applique à toutes les niches.
  Elle ne change jamais. Seule la longueur maximale des phrases
  peut varier selon la niche (ex: niche story peut aller à 25 mots).


================================================================
SECTION 5 — LES LOIS D'ÉCRITURE
================================================================

Définit les règles de qualité phrase par phrase.

LES 5 LOIS UNIVERSELLES (à inclure dans toute formule) :

LOI 1 — JAMAIS LA PHRASE ÉVIDENTE
  Après chaque phrase, pose-toi la question : un scripteur ordinaire
  écrirait-il exactement cette suite ? Si oui — supprime. Réécris
  depuis un angle inattendu mais vrai.

LOI 2 — CHAQUE PHRASE SE GAGNE
  Zéro remplissage. Chaque phrase fait au moins une de ces 4 choses :
  - Enseigne quelque chose de précis
  - Crée une émotion inattendue
  - Fait avancer l'histoire en montant les enjeux
  - Recadre une croyance tenue pour acquise

LOI 3 — LA SPÉCIFICITÉ EST LA CRÉATIVITÉ
  Chaque histoire a un prénom unique, un montant exact, une durée précise.
  Pas "beaucoup d'argent" — "2 340 euros".
  Pas "longtemps" — "quatorze mois".
  Deux histoires spécifiques ne peuvent jamais être identiques.

LOI 4 — ÉCRIRE POUR L'OREILLE
  Maximum 20 mots par phrase longue. Le script sera lu à voix haute.
  Compte. Coupe si nécessaire. Jamais de phrases qui s'essoufflent.

LOI 5 — L'ÉMOTION SE MÉRITE
  Ne dis jamais au spectateur ce qu'il doit ressentir.
  Montre une situation tellement spécifique et vraie
  que l'émotion arrive d'elle-même.

LOIS SPÉCIFIQUES PAR NICHE (exemples) :

Pour niche FINANCE/TRADING :
  - Tous les montants en euros, jamais en dollars
  - Citer des vrais traders : Ed Seykota, Jesse Livermore, Paul Tudor Jones
  - Nommer des concepts psychologiques précis : aversion à la perte,
    biais de récence, effet de disposition, déplétion de l'ego
  - Réalisme sombre — jamais de promesses de richesse rapide

Pour niche HISTOIRE/MYSTÈRE :
  - Commencer par la conséquence, remonter à la cause
  - Maintenir la cohérence absolue des faits (noms, lieux, dates)
  - Révéler l'information au compte-gouttes — jamais tout d'un coup
  - Tension construite progressivement — pas d'explosions émotionnelles vides

Pour niche ÉDUCATION/EXPLAINER :
  - Commencer par remettre en question une croyance commune
  - Expliquer simplement des concepts complexes (jamais de jargon nu)
  - Un chiffre précis dans les 90 premières secondes
  - Construire la compréhension comme des marches — jamais de sauts

Pour niche DÉVELOPPEMENT PERSONNEL :
  - L'identité avant le comportement — toujours
  - Des exemples de vraies personnes, pas des archétypes génériques
  - La résistance avant la solution — ne pas promettre la facilité
  - Finir sur une action précise et immédiate, pas sur un principe vague


================================================================
SECTION 6 — LA STRUCTURE DU SCRIPT (ORDRE OBLIGATOIRE)
================================================================

Définit l'ordre exact des parties du script.
L'IA DOIT suivre cet ordre. Aucune déviation permise.

STRUCTURE UNIVERSELLE RECOMMANDÉE :
  1. LE HOOK
  2. PROMOTION 1
  3. LE CORPS
  4. PROMOTION 2
  5. LE CLIMAX
  6. PROMOTION 3
  7. LA CONCLUSION

VARIANTES PAR NICHE :

Pour niche STORY/HORREUR (pas de promotions visibles) :
  1. L'ENTRÉE (in medias res)
  2. LA MONTÉE
  3. LE PIVOT
  4. LE CLIMAX
  5. LA RÉSOLUTION (ou non-résolution intentionnelle)
  6. [Une seule promotion naturelle intégrée dans l'histoire]

Pour niche ÉDUCATION (structure pédagogique) :
  1. LE CHOC (croyance fausse détruite)
  2. PROMOTION 1 (rapide)
  3. LA PREUVE (pourquoi c'est vrai)
  4. LE MÉCANISME (comment ça fonctionne)
  5. PROMOTION 2
  6. L'APPLICATION (comment utiliser)
  7. LA CONCLUSION (action unique)

RÈGLE ABSOLUE DE STRUCTURE :
  Après la CONCLUSION — rien.
  Le script se termine avec la dernière phrase de la conclusion.
  Jamais de retour au corps après le climax.
  Jamais de nouvel enseignement après la conclusion.


================================================================
SECTION 7 — LES RÈGLES DE CHAQUE PARTIE
================================================================

Définit les règles spécifiques de chaque partie listée en Section 6.
Voici les règles pour chaque partie de la structure universelle.

---
LE HOOK — RÈGLES OBLIGATOIRES
---

Le hook n'est pas une introduction. C'est une collision.

PROCESSUS AVANT D'ÉCRIRE LE HOOK :
  Étape 1 : Trouve la vraie blessure émotionnelle derrière le titre.
  Étape 2 : Identifie le comportement privé et honteux de ce public.
  Étape 3 : Génère 3 angles d'entrée — rejette les 2 premiers.
  Étape 4 : Entre au milieu d'une action ou d'une sensation.
  Étape 5 : Applique le rythme vivant dès la première phrase.

LES 3 PORTES D'ENTRÉE DU HOOK (une seule par script) :
  Porte 1 — MENACE D'IDENTITÉ : décris leur comportement privé.
  Porte 2 — ÉCART DE CURIOSITÉ : montre ce qu'ils croient vs la réalité.
  Porte 3 — RECONNAISSANCE ÉMOTIONNELLE : décris leur vie privée précisément.

TEST DU HOOK :
  Ce hook pourrait-il ouvrir un script différent sur un autre sujet ?
  Si oui — réécris. La blessure spécifique du TITRE doit être là.

---
LES PROMOTIONS — RÈGLES OBLIGATOIRES
---

RÈGLE ABSOLUE : Chaque promotion se termine par le lien en description.
LONGUEUR : 5 à 8 phrases maximum. Jamais plus.

STRUCTURE DE CHAQUE PROMOTION :
  Phrase 1-2 : Nomme la douleur exacte activée par le contenu juste avant.
  Phrase 3-4 : Connecte cette douleur au produit directement.
  Phrase 5 : Pourquoi ce produit et pas autre chose — en une phrase.
  Phrase 6 : Lien en description (formulation différente à chaque promo).

INTERDITS ABSOLUS DANS LES PROMOTIONS :
  - Jamais de prix
  - Jamais "achetez maintenant"
  - Jamais de liste de fonctionnalités
  - Jamais de tactiques d'urgence ou de rareté
  - La formulation du lien doit être différente dans les 3 promotions

---
LE CORPS — RÈGLES OBLIGATOIRES
---

Le corps alterne TOUJOURS entre enseignement et histoire.
L'enseignement donne quelque chose à penser.
L'histoire donne quelque chose à ressentir.

ARC ÉMOTIONNEL OBLIGATOIRE (planifier avant d'écrire) :
  R — RECONNAISSANCE : ils se voient dans le miroir
  C — CURIOSITÉ : ils réalisent qu'il manque quelque chose
  E — ESPOIR : quelqu'un a résolu ce problème
  T — TENSION : c'est plus difficile qu'ils ne pensaient
  CL — CLARTÉ : une vérité simple se déverrouille

RÈGLE DE RESPIRATION :
  L'enseignement est l'inspiration.
  L'histoire est l'expiration.
  Jamais d'enseignement prolongé sans histoire pour l'ancrer.
  Jamais d'histoire sans en extraire un insight.

RÈGLE DES PRÉNOMS :
  Jamais le même prénom deux fois dans le même script.
  Chaque personnage a : un prénom unique, un marché spécifique,
  depuis combien de temps il trade/pratique, un chiffre précis.

---
LE CLIMAX — RÈGLES OBLIGATOIRES
---

LONGUEUR : 8 à 12 phrases maximum. Pas une de plus.

TYPES DE CLIMAX (un seul par script) :
  Le Recadrage : leur douleur vue sous un angle radicalement différent.
  L'Adresse Directe : tu leur dis ce dont ils ont besoin d'entendre.
  La Vérité Silencieuse : quelque chose de simple qu'ils savaient sans l'admettre.

RÈGLES DU CLIMAX :
  - Parle directement avec "tu"
  - Ne reprend AUCUNE idée déjà dite dans le corps
  - Dernière phrase = la plus courte et la plus mémorable
  - Lu à voix haute — tu dois ressentir quelque chose

---
LA CONCLUSION — RÈGLES OBLIGATOIRES
---

LONGUEUR : 3 à 5 phrases maximum.
Elle ne résume pas. Elle ne répète pas. Elle ne réenseigne pas.
Elle laisse le spectateur avec une seule chose à faire ou ressentir.
Après la conclusion — rien. Le script est terminé.


================================================================
SECTION 8 — LES INTERDITS ABSOLUS
================================================================

Définit les phrases et patterns que l'IA ne doit JAMAIS utiliser.

PHRASES MORTES UNIVERSELLES (à mettre dans toute formule) :
  "Vous allez découvrir..." — écris le contenu directement
  "Je vais vous montrer..." — écris le contenu directement
  "Sans plus attendre..." — commence au milieu de l'action
  "Dans cette vidéo je vais..." — commence au milieu de l'action
  "Soyons honnêtes..." — implique que tu ne l'étais pas avant
  "Laissez-moi vous expliquer..." — explique-le, c'est tout
  "Changeur de jeu" — vide et surutilisé
  "Libérez votre potentiel" — vide et surutilisé

ADVERBES INTERDITS (remplace par des faits) :
  Jamais "incroyablement douloureux" — écris combien de nuits sans sommeil
  Jamais "absolument catastrophique" — écris le montant exact perdu
  Jamais "remarquablement efficace" — écris le pourcentage sur combien de jours

RÈGLE ANTI-DUPLICATION :
  Aucune idée ne peut apparaître deux fois dans le même script.
  Pas même reformulée. Pas même résumée.
  Si le climax reprend une idée du corps — réécris le climax.
  Si la conclusion reprend une idée du climax — réécris la conclusion.


================================================================
PARTIE 3 — TEMPLATE VIERGE À REMPLIR
================================================================

Copie ce template, remplis chaque [SECTION] et colle-le
dans le champ "Script Formula" des settings.

--- DÉBUT DU TEMPLATE ---

================================================================
FORMULE DE NICHE — [NOM DE TA NICHE]
Langue : [Français / English / Arabe / etc.]
================================================================

QUI TU ES QUAND TU ÉCRIS
Tu n'es pas [rôle générique].
Tu es [expérience vécue crédible].
Tu parles depuis [position].
Ta voix a trois qualités : [qualité 1]. [qualité 2]. [qualité 3].
Jamais [refus 1].
Jamais [refus 2].

LE PUBLIC
[Profil démographique et niveau d'expérience].
[Ce qu'ils savent / Ce qui leur manque].
[Ce qu'ils ont essayé sans résultat].
Le détail qui change tout : [moment émotionnel précis].

LA VOIX
[Adjectif] sans être [excès].
[Adjectif] sans être [excès].
[Adjectif] sans être [excès].

LOI FONDAMENTALE — LE RYTHME VIVANT
Chaque paragraphe suit : Court (max [X] mots) → Long (15-20 mots) → Court (max [X] mots).
INTERDIT : deux phrases courtes consécutives.

LES LOIS D'ÉCRITURE
LOI 1 — [Ta loi spécifique niche #1]
LOI 2 — [Ta loi spécifique niche #2]
LOI 3 — LA SPÉCIFICITÉ : chaque chiffre est précis, chaque prénom est unique.
LOI 4 — ÉCRIRE POUR L'OREILLE : maximum [X] mots par phrase.

STRUCTURE DU SCRIPT — ORDRE FIXE
1. LE HOOK
2. PROMOTION 1
3. LE CORPS
4. PROMOTION 2
5. LE CLIMAX
6. PROMOTION 3
7. LA CONCLUSION

LE HOOK
[Décris les 3 portes émotionnelles possibles pour cette niche].
[Décris le processus de sélection du hook pour cette niche].
[Test : ce hook pourrait-il ouvrir un autre script ? Si oui — réécris.]

LES PROMOTIONS
Produit : [Nom du produit]
Description : [Description en 2 lignes maximum]
Règle absolue : chaque promotion se termine par le lien en description.
Longueur : 5 à 8 phrases maximum.
[Tes règles spécifiques pour les promotions de cette niche]

LE CORPS
Arc émotionnel obligatoire : R → C → E → T → CL
[Tes règles d'enseignement spécifiques à cette niche]
[Tes règles d'histoires spécifiques à cette niche]
[Prénoms à utiliser — jamais deux fois le même]

LE CLIMAX
Longueur : 8 à 12 phrases maximum.
[Tes règles de climax pour cette niche]
Dernière phrase = la plus courte et la plus mémorable.

LA CONCLUSION
Longueur : 3 à 5 phrases maximum.
[Ta règle de clôture pour cette niche]
Rien après la conclusion.

INTERDITS ABSOLUS
[Phrases mortes spécifiques à ta niche]
[Adverbes à remplacer par des faits]
Zéro duplication d'idées dans le même script.

--- FIN DU TEMPLATE ---


================================================================
PARTIE 4 — EXEMPLES DE FORMULES PAR NICHE
================================================================

NICHE : HORREUR / FAITS DIVERS / TRUE CRIME
  Voix : narrateur froid qui sait tout. Jamais dramatique.
  Public : amateurs de mystère. Veulent les faits, pas les émotions fabriquées.
  Rythme : court-long-court. Phrases longues peuvent aller à 25 mots.
  Structure : Entrée in medias res → Montée → Pivot → Climax → Non-résolution
  Hook : commence par le crime/événement, jamais par le contexte.
  Corps : faits chronologiques avec détails sensoriels précis.
  Climax : la révélation finale ou la question qui reste sans réponse.
  Interdits : "incroyable", "choquant", "vous n'allez pas croire".

NICHE : FINANCE PERSONNELLE / ÉPARGNE
  Voix : quelqu'un qui a mal géré son argent et reconstruit.
  Public : 25-40 ans. Revenus moyens. Dettes ou zéro épargne.
  Rythme : court-long-court. Maximum 18 mots par phrase longue.
  Structure : Hook → Promo 1 → Corps → Promo 2 → Climax → Promo 3 → Conclusion
  Hook : le chiffre embarrassant de leur compte en banque, décrit de l'intérieur.
  Corps : arc R-C-E-T-CL avec des exemples en euros, pas en dollars.
  Climax : la vérité sur pourquoi l'argent ne change pas avec un salaire plus élevé.
  Interdits : "richesse", "liberté financière", "investissement magique".

NICHE : MOTIVATION / PRODUCTIVITÉ
  Voix : quelqu'un qui a arrêté d'être motivé et a commencé à être discipliné.
  Public : entrepreneurs et freelances. 6h du matin et 23h sont leurs horaires.
  Rythme : court-long-court. Maximum 17 mots par phrase longue.
  Structure : Hook → Corps (sans promotions séparées — intégrées naturellement) → Climax → Conclusion
  Hook : le moment précis où ils ont réalisé que la motivation ne reviendrait pas.
  Corps : systèmes > motivation. Identité > comportement.
  Climax : la distinction entre discipline et punition.
  Interdits : "potentiel", "passion", "succès", "crois en toi".

NICHE : SANTÉ / FITNESS
  Voix : quelqu'un qui a essayé tous les régimes et trouvé la simplicité.
  Public : 30-50 ans. Emploi sédentaire. Enfants. Peu de temps.
  Rythme : court-long-court. Maximum 20 mots par phrase longue.
  Structure : Hook → Promo 1 → Corps → Promo 2 → Climax → Promo 3 → Conclusion
  Hook : le matin du lundi dans le miroir, la résolution brisée d'hier.
  Corps : biologie comportementale > volonté. Petites habitudes > grands efforts ponctuels.
  Climax : le corps ne punit pas la paresse — il s'adapte à ce qu'on lui montre chaque jour.
  Interdits : "transformation", "challenge", "détox", "brûle les graisses".


================================================================
PARTIE 5 — CHECKLIST AVANT DE SOUMETTRE TA FORMULE
================================================================

Vérifie ces points avant de coller ta formule dans les settings :

□ L'identité du scripteur est spécifique et crédible ?
□ Le public cible a un "détail émotionnel qui change tout" ?
□ La voix est définie avec des opposés (direct sans être brutal) ?
□ La loi du rythme vivant court-long-court est explicitement définie ?
□ Au moins 5 lois d'écriture sont listées ?
□ La structure liste les parties dans l'ordre exact ?
□ Les règles du hook incluent les 3 portes émotionnelles ?
□ Les promotions ont une longueur max (5-8 phrases) définie ?
□ Le climax a une longueur max (8-12 phrases) définie ?
□ La conclusion a une longueur max (3-5 phrases) définie ?
□ La règle "rien après la conclusion" est explicite ?
□ La règle anti-duplication est incluse ?
□ Les interdits absolus spécifiques à cette niche sont listés ?

Si une case est vide — complète avant de soumettre.
Une formule incomplète = scripts incomplèts.


================================================================
FIN DU GUIDE
================================================================
Pour toute question ou mise à jour de ce guide,
modifie directement ta formule dans Settings → Script Formula.
"""

    return Response(
        guide,
        mimetype='text/plain; charset=utf-8',
        headers={
            'Content-Disposition': 'attachment; filename="guide-formules-niche.txt"',
            'Content-Type': 'text/plain; charset=utf-8'
        }
    )


@app.route('/api/settings/voices', methods=['GET'])
def get_voices():
    """Get all available Inworld AI voices"""
    from settings_manager import SettingsManager

    try:
        voices = SettingsManager.get_all_voices()
        voice_settings = SettingsManager.get_voice_settings()

        return jsonify({
            'success': True,
            'voices': voices,
            'current_settings': voice_settings
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/settings/voice', methods=['POST'])
def save_voice_settings():
    """Save voice settings (default voice, speaking rate)"""
    from settings_manager import SettingsManager

    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'No data provided'}), 400

        default_voice = data.get('default_voice')
        speaking_rate = data.get('speaking_rate')

        # Save voice settings
        settings = SettingsManager.save_voice_settings(
            default_voice=default_voice,
            speaking_rate=speaking_rate
        )

        return jsonify({
            'success': True,
            'message': 'Voice settings saved successfully',
            'settings': settings
        })

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/settings/video', methods=['GET'])
def get_video_settings():
    """Get current video zoom settings"""
    from settings_manager import SettingsManager

    try:
        video_settings = SettingsManager.get_video_settings()

        return jsonify({
            'success': True,
            'settings': video_settings
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/settings/video', methods=['POST'])
def save_video_settings():
    """Save video zoom settings"""
    from settings_manager import SettingsManager

    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'No data provided'}), 400

        enable_timed_zoom = data.get('enable_timed_zoom')
        zoom_direction = data.get('zoom_direction')
        zoom_duration = data.get('zoom_duration')
        zoom_amount = data.get('zoom_amount')

        # Save video settings
        settings = SettingsManager.save_video_settings(
            enable_timed_zoom=enable_timed_zoom,
            zoom_direction=zoom_direction,
            zoom_duration=zoom_duration,
            zoom_amount=zoom_amount
        )

        return jsonify({
            'success': True,
            'message': 'Video settings saved successfully',
            'settings': settings
        })

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# =============================================================================
# MEDIA UPLOAD & PREVIEW ROUTES
# =============================================================================

@app.route('/api/upload-media', methods=['POST'])
def upload_media_route():
    """Upload multiple media files"""
    import time

    try:
        files = request.files.getlist('files')
        media_type = request.form.get('type', 'image')

        if not files:
            return jsonify({'error': 'No files provided'}), 400

        uploaded_files = []

        for file in files:
            if file.filename == '':
                continue

            # Generate unique filename
            timestamp = int(time.time() * 1000)
            ext = file.filename.rsplit('.', 1)[1].lower()
            filename = f"{media_type}_{timestamp}_{len(uploaded_files)}.{ext}"
            filepath = os.path.join(UPLOAD_FOLDER, filename)

            file.save(filepath)
            uploaded_files.append(filepath)

        return jsonify({
            'success': True,
            'files': uploaded_files,
            'count': len(uploaded_files)
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/preview-image/<filename>', methods=['GET'])
def preview_image_route(filename):
    """Serve image for preview"""
    try:
        # Search in output/images subdirectories
        images_base = 'output/images'

        if os.path.exists(images_base):
            for subdir in os.listdir(images_base):
                subdir_path = os.path.join(images_base, subdir)
                if os.path.isdir(subdir_path):
                    image_path = os.path.join(subdir_path, filename)
                    if os.path.exists(image_path):
                        return send_file(image_path, mimetype='image/jpeg')

        # Also check uploads folder
        upload_path = os.path.join(UPLOAD_FOLDER, filename)
        if os.path.exists(upload_path):
            return send_file(upload_path, mimetype='image/jpeg')

        # Check stock folder
        stock_path = os.path.join('output/stock', filename)
        if os.path.exists(stock_path):
            return send_file(stock_path, mimetype='image/jpeg')

        return jsonify({'error': 'Image not found'}), 404

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/preview-video/<filename>', methods=['GET'])
def preview_video_route(filename):
    """Serve video for preview"""
    try:
        # Check output folder
        output_path = os.path.join(OUTPUT_FOLDER, filename)
        if os.path.exists(output_path):
            return send_file(output_path, mimetype='video/mp4')

        # Check uploads folder
        upload_path = os.path.join(UPLOAD_FOLDER, filename)
        if os.path.exists(upload_path):
            return send_file(upload_path, mimetype='video/mp4')

        # Check stock folder
        stock_path = os.path.join('output/stock', filename)
        if os.path.exists(stock_path):
            return send_file(stock_path, mimetype='video/mp4')

        # Check edited folder
        edited_path = os.path.join('output/edited', filename)
        if os.path.exists(edited_path):
            return send_file(edited_path, mimetype='video/mp4')

        return jsonify({'error': 'Video not found'}), 404

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/preview-audio/<filename>', methods=['GET'])
def preview_audio_route(filename):
    """Serve audio for preview"""
    try:
        # Check voices folder
        voices_path = os.path.join('output/voices', filename)
        if os.path.exists(voices_path):
            return send_file(voices_path, mimetype='audio/mpeg')

        # Check uploads folder
        upload_path = os.path.join(UPLOAD_FOLDER, filename)
        if os.path.exists(upload_path):
            return send_file(upload_path, mimetype='audio/mpeg')

        return jsonify({'error': 'Audio not found'}), 404

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/editor/process', methods=['POST'])
def editor_process_route():
    """
    Process video from MR BAHA Editor timeline

    Request JSON:
        {
            "clips": [
                {"id": "clip1", "start": 0, "end": 10, "videoPath": "uploads/video.mp4"},
                {"id": "clip2", "start": 10, "end": 20, "videoPath": "uploads/video.mp4", "overlay": {...}}
            ],
            "quality": "720" or "1080"
        }

    Response:
        {
            "success": true,
            "output_path": "output/edited/edited_video_123.mp4",
            "message": "Video exported successfully"
        }
    """
    try:
        data = request.json
        clips = data.get('clips', [])
        quality = data.get('quality', '720')

        if not clips:
            return jsonify({'success': False, 'error': 'No clips provided'}), 400

        # Create output directory
        output_dir = 'output/edited'
        ensure_directory_exists(output_dir)

        # Generate unique output filename
        timestamp = int(time.time() * 1000)
        output_filename = f'edited_video_{timestamp}.mp4'
        output_path = os.path.join(output_dir, output_filename)

        # Process each clip
        temp_clips = []
        temp_dir = TEMP_FOLDER

        for i, clip in enumerate(clips):
            # Support both 'path' (frontend) and 'videoPath' (legacy) field names
            clip_path = clip.get('path', clip.get('videoPath', ''))
            clip_type = clip.get('type', 'video')
            start_time = clip.get('start', 0)
            end_time = clip.get('end', 0)
            duration = end_time - start_time

            if not os.path.exists(clip_path):
                continue

            # Extract clip segment
            temp_clip = os.path.join(temp_dir, f'clip_{i}.mp4')

            if clip_type == 'image':
                # Convert image to video clip at specified duration
                cmd = [
                    'ffmpeg', '-y',
                    '-loop', '1',
                    '-framerate', '2',
                    '-i', clip_path,
                    '-t', str(duration),
                    '-vf', 'scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2',
                    '-c:v', 'libx264',
                    '-preset', 'fast',
                    '-tune', 'stillimage',
                    '-crf', '23',
                    '-an',
                    temp_clip
                ]
            else:
                # Extract video segment
                cmd = [
                    'ffmpeg', '-y',
                    '-i', clip_path,
                    '-ss', str(start_time),
                    '-t', str(duration),
                    '-vf', 'scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30',
                    '-c:v', 'libx264',
                    '-preset', 'fast',
                    '-crf', '23',
                    '-c:a', 'aac',
                    '-b:a', '128k',
                    temp_clip
                ]

            subprocess.run(cmd, check=True, capture_output=True)

            # Add overlay if present
            if 'overlay' in clip:
                overlay = clip['overlay']
                text = overlay.get('text', '')
                x = overlay.get('x', 100)
                y = overlay.get('y', 100)
                size = overlay.get('size', 48)
                color = overlay.get('color', 'white')

                overlay_clip = os.path.join(temp_dir, f'overlay_{i}.mp4')

                cmd = [
                    'ffmpeg', '-y',
                    '-i', temp_clip,
                    '-vf', f"drawtext=text='{text}':fontsize={size}:fontcolor={color}:x={x}:y={y}",
                    '-c:a', 'copy',
                    overlay_clip
                ]

                subprocess.run(cmd, check=True, capture_output=True)
                temp_clips.append(overlay_clip)
            else:
                temp_clips.append(temp_clip)

        # Concatenate all clips
        if temp_clips:
            # Create concat file
            concat_file = os.path.join(temp_dir, f'concat_{timestamp}.txt')
            with open(concat_file, 'w') as f:
                for clip in temp_clips:
                    f.write(f"file '{os.path.abspath(clip)}'\n")

            # Final concatenation - clips are already at target resolution, use stream copy
            cmd = [
                'ffmpeg', '-y',
                '-f', 'concat',
                '-safe', '0',
                '-i', concat_file,
                '-c:v', 'copy',
                '-c:a', 'aac',
                '-b:a', '192k',
                '-movflags', '+faststart',
                output_path
            ]

            subprocess.run(cmd, check=True, capture_output=True)

            # Cleanup temp files
            for clip in temp_clips:
                if os.path.exists(clip):
                    os.remove(clip)
            if os.path.exists(concat_file):
                os.remove(concat_file)

            return jsonify({
                'success': True,
                'output_path': output_path,
                'message': 'Video exported successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'No valid clips to process'
            }), 400

    except subprocess.CalledProcessError as e:
        return jsonify({
            'success': False,
            'error': f'FFmpeg error: {e.stderr.decode() if e.stderr else str(e)}'
        }), 500
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/list-voices', methods=['GET'])
def list_voices_route():
    """
    Fetch available English voices from Inworld TTS API.
    Query param: model_id (optional, for filtering - currently Inworld returns same voices for both models)
    """
    import base64
    import requests as req
    from config import Config

    try:
        api_key = Config.get_inworld_api_key()
        api_secret = Config.get_inworld_api_secret()

        if not api_key or not api_secret:
            return jsonify({'success': False, 'error': 'Inworld API credentials not configured'}), 400

        auth_string = f"{api_key}:{api_secret}"
        base64_auth = base64.b64encode(auth_string.encode('ascii')).decode('ascii')
        headers = {
            'Authorization': f'Basic {base64_auth}',
            'Content-Type': 'application/json'
        }

        response = req.get(
            'https://api.inworld.ai/tts/v1/voices?filter=language=en',
            headers=headers,
            timeout=15
        )

        if response.status_code != 200:
            return jsonify({'success': False, 'error': f'Inworld API error: {response.status_code}'}), 500

        data = response.json()
        voices = data.get('voices', [])

        # Normalize to simple list
        result = []
        for v in voices:
            voice_id = v.get('voiceId') or v.get('name', '')
            if voice_id:
                result.append({
                    'id': voice_id,
                    'displayName': v.get('displayName') or voice_id,
                    'gender': (v.get('voiceMetadata') or {}).get('gender', 'UNKNOWN'),
                })

        return jsonify({'success': True, 'voices': result})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/preview-voice', methods=['POST'])
def preview_voice_route():
    """
    Generate a short voice preview (~5 seconds) for the selected voice.
    Request JSON: { voice_id, model_id, language }
    """
    import base64 as b64
    import requests as req
    from config import Config

    PREVIEW_TEXT_EN = "Hello! This is a preview of how this voice sounds. I hope you enjoy the quality."
    PREVIEW_TEXT_FR = "Bonjour ! Voici un aperçu de cette voix. J'espère que vous apprécierez la qualité."

    try:
        data = request.get_json() or {}
        voice_id = data.get('voice_id', 'Olivia')
        model_id = data.get('model_id', 'inworld-tts-1.5-mini')
        language = data.get('language', 'en-US')

        preview_text = PREVIEW_TEXT_FR if language == 'fr-FR' else PREVIEW_TEXT_EN

        api_key = Config.get_inworld_api_key()
        api_secret = Config.get_inworld_api_secret()

        if not api_key or not api_secret:
            return jsonify({'success': False, 'error': 'Inworld API credentials not configured'}), 400

        auth_string = f"{api_key}:{api_secret}"
        base64_auth = b64.b64encode(auth_string.encode('ascii')).decode('ascii')
        headers = {
            'Authorization': f'Basic {base64_auth}',
            'Content-Type': 'application/json'
        }

        payload = {
            'text': preview_text,
            'voice_id': voice_id,
            'language': language,
            'audio_config': {
                'audio_encoding': 'MP3',
                'speaking_rate': 1.0
            },
            'temperature': 1.1,
            'model_id': model_id
        }

        response = req.post(
            'https://api.inworld.ai/tts/v1/voice',
            headers=headers,
            json=payload,
            timeout=30
        )

        if response.status_code != 200:
            return jsonify({'success': False, 'error': f'Inworld API error: {response.status_code} - {response.text}'}), 500

        response_data = response.json()
        audio_b64 = response_data.get('audioContent')
        if not audio_b64:
            return jsonify({'success': False, 'error': 'No audio returned'}), 500

        return jsonify({'success': True, 'audio_base64': audio_b64, 'voice_id': voice_id})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/generate-voice', methods=['POST'])
def generate_voice_route():
    """
    Generate AI voice using Inworld AI TTS

    Request JSON:
        {
            'script': 'Text to convert to speech',
            'voice_id': 'inworld-voice-1',  # optional, Inworld voice ID
            'model_id': 'inworld-tts-1.5-max'  # optional, TTS model (max or mini)
        }

    Response:
        {
            'success': True,
            'audio_url': '/api/download/voice_xxx.mp3',
            'audio_filename': 'voice_xxx.mp3',
            'duration_seconds': 123.45,
            'chunks_count': 5,
            'generation_time': 67.8
        }
    """
    from voice_generator import VoiceGenerator
    from config import Config
    import time
    import os

    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'No data provided'}), 400

        script = data.get('script', '').strip()
        voice_id = data.get('voice_id', 'Olivia')  # Default to Olivia voice
        model_id = data.get('model_id', 'inworld-tts-1.5-max')
        language = data.get('language', 'en-US')  # Default to English
        speaking_rate = float(data.get('speaking_rate', 1.0))  # Default to normal speed

        if not script:
            return jsonify({'error': 'Script text is required'}), 400

        # Validate Inworld API credentials
        api_key = Config.get_inworld_api_key()
        api_secret = Config.get_inworld_api_secret()

        if not api_key or not api_secret:
            return jsonify({
                'error': 'Inworld API credentials not configured. Please add your Inworld API Key and Secret in Settings.'
            }), 500

        # Generate output filename
        timestamp = int(time.time())
        audio_filename = f"voice_{timestamp}.mp3"
        audio_path = os.path.join(OUTPUT_FOLDER, audio_filename)

        print(f"\n🎙️ Starting voice generation...")
        print(f"   Script length: {len(script):,} characters")
        print(f"   Voice: {voice_id}")
        print(f"   Model: {model_id}")
        print(f"   Language: {language}")
        print(f"   Speaking rate: {speaking_rate}x")
        print(f"   Output: {audio_filename}")

        # Generate voice using Inworld AI TTS
        generator = VoiceGenerator(api_key=api_key, api_secret=api_secret)
        result = generator.generate_voice(
            script=script,
            output_path=audio_path,
            voice_id=voice_id,
            model_id=model_id,
            language=language,
            speaking_rate=speaking_rate,
            verbose=True
        )

        return jsonify({
            'success': True,
            'audio_url': f'/api/download/{audio_filename}',
            'audio_filename': audio_filename,
            'audio_path': audio_path,
            'duration_seconds': result['duration_seconds'],
            'chunks_count': result['chunks_count'],
            'generation_time': result['generation_time']
        })

    except ValueError as e:
        # Configuration or validation error
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
    except Exception as e:
        # Other errors (API errors, network errors, etc.)
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/assemble-video', methods=['POST'])
def assemble_video_route():
    """
    Assemble final video from voice + media
    Video duration will match voice duration exactly

    Request JSON:
        {
            'voice_path': 'output/voice_123.mp3',  # Path to voice audio
            'media_paths': [                        # Media files in order
                'output/images/img1.jpg',
                'output/images/img2.jpg',
                'uploads/video1.mp4'
            ],
            'title': 'My Video',                   # Optional title for filename
            'resolution': '1920x1080'              # Optional resolution
        }

    Response:
        {
            'success': True,
            'output_path': 'output/final_video_123.mp4',
            'output_filename': 'final_video_123.mp4',
            'duration_seconds': 780.5,
            'duration_formatted': '13m 0s',
            'file_size_mb': 125.4,
            'processing_time': 45.2,
            'media_count': 12,
            'voice_duration': 780.5
        }
    """
    from video_assembler import VideoAssembler
    import time

    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'No data provided'}), 400

        # Support both single voice and multiple voices (ranked)
        voice_paths = data.get('voice_paths', [])
        if not voice_paths:
            # Fallback to old single voice format
            single_voice = data.get('voice_path')
            if single_voice:
                voice_paths = [single_voice]

        media_paths = data.get('media_paths', [])
        title = data.get('title', 'video')
        resolution = data.get('resolution', '1920x1080')
        background_music_path = data.get('background_music_path')  # Optional
        use_ken_burns = data.get('use_ken_burns', False)  # Optional Ken Burns zoom effect

        if not voice_paths or len(voice_paths) == 0:
            return jsonify({'error': 'At least one voice is required (voice_paths array)'}), 400

        # Verify all voice files exist
        missing_voices = []
        for voice_path in voice_paths:
            if not os.path.exists(voice_path):
                missing_voices.append(voice_path)

        if missing_voices:
            return jsonify({
                'error': f'Voice files not found: {", ".join(missing_voices)}'
            }), 404

        if not media_paths or len(media_paths) == 0:
            return jsonify({'error': 'At least one media file is required'}), 400

        # Verify all media files exist
        missing_files = []
        for media_path in media_paths:
            if not os.path.exists(media_path):
                missing_files.append(media_path)

        if missing_files:
            return jsonify({
                'error': f'Media files not found: {", ".join(missing_files)}'
            }), 404

        # Generate output filename
        import re
        safe_title = re.sub(r'[^a-z0-9]', '_', title.lower())[:50]
        timestamp = int(time.time())
        output_filename = f"final_{safe_title}_{timestamp}.mp4"
        output_path = os.path.join(OUTPUT_FOLDER, output_filename)

        print(f"\n🎬 Starting video assembly...")
        print(f"   Voices: {len(voice_paths)} ranked voice(s)")
        print(f"   Media files: {len(media_paths)}")
        print(f"   Output: {output_filename}")

        # Step 1: Merge voices if multiple (in ranked order)
        if len(voice_paths) > 1:
            print(f"\n🎵 Merging {len(voice_paths)} voices in ranked order...")
            merged_voice_path = os.path.join(TEMP_FOLDER, f"merged_voice_{timestamp}.mp3")

            # Create concat file for FFmpeg
            concat_file = os.path.join(TEMP_FOLDER, f"voice_concat_{timestamp}.txt")
            with open(concat_file, 'w') as f:
                for vp in voice_paths:
                    f.write(f"file '{os.path.abspath(vp)}'\n")

            # Merge voices using FFmpeg concat
            merge_cmd = [
                'ffmpeg', '-y',
                '-f', 'concat',
                '-safe', '0',
                '-i', concat_file,
                '-c', 'copy',
                merged_voice_path
            ]

            result_merge = subprocess.run(merge_cmd, capture_output=True, text=True)
            if result_merge.returncode != 0:
                raise Exception(f"Failed to merge voices: {result_merge.stderr}")

            print(f"   ✅ Voices merged successfully")
            final_voice_path = merged_voice_path
        else:
            final_voice_path = voice_paths[0]

        # Step 2: Assemble video with merged voice
        assembler = VideoAssembler(
            output_dir=OUTPUT_FOLDER,
            temp_dir=TEMP_FOLDER
        )

        result = assembler.assemble_final_video(
            voice_path=final_voice_path,
            media_paths=media_paths,
            output_path=output_path,
            resolution=resolution,
            background_music_path=background_music_path,
            use_ken_burns=use_ken_burns,
            verbose=True
        )

        # Format duration for response
        duration_minutes = int(result['duration_seconds'] // 60)
        duration_seconds = int(result['duration_seconds'] % 60)
        duration_formatted = f"{duration_minutes}m {duration_seconds}s"

        return jsonify({
            'success': True,
            'output_path': output_path,
            'output_filename': output_filename,
            'download_url': f'/api/download/{output_filename}',
            'duration_seconds': result['duration_seconds'],
            'duration_formatted': duration_formatted,
            'file_size_mb': result['file_size_mb'],
            'processing_time': result['processing_time'],
            'media_count': result['media_count'],
            'voice_duration': result['voice_duration']
        })

    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# =============================================================================
# AUTO IMAGES AI - SEPARATE DIRECTOR GEMINI + REPLICATE
# =============================================================================

@app.route('/api/auto-images/generate', methods=['POST'])
def auto_images_generate():
    """
    Generate images using Auto Images AI system

    Request JSON:
        {
            'script': 'Full script text',
            'style_id': 'cinematic',
            'n_images': 10,
            'aspect_ratio': '16:9',
            'force_regenerate': false,
            'use_whisper_timing': false,  # Optional: Use Whisper STT for perfect timing
            'voice_path': 'output/voice_123.mp3'  # Required if use_whisper_timing=true
        }

    Response:
        {
            'success': True,
            'plan': {...},
            'timeline': {...},
            'stats': {...},
            'whisper_used': false
        }
    """
    from auto_images import DirectorClient, ImageGenerator, TimelineManager
    from auto_images.schema import AutoImagesPlan
    from config import Config
    from auto_images_style_manager import AutoImagesStyleManager

    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'No data provided'}), 400

        script = data.get('script', '').strip()
        style_id = data.get('style_id', 'cinematic')
        n_images = data.get('n_images', 10)
        aspect_ratio = data.get('aspect_ratio', '16:9')
        force_regenerate = data.get('force_regenerate', False)
        use_whisper_timing = data.get('use_whisper_timing', False)
        voice_path = data.get('voice_path')

        if not script:
            return jsonify({'error': 'Script is required'}), 400

        if n_images < 1 or n_images > 100:
            return jsonify({'error': 'n_images must be between 1 and 100'}), 400

        # Validate Whisper timing requirements
        if use_whisper_timing:
            if not voice_path:
                return jsonify({'error': 'voice_path is required when use_whisper_timing=true'}), 400
            if not os.path.exists(voice_path):
                return jsonify({'error': f'Voice file not found: {voice_path}'}), 404

        # Get style config
        style = AutoImagesStyleManager.get_style(style_id)
        if not style:
            return jsonify({'error': f'Style not found: {style_id}'}), 404

        # Get API keys
        director_api_key = Config.get_director_gemini_api_key()
        replicate_token = Config.get_replicate_api_token()

        if not director_api_key:
            return jsonify({'error': 'Director Gemini API key not configured'}), 500
        if not replicate_token:
            return jsonify({'error': 'Replicate API token not configured'}), 500

        print(f"\n{'='*60}")
        print(f"🎨 AUTO IMAGES AI - GENERATION")
        print(f"{'='*60}")

        # Step 0 (Optional): Whisper STT for perfect timing
        scene_timing_hints = None
        if use_whisper_timing:
            try:
                from whisper_stt import WhisperSTT

                print(f"\n🎤 WHISPER STT - Perfect Timing")
                whisper = WhisperSTT(model_size="base")
                result = whisper.transcribe_with_timestamps(
                    audio_path=voice_path,
                    verbose=True
                )

                # Create N scenes from timestamps
                scenes_with_timing = whisper.create_n_scenes(
                    segments=result['segments'],
                    n_images=n_images,
                    total_duration=result['segments'][-1]['end'] if result['segments'] else 0,
                    verbose=True
                )

                # Create timing hints for Director (what text is in each time window)
                scene_timing_hints = [
                    {
                        'scene_id': scene['scene_id'],
                        'start_time': scene['start'],
                        'end_time': scene['end'],
                        'duration': scene['duration'],
                        'text_content': scene['text']
                    }
                    for scene in scenes_with_timing
                ]

                print(f"   ✅ Created {len(scene_timing_hints)} scenes with perfect timing")

            except ImportError:
                print(f"   ⚠️ Whisper not installed. Install with: pip install openai-whisper")
                print(f"   ℹ️ Falling back to even distribution")
                use_whisper_timing = False
            except Exception as e:
                print(f"   ❌ Whisper transcription failed: {e}")
                print(f"   ℹ️ Falling back to even distribution")
                use_whisper_timing = False

        # Step 1: Plan with Director Gemini
        director = DirectorClient(
            api_key=director_api_key,
            model_name=Config.get_director_gemini_model()
        )

        # Load the editable Auto Images Formula
        from settings_manager import SettingsManager as _SM
        auto_images_formula = _SM.load_formula('auto_images')

        plan = director.plan_auto_images(
            script_text=script,
            style=style,
            n_images=n_images,
            scene_timing_hints=scene_timing_hints,
            force_regenerate=force_regenerate,
            verbose=True,
            formula=auto_images_formula,
        )

        # Step 2: Generate images with Replicate
        image_gen = ImageGenerator(
            api_token=replicate_token,
            max_workers=3
        )

        generated_items = image_gen.generate_images(
            plan=plan,
            aspect_ratio=aspect_ratio,
            verbose=True
        )

        # Step 3: Create timeline
        timeline_mgr = TimelineManager()
        timeline = timeline_mgr.create_timeline(
            items=generated_items,
            style_id=style_id,
            script_text=script,
            director_version=DirectorClient.DIRECTOR_VERSION
        )
        timeline_mgr.save_timeline(timeline)

        print(f"\n✅ AUTO IMAGES COMPLETE")
        print(f"   Generated: {len(generated_items)}/{n_images} images")
        print(f"   Timeline saved")
        print(f"{'='*60}\n")

        return jsonify({
            'success': True,
            'plan': plan.model_dump(),
            'timeline': timeline.model_dump(),
            'whisper_used': use_whisper_timing and scene_timing_hints is not None,
            'stats': {
                'requested': n_images,
                'generated': len(generated_items),
                'failed': n_images - len(generated_items)
            }
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/auto-images/timeline', methods=['GET'])
def auto_images_get_timeline():
    """Get current timeline"""
    from auto_images import TimelineManager

    try:
        timeline_mgr = TimelineManager()
        timeline = timeline_mgr.load_timeline()

        if timeline:
            return jsonify({
                'success': True,
                'timeline': timeline.model_dump()
            })
        else:
            return jsonify({
                'success': False,
                'error': 'No timeline found'
            }), 404

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/auto-images/timeline/add-local', methods=['POST'])
def auto_images_add_local():
    """
    Add local image to timeline

    Request JSON:
        {
            'image_path': '/path/to/image.jpg',
            'index': 5  # optional, null = append
        }
    """
    from auto_images import TimelineManager

    try:
        data = request.get_json()
        image_path = data.get('image_path')
        index = data.get('index')

        if not image_path:
            return jsonify({'error': 'image_path is required'}), 400

        timeline_mgr = TimelineManager()
        timeline = timeline_mgr.load_timeline()

        if not timeline:
            return jsonify({'error': 'No timeline found'}), 404

        timeline = timeline_mgr.add_local_image(timeline, image_path, index)

        return jsonify({
            'success': True,
            'timeline': timeline.model_dump()
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/auto-images/timeline/add-stock', methods=['POST'])
def auto_images_add_stock():
    """
    Add stock image to timeline

    Request JSON:
        {
            'image_path': '/path/to/stock.jpg',
            'index': 5  # optional, null = append
        }
    """
    from auto_images import TimelineManager

    try:
        data = request.get_json()
        image_path = data.get('image_path')
        index = data.get('index')

        if not image_path:
            return jsonify({'error': 'image_path is required'}), 400

        timeline_mgr = TimelineManager()
        timeline = timeline_mgr.load_timeline()

        if not timeline:
            return jsonify({'error': 'No timeline found'}), 404

        timeline = timeline_mgr.add_stock_image(timeline, image_path, index)

        return jsonify({
            'success': True,
            'timeline': timeline.model_dump()
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/auto-images/timeline/delete', methods=['POST'])
def auto_images_delete():
    """
    Delete image from timeline

    Request JSON:
        {
            'index': 5
        }
    """
    from auto_images import TimelineManager

    try:
        data = request.get_json()
        index = data.get('index')

        if index is None:
            return jsonify({'error': 'index is required'}), 400

        timeline_mgr = TimelineManager()
        timeline = timeline_mgr.load_timeline()

        if not timeline:
            return jsonify({'error': 'No timeline found'}), 404

        timeline = timeline_mgr.delete_image(timeline, index)

        return jsonify({
            'success': True,
            'timeline': timeline.model_dump()
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/auto-images/timeline/move', methods=['POST'])
def auto_images_move():
    """
    Move image in timeline

    Request JSON:
        {
            'old_index': 2,
            'new_index': 5
        }
    """
    from auto_images import TimelineManager

    try:
        data = request.get_json()
        old_index = data.get('old_index')
        new_index = data.get('new_index')

        if old_index is None or new_index is None:
            return jsonify({'error': 'old_index and new_index are required'}), 400

        timeline_mgr = TimelineManager()
        timeline = timeline_mgr.load_timeline()

        if not timeline:
            return jsonify({'error': 'No timeline found'}), 404

        timeline = timeline_mgr.move_image(timeline, old_index, new_index)

        return jsonify({
            'success': True,
            'timeline': timeline.model_dump()
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/auto-images/timeline/clear', methods=['POST'])
def auto_images_clear():
    """Clear timeline"""
    from auto_images import TimelineManager

    try:
        timeline_mgr = TimelineManager()
        success = timeline_mgr.clear_timeline()

        return jsonify({
            'success': success,
            'message': 'Timeline cleared' if success else 'No timeline to clear'
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/auto-images/styles', methods=['GET'])
def auto_images_get_styles():
    """Get all Auto Images styles"""
    from auto_images_style_manager import AutoImagesStyleManager

    try:
        styles = AutoImagesStyleManager.get_all_styles()
        return jsonify({
            'success': True,
            'styles': styles
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/auto-images/styles/<style_id>', methods=['GET'])
def auto_images_get_style(style_id):
    """Get specific Auto Images style"""
    from auto_images_style_manager import AutoImagesStyleManager

    try:
        style = AutoImagesStyleManager.get_style(style_id)
        if style:
            return jsonify({
                'success': True,
                'style': style
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Style not found'
            }), 404
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/auto-images/styles', methods=['POST'])
def auto_images_create_style():
    """
    Create new Auto Images style

    Request JSON:
        {
            'name': 'My Style',
            'description': 'Description of the style',
            'visual_rules': ['Rule 1', 'Rule 2', 'Rule 3'],
            'negative_rules': ['Avoid 1', 'Avoid 2'],
            'composition': 'Composition approach',
            'lighting': 'Lighting style',
            'color_palette': ['Color 1', 'Color 2', 'Color 3']
        }
    """
    from auto_images_style_manager import AutoImagesStyleManager

    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'No data provided'}), 400

        style = AutoImagesStyleManager.create_style(
            name=data.get('name', ''),
            description=data.get('description', ''),
            visual_rules=data.get('visual_rules', []),
            negative_rules=data.get('negative_rules', []),
            composition=data.get('composition', ''),
            lighting=data.get('lighting', ''),
            color_palette=data.get('color_palette', []),
            style_formula=data.get('style_formula', ''),
        )

        return jsonify({
            'success': True,
            'style': style
        })

    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/auto-images/styles/<style_id>', methods=['PUT'])
def auto_images_update_style(style_id):
    """
    Update existing Auto Images style (custom only)

    Request JSON: (all fields optional)
        {
            'name': 'Updated Name',
            'description': 'Updated description',
            'visual_rules': ['...'],
            'negative_rules': ['...'],
            'composition': '...',
            'lighting': '...',
            'color_palette': ['...']
        }
    """
    from auto_images_style_manager import AutoImagesStyleManager

    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'No data provided'}), 400

        style = AutoImagesStyleManager.update_style(
            style_id=style_id,
            name=data.get('name'),
            description=data.get('description'),
            visual_rules=data.get('visual_rules'),
            negative_rules=data.get('negative_rules'),
            composition=data.get('composition'),
            lighting=data.get('lighting'),
            color_palette=data.get('color_palette'),
            style_formula=data.get('style_formula'),
        )

        if style:
            return jsonify({
                'success': True,
                'style': style
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Style not found'
            }), 404

    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/auto-images/styles/<style_id>', methods=['DELETE'])
def auto_images_delete_style(style_id):
    """Delete Auto Images style (custom only)"""
    from auto_images_style_manager import AutoImagesStyleManager

    try:
        success = AutoImagesStyleManager.delete_style(style_id)

        if success:
            return jsonify({
                'success': True,
                'message': 'Style deleted'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Style not found or cannot delete built-in style'
            }), 404

    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# =============================================================================
# SEO GENERATOR
# =============================================================================


@app.route('/api/seo-generator', methods=['POST'])
def seo_generator():
    """
    Generate YouTube description + tags from title + script using Gemini.

    Request JSON:
        {
            'title': 'Video title',
            'script': 'Full script text',
            'link': 'https://...',          (optional)
            'formula_id': 'seo_abc123',     (optional — use a saved preset)
            'formula': 'Custom formula...'  (optional — inline override, highest priority)
        }
    """
    try:
        from settings_manager import SettingsManager
        from seo_formula_manager import SeoFormulaManager

        data = request.get_json() or {}
        title            = data.get('title', '').strip()
        script           = data.get('script', '').strip()
        link             = data.get('link', '').strip()
        formula_id       = data.get('formula_id', '').strip()
        formula_override = data.get('formula', '').strip()

        if not title and not script:
            return jsonify({'success': False, 'error': 'Provide at least a title or script'}), 400

        # Resolve formula: inline > named preset > default
        if formula_override:
            formula = formula_override
        elif formula_id:
            preset = SeoFormulaManager.get(formula_id)
            formula = preset['formula'] if preset else SeoFormulaManager.get_default_formula_text()
        else:
            formula = SeoFormulaManager.get_default_formula_text()

        # SEO Generator uses ONLY its own dedicated key. No fallback to other keys.
        gemini_key = Config.get_gemini_seo_api_key()
        if not gemini_key:
            return jsonify({'success': False, 'error': 'No SEO Generator API key configured. Add it in Settings → SEO Generator.'}), 400

        link_instruction = f'Include this link naturally in the description: {link}' if link else 'No product link provided — skip the CTA/link section.'

        prompt = f"""You are a professional YouTube SEO copywriter.

VIDEO TITLE: {title}

SCRIPT / CONTENT:
{script if script else '(no script provided — base description on the title only)'}

YOUR FORMULA / INSTRUCTIONS:
{formula}

LINK: {link_instruction}

OUTPUT: Return ONLY valid JSON — no markdown, no backticks, no extra text.
{{
  "description": "Full YouTube description following the formula",
  "tags": "tag1, tag2, tag3, ...",
  "language": "name of detected language (e.g. French, English, Arabic)"
}}

CRITICAL RULES:
- Tags MUST be comma-separated, total under 400 characters
- Description MUST directly reference and match the exact title
- Write description AND tags in the same language as the title/script
- If a link was provided, it MUST appear in the description
- Include realistic chapter timestamps (based on script flow)
"""

        import google.generativeai as genai
        genai.configure(api_key=gemini_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(prompt)
        raw = response.text.strip()

        if raw.startswith('```'):
            raw = raw.split('```')[1]
            if raw.startswith('json'):
                raw = raw[4:]
        raw = raw.strip().rstrip('`').strip()

        import json as _json
        result = _json.loads(raw)

        description = result.get('description', '')
        tags        = result.get('tags', '')
        language    = result.get('language', 'Unknown')

        if len(tags) > 400:
            tags = tags[:397].rsplit(',', 1)[0]

        return jsonify({
            'success': True,
            'description': description,
            'tags': tags,
            'language': language,
            'tags_length': len(tags),
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# SEO Formula Presets CRUD
@app.route('/api/seo-formulas', methods=['GET'])
def seo_formulas_list():
    """Get all saved SEO formula presets"""
    try:
        from seo_formula_manager import SeoFormulaManager
        return jsonify({'success': True, 'formulas': SeoFormulaManager.get_all()})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/seo-formulas', methods=['POST'])
def seo_formulas_create():
    """Create a new SEO formula preset"""
    try:
        from seo_formula_manager import SeoFormulaManager
        data = request.get_json() or {}
        preset = SeoFormulaManager.create(
            name=data.get('name', ''),
            formula=data.get('formula', ''),
        )
        return jsonify({'success': True, 'formula': preset})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/seo-formulas/<formula_id>', methods=['PUT'])
def seo_formulas_update(formula_id):
    """Update an existing SEO formula preset"""
    try:
        from seo_formula_manager import SeoFormulaManager
        data = request.get_json() or {}
        preset = SeoFormulaManager.update(
            formula_id=formula_id,
            name=data.get('name'),
            formula=data.get('formula'),
        )
        if preset:
            return jsonify({'success': True, 'formula': preset})
        return jsonify({'success': False, 'error': 'Preset not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/seo-formulas/<formula_id>', methods=['DELETE'])
def seo_formulas_delete(formula_id):
    """Delete an SEO formula preset"""
    try:
        from seo_formula_manager import SeoFormulaManager
        ok = SeoFormulaManager.delete(formula_id)
        return jsonify({'success': ok, 'error': None if ok else 'Not found'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# =============================================================================
# ERROR HANDLERS
# =============================================================================

@app.errorhandler(413)
def file_too_large(e):
    """Handle file too large error"""
    return jsonify({
        'error': 'File too large. Maximum size is 5GB'
    }), 413


@app.errorhandler(500)
def internal_error(e):
    """Handle internal server error"""
    return jsonify({
        'error': 'Internal server error',
        'message': str(e)
    }), 500


# =============================================================================
# TIMELINE EDITOR ENDPOINTS - MR BAHA EDITOR
# =============================================================================

@app.route('/api/timeline/trim', methods=['POST'])
def timeline_trim_clip():
    """
    Trim/cut a video clip

    Request:
        {
            "file_id": "unique-id",
            "start_time": 5.0,    # seconds
            "end_time": 15.0      # seconds
        }

    Response:
        {
            "success": true,
            "trimmed_file_id": "new-id",
            "duration": 10.0
        }
    """
    try:
        data = request.get_json()
        file_id = data.get('file_id')
        start_time = float(data.get('start_time', 0))
        end_time = float(data.get('end_time'))

        # Find input file
        input_file = None
        for file in os.listdir(UPLOAD_FOLDER):
            if file.startswith(file_id):
                input_file = os.path.join(UPLOAD_FOLDER, file)
                break

        if not input_file or not os.path.exists(input_file):
            return jsonify({'success': False, 'error': 'File not found'}), 404

        # Generate output file
        trimmed_id = str(uuid.uuid4())
        ext = os.path.splitext(input_file)[1]
        output_file = os.path.join(TEMP_FOLDER, f"{trimmed_id}_trimmed{ext}")

        # FFmpeg trim command
        duration = end_time - start_time
        cmd = [
            'ffmpeg', '-i', input_file,
            '-ss', str(start_time),
            '-t', str(duration),
            '-c', 'copy',
            '-y', output_file
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            return jsonify({
                'success': False,
                'error': 'Trim failed',
                'details': result.stderr
            }), 500

        return jsonify({
            'success': True,
            'trimmed_file_id': trimmed_id,
            'file_path': output_file,
            'duration': duration
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/timeline/image-to-video', methods=['POST'])
def timeline_image_to_video():
    """
    Convert image to video with specified duration

    Request:
        {
            "file_id": "image-id",
            "duration": 5.0  # seconds
        }

    Response:
        {
            "success": true,
            "video_file_id": "new-id",
            "duration": 5.0
        }
    """
    try:
        data = request.get_json()
        file_id = data.get('file_id')
        duration = float(data.get('duration', 5.0))

        # Find input image
        input_file = None
        for file in os.listdir(UPLOAD_FOLDER):
            if file.startswith(file_id):
                input_file = os.path.join(UPLOAD_FOLDER, file)
                break

        if not input_file or not os.path.exists(input_file):
            return jsonify({'success': False, 'error': 'Image not found'}), 404

        # Generate output video
        video_id = str(uuid.uuid4())
        output_file = os.path.join(TEMP_FOLDER, f"{video_id}_from_image.mp4")

        # FFmpeg command to create video from image
        cmd = [
            'ffmpeg',
            '-loop', '1',
            '-i', input_file,
            '-c:v', 'libx264',
            '-t', str(duration),
            '-pix_fmt', 'yuv420p',
            '-vf', 'scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2',
            '-r', '30',
            '-y', output_file
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            return jsonify({
                'success': False,
                'error': 'Image to video conversion failed',
                'details': result.stderr
            }), 500

        return jsonify({
            'success': True,
            'video_file_id': video_id,
            'file_path': output_file,
            'duration': duration
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/timeline/process', methods=['POST'])
def timeline_process():
    """
    Process entire timeline with clips, transitions, and effects

    Request:
        {
            "clips": [
                {
                    "file_id": "id1",
                    "type": "video",  # or "image"
                    "duration": 5.0,  # for images
                    "trim_start": 0,  # optional
                    "trim_end": 10,   # optional
                    "transition": "fade",  # fade, dissolve, wipe, slide, zoom, none
                    "transition_duration": 0.5
                },
                ...
            ],
            "audio_file_id": "audio-id",  # optional
            "output_quality": "1080"  # or "720"
        }

    Response:
        {
            "success": true,
            "output_file": "final_video.mp4",
            "download_url": "/api/download/..."
        }
    """
    try:
        data = request.get_json()
        clips_data = data.get('clips', [])
        audio_file_id = data.get('audio_file_id')
        quality = data.get('output_quality', '1080')

        print(f"\n🎬 ========== TIMELINE EXPORT STARTED ==========")
        print(f"📊 Received {len(clips_data)} clips to process")
        print(f"📊 Clips data: {clips_data}")

        if not clips_data:
            return jsonify({'success': False, 'error': 'No clips provided'}), 400

        # Process each clip (trim, convert images, etc.)
        processed_clips = []

        for idx, clip in enumerate(clips_data):
            file_id = clip['file_id']
            clip_type = clip['type']

            print(f"\n📦 Processing clip {idx+1}/{len(clips_data)}: {clip.get('filename', file_id)}")

            # Find input file
            input_file = None
            for file in os.listdir(UPLOAD_FOLDER):
                if file.startswith(file_id):
                    input_file = os.path.join(UPLOAD_FOLDER, file)
                    break

            # Also check TEMP folder
            if not input_file:
                for file in os.listdir(TEMP_FOLDER):
                    if file.startswith(file_id):
                        input_file = os.path.join(TEMP_FOLDER, file)
                        break

            if not input_file:
                print(f"⚠️ File not found for clip {idx+1}: {file_id}")
                continue

            print(f"✅ Found input file: {input_file}")

            processed_file = input_file

            # Convert image to video if needed
            if clip_type == 'image':
                duration = clip.get('duration', 5.0)
                temp_id = str(uuid.uuid4())
                video_file = os.path.join(TEMP_FOLDER, f"{temp_id}_clip{idx}.mp4")

                print(f"🖼️ Converting image to video ({duration}s)...")
                cmd = [
                    'ffmpeg',
                    '-loop', '1',
                    '-i', input_file,
                    '-c:v', 'libx264',
                    '-t', str(duration),
                    '-pix_fmt', 'yuv420p',
                    '-vf', 'scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2',
                    '-r', '30',
                    '-y', video_file
                ]

                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    print(f"❌ Image conversion failed: {result.stderr}")
                else:
                    print(f"✅ Image converted to video")
                processed_file = video_file

            # Trim if needed
            trim_start = clip.get('trim_start')
            trim_end = clip.get('trim_end')

            if trim_start is not None and trim_end is not None:
                trimmed_id = str(uuid.uuid4())
                trimmed_file = os.path.join(TEMP_FOLDER, f"{trimmed_id}_trimmed{idx}.mp4")
                duration = trim_end - trim_start

                print(f"✂️ Trimming: {trim_start}s to {trim_end}s (duration: {duration}s)")
                cmd = [
                    'ffmpeg', '-i', processed_file,
                    '-ss', str(trim_start),
                    '-t', str(duration),
                    '-c', 'copy',
                    '-y', trimmed_file
                ]

                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    print(f"❌ Trim failed: {result.stderr}")
                else:
                    print(f"✅ Trimmed successfully")
                processed_file = trimmed_file

            # Mute if needed
            is_muted = clip.get('muted', False)
            if is_muted and clip_type == 'video':
                muted_id = str(uuid.uuid4())
                muted_file = os.path.join(TEMP_FOLDER, f"{muted_id}_muted{idx}.mp4")

                cmd = [
                    'ffmpeg', '-i', processed_file,
                    '-an',  # Remove audio
                    '-c:v', 'copy',
                    '-y', muted_file
                ]

                subprocess.run(cmd, capture_output=True)
                processed_file = muted_file

            processed_clips.append({
                'file': processed_file,
                'transition': clip.get('transition', 'fade'),
                'transition_duration': clip.get('transition_duration', 0.5)
            })

        if not processed_clips:
            return jsonify({'success': False, 'error': 'No valid clips to process'}), 400

        print(f"\n🔗 Merging {len(processed_clips)} clips...")

        # Create concat file for FFmpeg
        concat_file = os.path.join(TEMP_FOLDER, f"concat_{uuid.uuid4()}.txt")
        with open(concat_file, 'w') as f:
            for clip in processed_clips:
                f.write(f"file '{os.path.abspath(clip['file'])}'\n")

        print(f"📝 Concat file created: {concat_file}")

        # Generate output file
        output_id = str(uuid.uuid4())
        output_file = os.path.join(OUTPUT_FOLDER, f"timeline_{output_id}.mp4")

        # Simple concat for now (advanced transitions need complex filter)
        if len(processed_clips) == 1:
            # Single clip - just copy
            cmd = [
                'ffmpeg', '-i', processed_clips[0]['file'],
                '-c', 'copy',
                '-y', output_file
            ]
        else:
            # Multiple clips - FAST concat using stream copy (no re-encoding!)
            # This is INSTANT for cuts and merges (no transcoding)
            cmd = [
                'ffmpeg',
                '-f', 'concat',
                '-safe', '0',
                '-i', concat_file,
                '-c', 'copy',  # STREAM COPY = INSTANT! No re-encoding
                '-y', output_file
            ]

        # Add audio if provided
        if audio_file_id:
            audio_file = None
            for file in os.listdir(UPLOAD_FOLDER):
                if file.startswith(audio_file_id):
                    audio_file = os.path.join(UPLOAD_FOLDER, file)
                    break

            if audio_file:
                # Re-encode with audio overlay
                temp_output = output_file.replace('.mp4', '_temp.mp4')
                os.rename(output_file, temp_output)

                cmd = [
                    'ffmpeg',
                    '-i', temp_output,
                    '-i', audio_file,
                    '-c:v', 'copy',
                    '-c:a', 'aac',
                    '-map', '0:v:0',
                    '-map', '1:a:0',
                    '-shortest',
                    '-y', output_file
                ]

                subprocess.run(cmd, capture_output=True)
                os.remove(temp_output)

        print(f"🎬 Running FFmpeg command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        print(f"✅ FFmpeg finished with return code: {result.returncode}")

        if result.returncode != 0:
            print(f"❌ FFmpeg error: {result.stderr}")
            return jsonify({
                'success': False,
                'error': 'Timeline processing failed',
                'details': result.stderr
            }), 500

        # Clean up temp files
        os.remove(concat_file)

        return jsonify({
            'success': True,
            'output_file': os.path.basename(output_file),
            'download_url': f'/api/download/{os.path.basename(output_file)}',
            'file_size': get_file_size(output_file)
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/timeline/merge', methods=['POST'])
def timeline_merge_clips():
    """
    Merge two clips with smooth transition

    Request:
        {
            "clip1_id": "id1",
            "clip2_id": "id2",
            "transition": "fade",  # fade, dissolve, wipe, slide, zoom
            "transition_duration": 1.0
        }

    Response:
        {
            "success": true,
            "merged_file_id": "new-id"
        }
    """
    try:
        data = request.get_json()
        clip1_id = data.get('clip1_id')
        clip2_id = data.get('clip2_id')
        transition = data.get('transition', 'fade')
        trans_duration = float(data.get('transition_duration', 1.0))

        # Find input files
        clip1_file = None
        clip2_file = None

        for file in os.listdir(UPLOAD_FOLDER):
            if file.startswith(clip1_id):
                clip1_file = os.path.join(UPLOAD_FOLDER, file)
            if file.startswith(clip2_id):
                clip2_file = os.path.join(UPLOAD_FOLDER, file)

        # Check TEMP folder too
        for file in os.listdir(TEMP_FOLDER):
            if not clip1_file and file.startswith(clip1_id):
                clip1_file = os.path.join(TEMP_FOLDER, file)
            if not clip2_file and file.startswith(clip2_id):
                clip2_file = os.path.join(TEMP_FOLDER, file)

        if not clip1_file or not clip2_file:
            return jsonify({'success': False, 'error': 'Clips not found'}), 404

        # Generate output
        merged_id = str(uuid.uuid4())
        output_file = os.path.join(TEMP_FOLDER, f"{merged_id}_merged.mp4")

        # Build transition filter based on type
        if transition == 'fade':
            # Crossfade transition
            filter_complex = (
                f"[0:v][1:v]xfade=transition=fade:duration={trans_duration}:offset=0[v];"
                f"[0:a][1:a]acrossfade=d={trans_duration}[a]"
            )
        elif transition == 'dissolve':
            filter_complex = (
                f"[0:v][1:v]xfade=transition=dissolve:duration={trans_duration}:offset=0[v];"
                f"[0:a][1:a]acrossfade=d={trans_duration}[a]"
            )
        elif transition == 'wipe':
            filter_complex = (
                f"[0:v][1:v]xfade=transition=wipeleft:duration={trans_duration}:offset=0[v];"
                f"[0:a][1:a]acrossfade=d={trans_duration}[a]"
            )
        elif transition == 'slide':
            filter_complex = (
                f"[0:v][1:v]xfade=transition=slideleft:duration={trans_duration}:offset=0[v];"
                f"[0:a][1:a]acrossfade=d={trans_duration}[a]"
            )
        else:
            # Simple concat for no transition
            filter_complex = "[0:v][0:a][1:v][1:a]concat=n=2:v=1:a=1[v][a]"

        cmd = [
            'ffmpeg',
            '-i', clip1_file,
            '-i', clip2_file,
            '-filter_complex', filter_complex,
            '-map', '[v]',
            '-map', '[a]',
            '-c:v', 'libx264',
            '-preset', 'fast',
            '-crf', '23',
            '-c:a', 'aac',
            '-y', output_file
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            # Fallback to simple concat if xfade fails
            concat_file = os.path.join(TEMP_FOLDER, f"concat_{merged_id}.txt")
            with open(concat_file, 'w') as f:
                f.write(f"file '{os.path.abspath(clip1_file)}'\n")
                f.write(f"file '{os.path.abspath(clip2_file)}'\n")

            cmd = [
                'ffmpeg',
                '-f', 'concat',
                '-safe', '0',
                '-i', concat_file,
                '-c', 'copy',
                '-y', output_file
            ]

            result = subprocess.run(cmd, capture_output=True)
            os.remove(concat_file)

        return jsonify({
            'success': True,
            'merged_file_id': merged_id,
            'file_path': output_file
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============================================================================
# AVATAR AI - Video generation with avatar loops + AI images/stock videos
# ============================================================================

@app.route('/api/avatar/generate', methods=['POST'])
def avatar_generate():
    """
    Generate avatar video with AI images or stock videos

    Body:
    {
        "avatar_video": "path/to/avatar.mp4",
        "audio": "path/to/audio.mp3",
        "mode": "ai_images" | "stock_videos",
        "script": "optional script for context",
        "stock_apis": ["pexels", "pixabay"]  // optional, for stock_videos mode
    }
    """
    try:
        from avatar_video_generator import AvatarVideoGenerator
        from avatar_video_assembler import AvatarVideoAssembler

        data = request.json

        avatar_video_path = data.get('avatar_video')
        audio_path = data.get('audio')
        mode = data.get('mode', 'ai_images')
        script = data.get('script', '')
        stock_apis = data.get('stock_apis', ['pexels'])
        use_whisper = data.get('use_whisper', False)  # Default: fast Gemini mode
        background_music_path = data.get('background_music_path')  # Optional
        image_provider = data.get('image_provider', 'gemini')  # 'replicate' or 'gemini'
        image_style = data.get('image_style', None)  # Style dict (or string ID) from frontend

        # Resolve string style ID to full style dict (backwards compat)
        if isinstance(image_style, str):
            try:
                from auto_images_style_manager import AutoImagesStyleManager
                style_mgr = AutoImagesStyleManager()
                resolved = style_mgr.get_style(image_style)
                if resolved:
                    image_style = resolved
            except Exception:
                pass

        if not avatar_video_path or not audio_path:
            return jsonify({
                'success': False,
                'error': 'avatar_video and audio are required'
            }), 400

        # CRITICAL: Script is REQUIRED so Gemini knows what media to place where
        if not script or len(script.strip()) < 50:
            return jsonify({
                'success': False,
                'error': 'Script is REQUIRED! Gemini needs the script text to know what videos/images to place at each timing. Please provide the full audio script.'
            }), 400

        # Validate mode
        if mode not in ['ai_images', 'stock_videos']:
            return jsonify({
                'success': False,
                'error': 'mode must be "ai_images" or "stock_videos"'
            }), 400

        print(f"\n🎬 AVATAR AI Generation Starting...")
        print(f"   Mode: {mode}")
        print(f"   Avatar: {avatar_video_path}")
        print(f"   Audio: {audio_path}")
        print(f"   Timing: {'Whisper STT (slow)' if use_whisper else 'Gemini Direct (fast)'}")

        # Step 1: Generate media plan
        generator = AvatarVideoGenerator()

        result = generator.generate_avatar_video(
            avatar_video_path=avatar_video_path,
            audio_path=audio_path,
            mode=mode,
            script=script,
            stock_apis=stock_apis,
            use_whisper=use_whisper,
            image_style=image_style,
            image_provider=image_provider,
            verbose=True
        )

        # Step 2: Assemble video
        assembler = AvatarVideoAssembler(
            temp_dir=TEMP_FOLDER,
            output_dir=OUTPUT_FOLDER  # Use same output folder as other videos
        )

        final_video = assembler.assemble_video(
            avatar_video_path=avatar_video_path,
            audio_path=audio_path,
            media_plan=result['media_plan'],
            media_items=result['media_items'],
            mode=mode,
            background_music_path=background_music_path,
            verbose=True
        )

        # Get just the filename for frontend
        video_filename = os.path.basename(final_video)

        return jsonify({
            'success': True,
            'video_path': video_filename,  # Just filename, not full path
            'media_plan': result['media_plan'],
            'audio_duration': result['audio_duration'],
            'generation_time': result['generation_time'],
            'mode': mode
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/avatar/upload-avatar', methods=['POST'])
def avatar_upload_avatar():
    """Upload avatar video and auto-mute it"""
    try:
        if 'avatar' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'}), 400

        file = request.files['avatar']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'}), 400

        # Save to upload folder
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"avatar_{timestamp}_{filename}"
        file_path = os.path.join(UPLOAD_FOLDER, filename)

        file.save(file_path)

        # Get video duration and auto-mute
        import subprocess

        # Get duration
        probe_cmd = [
            'ffprobe', '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            file_path
        ]
        duration_result = subprocess.run(probe_cmd, capture_output=True, text=True)
        duration = float(duration_result.stdout.strip()) if duration_result.stdout.strip() else 0

        # Auto-mute the video
        muted_filename = f"muted_{filename}"
        muted_path = os.path.join(UPLOAD_FOLDER, muted_filename)

        mute_cmd = [
            'ffmpeg', '-i', file_path,
            '-an',  # Remove audio
            '-c:v', 'copy',  # Copy video codec (no re-encoding)
            '-y',
            muted_path
        ]
        subprocess.run(mute_cmd, check=True, capture_output=True)

        # Remove original, keep muted version
        os.remove(file_path)

        return jsonify({
            'success': True,
            'path': muted_path,
            'filename': muted_filename,
            'duration': duration
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/avatar/upload-local-images', methods=['POST'])
def avatar_upload_local_images():
    """Upload multiple local images (all formats) for Local Images Mix."""
    import time as _time
    try:
        files = request.files.getlist('images')
        if not files:
            return jsonify({'success': False, 'error': 'No images provided'}), 400

        ALLOWED = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.tiff', '.avif'}
        saved = []
        for file in files:
            if not file or not file.filename:
                continue
            ext = os.path.splitext(file.filename)[1].lower()
            if ext not in ALLOWED:
                continue
            fname = secure_filename(file.filename)
            fname = f"localimg_{int(_time.time()*1000)}_{fname}"
            fpath = os.path.join(UPLOAD_FOLDER, fname)
            file.save(fpath)
            saved.append({'path': fpath, 'name': file.filename})

        if not saved:
            return jsonify({'success': False, 'error': 'No valid images found (check format)'}), 400

        return jsonify({'success': True, 'images': saved, 'count': len(saved)})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/avatar/generate-local-mix', methods=['POST'])
def avatar_generate_local_mix():
    """
    Generate avatar video mixed with user's local images.
    No AI generation — smart timing calc:
      Default: 30s avatar + 5s image per cycle.
      If images run out → avatar loops to end.
      If too many images → spacing compressed to fit all.
    """
    import subprocess as _sp
    import time as _time
    try:
        from avatar_video_assembler import AvatarVideoAssembler

        data = request.json or {}
        avatar_video_path = data.get('avatar_video')
        voice_paths       = data.get('voice_paths', [])
        audio_path        = data.get('audio') or (voice_paths[0] if voice_paths else None)
        image_paths       = data.get('image_paths', [])
        background_music  = data.get('background_music')

        if not avatar_video_path or not audio_path:
            return jsonify({'success': False, 'error': 'avatar_video and audio are required'}), 400
        if not image_paths:
            return jsonify({'success': False, 'error': 'At least one image_path is required'}), 400

        start_time = _time.time()

        # Merge multiple voice files if needed
        if len(voice_paths) > 1:
            merged = os.path.join(TEMP_FOLDER, f"merged_voice_{int(_time.time())}.mp3")
            cfile  = os.path.join(TEMP_FOLDER, f"voice_concat_{int(_time.time())}.txt")
            with open(cfile, 'w') as f:
                for vp in voice_paths:
                    f.write(f"file '{os.path.abspath(vp)}'\n")
            _sp.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0',
                     '-i', cfile, '-c', 'copy', merged],
                    check=True, capture_output=True)
            audio_path = merged

        # Get audio duration
        probe = _sp.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', audio_path],
            capture_output=True, text=True
        )
        total_duration = float(probe.stdout.strip())

        print(f"\n🖼️  LOCAL IMAGES MIX")
        print(f"   Audio: {total_duration:.1f}s | Images: {len(image_paths)}")

        # ── Smart timing ──────────────────────────────────────────────────────
        IMAGE_DUR   = 5.0   # seconds each image is shown
        DEFAULT_GAP = 30.0  # seconds of avatar between images (default)
        num_images  = len(image_paths)

        if num_images * (DEFAULT_GAP + IMAGE_DUR) <= total_duration:
            # Images fit comfortably; use default 30s gap, avatar loops at end
            avatar_gap = DEFAULT_GAP
        else:
            # Too many images: compress spacing so all fit
            cycle      = total_duration / num_images
            avatar_gap = max(3.0, cycle - IMAGE_DUR)

        print(f"   Cycle: {avatar_gap:.1f}s avatar + {IMAGE_DUR}s image")

        # ── Build segment list ────────────────────────────────────────────────
        segments    = []
        images_used = 0
        current     = 0.0

        while current < total_duration - 0.5:
            remaining = total_duration - current

            # If no more images or barely any time left → fill with avatar
            if images_used >= num_images or remaining <= IMAGE_DUR:
                segments.append({'type': 'avatar', 'duration': remaining})
                current = total_duration
                break

            # Avatar clip
            avt = min(avatar_gap, remaining)
            segments.append({'type': 'avatar', 'duration': avt})
            current += avt

            remaining = total_duration - current
            if remaining <= 0:
                break

            # Image clip
            img = min(IMAGE_DUR, remaining)
            segments.append({'type': 'ai_image', 'duration': img})
            current     += img
            images_used += 1

        # Tail: any leftover time → avatar
        if total_duration - current > 0.5:
            segments.append({'type': 'avatar', 'duration': total_duration - current})

        # ── Map images → segment indices ──────────────────────────────────────
        media_items = []
        img_idx = 0
        for seg_idx, seg in enumerate(segments):
            if seg['type'] == 'ai_image' and img_idx < num_images:
                media_items.append({'segment_index': seg_idx, 'path': image_paths[img_idx]})
                img_idx += 1

        media_plan = {'segments': segments}
        print(f"   Segments: {len(segments)} | Images placed: {images_used}")

        # ── Assemble with the same fast FFmpeg assembler ──────────────────────
        assembler = AvatarVideoAssembler(temp_dir=TEMP_FOLDER, output_dir=OUTPUT_FOLDER)
        final_video = assembler.assemble_video(
            avatar_video_path=avatar_video_path,
            audio_path=audio_path,
            media_plan=media_plan,
            media_items=media_items,
            mode='ai_images',          # reuses the image→video path
            background_music_path=background_music,
            verbose=True
        )

        return jsonify({
            'success': True,
            'video_path': os.path.basename(final_video),
            'audio_duration': total_duration,
            'images_used': images_used,
            'total_images': num_images,
            'segments_count': len(segments),
            'avatar_gap': avatar_gap,
            'generation_time': _time.time() - start_time
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/avatar/upload-audio', methods=['POST'])
def avatar_upload_audio():
    """Upload audio for avatar video"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'}), 400

        # Save to upload folder
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"avatar_audio_{timestamp}_{filename}"
        file_path = os.path.join(UPLOAD_FOLDER, filename)

        file.save(file_path)

        return jsonify({
            'success': True,
            'file_path': file_path,
            'filename': filename
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/avatar/status', methods=['GET'])
def avatar_status():
    """Get avatar generation status"""
    # TODO: Implement progress tracking if needed
    return jsonify({
        'success': True,
        'status': 'ready'
    })


@app.route('/api/check-script', methods=['GET'])
def check_script():
    """Check if a script file exists in the output folder"""
    try:
        import glob
        import os
        from datetime import datetime

        # Find all script files in output folder
        script_pattern = os.path.join(OUTPUT_FOLDER, 'script_*.txt')
        script_files = glob.glob(script_pattern)

        if not script_files:
            return jsonify({
                'success': True,
                'has_script': False
            })

        # Get the most recent script file
        most_recent_script = max(script_files, key=os.path.getmtime)

        # Read the script content
        with open(most_recent_script, 'r', encoding='utf-8') as f:
            script_content = f.read()

        # Get file stats
        file_stats = os.stat(most_recent_script)
        file_size = file_stats.st_size
        modified_time = datetime.fromtimestamp(file_stats.st_mtime)

        # Calculate stats
        char_count = len(script_content)
        word_count = len(script_content.split())

        return jsonify({
            'success': True,
            'has_script': True,
            'script': script_content,
            'script_filename': os.path.basename(most_recent_script),
            'length': char_count,
            'words': word_count,
            'file_size': file_size,
            'modified': modified_time.strftime('%Y-%m-%d %H:%M:%S')
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


ALAE_BAHA_PASSWORD = 'ALAEBMW'


@app.route('/api/alae-baha/saved-settings', methods=['GET'])
def alae_baha_saved_settings():
    """Return the actual saved API keys + formulas so the frontend form can be populated on startup.
    This runs on every page load so settings persist even if localStorage is cleared."""
    from settings_manager import SettingsManager
    try:
        settings = SettingsManager.load_settings()
        api_keys = settings.get('api_keys', {})
        return jsonify({
            'success': True,
            'api_keys': {
                'gemini':             api_keys.get('gemini', ''),
                'director_gemini':    api_keys.get('director_gemini', ''),
                'gemini_image':       api_keys.get('gemini_image', ''),
                'replicate':          api_keys.get('replicate', ''),
                'inworld':            api_keys.get('inworld', ''),
                'inworld_secret':     api_keys.get('inworld_secret', ''),
                'pexels':             api_keys.get('pexels', ''),
                'pixabay':            api_keys.get('pixabay', ''),
                'unsplash':           api_keys.get('unsplash', ''),
                'brave_search':       api_keys.get('brave_search', ''),
                'serper':             api_keys.get('serper', ''),
                'google_search':      api_keys.get('google_search', ''),
                'videvo':             api_keys.get('videvo', ''),
                'coverr':             api_keys.get('coverr', ''),
                'gemini_translate_1': api_keys.get('gemini_translate_1', ''),
                'gemini_translate_2': api_keys.get('gemini_translate_2', ''),
                'gemini_prompts':     api_keys.get('gemini_prompts', ''),
                'gemini_seo':         api_keys.get('gemini_seo', ''),
                'claude_key':         api_keys.get('claude_api_key', ''),
            },
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/alae-baha/export', methods=['POST'])
def alae_baha_export():
    """Export all settings, niches, styles, and formulas as a single JSON bundle."""
    from settings_manager import SettingsManager
    from niche_manager import NicheManager
    from auto_images_style_manager import AutoImagesStyleManager
    from seo_formula_manager import SeoFormulaManager
    from video_style_manager import VideoStyleManager

    try:
        data = request.get_json() or {}
        if data.get('password') != ALAE_BAHA_PASSWORD:
            return jsonify({'error': 'Incorrect password'}), 403

        settings = SettingsManager.load_settings()

        bundle = {
            'alae_baha_bundle': True,
            'version': '3.0',
            'exported_at': datetime.utcnow().isoformat(),
            'api_keys': settings.get('api_keys', {}),
            'voice_settings': settings.get('voice_settings', {}),
            'video_settings': settings.get('video_settings', {}),
            'formulas': {
                'title':       SettingsManager.load_formula('title'),
                'script':      SettingsManager.load_formula('script'),
                'image':       SettingsManager.load_formula('image'),
                'auto_images': SettingsManager.load_formula('auto_images'),
                'seo':         SettingsManager.load_formula('seo'),
            },
            'niches':       NicheManager.get_all_niches(),
            'image_styles': AutoImagesStyleManager.get_all_styles(),
            'seo_formulas': SeoFormulaManager.get_all(),          # named SEO presets
            'video_styles': [s for s in VideoStyleManager.get_all() if not s.get('built_in')],  # custom only
        }

        # Also include api_config.json if present
        from config import Config
        if Config.API_CONFIG_FILE.exists():
            try:
                with open(Config.API_CONFIG_FILE, 'r') as f:
                    bundle['api_config'] = json.load(f)
            except Exception:
                bundle['api_config'] = {}

        print(f"✅ Export bundle v3.0: {len(bundle['niches'])} niches, "
              f"{len(bundle['image_styles'])} image styles, "
              f"{len(bundle['video_styles'])} video styles, "
              f"{len(bundle['seo_formulas'])} SEO formulas")
        return jsonify({'success': True, 'bundle': bundle})

    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/alae-baha/import', methods=['POST'])
def alae_baha_import():
    """Import a settings bundle exported from another machine."""
    from settings_manager import SettingsManager
    from niche_manager import NicheManager
    from auto_images_style_manager import AutoImagesStyleManager
    from seo_formula_manager import SeoFormulaManager
    from video_style_manager import VideoStyleManager

    BUILTIN_IMAGE_IDS = {'cinematic', 'photorealistic', 'artistic', 'animated'}
    BUILTIN_VIDEO_IDS = {'cinematic_video', 'documentary_video', 'animated_video'}

    try:
        data = request.get_json() or {}
        if data.get('password') != ALAE_BAHA_PASSWORD:
            return jsonify({'error': 'Incorrect password'}), 403

        bundle = data.get('bundle')
        if not bundle or not bundle.get('alae_baha_bundle'):
            return jsonify({'error': 'Invalid bundle format'}), 400

        results = {
            'api_keys': False, 'formulas': False,
            'niches': 0, 'niches_skipped': 0,
            'image_styles': 0, 'image_styles_skipped': 0,
            'video_styles': 0, 'video_styles_skipped': 0,
            'seo_formulas': 0, 'seo_formulas_skipped': 0,
            'errors': []
        }

        # --- API Keys ---
        api_keys = bundle.get('api_keys', {})
        if api_keys:
            SettingsManager.save_api_keys(
                gemini=api_keys.get('gemini') or None,
                director_gemini=api_keys.get('director_gemini') or None,
                gemini_image=api_keys.get('gemini_image') or None,
                replicate=api_keys.get('replicate') or None,
                inworld=api_keys.get('inworld') or None,
                inworld_secret=api_keys.get('inworld_secret') or None,
                pexels=api_keys.get('pexels') or None,
                pixabay=api_keys.get('pixabay') or None,
                unsplash=api_keys.get('unsplash') or None,
                gemini_translate_1=api_keys.get('gemini_translate_1') or None,
                gemini_translate_2=api_keys.get('gemini_translate_2') or None,
            )
            results['api_keys'] = True

        # --- Voice & Video Settings ---
        voice = bundle.get('voice_settings', {})
        if voice:
            try:
                SettingsManager.save_voice_settings(
                    default_voice=voice.get('default_voice'),
                    speaking_rate=voice.get('speaking_rate'),
                )
            except Exception:
                pass

        video_set = bundle.get('video_settings', {})
        if video_set:
            try:
                SettingsManager.save_video_settings(
                    enable_timed_zoom=video_set.get('enable_timed_zoom'),
                    zoom_direction=video_set.get('zoom_direction'),
                    zoom_duration=video_set.get('zoom_duration'),
                    zoom_amount=video_set.get('zoom_amount'),
                )
            except Exception:
                pass

        # --- Formulas (title, script, image, auto_images, seo) ---
        formulas = bundle.get('formulas', {})
        if formulas:
            SettingsManager.save_formulas(
                title_formula=formulas.get('title'),
                script_formula=formulas.get('script'),
                image_formula=formulas.get('image'),
                auto_images_formula=formulas.get('auto_images'),
                seo_formula=formulas.get('seo'),
            )
            results['formulas'] = True

        # --- Niches (skip duplicates by name) ---
        existing_niche_names = {n['name'] for n in NicheManager.get_all_niches()}
        for niche in bundle.get('niches', []):
            name = niche.get('name', '').strip()
            if not name:
                continue
            if name in existing_niche_names:
                results['niches_skipped'] += 1
                continue
            try:
                NicheManager.create_niche(
                    name=name,
                    language=niche.get('language', 'English'),
                    writing_guidelines=niche.get('writing_guidelines', ''),
                )
                results['niches'] += 1
                existing_niche_names.add(name)
                print(f"   ✅ Niche: {name}")
            except Exception as e:
                results['errors'].append(f"Niche '{name}': {e}")

        # --- Auto Image Styles (skip built-ins & name duplicates) ---
        existing_img_names = {s['name'] for s in AutoImagesStyleManager.get_all_styles()}
        for style in bundle.get('image_styles', []):
            name     = style.get('name', '').strip()
            style_id = style.get('id', '')
            if not name or style_id in BUILTIN_IMAGE_IDS:
                results['image_styles_skipped'] += 1
                continue
            if name in existing_img_names:
                results['image_styles_skipped'] += 1
                continue
            try:
                style_formula = style.get('style_formula', '')
                visual_rules  = style.get('visual_rules', [])
                # If no formula and no rules, build minimal rules from description
                if not style_formula and len(visual_rules) < 3:
                    desc = style.get('description', 'Professional style')
                    visual_rules = [desc, 'High quality output', 'Consistent visual style']

                AutoImagesStyleManager.create_style(
                    name=name,
                    description=style.get('description', ''),
                    style_formula=style_formula,
                    visual_rules=visual_rules[:10],
                    negative_rules=style.get('negative_rules', ['Low quality', 'Blurry'])[:10],
                    composition=style.get('composition', ''),
                    lighting=style.get('lighting', ''),
                    color_palette=style.get('color_palette', [])[:10],
                )
                results['image_styles'] += 1
                existing_img_names.add(name)
                print(f"   ✅ Image style: {name}")
            except Exception as e:
                results['errors'].append(f"Image style '{name}': {e}")

        # --- Video Styles (skip built-ins & name duplicates) ---
        existing_vid_names = {s['name'] for s in VideoStyleManager.get_all() if not s.get('built_in')}
        for style in bundle.get('video_styles', []):
            name     = style.get('name', '').strip()
            style_id = style.get('id', '')
            if not name or style_id in BUILTIN_VIDEO_IDS:
                results['video_styles_skipped'] += 1
                continue
            if name in existing_vid_names:
                results['video_styles_skipped'] += 1
                continue
            try:
                VideoStyleManager.create(
                    name=name,
                    style_formula=style.get('style_formula', ''),
                    description=style.get('description', ''),
                )
                results['video_styles'] += 1
                existing_vid_names.add(name)
                print(f"   ✅ Video style: {name}")
            except Exception as e:
                results['errors'].append(f"Video style '{name}': {e}")

        # --- SEO Formula Presets (skip name duplicates) ---
        existing_seo_names = {f['name'] for f in SeoFormulaManager.get_all()}
        for preset in bundle.get('seo_formulas', []):
            name    = preset.get('name', '').strip()
            formula = preset.get('formula', '').strip()
            if not name or not formula:
                continue
            if name in existing_seo_names:
                results['seo_formulas_skipped'] += 1
                continue
            try:
                SeoFormulaManager.create(name=name, formula=formula)
                results['seo_formulas'] += 1
                existing_seo_names.add(name)
                print(f"   ✅ SEO formula: {name}")
            except Exception as e:
                results['errors'].append(f"SEO formula '{name}': {e}")

        print(f"✅ Import complete: {results['niches']} niches, "
              f"{results['image_styles']} image styles, "
              f"{results['video_styles']} video styles, "
              f"{results['seo_formulas']} SEO formulas, "
              f"{len(results['errors'])} errors")
        return jsonify({
            'success': True,
            'message': 'All settings imported successfully!',
            'results': results,
        })

    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# =============================================================================
# PROMPTS GENERATOR — raw image prompts from script + style (no image generation)
# =============================================================================

@app.route('/api/generate-prompts-only', methods=['POST'])
def generate_prompts_only():
    """
    Generate image OR video prompts scene-by-scene from a script.

    Request JSON:
        {
            "script":         "...",
            "style_id":       "cinematic",       # image style id  (mode=image)
            "video_style_id": "cinematic_video", # video style id  (mode=video)
            "count":          20,
            "mode":           "image" | "video"  # default: "image"
        }
    """
    from auto_images_style_manager import AutoImagesStyleManager
    from video_style_manager import VideoStyleManager
    from settings_manager import SettingsManager
    from config import Config
    import google.generativeai as genai

    CHUNK_SIZE = 15

    _auto_images_formula = SettingsManager.load_formula('auto_images')

    class _SafeDict(dict):
        def __missing__(self, key):
            return '{' + key + '}'

    # ---- IMAGE prompt builder ------------------------------------------------
    def build_image_prompt(script_segment, style, chunk_start, chunk_size, total_count, prev_prompts=None):
        style_name        = style.get('name', 'Cinematic')
        style_desc        = style.get('description', '')
        style_formula_raw = style.get('style_formula', '').strip()
        visual_rules      = style.get('visual_rules', [])
        negative_rules    = style.get('negative_rules', [])
        composition       = style.get('composition', '')
        lighting          = style.get('lighting', '')
        color_palette     = style.get('color_palette', [])

        color_palette_text = ', '.join(color_palette) if color_palette else 'rich, vivid colors'
        chunk_end = chunk_start + chunk_size - 1

        # Build style DNA — the mandatory visual fingerprint for EVERY prompt
        if style_formula_raw:
            style_dna = style_formula_raw
        else:
            dna_parts = [style_desc] if style_desc else []
            if visual_rules:
                dna_parts.append('Visual: ' + ' | '.join(visual_rules))
            if composition:
                dna_parts.append(f'Composition: {composition}')
            if lighting:
                dna_parts.append(f'Lighting: {lighting}')
            if color_palette_text:
                dna_parts.append(f'Colors: {color_palette_text}')
            style_dna = '\n'.join(dna_parts)

        negative_text = ''
        if negative_rules:
            negative_text = '\nNEVER include: ' + ', '.join(negative_rules)

        # Previously generated prompts — tell AI what subjects were already covered
        prev_section = ''
        if prev_prompts:
            previews = '\n'.join(f'- {p[:120]}' for p in prev_prompts[-6:])
            prev_section = f"""
ALREADY GENERATED — do NOT repeat these subjects or environments:
{previews}
"""

        formula_rendered = _auto_images_formula.format_map(_SafeDict(
            n_images=chunk_size,
            style_name=style_name,
            lighting=lighting,
            composition=composition,
            color_palette=color_palette_text,
        ))

        return f"""You are a professional image prompt writer for AI image generators (Flux, Midjourney, SDXL).

════════════════ STYLE CORE — {style_name} ════════════════
This is the MANDATORY visual DNA. Every single prompt you write MUST reflect this style.
Apply these parameters as the foundation of every prompt without exception:

{style_dna}{negative_text}
══════════════════════════════════════════════════════════

TASK: Generate EXACTLY {chunk_size} image prompts covering scenes {chunk_start}–{chunk_end} of {total_count} total.
Each prompt = one distinct visual scene extracted from the script segment below.
ALL prompts in ENGLISH. Follow the script CHRONOLOGICALLY. Each prompt covers a different moment.
{prev_section}
═══════════════ SCRIPT SEGMENT (scenes {chunk_start}–{chunk_end}) ═══════════════
{script_segment}
═══════════════════════════════════════════════════════════════════

{formula_rendered}

OUTPUT RULES:
1. EXACTLY {chunk_size} prompts separated by ONE blank line between each.
2. NO numbering, NO labels, NO preamble, NO explanation.
3. Each prompt = ONE continuous paragraph. NO line breaks inside a prompt.
4. Every prompt MUST embed the {style_name} style parameters above as its visual core.
5. Every prompt MUST end with: --no text, no captions, no watermarks, no labels
6. Every scene DISTINCT — different subject, angle, or environment from all others.
OUTPUT ONLY THE {chunk_size} PROMPTS. NOTHING ELSE."""

    # ---- VIDEO prompt builder ------------------------------------------------
    def build_video_prompt(script_segment, style, chunk_start, chunk_size, total_count, prev_prompts=None):
        style_name    = style.get('name', 'Cinematic')
        style_formula = style.get('style_formula', '').strip()
        chunk_end = chunk_start + chunk_size - 1

        style_dna = style_formula or f'Cinematic film quality, smooth controlled camera movement, {style_name} aesthetic, professional grade'

        prev_section = ''
        if prev_prompts:
            previews = '\n'.join(f'- {p[:120]}' for p in prev_prompts[-6:])
            prev_section = f"""
ALREADY GENERATED — do NOT repeat these subjects or shots:
{previews}
"""

        return f"""You are a professional video prompt writer for AI video generators (Sora, Runway Gen-3, Kling, Pika).

════════════════ VIDEO STYLE CORE — {style_name} ════════════════
This is the MANDATORY visual DNA. Every single prompt you write MUST apply this style as its base:

{style_dna}
══════════════════════════════════════════════════════════

TASK: Generate EXACTLY {chunk_size} video prompts covering scenes {chunk_start}–{chunk_end} of {total_count} total.
Each prompt = one distinct video shot extracted from the script segment below.
ALL prompts in ENGLISH. Follow the script CHRONOLOGICALLY. Each prompt covers a different moment.
{prev_section}
═══════════════ SCRIPT SEGMENT (scenes {chunk_start}–{chunk_end}) ═══════════════
{script_segment}
═══════════════════════════════════════════════════════════════════

OUTPUT RULES:
1. EXACTLY {chunk_size} prompts separated by ONE blank line between each.
2. NO numbering, NO labels, NO preamble, NO explanation.
3. Each prompt = ONE continuous paragraph. NO line breaks inside a prompt.
4. Every prompt MUST include in this order:
   - Duration: "X seconds," (5–10 s per scene)
   - Specific camera movement (slow dolly-in, wide pan left, aerial descent, static close-up, etc.)
   - Subject + action EXACTLY matching that script moment
   - Mood and lighting applying the {style_name} style core above
   - End with: high quality, smooth motion, --no text --no subtitles --no watermarks
5. Every scene DISTINCT — vary shot size, angle, camera movement from all others.
OUTPUT ONLY THE {chunk_size} PROMPTS. NOTHING ELSE."""

    def _dedup_prompts(prompts):
        """Remove duplicate or near-duplicate prompts based on first 80 chars fingerprint."""
        seen = set()
        result = []
        for p in prompts:
            fp = re.sub(r'\s+', ' ', p[:80].lower().strip())
            if fp not in seen:
                seen.add(fp)
                result.append(p)
        return result

    try:
        data = request.get_json() or {}
        script         = data.get('script', '').strip()
        mode           = data.get('mode', 'image')           # 'image' or 'video'
        style_id       = data.get('style_id', 'cinematic')
        video_style_id = data.get('video_style_id', 'cinematic_video')
        count          = int(data.get('count', 20))

        if not script:
            return jsonify({'error': 'Script is required'}), 400
        if count < 1 or count > 200:
            return jsonify({'error': 'count must be between 1 and 200'}), 400

        # Prompts Generator uses ONLY its own dedicated key.
        prompts_key = Config.get_gemini_prompts_api_key()
        if not prompts_key:
            return jsonify({'error': 'No Prompts Generator API key configured. Add it in Settings → Prompts Generator.'}), 500
        keys = [prompts_key]
        model_name = Config.get_director_gemini_model()
        gen_cfg    = {'temperature': 0.85, 'top_p': 0.95, 'max_output_tokens': 32768}
        print(f'🔑 Prompts generator using dedicated key …{_gem_key_label(prompts_key)}')

        # Resolve style
        if mode == 'video':
            style = VideoStyleManager.get(video_style_id)
            if not style:
                return jsonify({'error': f'Video style not found: {video_style_id}'}), 404
            prompt_builder = build_video_prompt
        else:
            style = AutoImagesStyleManager.get_style(style_id)
            if not style:
                return jsonify({'error': f'Image style not found: {style_id}'}), 404
            prompt_builder = build_image_prompt

        all_prompts = []
        remaining   = count
        chunk_start = 1
        script_len  = len(script)

        while remaining > 0:
            chunk_size = min(CHUNK_SIZE, remaining)

            # Slice the script proportionally so each chunk covers its own section
            seg_start = int((chunk_start - 1) / count * script_len)
            seg_end   = int((chunk_start + chunk_size - 1) / count * script_len)
            script_segment = script[seg_start:seg_end].strip() or script

            prompt_text = prompt_builder(
                script_segment, style, chunk_start, chunk_size, count,
                prev_prompts=all_prompts[-6:] if all_prompts else None,
            )

            print(f'\n{"🎬" if mode=="video" else "🎨"} Prompts [{mode}] '
                  f'chunk {chunk_start}–{chunk_start + chunk_size - 1}/{count}')
            raw = _gem_call_sdk(keys, model_name, gen_cfg, prompt_text).strip()

            parts = [p.strip() for p in raw.split('\n\n') if p.strip()]
            clean = [p for p in parts if len(p) > 40]
            clean = _dedup_prompts(clean)
            # Only add prompts not already in all_prompts
            seen_fps = {re.sub(r'\s+', ' ', p[:80].lower().strip()) for p in all_prompts}
            new_prompts = [p for p in clean if re.sub(r'\s+', ' ', p[:80].lower().strip()) not in seen_fps]
            all_prompts.extend(new_prompts[:chunk_size])

            chunk_start += chunk_size
            remaining   -= chunk_size
            # No explicit sleep — _gem_acquire() handles spacing automatically

        print(f'✅ Prompts [{mode}]: {len(all_prompts)} generated')
        return jsonify({
            'success':    True,
            'prompts':    all_prompts,
            'count':      len(all_prompts),
            'mode':       mode,
            'style_name': style.get('name', style_id),
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ---- Video Styles CRUD -------------------------------------------------------

@app.route('/api/video-styles', methods=['GET'])
def video_styles_list():
    try:
        from video_style_manager import VideoStyleManager
        return jsonify({'success': True, 'styles': VideoStyleManager.get_all()})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/video-styles', methods=['POST'])
def video_styles_create():
    try:
        from video_style_manager import VideoStyleManager
        data = request.get_json() or {}
        style = VideoStyleManager.create(
            name=data.get('name', ''),
            style_formula=data.get('style_formula', ''),
            description=data.get('description', ''),
        )
        return jsonify({'success': True, 'style': style})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/video-styles/<style_id>', methods=['PUT'])
def video_styles_update(style_id):
    try:
        from video_style_manager import VideoStyleManager
        data = request.get_json() or {}
        style = VideoStyleManager.update(
            style_id=style_id,
            name=data.get('name'),
            style_formula=data.get('style_formula'),
            description=data.get('description'),
        )
        if style:
            return jsonify({'success': True, 'style': style})
        return jsonify({'success': False, 'error': 'Style not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/video-styles/<style_id>', methods=['DELETE'])
def video_styles_delete(style_id):
    try:
        from video_style_manager import VideoStyleManager
        ok = VideoStyleManager.delete(style_id)
        return jsonify({'success': ok})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# =============================================================================
# MIXED GENERATOR — first half: video prompts, second half: image prompts
# =============================================================================

@app.route('/api/generate-mixed-prompts', methods=['POST'])
def generate_mixed_prompts():
    """
    Split script in two at split_char_pos, generate:
      - video prompts for the first part  (video_style_id, video_count)
      - image prompts for the second part (style_id,       image_count)

    Request JSON:
        {
            "script":         "full script text",
            "split_char_pos": 6000,          # char index where split happens
            "video_style_id": "cinematic_video",
            "video_count":    30,
            "style_id":       "cinematic",
            "image_count":    20
        }
    """
    from auto_images_style_manager import AutoImagesStyleManager
    from video_style_manager import VideoStyleManager
    from settings_manager import SettingsManager
    from config import Config
    import google.generativeai as genai
    import time as _time

    CHUNK_SIZE = 15

    _auto_images_formula = SettingsManager.load_formula('auto_images')

    class _SafeDict(dict):
        def __missing__(self, key):
            return '{' + key + '}'

    # ---- prompt builders (same logic as generate_prompts_only) ---------------
    def build_image_prompt(script_segment, style, chunk_start, chunk_size, total_count, prev_prompts=None):
        style_name        = style.get('name', 'Cinematic')
        style_desc        = style.get('description', '')
        style_formula_raw = style.get('style_formula', '').strip()
        visual_rules      = style.get('visual_rules', [])
        negative_rules    = style.get('negative_rules', [])
        composition       = style.get('composition', '')
        lighting          = style.get('lighting', '')
        color_palette     = style.get('color_palette', [])
        cp  = ', '.join(color_palette) if color_palette else 'rich, vivid colors'
        end = chunk_start + chunk_size - 1

        if style_formula_raw:
            style_dna = style_formula_raw
        else:
            dna_parts = [style_desc] if style_desc else []
            if visual_rules:
                dna_parts.append('Visual: ' + ' | '.join(visual_rules))
            if composition:
                dna_parts.append(f'Composition: {composition}')
            if lighting:
                dna_parts.append(f'Lighting: {lighting}')
            if cp:
                dna_parts.append(f'Colors: {cp}')
            style_dna = '\n'.join(dna_parts)

        negative_text = ('\nNEVER include: ' + ', '.join(negative_rules)) if negative_rules else ''
        prev_section = ''
        if prev_prompts:
            previews = '\n'.join(f'- {p[:120]}' for p in prev_prompts[-6:])
            prev_section = f'\nALREADY GENERATED — do NOT repeat these subjects or environments:\n{previews}\n'

        formula_rendered = _auto_images_formula.format_map(_SafeDict(
            n_images=chunk_size, style_name=style_name,
            lighting=lighting, composition=composition, color_palette=cp,
        ))
        return f"""You are a professional image prompt writer (Flux, Midjourney, SDXL).

════════════════ STYLE CORE — {style_name} ════════════════
MANDATORY visual DNA — embed this in EVERY prompt without exception:

{style_dna}{negative_text}
══════════════════════════════════════════════════════════

TASK: Generate EXACTLY {chunk_size} image prompts — scenes {chunk_start}–{end} of {total_count} total.
ALL prompts in ENGLISH. Chronological order. Each = a distinct moment from the script segment below.
{prev_section}
═══ SCRIPT SEGMENT (scenes {chunk_start}–{end}) ═══
{script_segment}
═══════════════════════════════════════════

{formula_rendered}

OUTPUT RULES:
1. EXACTLY {chunk_size} prompts separated by ONE blank line.
2. NO labels, NO numbering, NO preamble, NO explanation.
3. One continuous paragraph per prompt — no internal line breaks.
4. Every prompt MUST embed the {style_name} style core as its visual foundation.
5. End each: --no text, no captions, no watermarks, no labels
6. Every scene DISTINCT — different subject/angle/environment from all others.
OUTPUT ONLY THE {chunk_size} PROMPTS."""

    def build_video_prompt(script_segment, style, chunk_start, chunk_size, total_count, prev_prompts=None):
        style_name    = style.get('name', 'Cinematic')
        style_formula = style.get('style_formula', '').strip()
        end = chunk_start + chunk_size - 1
        style_dna = style_formula or f'Cinematic film quality, smooth controlled camera movement, {style_name} aesthetic, professional grade'

        prev_section = ''
        if prev_prompts:
            previews = '\n'.join(f'- {p[:120]}' for p in prev_prompts[-6:])
            prev_section = f'\nALREADY GENERATED — do NOT repeat these subjects or shots:\n{previews}\n'

        return f"""You are a professional video prompt writer (Sora, Runway, Kling, Pika).

════════════════ VIDEO STYLE CORE — {style_name} ════════════════
MANDATORY visual DNA — apply this as the base of EVERY prompt without exception:

{style_dna}
══════════════════════════════════════════════════════════

TASK: Generate EXACTLY {chunk_size} video prompts — scenes {chunk_start}–{end} of {total_count} total.
ALL prompts in ENGLISH. Chronological order. Each = a distinct moment from the script segment below.
{prev_section}
═══ SCRIPT SEGMENT (scenes {chunk_start}–{end}) ═══
{script_segment}
═══════════════════════════════════════════

OUTPUT RULES:
1. EXACTLY {chunk_size} prompts separated by ONE blank line.
2. NO labels, NO numbering, NO preamble, NO explanation.
3. One continuous paragraph per prompt — no internal line breaks.
4. Every prompt MUST include: duration ("X seconds,"), specific camera movement, subject + action from that script moment, mood/lighting applying the {style_name} style core, render quality suffix.
5. End each: high quality, smooth motion, --no text --no subtitles --no watermarks
6. Every scene DISTINCT — vary shot size, angle, camera movement from all others.
OUTPUT ONLY THE {chunk_size} PROMPTS."""

    def _dedup_p(prompts):
        import re as _re
        seen = set()
        result = []
        for p in prompts:
            fp = _re.sub(r'\s+', ' ', p[:80].lower().strip())
            if fp not in seen:
                seen.add(fp)
                result.append(p)
        return result

    # ---- main logic ----------------------------------------------------------
    def run_chunks(script_segment, style, total_count, prompt_builder, keys,
                   model_name, gen_cfg):
        import re as _re
        results = []
        remaining   = total_count
        chunk_start = 1
        seg_len     = len(script_segment)
        while remaining > 0:
            chunk_size = min(CHUNK_SIZE, remaining)
            s_start = int((chunk_start - 1) / total_count * seg_len)
            s_end   = int((chunk_start + chunk_size - 1) / total_count * seg_len)
            seg     = script_segment[s_start:s_end].strip() or script_segment
            pt  = prompt_builder(seg, style, chunk_start, chunk_size, total_count,
                                 prev_prompts=results[-6:] if results else None)
            raw = _gem_call_sdk(keys, model_name, gen_cfg, pt).strip()
            parts = [p.strip() for p in raw.split('\n\n') if p.strip() and len(p.strip()) > 40]
            parts = _dedup_p(parts)
            seen_fps = {_re.sub(r'\s+', ' ', p[:80].lower().strip()) for p in results}
            new = [p for p in parts if _re.sub(r'\s+', ' ', p[:80].lower().strip()) not in seen_fps]
            results.extend(new[:chunk_size])
            chunk_start += chunk_size
            remaining   -= chunk_size
        return results

    try:
        data = request.get_json() or {}
        script        = data.get('script', '').strip()
        split_pos     = int(data.get('split_char_pos', len(script) // 2))
        vid_style_id  = data.get('video_style_id', 'cinematic_video')
        video_count   = int(data.get('video_count', 20))
        img_style_id  = data.get('style_id', 'cinematic')
        image_count   = int(data.get('image_count', 20))

        if not script:
            return jsonify({'error': 'Script is required'}), 400

        # Clamp split
        split_pos = max(100, min(split_pos, len(script) - 100))

        script_first  = script[:split_pos].strip()
        script_second = script[split_pos:].strip()

        vid_style = VideoStyleManager.get(vid_style_id)
        if not vid_style:
            return jsonify({'error': f'Video style not found: {vid_style_id}'}), 404
        img_style = AutoImagesStyleManager.get_style(img_style_id)
        if not img_style:
            return jsonify({'error': f'Image style not found: {img_style_id}'}), 404

        # Mixed Prompts Generator uses ONLY its own dedicated key.
        prompts_key = Config.get_gemini_prompts_api_key()
        if not prompts_key:
            return jsonify({'error': 'No Prompts Generator API key configured. Add it in Settings → Prompts Generator.'}), 500
        keys = [prompts_key]
        model_name = Config.get_director_gemini_model()
        gen_cfg    = {'temperature': 0.85, 'top_p': 0.95, 'max_output_tokens': 32768}
        print(f'🔑 Mixed prompts using dedicated key …{_gem_key_label(prompts_key)}')

        # --- generate video prompts (first half) ---
        print(f'\n🎬 Mixed: generating {video_count} video prompts (first {split_pos} chars)…')
        video_prompts = run_chunks(script_first, vid_style, video_count,
                                   build_video_prompt, keys, model_name, gen_cfg)

        # --- generate image prompts (second half) ---
        # No manual sleep — _gem_acquire() handles key spacing automatically
        print(f'\n🖼️  Mixed: generating {image_count} image prompts (remaining {len(script)-split_pos} chars)…')
        image_prompts = run_chunks(script_second, img_style, image_count,
                                   build_image_prompt, keys, model_name, gen_cfg)

        video_duration_min = round((video_count * 10) / 60, 1)

        return jsonify({
            'success':       True,
            'video_prompts': video_prompts,
            'image_prompts': image_prompts,
            'video_count':   len(video_prompts),
            'image_count':   len(image_prompts),
            'split_pos':     split_pos,
            'total_chars':   len(script),
            'video_duration_min': video_duration_min,
            'vid_style_name': vid_style.get('name'),
            'img_style_name': img_style.get('name'),
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# SUPER AUTO EDITOR
# ─────────────────────────────────────────────────────────────────────────────

super_editor_jobs: dict = {}   # job_id → {status, progress, message, result, error}


def _ffprobe_duration(path: str) -> float:
    """Fast duration probe for auto timeline fallback."""
    try:
        cmd = [
            'ffprobe', '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            path,
        ]
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode().strip()
        return float(out)
    except Exception:
        return 0.0


@app.route('/api/super-auto-editor/start', methods=['POST'])
def super_auto_editor_start():
    """
    Start a Super Auto Editor job.

    Accepts multipart/form-data:
        avatar_file  – uploaded avatar video (MP4/MOV/…)
        script       – full script text
        title        – optional video title
    OR JSON:
        avatar_path  – server-side path to avatar video
        script       – full script text
        title        – optional

    Returns: { job_id, status, message }
    """
    SuperAutoEditor = None
    v2_available = False
    try:
        from super_auto_editor_v2.config.settings import load_config
        from super_auto_editor_v2.export_manager import ExportManager
        v2_available = True
    except Exception:
        v2_available = False

    try:
        from super_auto_editor import SuperAutoEditor as _LegacySuperAutoEditor
        SuperAutoEditor = _LegacySuperAutoEditor
    except SyntaxError as e:
        if not v2_available:
            return jsonify({
                'success': False,
                'error': (
                    "super_auto_editor.py has unresolved merge markers or invalid syntax. "
                    "Remove lines like <<<<<<<, =======, >>>>>>> and retry."
                ),
                'details': str(e)
            }), 500

    from settings_manager import SettingsManager

    try:
        # ── resolve avatar path ──────────────────────────────────────────────
        avatar_path = None
        title = 'super_auto_output'

        timeline_blocks = None
        mode = 'ultra_fast_draft'
        config_path = ''
        use_v2 = None

        if request.content_type and 'multipart/form-data' in request.content_type:
            script = request.form.get('script', '').strip()
            title  = request.form.get('title', title)
            mode   = (request.form.get('mode') or mode).strip() or mode
            config_path = (request.form.get('config_path') or '').strip()
            use_v2_raw = request.form.get('use_v2')
            if use_v2_raw is not None:
                use_v2 = str(use_v2_raw).lower() == 'true'
            timeline_raw = (request.form.get('timeline_blocks') or '').strip()
            if timeline_raw:
                try:
                    timeline_blocks = json.loads(timeline_raw)
                except Exception:
                    return jsonify({'success': False, 'error': 'Invalid timeline_blocks JSON'}), 400
            f      = request.files.get('avatar_file')
            if f:
                fname       = secure_filename(f.filename)
                avatar_path = os.path.join(UPLOAD_FOLDER, f'sae_{uuid.uuid4().hex}_{fname}')
                f.save(avatar_path)
        else:
            data        = request.get_json() or {}
            script      = data.get('script', '').strip()
            title       = data.get('title', title)
            avatar_path = data.get('avatar_path', '').strip()
            mode = (data.get('mode') or mode).strip() or mode
            config_path = (data.get('config_path') or '').strip()
            if 'use_v2' in data:
                use_v2 = bool(data.get('use_v2'))
            timeline_blocks = data.get('timeline_blocks')

        if not script:
            return jsonify({'success': False, 'error': 'script is required'}), 400
        if not avatar_path:
            return jsonify({'success': False, 'error': 'avatar_file or avatar_path is required'}), 400
        if not os.path.exists(avatar_path):
            return jsonify({'success': False, 'error': f'Avatar file not found: {avatar_path}'}), 404

        # ── load API keys ────────────────────────────────────────────────────
        saved     = SettingsManager.load_settings()
        api_keys  = saved.get('api_keys', {})
        gemini_keys = api_keys.get('gemini', [])
        if isinstance(gemini_keys, str):
            gemini_keys = [k.strip() for k in gemini_keys.split(',') if k.strip()]

        pexels_key        = api_keys.get('pexels',        '')
        pixabay_key       = api_keys.get('pixabay',       '')
        unsplash_key      = api_keys.get('unsplash',      '')
        brave_search_key  = api_keys.get('brave_search',  '')
        serper_key        = api_keys.get('serper',        '')
        google_search_key = api_keys.get('google_search', '')
        videvo_key        = api_keys.get('videvo',        '')
        coverr_key        = api_keys.get('coverr',        '')

        sae_cfg = saved.get('super_auto_editor', {}) if isinstance(saved, dict) else {}
        # Mode precedence: request.mode -> settings.mode -> map legacy settings.export_mode
        if not mode or mode == 'ultra_fast_draft':
            mode = (sae_cfg.get('mode') or mode).strip() if isinstance(sae_cfg, dict) else mode
            if not mode or mode == 'ultra_fast_draft':
                legacy_mode = (sae_cfg.get('export_mode', 'turbo') if isinstance(sae_cfg, dict) else 'turbo')
                mode = {
                    'turbo': 'ultra_fast_draft',
                    'balanced': 'fast_final',
                    'quality': 'quality_final',
                }.get(str(legacy_mode).strip().lower(), 'ultra_fast_draft')

        # ── create job ───────────────────────────────────────────────────────
        job_id = str(uuid.uuid4())
        super_editor_jobs[job_id] = {
            'status':   'queued',
            'progress': 0,
            'message':  'Job queued…',
            'result':   None,
            'error':    None,
        }

        def _run():
            nonlocal timeline_blocks
            try:
                super_editor_jobs[job_id]['status']  = 'processing'
                super_editor_jobs[job_id]['message'] = 'Starting Super Auto Editor…'

                def _progress(pct, msg):
                    super_editor_jobs[job_id]['progress'] = pct
                    super_editor_jobs[job_id]['message']  = msg

                default_engine = str(sae_cfg.get('engine', 'v2')).strip().lower() if isinstance(sae_cfg, dict) else 'v2'
                default_use_v2 = bool(sae_cfg.get('use_v2', default_engine == 'v2')) if isinstance(sae_cfg, dict) else True
                requested_use_v2 = default_use_v2 if use_v2 is None else use_v2
                should_use_v2 = v2_available and (requested_use_v2 or bool(timeline_blocks))
                if should_use_v2:
                    _progress(10, 'Preparing v2 timeline files…')
                    import tempfile
                    from pathlib import Path

                    # Build timeline if user did not provide one.
                    if not timeline_blocks:
                        # Speed-first default: open with avatar then alternate blocks.
                        dur = _ffprobe_duration(avatar_path)
                        cur = 0.0
                        blocks = []
                        first_avatar = min(3.0, max(0.5, dur))
                        blocks.append({"type": "avatar", "start": 0.0, "end": first_avatar})
                        cur = first_avatar
                        flip = "media"
                        while cur < dur:
                            span = 10.0 if flip == "media" else 6.0
                            nxt = min(dur, cur + span)
                            blocks.append({"type": flip, "start": round(cur, 3), "end": round(nxt, 3)})
                            cur = nxt
                            flip = "avatar" if flip == "media" else "media"
                        timeline_blocks = blocks

                    temp_root = Path(tempfile.mkdtemp(prefix='sae_v2_'))
                    script_path = temp_root / 'script.txt'
                    timeline_path = temp_root / 'timeline.json'
                    script_path.write_text(script, encoding='utf-8')
                    timeline_path.write_text(json.dumps(timeline_blocks), encoding='utf-8')

                    cfg = load_config(Path(config_path) if config_path else None)
                    # Inject keys from saved settings so UI works without env setup.
                    cfg.serper_api_key = cfg.serper_api_key or serper_key
                    cfg.brave_api_key = cfg.brave_api_key or brave_search_key
                    cfg.pexels_api_key = cfg.pexels_api_key or pexels_key
                    cfg.gemini_api_key = cfg.gemini_api_key or (gemini_keys[0] if gemini_keys else '')
                    manager = ExportManager(cfg)
                    final_name = f"{secure_filename(title) if title else 'super_auto_output'}_{uuid.uuid4().hex[:8]}.mp4"
                    output_path = Path(OUTPUT_FOLDER) / final_name
                    _progress(20, 'Running Super Auto Editor v2…')
                    manager.build(
                        avatar_video=Path(avatar_path),
                        script_path=script_path,
                        timeline_path=timeline_path,
                        output_path=output_path,
                        mode=mode,
                    )
                    result = {
                        'success': True,
                        'output_path': str(output_path),
                        'mode': mode,
                        'engine': 'v2',
                    }
                else:
                    if SuperAutoEditor is None:
                        raise RuntimeError('Legacy SuperAutoEditor unavailable and v2 disabled.')
                    editor = SuperAutoEditor(
                        gemini_keys       = gemini_keys,
                        pexels_key        = pexels_key,
                        pixabay_key       = pixabay_key,
                        unsplash_key      = unsplash_key,
                        brave_search_key  = brave_search_key,
                        serper_key        = serper_key,
                        google_search_key = google_search_key,
                        videvo_key        = videvo_key,
                        coverr_key        = coverr_key,
                        export_mode       = sae_cfg.get('export_mode', 'turbo'),
                        render_crf        = sae_cfg.get('render_crf'),
                        max_fc_clips      = sae_cfg.get('max_fc_clips'),
                        max_broll_coverage= sae_cfg.get('max_broll_coverage'),
                        search_workers    = sae_cfg.get('search_workers'),
                        download_workers  = sae_cfg.get('download_workers'),
                        encode_workers    = sae_cfg.get('encode_workers'),
                        progress_cb       = _progress,
                    )
                    result = editor.run(
                        avatar_path = avatar_path,
                        script      = script,
                        title       = title,
                    )
                super_editor_jobs[job_id].update({
                    'status':   'done',
                    'progress': 100,
                    'message':  '✅ Video assembled successfully!',
                    'result':   result,
                })
            except Exception as exc:
                import traceback
                traceback.print_exc()
                super_editor_jobs[job_id].update({
                    'status':  'error',
                    'message': str(exc),
                    'error':   str(exc),
                })

        t = threading.Thread(target=_run, daemon=True)
        t.start()

        return jsonify({
            'success': True,
            'job_id':  job_id,
            'status':  'queued',
            'message': 'Super Auto Editor job started',
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/super-auto-editor/status/<job_id>', methods=['GET'])
def super_auto_editor_status(job_id):
    """Poll status of a Super Auto Editor job."""
    job = super_editor_jobs.get(job_id)
    if not job:
        return jsonify({'success': False, 'error': 'Job not found'}), 404

    resp = dict(job)
    resp['success'] = True
    resp['job_id']  = job_id

    # If done, add download URL
    if job['status'] == 'done' and job.get('result'):
        out_path = job['result'].get('output_path', '')
        if out_path and os.path.exists(out_path):
            resp['download_url'] = f'/api/super-auto-editor/download/{job_id}'

    return jsonify(resp)


@app.route('/api/super-auto-editor/download/<job_id>', methods=['GET'])
def super_auto_editor_download(job_id):
    """Download the finished Super Auto Editor video."""
    job = super_editor_jobs.get(job_id)
    if not job or job['status'] != 'done':
        return jsonify({'error': 'Not ready'}), 404

    result   = job.get('result', {})
    out_path = result.get('output_path', '')
    if not out_path or not os.path.exists(out_path):
        return jsonify({'error': 'File not found'}), 404

    return send_file(
        out_path,
        as_attachment=True,
        download_name=os.path.basename(out_path),
        mimetype='video/mp4',
    )


# =============================================================================
# 📚 DIGITAL CREATE — Ebook Generator
# =============================================================================

# In-memory job store (same pattern as super-auto-editor)
_ebook_jobs: dict = {}


@app.route('/api/ebook/generate', methods=['POST'])
def ebook_generate():
    """
    Start an ebook generation job (background thread).
    Body: { title, details, pages }
    Returns: { job_id, status: "queued" }
    """
    import threading
    import uuid
    from config import Config

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    title   = (data.get('title') or '').strip()
    details = (data.get('details') or '').strip()
    pages   = int(data.get('pages') or 50)

    if not title:
        return jsonify({'error': 'title is required'}), 400
    if not details:
        return jsonify({'error': 'details is required'}), 400
    if pages < 5 or pages > 500:
        return jsonify({'error': 'pages must be between 5 and 500'}), 400

    errors = Config.validate_api_keys()
    if any('GEMINI' in e for e in errors):
        return jsonify({'error': 'Gemini API key not configured'}), 500

    job_id = str(uuid.uuid4())[:8]
    _ebook_jobs[job_id] = {
        'status'  : 'running',
        'title'   : title,
        'pages'   : pages,
        'progress': 'Starting research…',
        'result'  : None,
        'error'   : None,
    }

    def _run():
        try:
            from ebook_generator import EbookGenerator
            gen    = EbookGenerator()
            result = gen.generate(title=title, details=details, pages=pages, verbose=True)
            _ebook_jobs[job_id]['status'] = 'done'
            _ebook_jobs[job_id]['result'] = result
        except Exception as exc:
            _ebook_jobs[job_id]['status'] = 'error'
            _ebook_jobs[job_id]['error']  = str(exc)
            print(f"[ebook] job {job_id} failed: {exc}")

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({'success': True, 'job_id': job_id, 'status': 'running'})


@app.route('/api/ebook/status/<job_id>', methods=['GET'])
def ebook_status(job_id):
    """Poll for ebook job status."""
    job = _ebook_jobs.get(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    resp = dict(job)
    resp['success'] = True
    if job['status'] == 'done' and job.get('result'):
        resp['download_url'] = f'/api/ebook/download/{job_id}'
    return jsonify(resp)


@app.route('/api/ebook/download/<job_id>', methods=['GET'])
def ebook_download(job_id):
    """Download the finished PDF."""
    job = _ebook_jobs.get(job_id)
    if not job or job['status'] != 'done':
        return jsonify({'error': 'Not ready'}), 404
    result   = job.get('result', {})
    pdf_path = result.get('pdf_path', '')
    if not pdf_path or not os.path.exists(pdf_path):
        return jsonify({'error': 'File not found'}), 404
    return send_file(
        pdf_path,
        as_attachment=True,
        download_name=os.path.basename(pdf_path),
        mimetype='application/pdf',
    )


# =============================================================================
# BUNDLE GENERATOR — multi-ebook async parallel system
# =============================================================================
_bundle_jobs: dict = {}  # job_id -> {status, progress, message, result, error}


@app.route('/api/ebook/generate-bundle', methods=['POST'])
def bundle_generate():
    """
    Start a bundle generation job in a background thread.
    Body: { topic, details, num_ebooks, pages_per_ebook, audience?, tone? }
    Returns: { success, job_id, status: "running" }
    """
    import threading as _th

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    topic            = (data.get('topic') or '').strip()
    details          = (data.get('details') or topic).strip()
    num_ebooks       = int(data.get('num_ebooks') or 3)
    pages_per_ebook  = int(data.get('pages_per_ebook') or 30)
    audience         = (data.get('audience') or 'general').strip()
    tone             = (data.get('tone') or 'expert').strip()

    if not topic:
        return jsonify({'error': 'topic is required'}), 400
    if num_ebooks < 1 or num_ebooks > 20:
        return jsonify({'error': 'num_ebooks must be 1-20'}), 400
    if pages_per_ebook < 5 or pages_per_ebook > 500:
        return jsonify({'error': 'pages_per_ebook must be 5-500'}), 400

    errors = Config.validate_api_keys()
    if any('GEMINI' in e for e in errors):
        return jsonify({'error': 'Gemini API key not configured'}), 500

    job_id = str(uuid.uuid4())[:8]
    _bundle_jobs[job_id] = {
        'status'  : 'running',
        'progress': 3,
        'message' : 'Starting…',
        'result'  : None,
        'error'   : None,
    }

    def _progress_cb(pct: int, msg: str) -> None:
        _bundle_jobs[job_id]['progress'] = pct
        _bundle_jobs[job_id]['message']  = msg

    def _run() -> None:
        try:
            from bundle_generator import BundleGenerator
            gen    = BundleGenerator()
            result = gen.generate_bundle(
                bundle_topic      = topic,
                product_details   = details,
                num_ebooks        = num_ebooks,
                pages_per_ebook   = pages_per_ebook,
                audience          = audience,
                tone              = tone,
                verbose           = True,
                progress_callback = _progress_cb,
            )
            _bundle_jobs[job_id]['status']   = 'done'
            _bundle_jobs[job_id]['progress'] = 100
            _bundle_jobs[job_id]['message']  = '✅ Bundle ready!'
            _bundle_jobs[job_id]['result']   = result
        except Exception as exc:
            _bundle_jobs[job_id]['status']  = 'error'
            _bundle_jobs[job_id]['error']   = str(exc)
            _bundle_jobs[job_id]['message'] = f'❌ {exc}'
            print(f"[bundle] job {job_id} failed: {exc}")

    _th.Thread(target=_run, daemon=True).start()
    return jsonify({'success': True, 'job_id': job_id, 'status': 'running'})


@app.route('/api/ebook/bundle-status/<job_id>', methods=['GET'])
def bundle_status(job_id):
    """Poll for bundle job status."""
    job = _bundle_jobs.get(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    resp = {
        'success' : True,
        'status'  : job['status'],
        'progress': job['progress'],
        'message' : job['message'],
    }
    if job['status'] == 'done' and job.get('result'):
        resp['download_url'] = f'/api/ebook/bundle-download/{job_id}'
        result = job['result']
        resp['num_ebooks']    = result.get('num_ebooks', 0)
        resp['total_words']   = result.get('total_words', 0)
        resp['elapsed']       = result.get('elapsed', 0)
    elif job['status'] == 'error':
        resp['error'] = job['error']
    return jsonify(resp)


@app.route('/api/ebook/bundle-download/<job_id>', methods=['GET'])
def bundle_download(job_id):
    """Download the finished bundle ZIP."""
    job = _bundle_jobs.get(job_id)
    if not job or job['status'] != 'done':
        return jsonify({'error': 'Not ready'}), 404
    result   = job.get('result', {})
    zip_path = result.get('zip_path', '')
    if not zip_path or not os.path.exists(zip_path):
        return jsonify({'error': 'File not found'}), 404
    return send_file(
        zip_path,
        as_attachment=True,
        download_name=os.path.basename(zip_path),
        mimetype='application/zip',
    )


# =============================================================================
# PRO MULTI-LAYER EDITOR — smart export (copy / concat / filter_complex)
# =============================================================================
_PRO_JOBS: dict = {}  # job_id -> {status, progress, output, log, error}


def _pro_run_job(job_id: str, timeline: dict, out_path: str,
                 preset: str = 'ultrafast', crf: int = 23):
    import threading
    from smart_exporter import plan_export, run_export

    def _work():
        job = _PRO_JOBS[job_id]
        try:
            workdir = os.path.join(os.path.dirname(out_path), f'_pro_tmp_{job_id[:8]}')
            plan = plan_export(timeline, out_path, workdir, preset=preset, crf=crf)
            job['mode'] = plan.mode
            job['status'] = 'running'
            job['progress'] = 10
            ok, log = run_export(plan)
            job['log'] = log[-4000:]
            if ok:
                job['status'] = 'done'
                job['progress'] = 100
                job['output'] = os.path.basename(out_path)
            else:
                job['status'] = 'error'
                job['error'] = (log.splitlines()[-1] if log else 'Export failed')
            # cleanup workdir best-effort
            try:
                if os.path.isdir(workdir):
                    for f in os.listdir(workdir):
                        try: os.remove(os.path.join(workdir, f))
                        except Exception: pass
                    os.rmdir(workdir)
            except Exception: pass
        except Exception as e:
            job['status'] = 'error'
            job['error'] = str(e)

    t = threading.Thread(target=_work, daemon=True); t.start()


@app.route('/api/editor/pro-plan', methods=['POST'])
def pro_plan_export():
    """Dry-run: returns which mode would be used + the generated command(s)."""
    try:
        from smart_exporter import plan_export
        data = request.get_json() or {}
        timeline = data.get('timeline') or {}
        out_path = os.path.join(OUTPUT_FOLDER, 'pro_preview.mp4')
        workdir = os.path.join(OUTPUT_FOLDER, '_pro_tmp_preview')
        plan = plan_export(timeline, out_path, workdir,
                           preset=data.get('preset', 'ultrafast'),
                           crf=int(data.get('crf', 23)))
        return jsonify({
            'success': True,
            'mode': plan.mode,
            'debug': plan.debug,
            'num_inputs': len(plan.final_cmd),  # rough proxy
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/editor/pro-export', methods=['POST'])
def pro_export():
    """Start a Pro multi-layer export job.

    Body: { timeline: {...}, preset: 'ultrafast', crf: 23, filename: 'optional.mp4' }
    Returns: { success, job_id }
    """
    try:
        data = request.get_json() or {}
        timeline = data.get('timeline') or {}
        if not (timeline.get('tracks') or []):
            return jsonify({'success': False, 'error': 'timeline.tracks is required'}), 400
        filename = data.get('filename') or f'pro_export_{uuid.uuid4().hex[:8]}.mp4'
        if not filename.lower().endswith('.mp4'):
            filename += '.mp4'
        out_path = os.path.join(OUTPUT_FOLDER, filename)
        job_id = uuid.uuid4().hex
        _PRO_JOBS[job_id] = {
            'status': 'queued', 'progress': 0, 'output': None,
            'log': '', 'error': None, 'mode': None,
        }
        _pro_run_job(job_id, timeline, out_path,
                     preset=data.get('preset', 'ultrafast'),
                     crf=int(data.get('crf', 23)))
        return jsonify({'success': True, 'job_id': job_id, 'filename': filename})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/editor/pro-status/<job_id>', methods=['GET'])
def pro_export_status(job_id: str):
    j = _PRO_JOBS.get(job_id)
    if not j:
        return jsonify({'success': False, 'error': 'unknown job_id'}), 404
    return jsonify({
        'success': True,
        'status': j['status'],
        'progress': j.get('progress', 0),
        'mode': j.get('mode'),
        'output': j.get('output'),
        'error': j.get('error'),
        'log_tail': (j.get('log') or '')[-2000:],
    })


@app.route('/api/editor/ffprobe', methods=['POST'])
def pro_ffprobe():
    """Lightweight metadata probe for Pro editor (duration, w/h, fps, audio, codec)."""
    try:
        data = request.get_json() or {}
        path = data.get('path') or ''
        if not path: return jsonify({'success': False, 'error': 'path required'}), 400
        # resolve path: could be absolute, or basename inside upload/output folders
        candidates = [path]
        for base in [UPLOAD_FOLDER, OUTPUT_FOLDER]:
            candidates.append(os.path.join(base, os.path.basename(path)))
        abs_path = next((p for p in candidates if os.path.exists(p)), None)
        if not abs_path:
            return jsonify({'success': False, 'error': 'file not found'}), 404
        cmd = [
            'ffprobe', '-v', 'error', '-print_format', 'json',
            '-show_format', '-show_streams', abs_path,
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            return jsonify({'success': False, 'error': r.stderr[-500:]}), 500
        import json as _json
        info = _json.loads(r.stdout or '{}')
        vstream = next((s for s in info.get('streams', []) if s.get('codec_type') == 'video'), None)
        astream = next((s for s in info.get('streams', []) if s.get('codec_type') == 'audio'), None)
        fmt = info.get('format') or {}
        fps = 0.0
        if vstream:
            r_fps = vstream.get('r_frame_rate') or '0/1'
            try:
                num, den = r_fps.split('/')
                fps = float(num) / float(den) if float(den) else 0.0
            except Exception: pass
        return jsonify({
            'success': True,
            'path': abs_path,
            'duration': float(fmt.get('duration', 0) or 0),
            'width': int(vstream.get('width', 0)) if vstream else 0,
            'height': int(vstream.get('height', 0)) if vstream else 0,
            'fps': round(fps, 3),
            'video_codec': (vstream or {}).get('codec_name'),
            'audio_codec': (astream or {}).get('codec_name'),
            'has_audio': bool(astream),
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == '__main__':
    print("="*60)
    print("🎬 VIDEO EDITOR API SERVER")
    print("="*60)

    # Initialize database (will auto-create files if needed)
    print("\n📦 Initializing database...")
    from database import initialize_database
    initialize_database()

    # Create default image style if none exist
    print("\n🎨 Checking image styles...")
    from image_style_manager import ImageStyleManager
    styles = ImageStyleManager.get_all_styles()
    if not styles or len(styles) == 0:
        print("   Creating default image style...")
        default_prompts = [
            "Professional trading chart visualization with candlesticks, showing {MARKET_CONDITION}, clean financial aesthetic, 4K quality",
            "Abstract representation of {EMOTIONAL_STATE} in trading psychology, modern minimal design, dark professional theme",
            "Conceptual image of {MINDSET_CONCEPT}, trader at desk with multiple monitors, realistic photography style",
            "Financial market data visualization showing {CHART_PATTERN}, professional trading interface, blue and green accents",
            "Symbolic representation of {TRADING_ACTION}, clean infographic style, professional business aesthetic",
            "Abstract concept of {PSYCHOLOGICAL_TERM} in finance, minimal modern design, muted professional colors"
        ]
        try:
            default_style = ImageStyleManager.create_style("Default Trading Style", default_prompts)
            print(f"   ✅ Created default image style: {default_style['id']}")
        except Exception as e:
            print(f"   ⚠️ Could not create default style: {e}")
    else:
        print(f"   ✅ Found {len(styles)} image style(s)")

    # Create directories
    print("\n📁 Ensuring directories exist...")
    ensure_directory_exists(UPLOAD_FOLDER)
    ensure_directory_exists(TEMP_FOLDER)
    ensure_directory_exists(OUTPUT_FOLDER)

    print(f"\n📂 Upload folder: {os.path.abspath(UPLOAD_FOLDER)}")
    print(f"📂 Output folder: {os.path.abspath(OUTPUT_FOLDER)}")
    print(f"📂 Temp folder: {os.path.abspath(TEMP_FOLDER)}")

    # Check for data directory
    data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
    if os.path.exists(data_dir):
        print(f"📂 Data folder: {os.path.abspath(data_dir)}")

    print("="*60)
    print("🚀 Starting server on http://localhost:5000")
    print("="*60)
    print("\n📋 AI VIDEO STUDIO - Single Page Application")
    print("   • Main App:        http://localhost:5000/")
    print("   • Dashboard:       Navigate using sidebar")
    print("   • AI Generator:    Navigate using sidebar")
    print("   • MR BAHA Editor:  Navigate using sidebar")
    print("   • Output Files:    Navigate using sidebar")
    print("   • Settings:        Click ⚙️ button in header")
    print("="*60)

    # Check API configuration
    from config import Config
    status = Config.get_api_config_status()
    if status['gemini_configured'] and status['replicate_configured']:
        print("\n✅ API keys configured - Ready to generate videos!")
    else:
        print("\n⚠️  API keys not configured")
        print("   → Configure at: http://localhost:5000/api-config.html")
        if not status['gemini_configured']:
            print("   • Gemini API key needed for script generation")
        if not status['replicate_configured']:
            print("   • Replicate API token needed for image generation")
    print("="*60 + "\n")

    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True,
        threaded=True
    )
