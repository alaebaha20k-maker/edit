# ✂️ CAPCUT-STYLE TIMELINE EDITOR - IMPLEMENTATION PLAN

## 🎯 GOAL: Exact CapCut Experience

### **What Makes It CapCut-Style:**
1. **Frontend-only editing** - No FFmpeg until Export
2. **Split** - Creates 2 clips instantly (metadata only)
3. **Trim** - Drag clip edges to resize
4. **Delete** - Remove clips instantly
5. **Drag to reorder** - Instant reposition
6. **Playhead** - Red vertical line
7. **Time markers** - 00:00, 30:00, 01:00:00, etc.
8. **Visual thumbnails** - Show video frame
9. **Export** - Backend FFmpeg creates final video

---

## 📋 DATA STRUCTURE (Metadata Only)

```javascript
const timelineClips = [
  {
    id: 'clip_123',
    filename: 'video.mp4',
    fileId: 'server_abc',  // uploaded file ID
    filepath: '/uploads/abc.mp4',
    type: 'video',  // or 'image'
    originalDuration: 120,  // 2 minutes total
    trimStart: 10,    // starts at 10s (user trimmed)
    trimEnd: 90,      // ends at 90s (user trimmed)
    position: 0,      // position on timeline (in seconds)
    thumbnail: 'data:image/jpeg;base64,...',  // extracted frame
    selected: false
  },
  {
    id: 'clip_456',
    filename: 'image.jpg',
    fileId: 'server_def',
    filepath: '/uploads/def.jpg',
    type: 'image',
    duration: 5,  // user can change this
    position: 80,  // starts after first clip (90-10=80s duration)
    thumbnail: 'data:image/jpeg...',
    selected: false
  }
];

// Playhead position (in seconds)
let playheadPosition = 0;

// Zoom level (pixels per second)
let pixelsPerSecond = 10;

// Undo/redo history
let historyStack = [];
let historyIndex = -1;
```

---

## ⚡ SPLIT FUNCTION (Instant - Frontend Only)

```javascript
function splitClipAtPlayhead() {
  // Find clip at playhead position
  const clip = timelineClips.find(c => {
    const clipStart = c.position;
    const clipEnd = c.position + (c.trimEnd - c.trimStart);
    return playheadPosition >= clipStart && playheadPosition <= clipEnd;
  });
  
  if (!clip) {
    showNotification('⚠️ No clip at playhead position', 'warning');
    return;
  }
  
  // Save to undo history
  saveToHistory();
  
  // Calculate split point RELATIVE to clip's trim
  const splitPoint = playheadPosition - clip.position;  // e.g., 15s into clip
  const absoluteSplitPoint = clip.trimStart + splitPoint;  // e.g., 25s in original file
  
  // Create LEFT clip (from start to split)
  const leftClip = {
    ...clip,
    id: generateId(),
    trimEnd: absoluteSplitPoint,  // cut here
    // position stays same
  };
  
  // Create RIGHT clip (from split to end)
  const rightClip = {
    ...clip,
    id: generateId(),
    trimStart: absoluteSplitPoint,  // start here
    position: playheadPosition,  // starts where playhead is
  };
  
  // Replace original clip with 2 new clips
  const index = timelineClips.findIndex(c => c.id === clip.id);
  timelineClips.splice(index, 1, leftClip, rightClip);
  
  // Re-render timeline (visual update only)
  renderTimeline();
  
  showNotification('✅ Clip split!', 'success');
}

// Generate unique ID
function generateId() {
  return 'clip_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
}
```

**Result:** User sees 2 separate clips instantly. No FFmpeg, no processing!

---

## ✂️ TRIM BY DRAGGING EDGES (Instant - Frontend Only)

