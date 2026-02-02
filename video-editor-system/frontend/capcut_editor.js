// =============================================================================
// CAPCUT-STYLE TIMELINE EDITOR - INSTANT EDITING
// Complete implementation with split, trim, drag, undo/redo
// =============================================================================

// Timeline clips data (metadata only - NO FFmpeg until export!)
let capcutClips = [];
let capcutPlayhead = 0;
let capcutPixelsPerSecond = 10;
let capcutHistory = [];
let capcutHistoryIndex = -1;
let capcutZoomLevel = 1; // 1x, 2x, 5x, 10x, etc.
let capcutScrollPosition = 0;
let capcutIsDraggingPlayhead = false;

// Generate unique ID
function capcutGenerateId() {
    return 'clip_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
}

// File upload handlers
function capcutSelectFiles(event) {
    const files = Array.from(event.target.files);
    capcutUploadFiles(files, false); // false = append to end
}

function capcutInsertFilesAtPlayhead() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'video/*,image/*';
    input.multiple = true;
    input.onchange = (e) => {
        const files = Array.from(e.target.files);
        capcutUploadFiles(files, true); // true = insert at playhead
    };
    input.click();
}

function capcutDragOver(event) {
    event.preventDefault();
    event.stopPropagation();
    event.dataTransfer.dropEffect = 'copy';
}

function capcutDropFiles(event) {
    event.preventDefault();
    event.stopPropagation();
    const files = Array.from(event.dataTransfer.files);
    capcutUploadFiles(files, false); // false = append to end
}

async function capcutUploadFiles(files, insertAtPlayhead = false) {
    if (!files || files.length === 0) {
        console.log('⚠️ No files provided to upload');
        return;
    }
    console.log('📤 Upload started with ' + files.length + ' files');
    console.log('📤 Files:', files);
    showNotification('⏳ Uploading ' + files.length + ' file(s)...', 'info');

    const newClips = [];

    for (const file of files) {
        console.log('📂 Processing file: ' + file.name + ' (' + file.type + ')');
        const isVideo = file.type.startsWith('video/');
        const isImage = file.type.startsWith('image/');
        if (!isVideo && !isImage) continue;

        try {
            const formData = new FormData();
            formData.append('file', file);
            formData.append('type', isVideo ? 'video' : 'image');

            const response = await fetch('/api/upload', {
                method: 'POST',
                body: formData
            });

            const data = await response.json();
            console.log('📥 API response for ' + file.name + ':', data);
            if (!data.success) {
                console.warn('⚠️ Upload failed for ' + file.name);
                continue;
            }

            const url = URL.createObjectURL(file);
            let duration = isImage ? 10.0 : 0; // Default 10 seconds for images (can be extended)

            if (isVideo) {
                const video = document.createElement('video');
                video.src = url;
                await new Promise((resolve) => {
                    video.onloadedmetadata = () => {
                        duration = video.duration;
                        resolve();
                    };
                });
            }

            const thumbnail = await capcutExtractThumbnail(url, isVideo);

            const clip = {
                id: capcutGenerateId(),
                filename: file.name,
                fileId: data.file_id,
                filepath: '/uploads/' + data.file_id,
                type: isVideo ? 'video' : 'image',
                originalDuration: duration,
                trimStart: 0,
                trimEnd: duration,
                position: 0, // Will be set later
                thumbnail: thumbnail,
                url: url,
                selected: false,
                muted: false // Add muted property
            };

            newClips.push(clip);
            console.log('✅ Clip created successfully:', clip);
        } catch (error) {
            console.error('❌ Upload error for ' + file.name + ':', error);
            showNotification('❌ Upload failed: ' + error.message, 'error');
        }
    }

    console.log('📊 Total new clips created: ' + newClips.length);
    if (newClips.length === 0) {
        console.log('⚠️ No new clips created - check errors above');
        showNotification('⚠️ No valid files uploaded', 'warning');
        return;
    }

    console.log('✅ Created ' + newClips.length + ' new clips:', newClips);

    capcutSaveHistory();

    if (insertAtPlayhead) {
        // Insert at playhead position
        // Find the clip at playhead and insert after it
        let insertIndex = 0;
        for (let i = 0; i < capcutClips.length; i++) {
            const clip = capcutClips[i];
            const clipEnd = clip.position + (clip.trimEnd - clip.trimStart);
            if (capcutPlayhead >= clip.position && capcutPlayhead <= clipEnd) {
                insertIndex = i + 1;
                break;
            } else if (capcutPlayhead > clipEnd) {
                insertIndex = i + 1;
            }
        }

        // Insert new clips at position
        capcutClips.splice(insertIndex, 0, ...newClips);

        // Reposition all clips
        capcutSnapClips();

        showNotification('✅ Inserted ' + newClips.length + ' clip(s) at playhead', 'success');
    } else {
        // Append to end
        const lastClip = capcutClips[capcutClips.length - 1];
        const startPosition = lastClip ? (lastClip.position + (lastClip.trimEnd - lastClip.trimStart)) : 0;

        newClips.forEach((clip, i) => {
            let pos = startPosition;
            for (let j = 0; j < i; j++) {
                pos += (newClips[j].trimEnd - newClips[j].trimStart);
            }
            clip.position = pos;
        });

        capcutClips.push(...newClips);
        showNotification('✅ Added ' + newClips.length + ' file(s)', 'success');
    }

    console.log('📊 Total clips in timeline: ' + capcutClips.length);
    console.log('📊 All clips:', capcutClips);

    console.log('🎬 Calling capcutRenderTimeline()...');
    capcutRenderTimeline();

    // Auto zoom-to-fit after uploading to see full timeline
    setTimeout(() => {
        capcutZoomToFit();
        // Scroll to beginning to see playhead
        const container = document.getElementById('capcutTimelineContainer');
        if (container) {
            container.scrollLeft = 0;
        }
    }, 100);
}

