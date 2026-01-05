# 🎬 AI Video Generator System

## Complete AI-Powered Video Creation Platform

This system has been upgraded with full AI capabilities to automatically generate professional trading psychology videos using Gemini AI and Replicate.

---

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Set API Keys

```bash
# Set Gemini API Key (required for script generation)
export GEMINI_API_KEY='your-gemini-api-key-here'

# Set Replicate API Token (required for image generation)
export REPLICATE_API_TOKEN='your-replicate-token-here'
```

**Get API Keys:**
- Gemini: https://aistudio.google.com/app/apikey
- Replicate: https://replicate.com/account/api-tokens

### 3. Start the Server

```bash
cd backend
python api.py
```

Server will start at: http://localhost:5000

### 4. Access the Interfaces

- **Manual Editor:** http://localhost:5000/ (existing functionality)
- **AI Generator:** http://localhost:5000/generator.html (NEW!)

---

## 🎯 How It Works - Complete Workflow

### Step 1: Create Custom Niches

Niches define your content topic and writing style in any language.

**Via API:**
```bash
curl -X POST http://localhost:5000/api/niches \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Trading Psychology",
    "language": "English",
    "writing_guidelines": "Write about trading psychology with focus on discipline, emotional control, and risk management. Use clear language, real examples, and motivational tone. Target: 60,000+ characters..."
  }'
```

**Default Niches Included:**
- Trading Psychology (English)
- Psychologie du Trading (French)

Run this to create defaults:
```bash
cd backend
python niche_manager.py
```

### Step 2: Create Image Styles

Image styles define 6 prompt templates with dynamic variables.

**Via API:**
```bash
curl -X POST http://localhost:5000/api/image-styles \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Stick Figure Trading",
    "prompts": [
      "Minimalist stick figure trader at desk {TITLE_KEYWORDS}",
      "Simple stick figure showing {EMOTIONAL_STATE}",
      "Basic stick figure looking at chart {CHART_PATTERN}",
      "Clean stick figure celebrating trading win",
      "Stick figure analyzing market data",
      "Stick figure with zen mindset trading"
    ]
  }'
```

**Dynamic Variables:**
- `{TITLE_KEYWORDS}` - Extracted from title
- `{EMOTIONAL_STATE}` - Detected emotional state
- `{CHART_PATTERN}` - Technical analysis terms
- `{TRADING_ACTION}` - Trading actions
- `{MARKET_CONDITION}` - Market conditions
- `{MINDSET_CONCEPT}` - Psychology concepts

Run this to create defaults:
```bash
cd backend
python image_style_manager.py
```

### Step 3: Use the AI Generator UI

1. **Open:** http://localhost:5000/generator.html

2. **Select Niche & Style:**
   - Choose your niche (defines script style)
   - Choose your image style (defines visual aesthetic)

3. **Enter Title:**
   - Example: "The Zen Trader's Guide to Emotional Control"

4. **Generate Script:**
   - Click "Generate Script with Gemini AI"
   - Wait 1-2 minutes
   - Generates 60,000+ character voice-ready script
   - NO markdown, NO formatting - ready for narration

5. **Generate Images:**
   - Click "Generate 6 Images with Replicate"
   - Wait 1-2 minutes
   - Creates 6 AI-generated images based on style prompts

6. **Upload Audio:**
   - Upload your voice narration audio files
   - Supports multiple parts (ranked automatically)
   - Accepts: MP3, WAV, AAC, M4A

7. **Create Video:**
   - Click "Create Video"
   - System automatically:
     - Downloads all 6 images
     - Concatenates audio parts
     - Creates video clips from images
     - Assembles final video
     - Syncs perfectly with audio

8. **Download:**
   - Get your finished video in 1080p@30fps

---

## 📡 API Endpoints

### Niches

**GET /api/niches**
```bash
curl http://localhost:5000/api/niches
```

**POST /api/niches**
```bash
curl -X POST http://localhost:5000/api/niches \
  -H "Content-Type: application/json" \
  -d '{"name": "...", "language": "...", "writing_guidelines": "..."}'
```

**GET /api/niches/:id**
```bash
curl http://localhost:5000/api/niches/123e4567-e89b-12d3-a456-426614174000
```

### Image Styles

**GET /api/image-styles**
```bash
curl http://localhost:5000/api/image-styles
```

**POST /api/image-styles**
```bash
curl -X POST http://localhost:5000/api/image-styles \
  -H "Content-Type: application/json" \
  -d '{"name": "...", "prompts": ["...", "...", ...]}'
```

### AI Generation

