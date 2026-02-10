# 🎬 AVATAR AI - Video Generator

Generate professional videos with avatar loops + AI images or stock videos, perfectly synced to audio narration.

---

## 🎯 OVERVIEW

**Avatar AI** creates engaging videos by:
1. Looping your avatar video (e.g., 33 seconds)
2. Adding AI-generated images OR stock videos between avatar segments
3. Perfectly matching the exact length of your audio narration (e.g., 27 minutes)
4. Using ultra-fast FFmpeg processing

---

## 🌟 KEY FEATURES

### Two Modes:

#### 1. **AI Images Auto** 🖼️
- Pattern: `1 min avatar → 5 sec AI image → 1 min avatar → 5 sec AI image...`
- Uses Replicate Flux.1 Dev for high-quality AI images
- Last 2 minutes: Full avatar video
- Perfect for educational, talking-head content

#### 2. **Videos Stock Auto** 🎥
- Pattern: `30 sec avatar → 5-10 sec stock video → 30 sec avatar → 5-10 sec stock video...`
- Searches multiple stock APIs (Pexels, Pixabay)
- AI decides 5 sec vs 10 sec intelligently
- Last 2 minutes: Full avatar video
- Perfect for dynamic, engaging content

### Smart Features:
- ✅ **Exact Audio Sync** - Final video matches audio length perfectly
- ✅ **Whisper STT** - Analyzes audio for precise timing
- ✅ **Gemini AI** - Plans media sequence intelligently
- ✅ **Ultra-Fast FFmpeg** - Uses ultrafast preset for quick processing
- ✅ **Seamless Loops** - Avatar loops naturally
- ✅ **Last 2 Minutes** - Always full avatar to match exact duration

---

## 📋 REQUIREMENTS

### Backend Files:
- `avatar_video_generator.py` - Main generator with Whisper + Gemini
- `stock_video_downloader.py` - Multi-API stock video downloader
- `avatar_video_assembler.py` - Ultra-fast FFmpeg video assembly
- API endpoints in `api.py`

### Frontend:
- `avatar-ai.html` - User interface

### API Keys Required:
1. **GEMINI_API_KEY** - For AI planning
2. **REPLICATE_API_TOKEN** - For AI images (AI Images mode)
3. **PEXELS_API_KEY** - For stock videos (Videos Stock mode)
4. **PIXABAY_API_KEY** - For stock videos (optional)

---

## 🚀 QUICK START

### 1. Install Dependencies

```bash
pip install google-generativeai replicate requests
```

### 2. Set Up API Keys

Create `.env` file:
```bash
GEMINI_API_KEY=your_key
REPLICATE_API_TOKEN=your_token
PEXELS_API_KEY=your_key
PIXABAY_API_KEY=your_key  # optional
```

### 3. Start Server

```bash
cd backend
python api.py
```

### 4. Open Avatar AI

Go to: `http://localhost:5000/avatar-ai.html`

---

## 📖 HOW TO USE

### Step 1: Upload Avatar Video
- Click upload area
- Select your avatar video (e.g., 33 seconds)
- Supports: MP4, MOV

### Step 2: Upload Audio
- Click upload area
- Select your audio narration (e.g., 27 minutes)
- Supports: MP3, WAV

### Step 3: Select Mode
- **AI Images Auto**: For educational content
- **Videos Stock Auto**: For dynamic content

Optional: Add script for better AI context

### Step 4: Generate
- Click "Generate Avatar Video"
- Wait 5-15 minutes (depending on audio length)
- Download final video

---

## 🎨 HOW IT WORKS

### AI Images Mode:

```
Timeline:
[1 min avatar] → [5s AI image] → [1 min avatar] → [5s AI image] → ...
... → [Last 2 min: full avatar]
```

**Example** (27-minute audio):
- 0:00 - 1:00: Avatar loop
- 1:00 - 1:05: AI image #1
- 1:05 - 2:05: Avatar loop
- 2:05 - 2:10: AI image #2
- ...
- 25:00 - 27:00: Full avatar (last 2 minutes)

### Stock Videos Mode:

```
Timeline:
[30s avatar] → [5-10s stock] → [30s avatar] → [5-10s stock] → ...
... → [Last 2 min: full avatar]
```