async function capcutExtractThumbnail(url, isVideo) {
    return new Promise((resolve) => {
        if (isVideo) {
            const video = document.createElement('video');
            video.src = url;
            video.currentTime = 1;
            video.onseeked = () => {
                const canvas = document.createElement('canvas');
                canvas.width = 160;
                canvas.height = 90;
                const ctx = canvas.getContext('2d');
                ctx.drawImage(video, 0, 0, 160, 90);
                resolve(canvas.toDataURL('image/jpeg', 0.7));
            };
        } else {
            const img = new Image();
            img.onload = () => {
                const canvas = document.createElement('canvas');
                canvas.width = 160;
                canvas.height = 90;
                const ctx = canvas.getContext('2d');
                ctx.drawImage(img, 0, 0, 160, 90);
                resolve(canvas.toDataURL('image/jpeg', 0.7));
            };
            img.src = url;
        }
    });
}

// Render timeline (visual only - instant!)
function capcutRenderTimeline() {
    console.log('🎬 Rendering timeline with ' + capcutClips.length + ' clips');
    const track = document.getElementById('capcutTrack');
    const statusText = document.getElementById('capcutStatusText');
    const totalDuration = capcutCalculateTotalDuration();

    // Set track width to match timeline duration
    const displayDuration = Math.max(totalDuration + 30, 60);
    const trackWidth = Math.max(displayDuration * capcutPixelsPerSecond, 800);
    track.style.width = trackWidth + 'px';
    console.log('📏 Track width set to: ' + trackWidth + 'px, displayDuration: ' + displayDuration + 's, zoom: ' + capcutZoomLevel);

    if (capcutClips.length === 0) {
        track.innerHTML = '<div id="capcutEmptyMessage" style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); color: #666; font-size: 14px; pointer-events: none;">Timeline is empty - upload videos above</div>';
        statusText.textContent = 'Ready • 0 clips';
        capcutRenderTimeMarkers(); // Render markers even when empty
        return;
    }

    track.innerHTML = '';
    console.log('🗑️ Track cleared, innerHTML set to empty');

    capcutClips.forEach((clip, index) => {
        const duration = clip.trimEnd - clip.trimStart;
        const width = duration * capcutPixelsPerSecond;
        const left = clip.position * capcutPixelsPerSecond;

        console.log(`📦 Rendering clip ${index}: "${clip.filename}" - pos: ${clip.position}s, duration: ${duration}s, left: ${left}px, width: ${width}px`);

        const clipEl = document.createElement('div');
        clipEl.className = 'capcut-clip' + (clip.selected ? ' selected' : '');
        clipEl.dataset.clipId = clip.id;
        clipEl.style.cssText = 'position:absolute;left:' + left + 'px;width:' + width + 'px;height:80px;background:linear-gradient(135deg,#667eea,#764ba2);border-radius:8px;display:flex;align-items:center;cursor:move;overflow:hidden;' + (clip.selected ? 'border:3px solid #ff6b35;box-shadow:0 0 20px rgba(255,107,53,0.5);' : 'box-shadow:0 2px 10px rgba(0,0,0,0.3);');

        const leftHandle = document.createElement('div');
        leftHandle.style.cssText = 'position:absolute;left:0;top:0;width:8px;height:100%;background:rgba(255,255,255,0.3);cursor:ew-resize;z-index:10;';
        leftHandle.addEventListener('mousedown', (e) => capcutStartTrimLeft(clip.id, e));

        const rightHandle = document.createElement('div');
        rightHandle.style.cssText = 'position:absolute;right:0;top:0;width:8px;height:100%;background:rgba(255,255,255,0.3);cursor:ew-resize;z-index:10;';
        rightHandle.addEventListener('mousedown', (e) => capcutStartTrimRight(clip.id, e));

        const content = document.createElement('div');
        content.style.cssText = 'flex:1;display:flex;align-items:center;padding:0 10px;gap:10px;';

        const muteIcon = clip.type === 'video' ? (clip.muted ? '🔇' : '🔊') : '';
        const muteIndicator = clip.muted ? '<span style="background:#ff4444;padding:2px 6px;border-radius:3px;font-size:9px;font-weight:bold;">MUTED</span>' : '';

        content.innerHTML = '<img src="' + clip.thumbnail + '" style="width:50px;height:30px;border-radius:3px;object-fit:cover;"><div style="flex:1;overflow:hidden;"><div style="font-size:12px;font-weight:bold;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' + (clip.type === 'image' ? '🖼️' : '📹') + ' ' + clip.filename + ' ' + muteIndicator + '</div><div style="font-size:10px;color:rgba(255,255,255,0.7);">' + formatTime(duration) + '</div></div>';

        // Add mute button for videos
        if (clip.type === 'video') {
            const muteBtn = document.createElement('button');
            muteBtn.textContent = muteIcon;
            muteBtn.style.cssText = 'background:rgba(0,0,0,0.5);border:none;color:white;padding:5px 8px;border-radius:4px;cursor:pointer;font-size:16px;z-index:20;';
            muteBtn.title = clip.muted ? 'Unmute' : 'Mute';
            muteBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                capcutToggleMute(clip.id);
            });
            content.appendChild(muteBtn);
        }

        content.addEventListener('mousedown', (e) => {
            if (e.target.tagName !== 'BUTTON') {
                capcutStartDragClip(clip.id, e);
            }
        });
        clipEl.addEventListener('click', (e) => {
            if (e.target.closest('.capcut-clip') === clipEl && e.target.tagName !== 'BUTTON') {
                capcutSelectClip(clip.id, e.ctrlKey || e.metaKey);
            }
        });

        clipEl.appendChild(leftHandle);
        clipEl.appendChild(content);
        clipEl.appendChild(rightHandle);
        track.appendChild(clipEl);
        console.log('➕ Clip appended to DOM. Track now has ' + track.children.length + ' children');
    });

    console.log('✅ All ' + capcutClips.length + ' clips appended to track. Track children: ' + track.children.length);
    console.log('✅ Track element:', track);
    console.log('✅ Track innerHTML length:', track.innerHTML.length);

    const totalDuration = capcutCalculateTotalDuration();
    const selectedCount = capcutClips.filter(c => c.selected).length;
    statusText.textContent = 'Ready • ' + capcutClips.length + ' clip' + (capcutClips.length !== 1 ? 's' : '') + (selectedCount > 0 ? ' • ' + selectedCount + ' selected' : '') + ' • Total: ' + formatTime(totalDuration);

    capcutRenderTimeMarkers();

    console.log('🏁 Rendering complete!');
}