```javascript
// HTML: Each clip has left/right resize handles
<div class="timeline-clip" data-clip-id="clip_123">
  <div class="trim-handle left" onmousedown="startTrimLeft('clip_123', event)"></div>
  <div class="clip-content">
    <img src="thumbnail.jpg">
    <span>video.mp4 (1:20)</span>
  </div>
  <div class="trim-handle right" onmousedown="startTrimRight('clip_123', event)"></div>
</div>

// JavaScript: Drag left handle
function startTrimLeft(clipId, e) {
  e.preventDefault();
  e.stopPropagation();
  
  const clip = timelineClips.find(c => c.id === clipId);
  const clipEl = document.querySelector(`[data-clip-id="${clipId}"]`);
  const startX = e.clientX;
  const originalTrimStart = clip.trimStart;
  const originalPosition = clip.position;
  
  saveToHistory();  // for undo
  
  document.onmousemove = (moveE) => {
    const deltaX = moveE.clientX - startX;
    const deltaTime = deltaX / pixelsPerSecond;
    
    // Update trim start (can't go below 0 or past trimEnd)
    const newTrimStart = Math.max(0, Math.min(
      originalTrimStart + deltaTime,
      clip.trimEnd - 0.1  // leave at least 0.1s
    ));
    
    // Update position (move clip start point)
    const timeDelta = newTrimStart - clip.trimStart;
    clip.trimStart = newTrimStart;
    clip.position = originalPosition + timeDelta;
    
    // Update visual immediately
    updateClipVisual(clip);
  };
  
  document.onmouseup = () => {
    document.onmousemove = null;
    document.onmouseup = null;
    renderTimeline();  // final render
  };
}

// Drag right handle
function startTrimRight(clipId, e) {
  e.preventDefault();
  e.stopPropagation();
  
  const clip = timelineClips.find(c => c.id === clipId);
  const startX = e.clientX;
  const originalTrimEnd = clip.trimEnd;
  
  saveToHistory();
  
  document.onmousemove = (moveE) => {
    const deltaX = moveE.clientX - startX;
    const deltaTime = deltaX / pixelsPerSecond;
    
    // Update trim end (can't go past original duration or before trimStart)
    const newTrimEnd = Math.min(clip.originalDuration, Math.max(
      clip.trimStart + 0.1,
      originalTrimEnd + deltaTime
    ));
    
    clip.trimEnd = newTrimEnd;
    
    // Update visual immediately
    updateClipVisual(clip);
  };
  
  document.onmouseup = () => {
    document.onmousemove = null;
    document.onmouseup = null;
    renderTimeline();
  };
}

// Update clip visual (CSS only - super fast)
function updateClipVisual(clip) {
  const clipEl = document.querySelector(`[data-clip-id="${clip.id}"]`);
  if (!clipEl) return;
  
  const duration = clip.trimEnd - clip.trimStart;
  const width = duration * pixelsPerSecond;
  const left = clip.position * pixelsPerSecond;
  
  clipEl.style.width = width + 'px';
  clipEl.style.left = left + 'px';
  
  // Update duration display
  const durationEl = clipEl.querySelector('.clip-duration');
  if (durationEl) {
    durationEl.textContent = formatTime(duration);
  }
}
```

**Result:** User drags edge, clip resizes instantly. Smooth as butter!

---

## 🗑️ DELETE CLIPS (Instant - Frontend Only)

```javascript
function deleteSelectedClips() {
  const selectedClips = timelineClips.filter(c => c.selected);
  
  if (selectedClips.length === 0) {
    showNotification('⚠️ No clips selected', 'warning');
    return;
  }
  
  saveToHistory();
  
  // Remove selected clips
  selectedClips.forEach(clip => {
    const index = timelineClips.findIndex(c => c.id === clip.id);
    timelineClips.splice(index, 1);
  });
  
  // Reposition remaining clips (optional - close gaps)
  repositionClips();
  
  renderTimeline();
  
  showNotification(`✅ Deleted ${selectedClips.length} clip(s)`, 'success');
}

// Optional: Auto-close gaps after delete
function repositionClips() {
  let currentPosition = 0;
  
  timelineClips.forEach(clip => {
    clip.position = currentPosition;
    const duration = clip.type === 'image' 
      ? clip.duration 
      : (clip.trimEnd - clip.trimStart);
    currentPosition += duration;
  });
}
```

---

## 🔄 DRAG TO REORDER (Instant - Frontend Only)

```javascript
function startDragClip(clipId, e) {
  const clip = timelineClips.find(c => c.id === clipId);
  const clipEl = document.querySelector(`[data-clip-id="${clipId}"]`);
  const startX = e.clientX;
  const originalPosition = clip.position;
  
  saveToHistory();
  
  clipEl.classList.add('dragging');
  
  document.onmousemove = (moveE) => {
    const deltaX = moveE.clientX - startX;
    const deltaTime = deltaX / pixelsPerSecond;
    
    // Update position (can't go below 0)
    clip.position = Math.max(0, originalPosition + deltaTime);
    
    // Check if overlapping other clips
    const overlapping = findOverlappingClip(clip);
    if (overlapping) {
      // Swap positions
      const temp = clip.position;
      clip.position = overlapping.position;
      overlapping.position = temp;
    }
    
    // Update visual
    updateClipVisual(clip);
  };
  
  document.onmouseup = () => {
    clipEl.classList.remove('dragging');
    document.onmousemove = null;
    document.onmouseup = null;
    
    // Snap to grid (optional)
    snapClipsToGrid();
    
    renderTimeline();
  };
}

function findOverlappingClip(draggedClip) {
  return timelineClips.find(c => {
    if (c.id === draggedClip.id) return false;
    
    const dragStart = draggedClip.position;
    const clipStart = c.position;
    
    return Math.abs(dragStart - clipStart) < 1;  // within 1 second
  });
}
```

---

## ↶ UNDO/REDO (Instant - Frontend Only)