**Example** (27-minute audio):
- 0:00 - 0:30: Avatar loop
- 0:30 - 0:40: Stock video #1 (10 sec)
- 0:40 - 1:10: Avatar loop
- 1:10 - 1:15: Stock video #2 (5 sec)
- ...
- 25:00 - 27:00: Full avatar (last 2 minutes)

---

## 🔧 TECHNICAL DETAILS

### Media Planning (Gemini AI):
1. Analyzes audio duration with Whisper
2. Plans optimal media sequence
3. Decides 5 sec vs 10 sec for stock videos
4. Ensures exact duration match

### Stock Video Selection:
- Searches Pexels & Pixabay simultaneously
- Filters by minimum duration
- Prioritizes HD quality
- Auto-trims if too long

### Avatar Looping:
- Calculates number of loops needed
- Uses FFmpeg stream_loop
- Exact duration targeting

### Video Assembly:
- Ultra-fast FFmpeg preset
- Stream copy where possible
- 1920x1080 @ 30fps
- H.264 encoding

---

## 📊 PROCESSING TIME

**Example** (27-minute audio, AI Images mode):

| Task | Time |
|------|------|
| Audio analysis (Whisper) | 2-3 min |
| Media planning (Gemini) | 30 sec |
| Generate AI images (15 images) | 5-8 min |
| Video assembly (FFmpeg) | 2-3 min |
| **TOTAL** | **10-15 min** |

**Example** (27-minute audio, Stock Videos mode):

| Task | Time |
|------|------|
| Audio analysis (Whisper) | 2-3 min |
| Media planning (Gemini) | 30 sec |
| Download stock videos (20 videos) | 3-5 min |
| Video assembly (FFmpeg) | 2-3 min |
| **TOTAL** | **8-12 min** |

---

## 🎯 BEST PRACTICES

### Avatar Video:
- **Duration**: 15-60 seconds recommended
- **Quality**: 1080p or higher
- **Format**: MP4 (H.264)
- **Style**: Clean background, centered subject

### Audio Narration:
- **Quality**: Clear voice, minimal background noise
- **Format**: MP3 or WAV
- **Bitrate**: 192kbps or higher

### Script (Optional):
- Include script for better AI context
- Helps stock video search
- Improves AI image relevance

---

## 🐛 TROUBLESHOOTING

### "Whisper failed"
- Install Whisper: `pip install openai-whisper`
- Check audio file is valid
- Fallback uses FFprobe

### "No stock videos found"
- Check API keys are valid
- Try different search terms
- Use AI Images mode instead

### "Video out of sync"
- Last 2 minutes always match audio
- Middle sections may vary slightly
- Use Whisper STT for precision

### "Processing too slow"
- Reduce audio length
- Use AI Images (faster than stock)
- Upgrade server specs

---

## 🔐 API KEYS

### Get Your Keys:

1. **Gemini** (FREE)
   - https://makersuite.google.com/app/apikey

2. **Replicate** (Pay per use)
   - https://replicate.com/account/api-tokens

3. **Pexels** (FREE)
   - https://www.pexels.com/api/new/

4. **Pixabay** (FREE)
   - https://pixabay.com/api/docs/

---

## 📁 FILE STRUCTURE

```
backend/
├── avatar_video_generator.py      # Main generator
├── stock_video_downloader.py      # Stock video API
├── avatar_video_assembler.py      # FFmpeg assembly
├── whisper_stt.py                 # Audio analysis
├── .env.example                   # API keys template
└── README_AVATAR_AI.md            # This file

frontend/
└── avatar-ai.html                 # User interface
```

---

## 🚧 FUTURE ENHANCEMENTS

- [ ] More stock APIs (Unsplash Video, Videvo)
- [ ] Custom timing patterns
- [ ] Transitions between clips
- [ ] Background music support
- [ ] Batch processing
- [ ] Progress tracking improvements

---

## 📞 SUPPORT

For issues:
1. Check API keys are valid
2. Verify FFmpeg is installed
3. Review console logs
4. See main README.md

---

**Built with ❤️ for content creators**

**Version**: 1.0.0
**Last Updated**: 2026-02-10