function capcutRenderTimeMarkers() {
    const markersEl = document.getElementById('capcutTimeMarkers');
    const totalDuration = capcutCalculateTotalDuration();
    markersEl.innerHTML = '';

    // Always show at least 60 seconds
    const displayDuration = Math.max(totalDuration + 30, 60);
    markersEl.style.width = Math.max(displayDuration * capcutPixelsPerSecond, 800) + 'px';

    // Time marker interval based on zoom
    let interval = 30; // Default 30 seconds
    if (capcutZoomLevel >= 10) {
        interval = 5; // Every 5 seconds at high zoom
    } else if (capcutZoomLevel >= 5) {
        interval = 10; // Every 10 seconds
    } else if (capcutZoomLevel <= 0.5) {
        interval = 60; // Every minute at low zoom
    }

    // Generate markers starting from 0:00
    for (let t = 0; t <= displayDuration; t += interval) {
        const marker = document.createElement('span');
        marker.style.cssText = 'position:absolute;left:' + (t * capcutPixelsPerSecond) + 'px;font-size:11px;color:#aaa;cursor:pointer;padding:2px 5px;';
        marker.textContent = formatTime(t);
        marker.title = 'Click to move playhead here';

        // Make time markers clickable!
        marker.addEventListener('click', (e) => {
            e.stopPropagation();
            capcutPlayhead = t;
            capcutUpdatePlayheadPosition();
            capcutSeekPreviewToPlayhead();
            showNotification(`Playhead: ${formatTime(t)}`, 'info');
        });

        markersEl.appendChild(marker);
    }
}

function capcutCalculateTotalDuration() {
    if (capcutClips.length === 0) return 0;
    const lastClip = capcutClips[capcutClips.length - 1];
    return lastClip.position + (lastClip.trimEnd - lastClip.trimStart);
}

function capcutSelectClip(clipId, multi = false) {
    const clip = capcutClips.find(c => c.id === clipId);
    if (!clip) return;
    if (multi) {
        clip.selected = !clip.selected;
    } else {
        capcutClips.forEach(c => c.selected = false);
        clip.selected = true;

        // Load video into preview when selected
        capcutLoadVideoPreview(clip);
    }
    capcutRenderTimeline();
}

