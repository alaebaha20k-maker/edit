# 🚀 Complete System Setup & Deployment Guide

## ✅ **SYSTEM STATUS: PRODUCTION READY**

All features implemented, tested, and pushed to GitHub.

**Branch:** `claude/check-file-version-fpb6O`
**Latest Commit:** `db1f0f4` - Media upload and preview routes
**Total Commits:** 10

---

## 📦 **HOW TO RUN THE COMPLETE SYSTEM**

### **Step 1: Pull Latest Code from GitHub**

```bash
# Navigate to your project directory
cd /home/user/edit

# Pull latest changes from GitHub
git fetch origin
git checkout claude/check-file-version-fpb6O
git pull origin claude/check-file-version-fpb6O
```

**Verify you have the latest:**
```bash
git log --oneline -5
```

**Expected output:**
```
db1f0f4 feat: add media upload and preview routes for multi-file handling
e78db37 docs: add complete system summary and final documentation
058e150 feat: add MR BAHA video editor with CapCut-style interface
71cac90 docs: add AI generator documentation and JavaScript template
5c807b9 feat: add final video processor with mixed media support
```

---

### **Step 2: Install Python Dependencies**

```bash
cd video-editor-system/backend

# Create virtual environment (if not exists)
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate  # Linux/Mac
# OR
venv\Scripts\activate  # Windows

# Install all required packages
pip install -r requirements.txt
```

**If requirements.txt doesn't exist, install manually:**
```bash
pip install flask flask-cors
pip install google-generativeai replicate requests
pip install pathlib werkzeug
```

---

### **Step 3: Install System Dependencies**

**FFmpeg (Required for video processing):**

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install ffmpeg

# macOS
brew install ffmpeg

# Windows
# Download from: https://ffmpeg.org/download.html
# Add to PATH

# Verify installation
ffmpeg -version
ffprobe -version
```

---

### **Step 4: Create Required Directories**

```bash
cd video-editor-system

# Create all output directories
mkdir -p uploads
mkdir -p temp
mkdir -p output
mkdir -p output/images
mkdir -p output/stock
mkdir -p output/voices
mkdir -p output/edited
mkdir -p output/prompts
mkdir -p data
mkdir -p data/formulas
```

**Verify directory structure:**
```bash
tree -L 2 -d
```

**Expected structure:**
```
.
├── backend/
│   ├── venv/
│   └── *.py files
├── frontend/
│   └── *.html, *.js files
├── uploads/
├── temp/
├── output/
│   ├── images/
│   ├── stock/
│   ├── voices/
│   ├── edited/
│   └── prompts/
└── data/
    └── formulas/
```

---

### **Step 5: Start the Flask Server**

```bash
cd backend

# Activate virtual environment (if not already active)
source venv/bin/activate

# Start server
python3 api.py
```

**Expected startup output:**
```
============================================================
🎬 VIDEO EDITOR API SERVER
============================================================

📦 Initializing database...

📁 Ensuring directories exist...
📂 Upload folder: /path/to/uploads
📂 Output folder: /path/to/output
📂 Temp folder: /path/to/temp
📂 Data folder: /path/to/data
============================================================
🚀 Starting server on http://localhost:5000
============================================================

📋 Available pages:
   • Main editor:     http://localhost:5000/
   • Settings:        http://localhost:5000/settings.html ⚙️
   • AI generator:    http://localhost:5000/generator.html
   • Output files:    http://localhost:5000/output
============================================================

⚠️  API keys not configured
   → Configure at: http://localhost:5000/settings.html
   • Gemini API key needed for script generation
   • Replicate API token needed for image generation
   • Inworld AI key needed for voice generation (optional)
   • Pexels API key needed for stock footage (optional)
============================================================

 * Serving Flask app 'api'
 * Debug mode: on
 * Running on http://0.0.0.0:5000
```

---

### **Step 6: Configure API Keys**

1. **Open browser:** `http://localhost:5000/settings.html`

2. **Go to Tab 1 - API Keys**

3. **Enter your API keys:**

   **Gemini API Key (Required):**
   - Get from: https://aistudio.google.com/app/apikey
   - Example: `AIza...`
   - Used for: Script generation, title generation, image prompts

   **Replicate API Token (Required):**
   - Get from: https://replicate.com/account/api-tokens
   - Example: `r8_...`
   - Used for: AI image generation (Flux model)

   **Inworld AI API Key (Optional):**
   - Get from: https://studio.inworld.ai/
   - Example: Base64 encoded credential
   - Used for: Text-to-speech voice generation

   **Pexels API Key (Optional):**
   - Get from: https://www.pexels.com/api/
   - Free tier available
   - Used for: Stock footage and photos

4. **Click "Save API Keys"**

5. **Verify:** Status indicators should show "✓ Configured"

---

### **Step 7: Access the System**

**Main Pages:**

📺 **Video Editor:**
```
http://localhost:5000/
```
- Original video editor
- Upload, cut, merge videos
- Add audio tracks

⚙️ **Settings:**
```
http://localhost:5000/settings.html
```
- Configure API keys
- Customize generation formulas
- Select voice settings

🤖 **AI Generator:**
```
http://localhost:5000/generator.html
```
- Generate AI videos
- Script generation (Gemini)
- Image generation (Replicate)
- Stock footage (Pexels)
- Voice generation (Inworld AI)
- Final video processing

📁 **Output Files:**
```
http://localhost:5000/output
```
- Browse generated videos
- Download files
- View file stats

---

## 🔧 **VS CODE LOCALE UPDATE**

