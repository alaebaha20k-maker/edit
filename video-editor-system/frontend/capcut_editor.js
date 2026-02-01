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

// Generate unique ID
function capcutGenerateId() {
    return 'clip_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
}

// File upload handlers
function capcutSelectFiles(event) {
    const files = Array.from(event.target.files);
    capcutUploadFiles(files);
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
    capcutUploadFiles(files);
}

async function capcutUploadFiles(files) {
    if (!files || files.length === 0) return;
    showNotification('⏳ Uploading ' + files.length + ' file(s)...', 'info');

    for (const file of files) {
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
            if (!data.success) continue;

            const url = URL.createObjectURL(file);
            let duration = isImage ? 5.0 : 0;

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
            const lastClip = capcutClips[capcutClips.length - 1];
            const position = lastClip ? (lastClip.position + (lastClip.trimEnd - lastClip.trimStart)) : 0;

            const clip = {
                id: capcutGenerateId(),
                filename: file.name,
                fileId: data.file_id,
                filepath: '/uploads/' + data.file_id,
                type: isVideo ? 'video' : 'image',
                originalDuration: duration,
                trimStart: 0,
                trimEnd: duration,
                position: position,
                thumbnail: thumbnail,
                url: url,
                selected: false
            };

            capcutClips.push(clip);
        } catch (error) {
            console.error('Upload error:', error);
        }
    }

    capcutSaveHistory();
    capcutRenderTimeline();
    showNotification('✅ Added ' + files.length + ' file(s)', 'success');
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
    const track = document.getElementById('capcutTrack');
    const statusText = document.getElementById('capcutStatusText');

    if (capcutClips.length === 0) {
        track.innerHTML = '<div id="capcutEmptyMessage" style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); color: #666; font-size: 14px; pointer-events: none;">Timeline is empty - upload videos above</div>';
        statusText.textContent = 'Ready • 0 clips';
        return;
    }

    track.innerHTML = '';

    capcutClips.forEach((clip, index) => {
        const duration = clip.trimEnd - clip.trimStart;
        const width = duration * capcutPixelsPerSecond;
        const left = clip.position * capcutPixelsPerSecond;

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
        content.innerHTML = '<img src="' + clip.thumbnail + '" style="width:50px;height:30px;border-radius:3px;object-fit:cover;"><div style="flex:1;overflow:hidden;"><div style="font-size:12px;font-weight:bold;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' + (clip.type === 'image' ? '🖼️' : '📹') + ' ' + clip.filename + '</div><div style="font-size:10px;color:rgba(255,255,255,0.7);">' + formatTime(duration) + '</div></div>';

        content.addEventListener('mousedown', (e) => capcutStartDragClip(clip.id, e));
        clipEl.addEventListener('click', (e) => {
            if (e.target.closest('.capcut-clip') === clipEl) {
                capcutSelectClip(clip.id, e.ctrlKey || e.metaKey);
            }
        });

        clipEl.appendChild(leftHandle);
        clipEl.appendChild(content);
        clipEl.appendChild(rightHandle);
        track.appendChild(clipEl);
    });

    const totalDuration = capcutCalculateTotalDuration();
    const selectedCount = capcutClips.filter(c => c.selected).length;
    statusText.textContent = 'Ready • ' + capcutClips.length + ' clip' + (capcutClips.length !== 1 ? 's' : '') + (selectedCount > 0 ? ' • ' + selectedCount + ' selected' : '') + ' • Total: ' + formatTime(totalDuration);

    capcutRenderTimeMarkers();
}