// Load video into preview
function capcutLoadVideoPreview(clip) {
    const video = document.getElementById('editorVideoPreview');
    const placeholder = document.getElementById('editorPlaceholder');
    const timeDisplay = document.getElementById('editorTimeDisplay');
    const playBtn = document.getElementById('editorPlayBtn');

    if (!video) return;

    if (clip.type === 'video') {
        // Show video
        video.src = clip.url;
        video.style.display = 'block';
        placeholder.style.display = 'none';
        timeDisplay.style.display = 'block';
        if (playBtn) playBtn.style.display = 'block';

        // Seek to clip's trim start
        video.currentTime = clip.trimStart;

        // Update time display
        video.addEventListener('loadedmetadata', () => {
            capcutUpdateTimeDisplay();
        });

        video.addEventListener('timeupdate', () => {
            capcutUpdateTimeDisplay();
        });

        // Update play button icon when video plays/pauses
        video.addEventListener('play', () => {
            if (playBtn) playBtn.textContent = '⏸️';
        });

        video.addEventListener('pause', () => {
            if (playBtn) playBtn.textContent = '▶️';
        });

        video.addEventListener('ended', () => {
            if (playBtn) playBtn.textContent = '▶️';
        });
    } else {
        // Show image
        video.style.display = 'none';
        if (playBtn) playBtn.style.display = 'none';
        const canvas = document.getElementById('editorCanvasPreview');
        if (canvas) {
            canvas.style.display = 'block';
            placeholder.style.display = 'none';
            const ctx = canvas.getContext('2d');
            const img = new Image();
            img.onload = () => {
                canvas.width = img.width;
                canvas.height = img.height;
                ctx.drawImage(img, 0, 0);
            };
            img.src = clip.url;
        }
    }
}

// Update time display
function capcutUpdateTimeDisplay() {
    const video = document.getElementById('editorVideoPreview');
    const timeDisplay = document.getElementById('editorTimeDisplay');

    if (!video || !timeDisplay) return;

    const current = video.currentTime;
    const duration = video.duration || 0;

    const currentTime = formatTime(current);
    const totalTime = formatTime(duration);

    timeDisplay.textContent = currentTime + ' / ' + totalTime;
}

// Play/Pause toggle
function capcutTogglePlay() {
    const video = document.getElementById('editorVideoPreview');
    if (!video || !video.src) return;

    if (video.paused) {
        video.play();
    } else {
        video.pause();
    }
}

// Split at playhead (instant!)
function capcutSplitAtPlayhead() {
    const clip = capcutClips.find(c => {
        const clipStart = c.position;
        const clipEnd = c.position + (c.trimEnd - c.trimStart);
        return capcutPlayhead >= clipStart && capcutPlayhead < clipEnd;
    });

    if (!clip) {
        showNotification('⚠️ No clip at playhead', 'warning');
        return;
    }

    capcutSaveHistory();

    const splitPoint = capcutPlayhead - clip.position;
    const absoluteSplitPoint = clip.trimStart + splitPoint;

    const leftClip = {
        ...clip,
        id: capcutGenerateId(),
        trimEnd: absoluteSplitPoint,
        selected: false
    };

    const rightClip = {
        ...clip,
        id: capcutGenerateId(),
        trimStart: absoluteSplitPoint,
        position: capcutPlayhead,
        selected: false
    };

    const index = capcutClips.findIndex(c => c.id === clip.id);
    capcutClips.splice(index, 1, leftClip, rightClip);

    capcutRenderTimeline();
    showNotification('✅ Clip split!', 'success');
}

// Trim by dragging (instant!)
function capcutStartTrimLeft(clipId, e) {
    e.preventDefault();
    e.stopPropagation();
    const clip = capcutClips.find(c => c.id === clipId);
    if (!clip) return;

    capcutSaveHistory();
    const startX = e.clientX;
    const originalTrimStart = clip.trimStart;
    const originalPosition = clip.position;

    document.onmousemove = (moveE) => {
        const deltaX = moveE.clientX - startX;
        const deltaTime = deltaX / capcutPixelsPerSecond;
        const newTrimStart = Math.max(0, Math.min(originalTrimStart + deltaTime, clip.trimEnd - 0.1));
        const timeDelta = newTrimStart - clip.trimStart;
        clip.trimStart = newTrimStart;
        clip.position = originalPosition + timeDelta;
        capcutUpdateClipVisual(clip);
    };

    document.onmouseup = () => {
        document.onmousemove = null;
        document.onmouseup = null;
        capcutRenderTimeline();
    };
}

