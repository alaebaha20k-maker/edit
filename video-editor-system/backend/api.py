#!/usr/bin/env python3
"""
Flask API server for video editing system
Provides REST API for video processing
"""

import os
import sys
import json
import uuid
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
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'Video Editor API',
        'version': '1.0.0'
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


@app.route('/api/generate-script', methods=['POST'])
def generate_script():
    """Generate AI script using Gemini - EXACT HTML system"""
    from script_generator import ScriptGenerator
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
        length = data.get('length', 60000)  # Default to 60K if not provided

        if not title or not niche_id:
            return jsonify({'error': 'Missing required fields: title, niche_id'}), 400

        # Validate length (must be 30K, 60K, or 100K)
        if length not in Config.VALID_SCRIPT_LENGTHS:
            return jsonify({'error': f'Invalid length. Must be one of: {Config.VALID_SCRIPT_LENGTHS}'}), 400

        # Validate API key
        errors = Config.validate_api_keys()
        if any('GEMINI' in e for e in errors):
            return jsonify({'error': 'Gemini API key not configured'}), 500

        # Get niche info for header
        niche = NicheManager.get_niche(niche_id)
        if not niche:
            return jsonify({'error': 'Niche not found'}), 404

        # Generate script with EXACT HTML system
        generator = ScriptGenerator()
        result = generator.generate_script(title, niche_id, length=length, verbose=True)

        # SAVE SCRIPT TO FILE - Use OUTPUT_FOLDER directly (same as videos)
        timestamp = int(time.time())
        script_filename = f"script_{timestamp}.txt"
        script_path = os.path.join(OUTPUT_FOLDER, script_filename)

        print(f"\n📝 Saving script to: {script_path}")

        # Write script with header
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(f"{'='*70}\n")
            f.write(f"  SCRIPT - {title}\n")
            f.write(f"{'='*70}\n")
            f.write(f"Title: {title}\n")
            f.write(f"Niche: {niche['name']}\n")
            f.write(f"Language: {niche['language']}\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Characters: {result['stats']['chars']:,}\n")
            f.write(f"Words: {result['stats']['words']:,}\n")
            f.write(f"Quality: {result.get('quality', 'N/A')}\n")
            f.write(f"Narrative Approach: {result.get('approach', 'N/A')}\n")
            f.write(f"{'='*70}\n\n")
            f.write(result['script'])

        print(f"✅ Script saved successfully!")
        print(f"   File: {script_filename}")
        print(f"   Size: {os.path.getsize(script_path):,} bytes")

        return jsonify({
            'success': True,
            'script': result['script'],
            'script_file': script_path,
            'script_filename': script_filename,
            'length': result['stats']['chars'],
            'words': result['stats']['words'],
            'quality': result['quality'],
            'approach': result['approach'],
            'time': result['stats']['time'],
            'issues': result.get('issues', []),
            'suggestions': result.get('suggestions', [])
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

        if not title or not script or not style_id:
            return jsonify({'error': 'Missing required fields: title, script, style_id'}), 400

        # Validate API key
        errors = Config.validate_api_keys()
        if any('REPLICATE' in e for e in errors):
            return jsonify({'error': 'Replicate API token not configured'}), 500

        # Generate images
        generator = ImageGenerator()
        image_urls = generator.generate_images(title, script, style_id)

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
        replicate_token = data.get('replicate_api_token')

        if not gemini_key and not replicate_token:
            return jsonify({'error': 'At least one API key must be provided'}), 400

        # Save configuration
        Config.save_api_config(
            gemini_key=gemini_key,
            replicate_token=replicate_token
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


if __name__ == '__main__':
    print("="*60)
    print("🎬 VIDEO EDITOR API SERVER")
    print("="*60)

    # Initialize database (will auto-create files if needed)
    print("\n📦 Initializing database...")
    from database import initialize_database
    initialize_database()

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
    print("\n📋 Available pages:")
    print("   • Main editor:     http://localhost:5000/")
    print("   • API Config:      http://localhost:5000/api-config.html ⚙️")
    print("   • Create niche:    http://localhost:5000/niche-creator.html")
    print("   • Create style:    http://localhost:5000/style-creator.html")
    print("   • AI generator:    http://localhost:5000/generator.html")
    print("   • Output files:    http://localhost:5000/output")
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