After pulling from GitHub, update your VS Code workspace:

```bash
# Navigate to project root
cd /home/user/edit/video-editor-system

# Open in VS Code
code .
```

**VS Code Settings (.vscode/settings.json):**

```json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/backend/venv/bin/python",
  "python.analysis.extraPaths": [
    "${workspaceFolder}/backend"
  ],
  "files.exclude": {
    "**/__pycache__": true,
    "**/*.pyc": true,
    "**/venv": false,
    "**/data": true
  },
  "python.linting.enabled": true,
  "python.linting.pylintEnabled": true,
  "editor.formatOnSave": true,
  "python.formatting.provider": "autopep8"
}
```

**Reload VS Code:**
```
Ctrl+Shift+P (Cmd+Shift+P on Mac)
→ "Developer: Reload Window"
```

---

## 🌐 **NETWORK ACCESS**

**Local Only (Default):**
```
http://localhost:5000
http://127.0.0.1:5000
```

**LAN Access:**
If you want to access from other devices on your network:

1. Find your local IP:
```bash
# Linux/Mac
ifconfig | grep "inet "
# OR
ip addr show

# Windows
ipconfig
```

2. Access from other devices:
```
http://YOUR_LOCAL_IP:5000
```

Example: `http://192.168.1.100:5000`

---

## 🔒 **SECURITY NOTES**

**API Keys:**
- Stored in `data/settings.json`
- **Already in .gitignore** - will NOT be committed to Git
- Keep this file secure
- Never share API keys

**Backup your settings:**
```bash
# Backup settings and formulas
cp data/settings.json data/settings.backup.json
cp -r data/formulas data/formulas.backup
```

---

## 📊 **MONITORING & LOGS**

**Terminal Logs:**
The Flask server outputs detailed logs:

```bash
# Watch for these patterns:

✅ Success:
   ✅ Settings loaded
   ✅ API keys configured
   ✅ Script generation complete
   ✅ Image generated successfully
   ✅ Video complete!

📝 Progress:
   🚀 Starting...
   🎨 Processing image 3/6...
   🎬 Rendering video...
   🔗 Merging audio...

⚠️ Warnings:
   ⚠️  API keys not configured
   ⚠️  Rate limit detected, waiting 11s...

❌ Errors:
   ❌ Error: API key invalid
   ❌ Error: File not found
```

**Log File (Optional):**
```bash
# Run with logging to file
python3 api.py > logs/app.log 2>&1 &

# View logs
tail -f logs/app.log
```

---

## 🐛 **TROUBLESHOOTING**

### **Server won't start:**
```bash
# Check port 5000 is available
lsof -i :5000
# OR
netstat -an | grep 5000

# Kill existing process
kill -9 <PID>

# Try different port
export FLASK_RUN_PORT=5001
python3 api.py
```

### **Import errors:**
```bash
# Reinstall dependencies
pip install --force-reinstall flask flask-cors
pip install --force-reinstall google-generativeai replicate

# Check Python version (3.8+)
python3 --version
```

### **FFmpeg not found:**
```bash
# Verify FFmpeg installed
which ffmpeg
which ffprobe

# Add to PATH if needed
export PATH=$PATH:/usr/local/bin
```

### **API errors:**
```bash
# Test API keys
curl http://localhost:5000/api/config/test

# Check settings
cat data/settings.json
```

### **Permissions errors:**
```bash
# Fix directory permissions
chmod -R 755 uploads output temp data

# Fix file permissions
chmod 644 data/settings.json
```

---

## 📈 **PERFORMANCE OPTIMIZATION**

**Faster Processing:**

1. **Use SSD for temp directory:**
```python
# In config.py
TEMP_FOLDER = '/path/to/ssd/temp'
```

2. **Increase FFmpeg threads:**
```bash
# Add to video_processor.py
'-threads', '4'  # Use 4 CPU cores
```

3. **Reduce image size for testing:**
```python
# In image_prompts_generator.py
# Change 1080p to 720p for faster testing
```

---

## 🔄 **UPDATING THE SYSTEM**

**Pull latest changes:**
```bash
git fetch origin
git pull origin claude/check-file-version-fpb6O

# Check for new dependencies
pip install -r requirements.txt --upgrade

# Restart server
# Ctrl+C to stop
python3 api.py
```

---

## 🎯 **QUICK START CHECKLIST**

- [ ] Clone/pull from GitHub
- [ ] Install Python dependencies (`pip install -r requirements.txt`)
- [ ] Install FFmpeg
- [ ] Create directories (`mkdir -p uploads output temp data`)
- [ ] Start server (`python3 api.py`)
- [ ] Open browser (`http://localhost:5000`)
- [ ] Configure API keys (`http://localhost:5000/settings.html`)
- [ ] Test script generation
- [ ] Test image generation
- [ ] Test final video processing
- [ ] ✅ **System Ready!**

---

## 🎉 **CONGRATULATIONS!**

Your **Complete AI Video Generation System** is now running!

**What you can do:**
- Generate AI scripts with Gemini
- Generate 3-30 AI images per video
- Fetch stock footage from Pexels
- Generate AI voices with Inworld
- Mix media (AI + stock + manual)
- Edit videos with timeline editor
- Export professional videos

**Support & Documentation:**
- `TESTING_CHECKLIST.md` - Complete testing guide
- `COMPLETE_SYSTEM_SUMMARY.md` - Full system overview
- `AI_GENERATOR_README.md` - API documentation
- `EDITOR_IMPLEMENTATION.md` - Editor guide

**Have fun creating videos!** 🎬🚀