function capcutRenderTimeMarkers() {
    const markersEl = document.getElementById('capcutTimeMarkers');
    const totalDuration = capcutCalculateTotalDuration();
    markersEl.innerHTML = '';
    markersEl.style.width = Math.max(totalDuration * capcutPixelsPerSecond, 800) + 'px';

    for (let t = 0; t <= totalDuration + 30; t += 30) {
        const marker = document.createElement('span');
        marker.style.cssText = 'position:absolute;left:' + (t * capcutPixelsPerSecond) + 'px;font-size:11px;color:#aaa;';
        marker.textContent = formatTime(t);
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

    if (!video) return;

    if (clip.type === 'video') {
        // Show video
        video.src = clip.url;
        video.style.display = 'block';
        placeholder.style.display = 'none';
        timeDisplay.style.display = 'block';

        // Seek to clip's trim start
        video.currentTime = clip.trimStart;

        // Update time display
        video.addEventListener('loadedmetadata', () => {
            capcutUpdateTimeDisplay();
        });

        video.addEventListener('timeupdate', () => {
            capcutUpdateTimeDisplay();
        });
    } else {
        // Show image
        video.style.display = 'none';
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
        const newTrimEnd = Math.min(clip.originalDuration, Math.max(clip.trimStart + 0.1, originalTrimEnd + deltaTime));
        clip.trimEnd = newTrimEnd;
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

// Drag to reorder (instant!)
function capcutStartDragClip(clipId, e) {
    const clip = capcutClips.find(c => c.id === clipId);
    if (!clip) return;

    const startX = e.clientX;
    const originalPosition = clip.position;
    capcutSaveHistory();
    let hasMoved = false;

    document.onmousemove = (moveE) => {
        hasMoved = true;
        const deltaX = moveE.clientX - startX;
        const deltaTime = deltaX / capcutPixelsPerSecond;
        clip.position = Math.max(0, originalPosition + deltaTime);
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

function capcutSnapClips() {
    capcutClips.sort((a, b) => a.position - b.position);
    let currentPos = 0;
    capcutClips.forEach(clip => {
        clip.position = currentPos;
        currentPos += (clip.trimEnd - clip.trimStart);
    });
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

// Zoom
function capcutZoomIn() {
    capcutPixelsPerSecond = Math.min(capcutPixelsPerSecond * 1.5, 50);
    capcutRenderTimeline();
}

function capcutZoomOut() {
    capcutPixelsPerSecond = Math.max(capcutPixelsPerSecond / 1.5, 2);
    capcutRenderTimeline();
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
            fileId: clip.fileId,
            filename: clip.filename,
            type: clip.type,
            trimStart: clip.trimStart,
            trimEnd: clip.trimEnd,
            duration: clip.type === 'image' ? (clip.trimEnd - clip.trimStart) : null,
            position: clip.position
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

// Keyboard shortcuts
document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

    if (e.ctrlKey || e.metaKey) {
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
        }
    } else if (e.key === 'Delete' || e.key === 'Backspace') {
        if (document.activeElement.tagName !== 'INPUT') {
            e.preventDefault();
            capcutDeleteSelected();
        }
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

// Make playhead draggable and clickable
function capcutInitializePlayhead() {
    const container = document.getElementById('capcutTimelineContainer');
    const playheadEl = document.getElementById('capcutPlayhead');

    if (!container || !playheadEl) return;

    // Click timeline to move playhead
    container.addEventListener('click', (e) => {
        if (e.target.closest('.capcut-clip') || e.target.closest('.capcut-trim-handle')) {
            return; // Don't move playhead if clicking clip/handle
        }

        const rect = container.getBoundingClientRect();
        const clickX = e.clientX - rect.left + container.scrollLeft;
        const timeAtClick = clickX / capcutPixelsPerSecond;

        capcutPlayhead = Math.max(0, timeAtClick);
        capcutUpdatePlayheadPosition();
        capcutSeekPreviewToPlayhead();
    });

    // Drag playhead
    playheadEl.addEventListener('mousedown', (e) => {
        e.preventDefault();
        e.stopPropagation();

        const startX = e.clientX;
        const startPlayhead = capcutPlayhead;

        document.onmousemove = (moveE) => {
            const deltaX = moveE.clientX - startX;
            const deltaTime = deltaX / capcutPixelsPerSecond;

            capcutPlayhead = Math.max(0, startPlayhead + deltaTime);
            capcutUpdatePlayheadPosition();
            capcutSeekPreviewToPlayhead();
        };

        document.onmouseup = () => {
            document.onmousemove = null;
            document.onmouseup = null;
        };
    });

    // Show playhead initially
    playheadEl.style.display = 'block';
    capcutUpdatePlayheadPosition();
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