function capcutStartTrimRight(clipId, e) {
    e.preventDefault();
    e.stopPropagation();
    const clip = capcutClips.find(c => c.id === clipId);
    if (!clip) return;

    capcutSaveHistory();
    const startX = e.clientX;
    const originalTrimEnd = clip.trimEnd;

    document.onmousemove = (moveE) => {
        const deltaX = moveE.clientX - startX;
        const deltaTime = deltaX / capcutPixelsPerSecond;

        if (clip.type === 'image') {
            // Images can be extended to any duration
            const newTrimEnd = Math.max(clip.trimStart + 0.1, originalTrimEnd + deltaTime);
            clip.trimEnd = newTrimEnd;
            // Update original duration if extended
            if (newTrimEnd > clip.originalDuration) {
                clip.originalDuration = newTrimEnd;
            }
        } else {
            // Videos limited to original duration
            const newTrimEnd = Math.min(clip.originalDuration, Math.max(clip.trimStart + 0.1, originalTrimEnd + deltaTime));
            clip.trimEnd = newTrimEnd;
        }
        capcutUpdateClipVisual(clip);
    };

    document.onmouseup = () => {
        document.onmousemove = null;
        document.onmouseup = null;
        capcutRenderTimeline();
    };
}

function capcutUpdateClipVisual(clip) {
    const clipEl = document.querySelector('[data-clip-id="' + clip.id + '"]');
    if (!clipEl) return;
    const duration = clip.trimEnd - clip.trimStart;
    clipEl.style.width = (duration * capcutPixelsPerSecond) + 'px';
    clipEl.style.left = (clip.position * capcutPixelsPerSecond) + 'px';
}

// Drag to reorder (instant!) - WITH MAGNETIC SNAPPING
function capcutStartDragClip(clipId, e) {
    const clip = capcutClips.find(c => c.id === clipId);
    if (!clip) return;

    const startX = e.clientX;
    const originalPosition = clip.position;
    capcutSaveHistory();
    let hasMoved = false;
    let lastSnapPosition = null;

    document.onmousemove = (moveE) => {
        hasMoved = true;
        const deltaX = moveE.clientX - startX;
        const deltaTime = deltaX / capcutPixelsPerSecond;
        let newPosition = Math.max(0, originalPosition + deltaTime);

        // Apply magnetic snapping
        newPosition = capcutMagneticSnap(clipId, newPosition);

        // Visual feedback for snapping
        if (lastSnapPosition !== null && newPosition !== lastSnapPosition) {
            // Snapped! Show subtle visual feedback
            const clipEl = document.querySelector(`[data-clip-id="${clipId}"]`);
            if (clipEl) {
                clipEl.style.boxShadow = '0 0 15px rgba(102, 126, 234, 0.8)';
                setTimeout(() => {
                    clipEl.style.boxShadow = '';
                }, 200);
            }
        }

        lastSnapPosition = newPosition;
        clip.position = newPosition;
        capcutUpdateClipVisual(clip);
    };

    document.onmouseup = () => {
        document.onmousemove = null;
        document.onmouseup = null;
        if (hasMoved) {
            capcutSnapClips();
            capcutRenderTimeline();
        }
    };
}

// Smart snap - Auto-close gaps and magnetic snapping
function capcutSnapClips() {
    if (capcutClips.length === 0) return;

    // Sort by position
    capcutClips.sort((a, b) => a.position - b.position);

    // Auto-close gaps
    let currentPos = 0;
    capcutClips.forEach(clip => {
        const duration = clip.trimEnd - clip.trimStart;

        // If gap is less than 1 second, auto-close it
        if (Math.abs(clip.position - currentPos) < 1.0) {
            clip.position = currentPos;
        } else {
            // Keep the gap if it's intentional (> 1 second)
            currentPos = clip.position;
        }

        currentPos = clip.position + duration;
    });
}

// Magnetic snap when dragging - clips attract to each other
function capcutMagneticSnap(clipId, newPosition) {
    const clip = capcutClips.find(c => c.id === clipId);
    if (!clip) return newPosition;

    const clipDuration = clip.trimEnd - clip.trimStart;
    const SNAP_THRESHOLD = 10 / capcutPixelsPerSecond; // 10 pixels in time

    // Check snap to other clips
    for (const otherClip of capcutClips) {
        if (otherClip.id === clipId) continue;

        const otherEnd = otherClip.position + (otherClip.trimEnd - otherClip.trimStart);

        // Snap to start of other clip
        if (Math.abs(newPosition + clipDuration - otherClip.position) < SNAP_THRESHOLD) {
            return otherClip.position - clipDuration;
        }

        // Snap to end of other clip
        if (Math.abs(newPosition - otherEnd) < SNAP_THRESHOLD) {
            return otherEnd;
        }
    }

    // Snap to timeline start
    if (Math.abs(newPosition) < SNAP_THRESHOLD) {
        return 0;
    }

    return newPosition;
}

