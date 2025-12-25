# Quick Start Guide

Get up and running with the Video Editing Automation System in 5 minutes!

## Step 1: Install (2 minutes)

### Linux/macOS
```bash
chmod +x install.sh
./install.sh
```

### Windows
```batch
install.bat
```

## Step 2: Test Installation (1 minute)

```bash
python3 test_system.py
```

All tests should pass with green checkmarks.

## Step 3: Create Sample Data (1 minute)

```bash
python3 create_sample_data.py
```

This creates test videos, images, and audio files in `sample_data/`.

## Step 4: Run the System (1 minute)

### Option A: Web Interface
```bash
python3 backend/api.py
```

Then open your browser to: **http://localhost:5000**

### Option B: Command Line
```bash
python3 backend/main.py
```

## First Video Creation

### Using the Web Interface:

1. **Upload Visual Media** (Line 1):
   - Drag & drop: `sample_data/intro.mp4`
   - Drag & drop: `sample_data/slide1.jpg`
   - Drag & drop: `sample_data/demo.mp4`

2. **Upload Audio** (Line 2):
   - Drag & drop: `sample_data/narration1.mp3`
   - Drag & drop: `sample_data/music.mp3`

3. **Configure**:
   - Whisper Model: Base (recommended)
   - Output Filename: my_first_video.mp4

4. **Create**:
   - Click "🚀 Create Video"
   - Wait for processing (~2-3 minutes)
   - Download your video!

### Using Python Code:

```python
from backend.main import VideoEditorSystem

# Initialize
editor = VideoEditorSystem()

# Define media (in ranked order)
visual_media = [
    {'rank': 1, 'type': 'video', 'path': 'sample_data/intro.mp4'},
    {'rank': 2, 'type': 'image', 'path': 'sample_data/slide1.jpg'},
    {'rank': 3, 'type': 'video', 'path': 'sample_data/demo.mp4'},
]

audio_files = [
    {'rank': 1, 'path': 'sample_data/narration1.mp3'},
    {'rank': 2, 'path': 'sample_data/music.mp3'},
]

# Process
result = editor.process_video_project(
    visual_media=visual_media,
    audio_files=audio_files,
    whisper_model="base"
)

print(f"✅ Video created: {result['output_path']}")
```

## What Happens?

1. ✓ Validates all files
2. ✓ Calculates image display times (to match audio length)
3. ✓ Converts images to video clips
4. ✓ Normalizes all videos to 1080p@30fps
5. ✓ Concatenates everything in ranked order
6. ✓ Merges all audio files
7. ✓ Generates AI captions (Whisper)
8. ✓ Creates final video with captions

**Result**: Professional 1080p video in `output/` folder!

## Troubleshooting

### "FFmpeg not found"
```bash
# Ubuntu/Debian
sudo apt install ffmpeg

# macOS
brew install ffmpeg
```

### "Whisper not installed"
```bash
pip install openai-whisper
```

### Slow processing?
- Use Whisper model "base" or "tiny"
- Use smaller/shorter videos
- Close other applications

## Next Steps

- Read full documentation: `README.md`
- Run tests: `python3 test_system.py`
- Try with your own media files
- Explore the REST API

## Support

Having issues?
1. Run tests: `python3 test_system.py`
2. Check README.md troubleshooting section
3. Verify FFmpeg: `ffmpeg -version`
4. Check Python: `python3 --version` (needs 3.8+)

---

**You're all set! 🎉 Start creating amazing videos!**
