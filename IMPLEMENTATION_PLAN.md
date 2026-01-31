# Implementation Plan for Video Editor Enhancements

## ✅ FEATURES I CAN IMPLEMENT NOW (Frontend Only)

### 1. Formula System with Named Dropdowns ✅
- Save multiple formulas with names
- Dropdown selection in Generator
- No manual topic input needed
- **STATUS**: Implementing now

### 2. Script Download Button ✅
- Download generated script as .txt file
- **STATUS**: Implementing now

### 3. Multiple Stock Sources ✅
- **Pexels** (videos + images) - Already working
- **Pixabay** (images + videos) - Can add
- **Unsplash** (images only) - Can add
- **Coverr** (videos only - NO API, scraping needed)
- **Videvo** (videos only - NO PUBLIC API)
- **STATUS**: Can add Pixabay & Unsplash only

### 4. Media Upload Visualization ✅
- Show uploaded files as thumbnails
- **STATUS**: Implementing now

### 5. Media Library with Ranking ✅
- Show all media (uploaded, stock, AI)
- Drag to reorder/rank
- Mute option for videos
- **STATUS**: Implementing now

### 6. Improved MR BAHA Editor ✅
- Visual selection (not manual time entry)
- Click to select region → Cut button
- **STATUS**: Can improve UX

---

## ❌ FEATURES THAT **REQUIRE BACKEND** (Cannot do in frontend)

### 1. AI Image Generation (Replicate) ❌
**Why backend needed:**
- Replicate API token must stay SECRET (security)
- Cannot expose in frontend JavaScript (anyone can steal it)
- Backend proxy required

**Current status**: Warning shown correctly

### 2. Voice Generation (Inworld AI) ❌
**Why backend needed:**
- Same security issue - API key exposure
- Inworld requires server-side SDK
- Real-time audio streaming needs backend

**Current status**: Warning shown correctly

### 3. Final Video Processing (FFmpeg) ❌
**Why backend needed:**
- FFmpeg is a command-line tool, runs on server only
- Cannot run in browser
- Video encoding/merging requires server processing
- Memory intensive (browsers crash)

**Solution needed**: Backend API endpoint for video processing

### 4. Automatic Media Duration Calculation ❌
**Depends on**: FFmpeg backend
**Why**: Need to render final video with calculated timings

---

## 🔧 WHAT I'M IMPLEMENTING RIGHT NOW

1. **Formula Management System**
   - Add named formulas in Settings
   - Select by name in Generator
   - No topic input needed

2. **Download Script Button**
   - Simple .txt file download

3. **Pixabay & Unsplash Integration**
   - Add API support
   - Combined stock search

4. **Media Library UI**
   - Visual library of all media
   - Drag to reorder
   - Mute checkboxes for videos

5. **Better Upload Feedback**
   - Thumbnails for uploaded files
   - Visual confirmation

---

## 📋 AFTER THIS UPDATE

### YOU CAN DO:
✅ Create named formulas
✅ Generate titles without typing topics
✅ Generate scripts using formulas
✅ Download scripts as .txt
✅ Upload and see your media
✅ Search Pexels, Pixabay, Unsplash
✅ Rank/order media
✅ Mute videos

### YOU CANNOT DO (needs backend):
❌ Generate AI images (Replicate)
❌ Generate voice (Inworld)
❌ Export final video (FFmpeg)
❌ Auto-calculate media durations

### SOLUTION:
You need to implement backend API endpoints for:
1. `/api/generate-images` (Replicate proxy)
2. `/api/generate-voice` (Inworld proxy)
3. `/api/process-video` (FFmpeg processing)

I can help you with backend code AFTER we finish frontend features.

---

## 🚀 IMPLEMENTATION ORDER

1. ✅ Formula system (NOW)
2. ✅ Script download (NOW)
3. ✅ Stock sources (NOW)
4. ✅ Media library (NOW)
5. ✅ Upload visualization (NOW)
6. ❌ Backend APIs (LATER - your choice)
