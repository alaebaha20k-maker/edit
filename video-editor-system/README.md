# 🎬 AI-Powered Video Generation System

A complete end-to-end system for generating high-quality YouTube videos using AI. Automatically creates scripts, generates images, converts text to speech, and assembles professional videos with zoom effects, transitions, and audio mixing.

---

## 📋 TABLE OF CONTENTS

1. [Overview](#overview)
2. [System Architecture](#system-architecture)
3. [Core Features](#core-features)
4. [System Components](#system-components)
5. [Installation](#installation)
6. [Configuration](#configuration)
7. [Usage Guide](#usage-guide)
8. [API Endpoints](#api-endpoints)
9. [File Structure](#file-structure)
10. [Advanced Features](#advanced-features)
11. [Troubleshooting](#troubleshooting)

---

## 🎯 OVERVIEW

This system automates the entire YouTube video creation pipeline:

1. **Generate Title** → AI creates engaging titles based on your niche
2. **Generate Script** → AI writes voice-ready narration (supports multiple languages)
3. **Generate Images** → AI creates stunning visuals that match the script
4. **Text-to-Speech** → Converts script to natural voice (multiple voices supported)
5. **Video Assembly** → Combines everything with zoom effects, transitions, and background music
6. **Export** → Professional MP4 video ready to upload

### 🌟 Key Highlights

- **Multilingual Support**: Spanish, German, French, English (auto-detected from title)
- **AI-Powered**: Uses Gemini 2.5 Flash for scripts and RunPod/Replicate for images
- **Professional Quality**: Zoom effects, transitions, audio mixing, perfect timing
- **Modular Design**: Each component works independently or as a pipeline
- **Media Libraries**: Voice library and image library for reusable content
- **Real-time Monitoring**: Progress tracking and live previews

---

## 🏗️ SYSTEM ARCHITECTURE

```
┌─────────────────────────────────────────────────────────────┐
│                    FRONTEND (Web UI)                        │
│  index.html │ app.js │ unified-generator.js │ styles.css   │
└─────────────────────────┬───────────────────────────────────┘
                          │ HTTP REST API
┌─────────────────────────▼───────────────────────────────────┐
│                    BACKEND (Python Flask)                    │
│                         api.py                               │
└──────┬──────┬──────┬──────┬──────┬──────┬──────┬──────┬────┘
       │      │      │      │      │      │      │      │
   ┌───▼──┐ ┌─▼────┐ ┌▼───┐ ┌▼──┐ ┌▼───┐ ┌▼────┐ ┌▼───┐ ┌▼──┐
   │Title │ │Script│ │Img │ │TTS│ │Video│ │Media│ │Niche│ │DB │
   │  Gen │ │  Gen │ │Gen │ │   │ │Asm │ │ Lib │ │Mgmt │ │   │
   └──────┘ └──────┘ └────┘ └───┘ └────┘ └─────┘ └─────┘ └───┘
       │        │       │      │      │
   ┌───▼────────▼───────▼──────▼──────▼────┐
   │         AI Services Layer             │
   │  Gemini │ RunPod │ Replicate │ ElevenLabs │
   └───────────────────────────────────────┘
```

---

## ✨ CORE FEATURES

### 1. **Title Generation** 🎯
- AI-powered title creation using customizable formulas
- Niche-specific title strategies
- Automatic language detection
- Hook + Topic + Value Promise structure
- **API**: `/api/generate-title`

### 2. **Script Generation** 📝
- **3-Chunk Architecture** (30% Hook / 40% Content / 30% Conclusion)
- Multilingual support (auto-detected from title)
- Length: 1,000 - 80,000 characters
- Voice-ready narration (no visual cues, timestamps, or formatting)
- Title-lock validation (prevents topic drift)
- Uses niche writing guidelines
- **API**: `/api/generate-script`

### 3. **Image Generation** 🖼️
- **AI Director System**: Analyzes script and generates perfect image prompts
- **Multi-Provider Support**:
  - RunPod (Flux.1 Schnell - fastest)
  - Replicate (Flux.1 Dev - highest quality)
- **Auto Images**: Intelligently determines number of images needed
- **Perfect Timing**: Optional Whisper STT for precise image-to-narration alignment
- **Timed Zoom Effects**: Dynamic zoom on each image
- **API**: `/api/generate-image-prompts`, `/api/generate-images-runpod`

### 4. **Text-to-Speech** 🔊
- **ElevenLabs Integration**: Professional voice synthesis
- **Voice Library**: Save and reuse favorite voices
- Multiple voice models supported
- Natural-sounding narration
- **API**: `/api/text-to-speech`

### 5. **Video Assembly** 🎥
- **Automatic Timing**: Matches images to script perfectly
- **Zoom Effects**: Ken Burns effect on all images
- **Transitions**: Smooth crossfades between images
- **Audio Mixing**:
  - Voice narration (primary track)
  - Background music (ducked under voice)
  - Adjustable volume levels
- **Professional Output**: 1920x1080 MP4 with H.264 encoding
- **API**: `/api/assemble-video`

### 6. **Media Libraries** 📚
- **Voice Library**: Save voices with name, provider, and settings
- **Image Library**: Store generated images with metadata
- **Multi-Select**: Download or delete multiple items at once
- **Search & Filter**: Find content quickly

### 7. **Niche Management** 🎨
- Create custom niches with writing guidelines
- Language settings per niche
- Product integration support
- Formula customization (title, script, image)
- **API**: `/api/niches`

---

## 🔧 SYSTEM COMPONENTS

### Backend Components

#### 1. **Script Generators**
- `script_generator_3chunk.py` - **Production version** (3-chunk system)
- `script_generator.py` - Alternative with one-block generation
- `chunk_planner.py` - Calculates chunk sizes (30/40/30 split)
- `title_generator.py` - AI title generation

#### 2. **Image Generation**
- `auto_images/director_client.py` - AI Director for image planning
- `image_generator_runpod.py` - RunPod Flux.1 Schnell integration
- `replicate_image_generator.py` - Replicate API integration
- `whisper_stt.py` - Audio timing analysis (optional)

#### 3. **Video Assembly**
- `video_assembler.py` - Main video assembly with MoviePy
- `audio_mixer.py` - Professional audio mixing and ducking

#### 4. **Core Services**
- `api.py` - Main Flask REST API server
- `database.py` - JSON-based data persistence
- `niche_manager.py` - Niche CRUD operations
- `settings_manager.py` - Formula and settings management
- `config.py` - Centralized configuration

#### 5. **Utilities**
- `utils.py` - Language detection, file operations
- `test_language_detection.py` - Language detection test suite

### Frontend Components

#### 1. **Main Interface**
- `index.html` - Main web interface
- `app.js` - Core application logic
- `unified-generator.js` - Unified video generation workflow
- `styles.css` - UI styling

#### 2. **Configuration Pages**
- `api-config.html` - API key configuration
- `settings.html` - Formula editor
- `test.html` - Testing interface

---

## 🚀 INSTALLATION

### Prerequisites

```bash
# System Requirements
- Python 3.8+
- FFmpeg (for video processing)
- 4GB+ RAM
- 10GB+ disk space

# Operating Systems
- Linux (recommended)
- macOS
- Windows (with WSL recommended)
```

### Step 1: Clone Repository

```bash
git clone https://github.com/alaebaha20k-maker/edit.git
cd edit/video-editor-system
```

### Step 2: Install Python Dependencies

```bash
cd backend
pip install -r requirements.txt
```

**Key Dependencies:**
- `flask` - Web server
- `google-generativeai` - Gemini API
- `moviepy` - Video editing
- `replicate` - Image generation
- `requests` - HTTP client
- `python-dotenv` - Environment variables

### Step 3: Install FFmpeg

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install ffmpeg
```

**macOS:**
```bash
brew install ffmpeg
```

**Windows:**
Download from https://ffmpeg.org/download.html

### Step 4: Configuration

Create `.env` file in `backend/` directory:

```bash
# Required API Keys
GEMINI_API_KEY=your_gemini_api_key_here
RUNPOD_API_KEY=your_runpod_api_key_here
ELEVENLABS_API_KEY=your_elevenlabs_api_key_here

# Optional API Keys
REPLICATE_API_TOKEN=your_replicate_api_key_here
```

### Step 5: Start the Server

```bash
cd backend
python api.py
```

Server starts at: `http://localhost:5000`

### Step 6: Open Web Interface

Open in browser:
```
http://localhost:5000
```

---

## ⚙️ CONFIGURATION

### API Keys Setup

Navigate to: `http://localhost:5000/api-config.html`

**Required Keys:**

1. **Gemini API Key** (Google AI)
   - Get it: https://makersuite.google.com/app/apikey
   - Used for: Title generation, script generation, image prompts

2. **RunPod API Key**
   - Get it: https://www.runpod.io/console/user/settings
   - Used for: Fast image generation (Flux.1 Schnell)

3. **ElevenLabs API Key**
   - Get it: https://elevenlabs.io/
   - Used for: Text-to-speech voice synthesis

**Optional Keys:**

4. **Replicate API Token**
   - Get it: https://replicate.com/account/api-tokens
   - Used for: High-quality image generation (Flux.1 Dev)

### Formula Configuration

Navigate to: `http://localhost:5000/settings.html`

**Available Formulas:**

1. **Title Formula** - Defines title structure
2. **Script Formula** - Defines narrative flow
3. **Image Formula** - Guides image generation

### Niche Configuration

Create custom niches with:
- Name and description
- Default language
- Writing guidelines
- Product mentions (optional)

---

## 📖 USAGE GUIDE

### Quick Start: Generate Your First Video

#### Step 1: Create a Niche

1. Go to main interface
2. Click **"Add Niche"**
3. Fill in details
4. Click **"Save"**

#### Step 2: Generate Title

1. Enter topic
2. Select niche
3. Click **"Generate Title"**

#### Step 3: Generate Script

1. Title auto-filled
2. Select script length
3. Click **"Generate Script"**

#### Step 4: Generate Images

1. Script auto-filled
2. Select provider
3. Click **"Generate Images"**

#### Step 5: Generate Voice

1. Select a voice
2. Click **"Generate TTS"**

#### Step 6: Assemble Video

1. Optional: Add background music
2. Click **"Assemble Video"**
3. Video downloads automatically

**Total Time: 5-10 minutes for a complete video!**

---

## 🔌 API ENDPOINTS

### Title Generation
```http
POST /api/generate-title
```

### Script Generation
```http
POST /api/generate-script
```

### Image Generation
```http
POST /api/generate-image-prompts
POST /api/generate-images-runpod
```

### Text-to-Speech
```http
POST /api/text-to-speech
```

### Video Assembly
```http
POST /api/assemble-video
```

### Niche Management
```http
GET    /api/niches
POST   /api/niches
PUT    /api/niches/<id>
DELETE /api/niches/<id>
```

For detailed API documentation, see the inline comments in `api.py`.

---

## 📁 FILE STRUCTURE

```
video-editor-system/
├── backend/
│   ├── api.py                          # Main Flask API server
│   ├── config.py                       # Configuration
│   ├── database.py                     # Data persistence
│   ├── script_generator_3chunk.py      # Script generator (production)
│   ├── script_generator.py             # Alternative generator
│   ├── chunk_planner.py                # Chunk planning
│   ├── title_generator.py              # Title generation
│   ├── auto_images/
│   │   └── director_client.py          # AI Director
│   ├── image_generator_runpod.py       # RunPod integration
│   ├── replicate_image_generator.py    # Replicate integration
│   ├── eleven_tts.py                   # ElevenLabs TTS
│   ├── video_assembler.py              # Video assembly
│   ├── audio_mixer.py                  # Audio mixing
│   ├── whisper_stt.py                  # Audio timing
│   ├── niche_manager.py                # Niche management
│   ├── settings_manager.py             # Settings
│   ├── utils.py                        # Utilities + Language detection
│   ├── data/                           # Data storage
│   ├── output/                         # Generated videos
│   ├── media_library/                  # Media storage
│   ├── README_LANGUAGE_DETECTION.md    # Language docs
│   └── requirements.txt                # Dependencies
│
├── frontend/
│   ├── index.html                      # Main interface
│   ├── app.js                          # Application logic
│   ├── unified-generator.js            # Workflow
│   ├── styles.css                      # Styling
│   ├── api-config.html                 # API configuration
│   ├── settings.html                   # Formula editor
│   └── test.html                       # Testing
│
└── README.md                           # This file
```

---

## 🌟 ADVANCED FEATURES

### 1. **Automatic Language Detection**

The system automatically detects the language from your video title:

- **Spanish** - Detects ñ, á, é, í, ó, ú and Spanish words
- **German** - Detects ä, ö, ü, ß and German words
- **French** - Detects à, ç, è, é, ê and French words
- **English** - Default language

See: `backend/README_LANGUAGE_DETECTION.md` for complete details

### 2. **AI Director System**

Analyzes your script and intelligently plans image generation with:
- Scene analysis
- Image count optimization
- Timing suggestions
- Prompt generation with reasoning

### 3. **Timed Zoom Effects**

Every image gets a dynamic Ken Burns zoom effect based on duration.

### 4. **Smart Audio Mixing**

Professional audio with:
- Voice priority
- Music ducking
- Volume normalization
- Smooth transitions

### 5. **Formula System**

Customize content generation with flexible formulas for titles, scripts, and images.

### 6. **Media Library Management**

Save and reuse:
- Favorite voices
- Generated images
- Multi-select operations

### 7. **Quality Validation**

Scripts are validated for:
- Length accuracy (±10%)
- Format compliance
- Title lock
- Clean output

---

## 🐛 TROUBLESHOOTING

### Common Issues

**"GEMINI_API_KEY not set"**
- Add key to `.env` file or via web interface

**"FFmpeg not found"**
- Install FFmpeg: `sudo apt install ffmpeg`

**"Rate limit exceeded"**
- Wait 60 seconds between generations
- Free tier: 20 calls/min (Gemini)

**"Script validation failed"**
- System auto-retries up to 3 times
- Check niche guidelines are clear

**"Image generation timeout"**
- Check API key is valid
- Try different provider

**"Video assembly failed"**
- Verify FFmpeg is installed
- Check disk space (need 2GB+)

**"Language not detected correctly"**
- Add language-specific characters to title
- See language detection README

**"Audio out of sync"**
- Enable Whisper STT for perfect timing
- Adjust image duration manually

### Getting Help

1. Check console logs for errors
2. Test components individually
3. Verify API keys are valid
4. Review documentation
5. Create GitHub issue with logs

---

## 📊 SYSTEM REQUIREMENTS

### Minimum
- **CPU**: Dual-core 2.0 GHz
- **RAM**: 4 GB
- **Storage**: 10 GB free
- **Internet**: 10 Mbps
- **Python**: 3.8+
- **FFmpeg**: Latest

### Recommended
- **CPU**: Quad-core 3.0 GHz+
- **RAM**: 8 GB+
- **Storage**: 50 GB+ SSD
- **Internet**: 50 Mbps+
- **Python**: 3.10+

### API Rate Limits

**Gemini (Free Tier):**
- 20 requests/minute
- 1,500 requests/day

**ElevenLabs (Free Tier):**
- 10,000 characters/month

**RunPod / Replicate:**
- Pay per use
- No rate limits

---

## 🔐 SECURITY & PRIVACY

- API keys stored in `.env` (not committed to git)
- All data stored locally
- No external data sharing except AI APIs
- Keep API keys secret

---

## 🚧 ROADMAP

**Planned Features:**
- More language support
- YouTube direct upload
- Video templates
- Batch generation
- Custom voice cloning
- Analytics dashboard
- Subtitle generation

---

## 📄 LICENSE

This project is proprietary software. All rights reserved.

---

## 👥 CONTRIBUTING

Contributions welcome! Please:
1. Fork the repository
2. Create feature branch
3. Make changes
4. Submit pull request

---

## 📞 SUPPORT

- **Issues**: https://github.com/alaebaha20k-maker/edit/issues
- **Documentation**: See README files in each directory

---

## 🎉 ACKNOWLEDGMENTS

**AI Services:**
- Google Gemini 2.5 Flash
- RunPod Flux.1 Schnell
- Replicate Flux.1 Dev
- ElevenLabs Text-to-Speech
- OpenAI Whisper

**Libraries:**
- Flask
- MoviePy
- FFmpeg

---

**Built with ❤️ for content creators**

**Version**: 1.0.0
**Last Updated**: 2026-02-09