// Delete selected (instant!)
function capcutDeleteSelected() {
    const selectedClips = capcutClips.filter(c => c.selected);
    if (selectedClips.length === 0) {
        showNotification('⚠️ No clips selected', 'warning');
        return;
    }

    capcutSaveHistory();
    capcutClips = capcutClips.filter(c => !c.selected);
    capcutSnapClips();
    capcutRenderTimeline();
    showNotification('✅ Deleted ' + selectedClips.length + ' clip(s)', 'success');
}

// Toggle mute for clip
function capcutToggleMute(clipId) {
    const clip = capcutClips.find(c => c.id === clipId);
    if (!clip || clip.type !== 'video') return;

    capcutSaveHistory();
    clip.muted = !clip.muted;
    capcutRenderTimeline();
    showNotification(clip.muted ? '🔇 Clip muted' : '🔊 Clip unmuted', 'info');
}

// Undo/Redo (instant!)
function capcutSaveHistory() {
    capcutHistory = capcutHistory.slice(0, capcutHistoryIndex + 1);
    capcutHistory.push(JSON.parse(JSON.stringify(capcutClips)));
    capcutHistoryIndex++;
    if (capcutHistory.length > 50) {
        capcutHistory.shift();
        capcutHistoryIndex--;
    }
}

function capcutUndo() {
    if (capcutHistoryIndex <= 0) {
        showNotification('⚠️ Nothing to undo', 'warning');
        return;
    }
    capcutHistoryIndex--;
    capcutClips = JSON.parse(JSON.stringify(capcutHistory[capcutHistoryIndex]));
    capcutRenderTimeline();
    showNotification('↶ Undone', 'info');
}

function capcutRedo() {
    if (capcutHistoryIndex >= capcutHistory.length - 1) {
        showNotification('⚠️ Nothing to redo', 'warning');
        return;
    }
    capcutHistoryIndex++;
    capcutClips = JSON.parse(JSON.stringify(capcutHistory[capcutHistoryIndex]));
    capcutRenderTimeline();
    showNotification('↷ Redone', 'info');
}

// Advanced Zoom System
const ZOOM_LEVELS = [0.5, 1, 2, 5, 10, 20, 50, 100, 200];
const BASE_PIXELS_PER_SECOND = 10;

function capcutZoomIn() {
    const currentIndex = ZOOM_LEVELS.findIndex(z => z >= capcutZoomLevel);
    if (currentIndex < ZOOM_LEVELS.length - 1) {
        capcutZoomLevel = ZOOM_LEVELS[currentIndex + 1];
        capcutPixelsPerSecond = BASE_PIXELS_PER_SECOND * capcutZoomLevel;
        capcutRenderTimeline();
        showNotification(`Zoom: ${capcutZoomLevel}x`, 'info');
    }
}

function capcutZoomOut() {
    const currentIndex = ZOOM_LEVELS.findIndex(z => z >= capcutZoomLevel);
    if (currentIndex > 0) {
        capcutZoomLevel = ZOOM_LEVELS[currentIndex - 1];
        capcutPixelsPerSecond = BASE_PIXELS_PER_SECOND * capcutZoomLevel;
        capcutRenderTimeline();
        showNotification(`Zoom: ${capcutZoomLevel}x`, 'info');
    }
}

function capcutZoomToFit() {
    // Calculate zoom to fit entire timeline in view
    let totalDuration = capcutCalculateTotalDuration();

    // If empty timeline, use default
    if (totalDuration === 0) {
        totalDuration = 60;
    }

    const container = document.getElementById('capcutTimelineContainer');
    if (!container) return;

    const containerWidth = container.clientWidth - 100; // Account for padding and scrollbar
    const idealPixelsPerSecond = containerWidth / totalDuration;

    // Calculate ideal zoom
    let idealZoom = idealPixelsPerSecond / BASE_PIXELS_PER_SECOND;

    // Clamp to available zoom levels
    idealZoom = Math.max(ZOOM_LEVELS[0], Math.min(idealZoom, ZOOM_LEVELS[ZOOM_LEVELS.length - 1]));

    // Find closest zoom level
    const closestZoom = ZOOM_LEVELS.reduce((prev, curr) =>
        Math.abs(curr - idealZoom) < Math.abs(prev - idealZoom) ? curr : prev
    );

    capcutZoomLevel = closestZoom;
    capcutPixelsPerSecond = BASE_PIXELS_PER_SECOND * capcutZoomLevel;
    capcutRenderTimeline();

    // Scroll to beginning to see playhead
    setTimeout(() => {
        container.scrollLeft = 0;
    }, 50);

    showNotification(`Fit: ${capcutZoomLevel}x (${formatTime(totalDuration)} total)`, 'info');
}

function capcutZoomReset() {
    capcutZoomLevel = 1;
    capcutPixelsPerSecond = BASE_PIXELS_PER_SECOND;
    capcutRenderTimeline();
    showNotification('Zoom: 1x (default)', 'info');
}