**POST /api/generate-script**
```bash
curl -X POST http://localhost:5000/api/generate-script \
  -H "Content-Type: application/json" \
  -d '{"title": "...", "niche_id": "..."}'
```

**POST /api/generate-images**
```bash
curl -X POST http://localhost:5000/api/generate-images \
  -H "Content-Type: application/json" \
  -d '{"title": "...", "script": "...", "style_id": "..."}'
```

**POST /api/process-ai-video**
```bash
curl -X POST http://localhost:5000/api/process-ai-video \
  -H "Content-Type: application/json" \
  -d '{
    "title": "...",
    "image_urls": ["...", "...", ...],
    "audio_files": [{"rank": 1, "file_id": "..."}],
    "niche_id": "...",
    "style_id": "...",
    "script": "..."
  }'
```

### Recent Videos

**GET /api/videos/recent**
```bash
curl http://localhost:5000/api/videos/recent?limit=10
```

---

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────┐
│                   FRONTEND                          │
├─────────────────────────────────────────────────────┤
│ • generator.html - AI workflow UI                  │
│ • index.html - Manual editor (existing)             │
└─────────────────────────────────────────────────────┘
                        │
                        ↓
┌─────────────────────────────────────────────────────┐
│                   FLASK API                         │
├─────────────────────────────────────────────────────┤
│ • /api/niches - Niche CRUD                          │
│ • /api/image-styles - Style CRUD                    │
│ • /api/generate-script - Gemini integration         │
│ • /api/generate-images - Replicate integration      │
│ • /api/process-ai-video - Video assembly            │
└─────────────────────────────────────────────────────┘
                        │
        ┌───────────────┼───────────────┐
        ↓               ↓               ↓
┌───────────────┐ ┌──────────────┐ ┌──────────────┐
│  GEMINI API   │ │ REPLICATE API│ │   FFmpeg     │
├───────────────┤ ├──────────────┤ ├──────────────┤
│ • Script Gen  │ │ • Image Gen  │ │ • Video Proc │
│ • 60K chars   │ │ • Flux Model │ │ • 1080p@30   │
│ • 3-part sys  │ │ • 6 images   │ │ • Audio sync │
└───────────────┘ └──────────────┘ └──────────────┘
                        │
                        ↓
┌─────────────────────────────────────────────────────┐
│                JSON DATABASES                        │
├─────────────────────────────────────────────────────┤
│ • data/niches.json - Custom niches                  │
│ • data/image_styles.json - Image styles             │
│ • data/videos.json - Generated videos               │
└─────────────────────────────────────────────────────┘
```

---

## 📂 File Structure

```
video-editor-system/
├── backend/
│   ├── api.py                    # Flask server with all routes
│   ├── config.py                 # Configuration & API keys (NEW)
│   ├── database.py               # JSON database operations (NEW)
│   ├── niche_manager.py          # Niche CRUD operations (NEW)
│   ├── image_style_manager.py    # Style CRUD operations (NEW)
│   ├── script_generator.py       # Gemini AI integration (NEW)
│   ├── image_generator.py        # Replicate integration (NEW)
│   ├── main.py                   # Video processing (UPDATED)
│   ├── ffmpeg_processor.py       # FFmpeg operations
│   ├── duration_calculator.py    # Duration calculations
│   ├── file_validator.py         # File validation
│   └── utils.py                  # Utilities
├── frontend/
│   ├── index.html                # Manual editor UI
│   ├── generator.html            # AI generator UI (NEW)
│   ├── app.js                    # Frontend logic
│   └── styles.css                # Styles
├── data/                         # JSON databases (NEW)
│   ├── niches.json
│   ├── image_styles.json
│   └── videos.json
├── uploads/                      # Uploaded files
├── temp/                         # Temporary processing files
├── output/                       # Final videos
└── requirements.txt              # Python dependencies (UPDATED)
```

---

## ⚙️ Configuration

Edit `backend/config.py` to customize:

```python
# Gemini Settings
GEMINI_MODEL = 'gemini-2.0-flash-exp'
GEMINI_TEMPERATURE = 0.85
GEMINI_MAX_TOKENS = 8192

# Replicate Settings
REPLICATE_MODEL = 'black-forest-labs/flux-schnell'

# Script Settings
TARGET_SCRIPT_LENGTH = 60000
MIN_SCRIPT_LENGTH = 50000
MAX_SCRIPT_LENGTH = 70000

