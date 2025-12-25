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
ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'bmp', 'gif', 'tiff', 'webp'}
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
    Process video project

    Request JSON:
        {
            'visual_media': [
                {'rank': 1, 'type': 'video', 'file_id': '...'},
                {'rank': 2, 'type': 'image', 'file_id': '...'}
            ],
            'audio_files': [
                {'rank': 1, 'file_id': '...'}
            ],
            'whisper_model': 'base',  # optional
            'output_filename': 'my_video.mp4'  # optional
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
        whisper_model = data.get('whisper_model', 'base')
        output_filename = data.get('output_filename')

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
            file_ext = self._find_uploaded_file(file_id)
            if not file_ext:
                return jsonify({'error': f'File not found: {file_id}'}), 404

            item['path'] = os.path.join(app.config['UPLOAD_FOLDER'], f"{file_id}.{file_ext}")

        for item in audio_files:
            file_id = item.get('file_id')
            if not file_id:
                return jsonify({'error': 'Missing file_id in audio_files'}), 400

            # Find file with this ID
            file_ext = self._find_uploaded_file(file_id)
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
                whisper_model=whisper_model,
                output_filename=output_filename,
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


@app.route('/api/download/<filename>', methods=['GET'])
def download_file(filename):
    """Download output file"""
    try:
        return send_from_directory(
            OUTPUT_FOLDER,
            filename,
            as_attachment=True
        )
    except FileNotFoundError:
        return jsonify({'error': 'File not found'}), 404


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
    print(f"Upload folder: {os.path.abspath(UPLOAD_FOLDER)}")
    print(f"Output folder: {os.path.abspath(OUTPUT_FOLDER)}")
    print(f"Temp folder: {os.path.abspath(TEMP_FOLDER)}")
    print("="*60)
    print("Starting server on http://localhost:5000")
    print("="*60)

    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True,
        threaded=True
    )