// Export (backend FFmpeg - runs ONCE!)
async function capcutExport() {
    if (capcutClips.length === 0) {
        showNotification('⚠️ Timeline is empty', 'warning');
        return;
    }

    const exportBtn = document.getElementById('capcutExportBtn');
    const exportProgress = document.getElementById('capcutExportProgress');
    const exportStatus = document.getElementById('capcutExportStatus');
    const exportBar = document.getElementById('capcutExportBar');
    const exportPercent = document.getElementById('capcutExportPercent');

    try {
        exportBtn.disabled = true;
        exportBtn.textContent = '⏳ Exporting...';
        exportProgress.style.display = 'block';
        exportStatus.textContent = 'Preparing export...';
        exportBar.style.width = '10%';
        exportPercent.textContent = '10%';

        const clipsData = capcutClips.map(clip => ({
            file_id: clip.fileId,
            filename: clip.filename,
            type: clip.type,
            trim_start: clip.trimStart,
            trim_end: clip.trimEnd,
            duration: clip.type === 'image' ? (clip.trimEnd - clip.trimStart) : null,
            position: clip.position,
            muted: clip.muted || false
        }));

        exportStatus.textContent = 'Processing with FFmpeg...';
        exportBar.style.width = '30%';
        exportPercent.textContent = '30%';

        const response = await fetch('/api/timeline/process', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                clips: clipsData,
                output_quality: document.getElementById('capcutExportQuality').value
            })
        });

        exportBar.style.width = '60%';
        exportPercent.textContent = '60%';

        const data = await response.json();

        if (data.success) {
            exportBar.style.width = '100%';
            exportPercent.textContent = '100%';
            exportStatus.textContent = '✅ Export complete!';

            window.open(data.download_url, '_blank');
            showNotification('✅ Video exported!', 'success');

            setTimeout(() => {
                exportProgress.style.display = 'none';
            }, 3000);
        } else {
            throw new Error(data.error);
        }
    } catch (error) {
        console.error('Export error:', error);
        showNotification('❌ Export failed: ' + error.message, 'error');
        exportStatus.textContent = '❌ Export failed';
    } finally {
        exportBtn.disabled = false;
        exportBtn.textContent = '🚀 Export Final Video';
    }
}

// Keyboard shortcuts - PROFESSIONAL GRADE
document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

    if (e.key === ' ' || e.key === 'Spacebar') {
        // Spacebar to play/pause
        e.preventDefault();
        capcutTogglePlay();
    } else if (e.ctrlKey || e.metaKey) {
        if (e.key === 'z') {
            e.preventDefault();
            if (e.shiftKey) {
                capcutRedo();
            } else {
                capcutUndo();
            }
        } else if (e.key === 'y') {
            e.preventDefault();
            capcutRedo();
        } else if (e.key === 'b') {
            e.preventDefault();
            capcutSplitAtPlayhead();
        } else if (e.key === '=' || e.key === '+') {
            // Ctrl + = or Ctrl + + to zoom in
            e.preventDefault();
            capcutZoomIn();
        } else if (e.key === '-' || e.key === '_') {
            // Ctrl + - to zoom out
            e.preventDefault();
            capcutZoomOut();
        } else if (e.key === '0') {
            // Ctrl + 0 to zoom to fit
            e.preventDefault();
            capcutZoomToFit();
        } else if (e.key === '1') {
            // Ctrl + 1 to reset zoom
            e.preventDefault();
            capcutZoomReset();
        }
    } else if (e.key === 'Delete' || e.key === 'Backspace') {
        if (document.activeElement.tagName !== 'INPUT') {
            e.preventDefault();
            capcutDeleteSelected();
        }
    } else if (e.key === 'Home') {
        // Jump to beginning
        e.preventDefault();
        capcutPlayhead = 0;
        capcutUpdatePlayheadPosition();
        capcutSeekPreviewToPlayhead();
        const container = document.getElementById('capcutTimelineContainer');
        if (container) container.scrollLeft = 0;
    } else if (e.key === 'End') {
        // Jump to end
        e.preventDefault();
        capcutPlayhead = capcutCalculateTotalDuration();
        capcutUpdatePlayheadPosition();
        capcutSeekPreviewToPlayhead();
    } else if (e.key === 'ArrowLeft') {
        // Frame back (1 second)
        e.preventDefault();
        capcutPlayhead = Math.max(0, capcutPlayhead - 1);
        capcutUpdatePlayheadPosition();
        capcutSeekPreviewToPlayhead();
    } else if (e.key === 'ArrowRight') {
        // Frame forward (1 second)
        e.preventDefault();
        capcutPlayhead = Math.min(capcutCalculateTotalDuration(), capcutPlayhead + 1);
        capcutUpdatePlayheadPosition();
        capcutSeekPreviewToPlayhead();
    }
});