# Images
IMAGES_PER_VIDEO = 6
IMAGE_DURATION_SECONDS = 5.0
```

---

## 🎨 Example Workflow

```bash
# 1. Create a niche
curl -X POST http://localhost:5000/api/niches \
  -H "Content-Type: application/json" \
  -d '{"name": "Zen Trading", "language": "English", "writing_guidelines": "..."}'

# Response: {"success": true, "niche": {"id": "abc-123", ...}}

# 2. Create an image style
curl -X POST http://localhost:5000/api/image-styles \
  -H "Content-Type: application/json" \
  -d '{"name": "Stick Figures", "prompts": [...]}'

# Response: {"success": true, "style": {"id": "def-456", ...}}

# 3. Generate script
curl -X POST http://localhost:5000/api/generate-script \
  -H "Content-Type: application/json" \
  -d '{"title": "Emotional Control Guide", "niche_id": "abc-123"}'

# Response: {"success": true, "script": "...", "length": 62450}

# 4. Generate images
curl -X POST http://localhost:5000/api/generate-images \
  -H "Content-Type: application/json" \
  -d '{"title": "...", "script": "...", "style_id": "def-456"}'

# Response: {"success": true, "image_urls": [...], "count": 6}

# 5. Upload audio (use /api/upload endpoint)

# 6. Create video (use /api/process-ai-video endpoint)
```

---

## 🔍 Troubleshooting

### API Keys Not Set
```
Error: GEMINI_API_KEY not set
```
**Solution:** Export API keys before starting server:
```bash
export GEMINI_API_KEY='your-key'
export REPLICATE_API_TOKEN='your-token'
python api.py
```

### Script Generation Fails
```
Error: Invalid niche_id
```
**Solution:** Create niches first or use existing niche IDs from `/api/niches`

### Image Generation Slow
- Normal: Takes 1-2 minutes for 6 images
- Replicate Flux Schnell processes sequentially
- Cost: ~$0.018 per video (6 images × $0.003)

### Video Processing Fails
- Check all 6 image URLs are valid
- Ensure audio files are uploaded
- Check FFmpeg is installed: `ffmpeg -version`

---

## 💡 Pro Tips

### Multi-Language Support
Create niches in any language:
```json
{
  "name": "تحليل التداول",
  "language": "Arabic",
  "writing_guidelines": "اكتب عن علم نفس التداول..."
}
```

### Custom Image Variables
Use dynamic variables in your image prompts:
```
"Trader showing {EMOTIONAL_STATE} while analyzing {CHART_PATTERN} in {MARKET_CONDITION}"
```

### Multiple Audio Parts
Upload multiple audio files for long-form content:
- Part 1: Introduction (5 min)
- Part 2: Main content (20 min)
- Part 3: Conclusion (5 min)

System automatically concatenates in order.

---

## 📊 System Capabilities

- **Script Generation:** 60,000+ character scripts
- **Image Generation:** 6 AI images per video
- **Video Output:** 1080p @ 30fps
- **Audio Support:** Multi-part concatenation
- **Languages:** Any language supported by Gemini
- **Processing Speed:** ~2-3 minutes end-to-end
- **Cost per Video:** ~$0.018 (images only)

---

## 🔗 Resources

- **Gemini API:** https://ai.google.dev/
- **Replicate:** https://replicate.com/
- **Flux Schnell Model:** https://replicate.com/black-forest-labs/flux-schnell
- **FFmpeg:** https://ffmpeg.org/

---

## 🎉 What's New vs Original System

### AI Features ✨
- ✅ Gemini AI script generation
- ✅ Replicate AI image generation
- ✅ Custom niche system
- ✅ Custom image style system
- ✅ Multi-language support
- ✅ Dynamic variable system
- ✅ JSON database tracking
- ✅ Complete workflow UI

### Preserved Features 🛡️
- ✅ Manual video editor (100% compatible)
- ✅ Multi-video/image support
- ✅ Smart video normalization
- ✅ Perfect audio/video sync
- ✅ Mute videos option
- ✅ JFIF image support
- ✅ Ultra-fast processing

---

## 📝 Summary

This upgrade transforms the video editor into a **complete AI content generation platform** while maintaining full backward compatibility with the original manual editing system.

**Use Cases:**
1. **AI Generation:** Title → Script → Images → Audio → Video (fully automated)
2. **Manual Editing:** Upload files → Process → Video (original functionality)
3. **Hybrid:** AI script/images + manual video clips

**Perfect for:**
- Trading psychology content creators
- Multi-language video production
- High-volume content generation
- Automated video workflows

---

**Created:** January 5, 2026
**Version:** 2.0 - AI Video Generator
**Status:** ✅ Production Ready
