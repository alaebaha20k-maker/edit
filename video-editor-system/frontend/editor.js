/**
 * MR BAHA Editor - CapCut-style Video Editor
 * Complete JavaScript Logic
 */

let mainVideo = null;
let clips = [];
let selectedClip = null;
let currentTime = 0;
let isPlaying = false;

// ==================== VIDEO UPLOAD ====================

async function loadMainVideo(event) {
    const file = event.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);
    formData.append('type', 'video');

    try {
        const response = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (data.success) {
            mainVideo = {
                path: data.path,
                filename: data.filename,
                duration: 0  // Will be set when video loads
            };

            // Load video in preview
            const video = document.getElementById('previewVideo');
            video.src = `/api/preview-video/${data.filename}`;

            video.addEventListener('loadedmetadata', function() {
                mainVideo.duration = video.duration;
                document.getElementById('totalTime').textContent = formatTime(video.duration);

                // Create initial clip (full video)
                clips = [{
                    id: 1,
                    type: 'video',
                    path: mainVideo.path,
                    start: 0,
                    end: mainVideo.duration,
                    duration: mainVideo.duration
                }];

                updateTimeline();
            });

            // Update current time display
            video.addEventListener('timeupdate', function() {
                currentTime = video.currentTime;
                document.getElementById('currentTime').textContent = formatTime(currentTime);
                updatePlayhead();
            });

        } else {
            alert('Error uploading video: ' + data.error);
        }

    } catch (error) {
        alert('Error: ' + error.message);
    }
}

// ==================== PLAYBACK CONTROLS ====================

function playPause() {
    const video = document.getElementById('previewVideo');

    if (video.paused) {
        video.play();
        isPlaying = true;
    } else {
        video.pause();
        isPlaying = false;
    }
}

function skipBackward() {
    const video = document.getElementById('previewVideo');
    video.currentTime = Math.max(0, video.currentTime - 5);
}

function skipForward() {
    const video = document.getElementById('previewVideo');
    video.currentTime = Math.min(video.duration, video.currentTime + 5);
}

function stop() {
    const video = document.getElementById('previewVideo');
    video.pause();
    video.currentTime = 0;
    isPlaying = false;
}