function formatTime(seconds) {
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    if (hrs > 0) {
        return hrs + ':' + (mins < 10 ? '0' : '') + mins + ':' + (secs < 10 ? '0' : '') + secs;
    } else {
        return mins + ':' + (secs < 10 ? '0' : '') + secs;
    }
}

console.log('✅ CapCut-style timeline editor initialized');

// =============================================================================
// PLAYHEAD - DRAGGABLE & SYNCED WITH PREVIEW
// =============================================================================

// Make playhead draggable and clickable - SMOOTH VERSION
function capcutInitializePlayhead() {
    const container = document.getElementById('capcutTimelineContainer');
    const playheadEl = document.getElementById('capcutPlayhead');

    if (!container || !playheadEl) return;

    // Click timeline to move playhead
    container.addEventListener('click', (e) => {
        if (capcutIsDraggingPlayhead) return; // Ignore click if just finished dragging
        if (e.target.closest('.capcut-clip') || e.target.closest('.capcut-trim-handle')) {
            return; // Don't move playhead if clicking clip/handle
        }

        const rect = container.getBoundingClientRect();
        const clickX = e.clientX - rect.left + container.scrollLeft;
        const timeAtClick = clickX / capcutPixelsPerSecond;

        capcutPlayhead = Math.max(0, Math.min(timeAtClick, capcutCalculateTotalDuration() + 10));
        capcutUpdatePlayheadPosition();
        capcutSeekPreviewToPlayhead();
    });

    // Drag playhead - SMOOTH with auto-scroll
    playheadEl.addEventListener('mousedown', (e) => {
        e.preventDefault();
        e.stopPropagation();

        capcutIsDraggingPlayhead = true;
        playheadEl.style.cursor = 'grabbing';

        const containerRect = container.getBoundingClientRect();

        document.onmousemove = (moveE) => {
            // Calculate time based on mouse position
            const mouseX = moveE.clientX;
            const relativeX = mouseX - containerRect.left;
            const scrollX = container.scrollLeft;

            // Calculate time
            const timeAtMouse = (relativeX + scrollX) / capcutPixelsPerSecond;
            capcutPlayhead = Math.max(0, timeAtMouse);

            // Auto-scroll if near edges
            const scrollMargin = 50;
            if (relativeX < scrollMargin && scrollX > 0) {
                container.scrollLeft -= 10;
            } else if (relativeX > containerRect.width - scrollMargin) {
                container.scrollLeft += 10;
            }

            capcutUpdatePlayheadPosition();
            capcutSeekPreviewToPlayhead();
        };

        document.onmouseup = () => {
            document.onmousemove = null;
            document.onmouseup = null;
            playheadEl.style.cursor = 'grab';

            setTimeout(() => {
                capcutIsDraggingPlayhead = false;
            }, 100);
        };
    });

    // Show playhead initially
    playheadEl.style.display = 'block';
    playheadEl.style.cursor = 'grab';
    capcutUpdatePlayheadPosition();

    // Mouse wheel zoom on timeline
    container.addEventListener('wheel', (e) => {
        if (e.ctrlKey || e.metaKey) {
            e.preventDefault();
            if (e.deltaY < 0) {
                capcutZoomIn();
            } else {
                capcutZoomOut();
            }
        }
    }, { passive: false });
}

// Update playhead visual position
function capcutUpdatePlayheadPosition() {
    const playheadEl = document.getElementById('capcutPlayhead');
    if (!playheadEl) return;

    const leftPos = capcutPlayhead * capcutPixelsPerSecond;
    playheadEl.style.left = leftPos + 'px';
}

// Seek video preview to playhead position
function capcutSeekPreviewToPlayhead() {
    const video = document.getElementById('editorVideoPreview');
    if (!video || !video.src) return;

    // Find which clip the playhead is on
    const clip = capcutClips.find(c => {
        const clipStart = c.position;
        const clipEnd = c.position + (c.trimEnd - c.trimStart);
        return capcutPlayhead >= clipStart && capcutPlayhead < clipEnd;
    });

    if (clip && clip.type === 'video') {
        // Load this clip if not already loaded
        if (video.src !== clip.url) {
            video.src = clip.url;
        }

        // Calculate time within clip
        const timeInClip = capcutPlayhead - clip.position;
        const actualTime = clip.trimStart + timeInClip;

        video.currentTime = actualTime;

        // Update time display
        capcutUpdateTimeDisplay();
    }
}

// Initialize when page loads
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', capcutInitializePlayhead);
} else {
    capcutInitializePlayhead();
}

// Update playhead position when rendering timeline
const originalRenderTimeline = capcutRenderTimeline;
capcutRenderTimeline = function() {
    originalRenderTimeline();
    capcutUpdatePlayheadPosition();
};

console.log('✅ CapCut playhead initialized - Click timeline or drag playhead to scrub video');
