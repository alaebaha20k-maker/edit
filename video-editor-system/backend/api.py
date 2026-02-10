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
import subprocess
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
from pathlib import Path

# Add backend directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main import VideoEditorSystem
from utils import ensure_directory_exists, get_file_size, format_time


# Initialize Flask app
app = Flask(__name__, static_folder='../frontend', static_url_path='')
CORS(app)  # Enable CORS for frontend

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


@app.route('/api/niches/<niche_id>', methods=['GET', 'DELETE'])
def manage_niche(niche_id):
    """Get or delete specific niche by ID"""
    from niche_manager import NicheManager

    try:
        if request.method == 'GET':
            niche = NicheManager.get_niche(niche_id)

            if not niche:
                return jsonify({'error': 'Niche not found'}), 404

            return jsonify({'niche': niche})

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

        title = data.get('title')
        niche_id = data.get('niche_id')
        length = data.get('length', Config.DEFAULT_SCRIPT_LENGTH)  # Default to 10K

        if not title or not niche_id:
            return jsonify({'error': 'Missing required fields: title, niche_id'}), 400

        # Validate length (must be between MIN and MAX)
        if not Config.validate_script_length(length):
            return jsonify({
                'error': f'Invalid length. Must be between {Config.MIN_SCRIPT_LENGTH} and {Config.MAX_SCRIPT_LENGTH} characters'
            }), 400

        # Validate API key
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
        result = generator.generate_script(title, niche_id, length=length, verbose=True)

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
        replicate_token = data.get('replicate_api_token')
        inworld_key = data.get('inworld_api_key')
        inworld_secret = data.get('inworld_api_secret')

        if not gemini_key and not director_gemini_key and not replicate_token and not inworld_key and not inworld_secret:
            return jsonify({'error': 'At least one API key must be provided'}), 400

        # Save configuration
        Config.save_api_config(
            gemini_key=gemini_key,
            director_gemini_key=director_gemini_key,
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


@app.route('/api/settings/api-keys', methods=['POST'])
def save_api_keys():
    """Save API keys (Script Writer Gemini, Director Gemini, Replicate, Inworld AI, Pexels, Pixabay)"""
    from settings_manager import SettingsManager

    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'No data provided'}), 400

        gemini = data.get('gemini')
        director_gemini = data.get('director_gemini')
        replicate = data.get('replicate')
        inworld = data.get('inworld')
        pexels = data.get('pexels')
        pixabay = data.get('pixabay')

        # Save API keys (Script Writer Gemini and Director Gemini are SEPARATE!)
        settings = SettingsManager.save_api_keys(
            gemini=gemini,
            director_gemini=director_gemini,
            replicate=replicate,
            inworld=inworld,
            pexels=pexels,
            pixabay=pixabay
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

        title_formula = data.get('title_formula')
        script_formula = data.get('script_formula')
        image_formula = data.get('image_formula')

        # Save formulas
        success = SettingsManager.save_formulas(
            title_formula=title_formula,
            script_formula=script_formula,
            image_formula=image_formula
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
        if formula_type not in ['title', 'script', 'image']:
            return jsonify({'error': 'Invalid formula type. Must be: title, script, or image'}), 400

        formula = SettingsManager.load_formula(formula_type)

        return jsonify({
            'success': True,
            'formula_type': formula_type,
            'formula': formula
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


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
            clip_path = clip.get('videoPath', '')
            start_time = clip.get('start', 0)
            end_time = clip.get('end', 0)
            duration = end_time - start_time

            if not os.path.exists(clip_path):
                continue

            # Extract clip segment
            temp_clip = os.path.join(temp_dir, f'clip_{i}.mp4')

            cmd = [
                'ffmpeg', '-y',
                '-i', clip_path,
                '-ss', str(start_time),
                '-t', str(duration),
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

            # Set quality parameters
            if quality == '1080':
                scale = 'scale=1920:1080'
                crf = '18'
            else:
                scale = 'scale=1280:720'
                crf = '23'

            # Final concatenation
            cmd = [
                'ffmpeg', '-y',
                '-f', 'concat',
                '-safe', '0',
                '-i', concat_file,
                '-vf', scale,
                '-c:v', 'libx264',
                '-preset', 'medium',
                '-crf', crf,
                '-c:a', 'aac',
                '-b:a', '192k',
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

        plan = director.plan_auto_images(
            script_text=script,
            style=style,
            n_images=n_images,
            scene_timing_hints=scene_timing_hints,  # Pass timing hints to Director
            force_regenerate=force_regenerate,
            verbose=True
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
            color_palette=data.get('color_palette', [])
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
            color_palette=data.get('color_palette')
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

        if not avatar_video_path or not audio_path:
            return jsonify({
                'success': False,
                'error': 'avatar_video and audio are required'
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

        # Step 1: Generate media plan
        generator = AvatarVideoGenerator()

        result = generator.generate_avatar_video(
            avatar_video_path=avatar_video_path,
            audio_path=audio_path,
            mode=mode,
            script=script,
            stock_apis=stock_apis,
            verbose=True
        )

        # Step 2: Assemble video
        assembler = AvatarVideoAssembler()

        final_video = assembler.assemble_video(
            avatar_video_path=avatar_video_path,
            audio_path=audio_path,
            media_plan=result['media_plan'],
            media_items=result['media_items'],
            mode=mode,
            verbose=True
        )

        return jsonify({
            'success': True,
            'video_path': final_video,
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