```javascript
function saveToHistory() {
  // Remove any redo history
  historyStack = historyStack.slice(0, historyIndex + 1);
  
  // Save current state
  historyStack.push(JSON.parse(JSON.stringify(timelineClips)));
  historyIndex++;
  
  // Limit history to 50 states
  if (historyStack.length > 50) {
    historyStack.shift();
    historyIndex--;
  }
}

function timelineUndo() {
  if (historyIndex <= 0) {
    showNotification('⚠️ Nothing to undo', 'warning');
    return;
  }
  
  historyIndex--;
  timelineClips = JSON.parse(JSON.stringify(historyStack[historyIndex]));
  renderTimeline();
  showNotification('↶ Undone', 'info');
}

function timelineRedo() {
  if (historyIndex >= historyStack.length - 1) {
    showNotification('⚠️ Nothing to redo', 'warning');
    return;
  }
  
  historyIndex++;
  timelineClips = JSON.parse(JSON.stringify(historyStack[historyIndex]));
  renderTimeline();
  showNotification('↷ Redone', 'info');
}

// Keyboard shortcuts
document.addEventListener('keydown', (e) => {
  if (e.ctrlKey || e.metaKey) {
    if (e.key === 'z') {
      e.preventDefault();
      if (e.shiftKey) {
        timelineRedo();
      } else {
        timelineUndo();
      }
    } else if (e.key === 'y') {
      e.preventDefault();
      timelineRedo();
    } else if (e.key === 'b') {
      e.preventDefault();
      splitClipAtPlayhead();
    }
  } else if (e.key === 'Delete' || e.key === 'Backspace') {
    e.preventDefault();
    deleteSelectedClips();
  }
});
```

---

## 🎬 EXPORT (Backend FFmpeg - ONLY RUNS ONCE)

```javascript
async function exportTimeline() {
  if (timelineClips.length === 0) {
    showNotification('⚠️ Timeline is empty', 'warning');
    return;
  }
  
  showNotification('⏳ Preparing export...', 'info');
  
  // Prepare data for backend
  const exportData = {
    clips: timelineClips.map(clip => ({
      fileId: clip.fileId,
      filename: clip.filename,
      type: clip.type,
      trimStart: clip.trimStart,
      trimEnd: clip.trimEnd,
      duration: clip.duration,  // for images
      position: clip.position
    })),
    totalDuration: calculateTotalDuration(),
    quality: document.getElementById('exportQuality').value
  };
  
  try {
    const response = await fetch('/api/timeline/export-final', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(exportData)
    });
    
    const data = await response.json();
    
    if (data.success) {
      showNotification('✅ Video exported!', 'success');
      
      // Download file
      window.open(data.download_url, '_blank');
    } else {
      throw new Error(data.error);
    }
  } catch (error) {
    showNotification('❌ Export failed: ' + error.message, 'error');
  }
}
```

### **Backend Export Endpoint:**

```javascript
app.post('/api/timeline/export-final', async (req, res) => {
  const { clips, quality } = req.body;
  
  try {
    // Step 1: Process each clip
    const processedFiles = [];
    
    for (let i = 0; i < clips.length; i++) {
      const clip = clips[i];
      const tempFile = `temp_${i}.mp4`;
      
      if (clip.type === 'video') {
        // Trim video
        const duration = clip.trimEnd - clip.trimStart;
        await runFFmpeg([
          '-ss', clip.trimStart,
          '-i', clip.filepath,
          '-t', duration,
          '-c', 'copy',
          '-y', tempFile
        ]);
      } else if (clip.type === 'image') {
        // Convert image to video
        await runFFmpeg([
          '-loop', '1',
          '-i', clip.filepath,
          '-c:v', 'libx264',
          '-t', clip.duration,
          '-pix_fmt', 'yuv420p',
          '-vf', 'scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2',
          '-r', '30',
          '-y', tempFile
        ]);
      }
      
      processedFiles.push(tempFile);
    }
    
    // Step 2: Concatenate all clips
    const concatFile = 'concat_list.txt';
    const fileList = processedFiles.map(f => `file '${path.resolve(f)}'`).join('\n');
    fs.writeFileSync(concatFile, fileList);
    
    const outputFile = `output/timeline_${Date.now()}.mp4`;
    
    await runFFmpeg([
      '-f', 'concat',
      '-safe', '0',
      '-i', concatFile,
      '-c', 'copy',
      '-y', outputFile
    ]);
    
    // Clean up temp files
    processedFiles.forEach(f => fs.unlinkSync(f));
    fs.unlinkSync(concatFile);
    
    res.json({
      success: true,
      download_url: `/api/download/${path.basename(outputFile)}`,
      filename: path.basename(outputFile)
    });
    
  } catch (error) {
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});
```

---

## ✅ WHY THIS IS PERFECT

### **Frontend = Instant:**
- Split: 0ms (just create 2 objects)
- Trim: 0ms (just update numbers)
- Delete: 0ms (remove from array)
- Drag: 0ms (update position)
- Undo/Redo: 0ms (load from history)

### **Backend = Professional:**
- FFmpeg runs ONCE on export
- High-quality output
- Handles all formats
- Proper video encoding

### **User Experience:**
- Smooth like CapCut ✓
- Instant editing ✓
- Professional export ✓
- No lag ✓
- No CORS errors ✓

---

## 🚀 THIS IS THE RIGHT WAY!

**Before:**
- Every action called FFmpeg
- Slow, laggy, errors
- Bad UX

**Now:**
- Edit = instant metadata changes
- Export = one FFmpeg run
- Perfect UX

**Ready to implement!** 🎬