function formatTime(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

// ==================== TIMELINE ====================

function updateTimeline() {
    const track = document.getElementById('timelineTrack');
    track.innerHTML = '';

    clips.forEach(clip => {
        const clipDiv = document.createElement('div');
        clipDiv.className = 'clip';
        clipDiv.dataset.id = clip.id;

        if (selectedClip && selectedClip.id === clip.id) {
            clipDiv.classList.add('selected');
        }

        // Calculate width based on duration (simplified)
        const width = Math.max(100, clip.duration * 50);  // 50px per second
        clipDiv.style.width = width + 'px';

        clipDiv.innerHTML = `
            <div class="clip-controls">
                <button onclick="splitClip(${clip.id})">✂️ Split</button>
                <button onclick="deleteClip(${clip.id})">🗑️ Delete</button>
            </div>
            <div class="clip-content">
                <div class="clip-type">${clip.type}</div>
                <div class="clip-duration">${formatTime(clip.duration)}</div>
            </div>
        `;

        clipDiv.addEventListener('click', () => selectClip(clip.id));

        track.appendChild(clipDiv);
    });
}

function selectClip(clipId) {
    selectedClip = clips.find(c => c.id === clipId);
    updateTimeline();
}

function updatePlayhead() {
    if (!mainVideo) return;

    const playhead = document.getElementById('playhead');
    const timeline = document.getElementById('timeline');

    // Calculate position (simplified)
    const percentage = (currentTime / mainVideo.duration) * 100;
    playhead.style.left = percentage + '%';
}

// ==================== EDITING OPERATIONS ====================

function splitAtPlayhead() {
    if (!selectedClip) {
        alert('Please select a clip first');
        return;
    }

    const video = document.getElementById('previewVideo');
    const splitTime = video.currentTime;

    // Check if split time is within selected clip
    if (splitTime <= selectedClip.start || splitTime >= selectedClip.end) {
        alert('Split point must be within the selected clip');
        return;
    }

    // Create two new clips
    const newId = Math.max(...clips.map(c => c.id)) + 1;

    const clip1 = {
        ...selectedClip,
        end: splitTime,
        duration: splitTime - selectedClip.start
    };

    const clip2 = {
        ...selectedClip,
        id: newId,
        start: splitTime,
        duration: selectedClip.end - splitTime
    };

    // Replace original clip with two new clips
    const index = clips.findIndex(c => c.id === selectedClip.id);
    clips.splice(index, 1, clip1, clip2);

    selectedClip = null;
    updateTimeline();
}

function splitClip(clipId) {
    const clip = clips.find(c => c.id === clipId);
    if (!clip) return;

    selectedClip = clip;

    // Set video to clip's start time
    const video = document.getElementById('previewVideo');
    video.currentTime = clip.start;

    alert('Position the playhead where you want to split, then click Split again');
}

function deleteClip(clipId) {
    if (!confirm('Delete this clip?')) return;

    clips = clips.filter(c => c.id !== clipId);

    if (clips.length === 0) {
        alert('Cannot delete all clips. At least one clip must remain.');
        // Restore
        clips = [{
            id: 1,
            type: 'video',
            path: mainVideo.path,
            start: 0,
            end: mainVideo.duration,
            duration: mainVideo.duration
        }];
    }

    selectedClip = null;
    updateTimeline();
}

// ==================== ADD MEDIA ====================

function addImage() {
    document.getElementById('addImageFile').click();
}

function addVideo() {
    document.getElementById('addVideoFile').click();
}

document.addEventListener('DOMContentLoaded', function() {
    // Image upload handler
    document.getElementById('addImageFile').addEventListener('change', async function(event) {
        const files = event.target.files;
        if (files.length === 0) return;

        for (let file of files) {
            const formData = new FormData();
            formData.append('file', file);
            formData.append('type', 'image');

            try {
                const response = await fetch('/api/upload', {
                    method: 'POST',
                    body: formData
                });

                const data = await response.json();

                if (data.success) {
                    const newId = Math.max(...clips.map(c => c.id)) + 1;

                    clips.push({
                        id: newId,
                        type: 'image',
                        path: data.path,
                        start: 0,
                        end: 5,  // Default 5 seconds
                        duration: 5
                    });

                    updateTimeline();
                }
            } catch (error) {
                alert('Error uploading image: ' + error.message);
            }
        }
    });

    // Video upload handler
    document.getElementById('addVideoFile').addEventListener('change', async function(event) {
        const files = event.target.files;
        if (files.length === 0) return;

        for (let file of files) {
            const formData = new FormData();
            formData.append('file', file);
            formData.append('type', 'video');

            try {
                const response = await fetch('/api/upload', {
                    method: 'POST',
                    body: formData
                });

                const data = await response.json();

                if (data.success) {
                    // Load video to get duration
                    const tempVideo = document.createElement('video');
                    tempVideo.src = `/api/preview-video/${data.filename}`;

                    tempVideo.addEventListener('loadedmetadata', function() {
                        const newId = Math.max(...clips.map(c => c.id)) + 1;

                        clips.push({
                            id: newId,
                            type: 'video',
                            path: data.path,
                            start: 0,
                            end: tempVideo.duration,
                            duration: tempVideo.duration
                        });

                        updateTimeline();
                    });
                }
            } catch (error) {
                alert('Error uploading video: ' + error.message);
            }
        }
    });
});

// ==================== EXPORT ====================

async function exportVideo() {
    if (clips.length === 0) {
        alert('No clips to export');
        return;
    }

    const quality = document.getElementById('exportQuality').value;

    document.getElementById('exportProgress').style.display = 'block';
    document.getElementById('exportResult').style.display = 'none';

    const statusDiv = document.getElementById('exportStatus');
    const progressFill = document.getElementById('exportProgressFill');

    statusDiv.innerHTML = '<div>🎬 Exporting video...</div>';
    progressFill.style.width = '20%';
    progressFill.textContent = '20%';

    try {
        const response = await fetch('/api/editor/process', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                clips: clips,
                quality: quality
            })
        });

        const data = await response.json();

        if (data.success) {
            progressFill.style.width = '100%';
            progressFill.textContent = '100%';
            statusDiv.innerHTML += '<div>✅ Export complete!</div>';

            document.getElementById('exportResult').style.display = 'block';
            window.currentExportFile = data.output_path.split('/').pop();

        } else {
            alert('Error: ' + data.error);
        }

    } catch (error) {
        statusDiv.innerHTML += '<div>❌ Error: ' + error.message + '</div>';
    }
}

function downloadEdited() {
    if (window.currentExportFile) {
        window.location.href = `/api/download/${window.currentExportFile}`;
    }
}

// Export functions to global scope
window.loadMainVideo = loadMainVideo;
window.playPause = playPause;
window.skipBackward = skipBackward;
window.skipForward = skipForward;
window.stop = stop;
window.splitAtPlayhead = splitAtPlayhead;
window.splitClip = splitClip;
window.deleteClip = deleteClip;
window.addImage = addImage;
window.addVideo = addVideo;
window.exportVideo = exportVideo;
window.downloadEdited = downloadEdited;

console.log('MR BAHA Editor loaded successfully');
