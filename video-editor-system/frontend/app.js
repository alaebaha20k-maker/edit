/**
 * AI VIDEO STUDIO - Complete Frontend Logic
 * Single Page Application JavaScript
 */

// =============================================================================
// GLOBAL STATE
// =============================================================================
const appState = {
    currentTab: 'dashboard',
    generatedTitle: '',
    generatedScript: '',
    scriptPath: '',
    imageFiles: [],
    audioFiles: [],
    editorClips: [],
    selectedClip: null,
    editorVideo: null,
    settings: {}
};

// =============================================================================
// TAB NAVIGATION
// =============================================================================
function showTab(tabName) {
    // Hide all tabs
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.remove('active');
    });

    // Remove active from all nav buttons
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.classList.remove('active');
    });

    // Show selected tab
    const selectedTab = document.getElementById(`tab-${tabName}`);
    if (selectedTab) {
        selectedTab.classList.add('active');
    }

    // Add active to clicked nav button
    const selectedBtn = document.querySelector(`[data-tab="${tabName}"]`);
    if (selectedBtn) {
        selectedBtn.classList.add('active');
    }

    appState.currentTab = tabName;

    // Load specific tab content
    if (tabName === 'output') {
        refreshOutputFiles();
    }
}

// =============================================================================
// SETTINGS MODAL
// =============================================================================
function openSettings() {
    const modal = document.getElementById('settingsModal');
    modal.classList.add('show');
    loadSettings();
}

function closeSettings() {
    const modal = document.getElementById('settingsModal');
    modal.classList.remove('show');
}

async function loadSettings() {
    try {
        const response = await fetch('/api/settings');
        const data = await response.json();
        appState.settings = data;

        // Load formulas
        if (data.formulas) {
            document.getElementById('titleFormula').value = data.formulas.title || '';
            document.getElementById('scriptFormula').value = data.formulas.script || '';
            document.getElementById('imageFormula').value = data.formulas.image || '';
        }
    } catch (error) {
        console.error('Error loading settings:', error);
    }
}

async function saveSettings() {
    const settings = {
        api_keys: {
            gemini: document.getElementById('geminiKey').value,
            replicate: document.getElementById('replicateKey').value,
            inworld: document.getElementById('inworldKey').value,
            pexels: document.getElementById('pexelsKey').value
        },
        formulas: {
            title: document.getElementById('titleFormula').value,
            script: document.getElementById('scriptFormula').value,
            image: document.getElementById('imageFormula').value
        }
    };

    try {
        // Save API keys
        await fetch('/api/settings/api-keys', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(settings.api_keys)
        });

        // Save formulas
        await fetch('/api/settings/formulas', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(settings.formulas)
        });

        alert('✅ Settings saved successfully!');
        closeSettings();
    } catch (error) {
        alert('❌ Error saving settings: ' + error.message);
    }
}

function togglePassword(inputId) {
    const input = document.getElementById(inputId);
    input.type = input.type === 'password' ? 'text' : 'password';
}

// =============================================================================
// GENERATOR - TITLE
// =============================================================================
function toggleTitleMode() {
    const mode = document.querySelector('input[name="titleMode"]:checked').value;
    document.getElementById('titleManualSection').style.display = mode === 'manual' ? 'block' : 'none';
    document.getElementById('titleAutoSection').style.display = mode === 'auto' ? 'block' : 'none';
}

async function generateTitle() {
    const topic = document.getElementById('titleTopic').value;
    if (!topic) {
        alert('Please enter a topic');
        return;
    }

    const resultBox = document.getElementById('titleResult');
    resultBox.style.display = 'block';
    resultBox.innerHTML = '<p>🤖 Generating title...</p>';

    try {
        const response = await fetch('/api/generate-title', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({topic})
        });

        const data = await response.json();

        if (data.success) {
            appState.generatedTitle = data.title;
            document.getElementById('titleInput').value = data.title;
            resultBox.innerHTML = `<p>✅ Generated: <strong>${data.title}</strong></p>`;
        } else {
            resultBox.innerHTML = `<p>❌ Error: ${data.error}</p>`;
        }
    } catch (error) {
        resultBox.innerHTML = `<p>❌ Error: ${error.message}</p>`;
    }
}

// =============================================================================
// GENERATOR - SCRIPT
// =============================================================================
function toggleScriptMode() {
    const mode = document.querySelector('input[name="scriptMode"]:checked').value;
    document.getElementById('scriptManualSection').style.display = mode === 'manual' ? 'block' : 'none';
    document.getElementById('scriptAutoSection').style.display = mode === 'auto' ? 'block' : 'none';
}

async function generateScript() {
    const title = document.getElementById('titleInput').value;
    if (!title) {
        alert('Please enter a title first');
        return;
    }

    const length = document.getElementById('scriptLength').value;
    const resultBox = document.getElementById('scriptResult');
    const statsBox = document.getElementById('scriptStats');

    resultBox.style.display = 'block';
    statsBox.style.display = 'none';
    resultBox.innerHTML = '<p>🤖 Generating script with Gemini 2.5... This may take 1-2 minutes...</p>';

    try {
        const response = await fetch('/api/generate-script', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                title,
                target_length: parseInt(length)
            })
        });

        const data = await response.json();

        if (data.success) {
            appState.generatedScript = data.script;
            appState.scriptPath = data.script_path;
            document.getElementById('scriptInput').value = data.script;

            resultBox.innerHTML = '<p>✅ Script generated successfully!</p>';
            statsBox.style.display = 'block';
            statsBox.innerHTML = `
                <p><strong>Quality:</strong> ${data.stats.quality}</p>
                <p><strong>Characters:</strong> ${data.stats.chars.toLocaleString()}</p>
                <p><strong>Words:</strong> ${data.stats.words.toLocaleString()}</p>
                <p><strong>Est. Duration:</strong> ${data.stats.estimated_duration}</p>
                <p><strong>Issues:</strong> ${data.stats.issues}</p>
            `;
        } else {
            resultBox.innerHTML = `<p>❌ Error: ${data.error}</p>`;
        }
    } catch (error) {
        resultBox.innerHTML = `<p>❌ Error: ${error.message}</p>`;
    }
}

// =============================================================================
// GENERATOR - MEDIA
// =============================================================================
function toggleMediaSection(type) {
    if (type === 'ai') {
        const checked = document.getElementById('useAiImages').checked;
        document.getElementById('aiImagesSection').style.display = checked ? 'block' : 'none';
    } else if (type === 'manual') {
        const checked = document.getElementById('useManualMedia').checked;
        document.getElementById('manualMediaSection').style.display = checked ? 'block' : 'none';
    } else if (type === 'stock') {
        const checked = document.getElementById('useStockFootage').checked;
        document.getElementById('stockFootageSection').style.display = checked ? 'block' : 'none';
    }
}

async function generateAiImages() {
    const script = document.getElementById('scriptInput').value;
    if (!script) {
        alert('Please generate or enter a script first');
        return;
    }

    const count = parseInt(document.getElementById('aiImageCount').value);
    const progressBox = document.getElementById('aiImageProgress');
    const previewBox = document.getElementById('aiImagePreview');

    progressBox.style.display = 'block';
    progressBox.innerHTML = `<p>🎨 Generating ${count} AI images... This will take ~${count * 12} seconds (11s per image)</p>`;
    previewBox.innerHTML = '';

    try {
        const response = await fetch('/api/generate-images', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                script_path: appState.scriptPath || 'temp_script.txt',
                script_text: script,
                count: count
            })
        });

        const data = await response.json();

        if (data.success) {
            appState.imageFiles = data.images;
            progressBox.innerHTML = `<p>✅ Generated ${data.images.length} images successfully!</p>`;

            // Display images
            data.images.forEach(img => {
                const imgEl = document.createElement('img');
                imgEl.src = `/api/preview-image/${img.filename}`;
                imgEl.alt = img.prompt;
                imgEl.title = img.prompt;
                previewBox.appendChild(imgEl);
            });
        } else {
            progressBox.innerHTML = `<p>❌ Error: ${data.error}</p>`;
        }
    } catch (error) {
        progressBox.innerHTML = `<p>❌ Error: ${error.message}</p>`;
    }
}

async function extractKeywords() {
    const script = document.getElementById('scriptInput').value;
    if (!script) {
        alert('Please generate or enter a script first');
        return;
    }

    try {
        const response = await fetch('/api/extract-keywords', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({script_text: script})
        });

        const data = await response.json();

        if (data.success) {
            document.getElementById('stockKeywords').value = data.keywords.join(', ');
        }
    } catch (error) {
        alert('Error extracting keywords: ' + error.message);
    }
}

async function fetchStockFootage() {
    const keywords = document.getElementById('stockKeywords').value;
    if (!keywords) {
        alert('Please enter keywords or extract them from script');
        return;
    }

    const type = document.querySelector('input[name="stockType"]:checked').value;
    const count = parseInt(document.getElementById('stockCount').value);
    const progressBox = document.getElementById('stockProgress');
    const previewBox = document.getElementById('stockPreview');

    progressBox.style.display = 'block';
    progressBox.innerHTML = `<p>📹 Fetching ${count} stock ${type} from Pexels...</p>`;
    previewBox.innerHTML = '';

    try {
        const response = await fetch('/api/fetch-stock', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                keywords: keywords,
                media_type: type,
                count: count
            })
        });

        const data = await response.json();

        if (data.success) {
            progressBox.innerHTML = `<p>✅ Downloaded ${data.items.length} ${type} successfully!</p>`;

            // Display previews
            data.items.forEach(item => {
                if (type === 'photos') {
                    const imgEl = document.createElement('img');
                    imgEl.src = `/api/preview-image/${item.filename}`;
                    previewBox.appendChild(imgEl);
                } else {
                    const videoEl = document.createElement('video');
                    videoEl.src = `/api/preview-video/${item.filename}`;
                    videoEl.controls = true;
                    videoEl.style.width = '100%';
                    videoEl.style.maxHeight = '200px';
                    previewBox.appendChild(videoEl);
                }
            });
        } else {
            progressBox.innerHTML = `<p>❌ Error: ${data.error}</p>`;
        }
    } catch (error) {
        progressBox.innerHTML = `<p>❌ Error: ${error.message}</p>`;
    }
}

// Handle media uploads
document.addEventListener('DOMContentLoaded', () => {
    const mediaUpload = document.getElementById('mediaUpload');
    if (mediaUpload) {
        mediaUpload.addEventListener('change', async (e) => {
            const files = e.target.files;
            if (files.length === 0) return;

            const formData = new FormData();
            for (let file of files) {
                formData.append('files', file);
            }
            formData.append('type', 'media');

            try {
                const response = await fetch('/api/upload-media', {
                    method: 'POST',
                    body: formData
                });

                const data = await response.json();
                if (data.success) {
                    alert(`✅ Uploaded ${data.files.length} files`);
                    // Display preview
                    const previewBox = document.getElementById('manualMediaPreview');
                    previewBox.innerHTML = '';
                    data.files.forEach(file => {
                        const img = document.createElement('img');
                        img.src = `/api/preview-image/${file}`;
                        previewBox.appendChild(img);
                    });
                }
            } catch (error) {
                alert('Error uploading files: ' + error.message);
            }
        });
    }
});

// =============================================================================
// GENERATOR - VOICE
// =============================================================================
function toggleVoiceMode() {
    const mode = document.querySelector('input[name="voiceMode"]:checked').value;
    document.getElementById('voiceManualSection').style.display = mode === 'manual' ? 'block' : 'none';
    document.getElementById('voiceAutoSection').style.display = mode === 'auto' ? 'block' : 'none';
}

// Update speaking rate display
document.addEventListener('DOMContentLoaded', () => {
    const rateSlider = document.getElementById('speakingRate');
    const rateDisplay = document.getElementById('speakingRateValue');
    if (rateSlider && rateDisplay) {
        rateSlider.addEventListener('input', (e) => {
            rateDisplay.textContent = e.target.value + 'x';
        });
    }
});

async function generateVoice() {
    const script = document.getElementById('scriptInput').value;
    if (!script) {
        alert('Please generate or enter a script first');
        return;
    }

    const voice = document.getElementById('voiceSelect').value;
    const rate = parseFloat(document.getElementById('speakingRate').value);
    const progressBox = document.getElementById('voiceProgress');

    progressBox.style.display = 'block';
    progressBox.innerHTML = '<p>🎙️ Generating AI voice... This may take a few minutes...</p>';

    try {
        const response = await fetch('/api/generate-voice', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                script_path: appState.scriptPath || 'temp_script.txt',
                voice_id: voice,
                speaking_rate: rate
            })
        });

        const data = await response.json();

        if (data.success) {
            appState.audioFiles = [data.audio_path];
            progressBox.innerHTML = `<p>✅ Voice generated: ${data.audio_path}</p>`;
        } else {
            progressBox.innerHTML = `<p>❌ Error: ${data.error}</p>`;
        }
    } catch (error) {
        progressBox.innerHTML = `<p>❌ Error: ${error.message}</p>`;
    }
}

// Handle audio uploads
document.addEventListener('DOMContentLoaded', () => {
    const audioUpload = document.getElementById('audioUpload');
    if (audioUpload) {
        audioUpload.addEventListener('change', async (e) => {
            const files = e.target.files;
            if (files.length === 0) return;

            const formData = new FormData();
            for (let file of files) {
                formData.append('files', file);
            }
            formData.append('type', 'audio');

            try {
                const response = await fetch('/api/upload-media', {
                    method: 'POST',
                    body: formData
                });

                const data = await response.json();
                if (data.success) {
                    appState.audioFiles = data.files;
                    const list = document.getElementById('audioList');
                    list.innerHTML = `<p>✅ Uploaded ${data.files.length} audio files</p>`;
                }
            } catch (error) {
                alert('Error uploading audio: ' + error.message);
            }
        });
    }
});

// =============================================================================
// GENERATOR - PROCESS VIDEO
// =============================================================================
async function processVideo() {
    const title = document.getElementById('titleInput').value;
    const script = document.getElementById('scriptInput').value;
    const quality = document.querySelector('input[name="quality"]:checked').value;

    if (!title || !script) {
        alert('Please provide at least a title and script');
        return;
    }

    const progressContainer = document.getElementById('videoProgress');
    const progressFill = document.getElementById('progressFill');
    const progressText = document.getElementById('progressText');
    const resultContainer = document.getElementById('videoResult');

    progressContainer.style.display = 'block';
    resultContainer.style.display = 'none';
    progressFill.style.width = '10%';
    progressText.textContent = 'Initializing video processing...';

    try {
        // Simulate progress (you can implement real progress tracking)
        progressFill.style.width = '30%';
        progressText.textContent = 'Processing media files...';

        const response = await fetch('/api/process-final-video', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                title: title,
                script_path: appState.scriptPath,
                images: appState.imageFiles,
                audio_files: appState.audioFiles,
                quality: quality
            })
        });

        progressFill.style.width = '60%';
        progressText.textContent = 'Assembling final video...';

        const data = await response.json();

        progressFill.style.width = '100%';
        progressText.textContent = 'Complete!';

        if (data.success) {
            progressContainer.style.display = 'none';
            resultContainer.style.display = 'block';

            const videoInfo = document.getElementById('videoInfo');
            videoInfo.innerHTML = `
                <p><strong>Output:</strong> ${data.output_path}</p>
                <p><strong>Size:</strong> ${data.stats.size || 'N/A'}</p>
                <p><strong>Duration:</strong> ${data.stats.duration || 'N/A'}</p>
            `;

            const downloadBtn = document.getElementById('downloadBtn');
            downloadBtn.onclick = () => {
                window.location.href = `/api/download/${data.output_path.split('/').pop()}`;
            };
        } else {
            progressText.textContent = `Error: ${data.error}`;
        }
    } catch (error) {
        progressText.textContent = `Error: ${error.message}`;
    }
}

// =============================================================================
// EDITOR - VIDEO UPLOAD
// =============================================================================
document.addEventListener('DOMContentLoaded', () => {
    const editorVideoInput = document.getElementById('editorVideoInput');
    if (editorVideoInput) {
        editorVideoInput.addEventListener('change', (e) => {
            const file = e.target.files[0];
            if (!file) return;

            // Use local file URL - no need to upload to server first
            const fileUrl = URL.createObjectURL(file);
            loadEditorVideo(fileUrl, file.name);
        });
    }
});

function loadEditorVideo(fileUrl, fileName) {
    try {
        const preview = document.getElementById('editorVideoPreview');
        preview.src = fileUrl;
        preview.load();

        appState.editorVideo = {
            path: fileUrl,
            fileName: fileName || 'video.mp4',
            duration: 0
        };

        // Show sections
        document.getElementById('editorPreviewSection').style.display = 'block';
        document.getElementById('editorTimelineSection').style.display = 'block';
        document.getElementById('editorToolsSection').style.display = 'block';
        document.getElementById('editorExportSection').style.display = 'block';

        // Wait for metadata
        preview.addEventListener('loadedmetadata', () => {
            appState.editorVideo.duration = preview.duration;

            // Create initial clip
            appState.editorClips = [{
                id: 'clip-0',
                videoPath: fileUrl,
                start: 0,
                end: preview.duration,
                duration: preview.duration
            }];

            updateEditorTimeline();
        });
    } catch (error) {
        alert('Error loading video: ' + error.message);
        console.error('Editor load error:', error);
    }
}

// =============================================================================
// EDITOR - PLAYBACK CONTROLS
// =============================================================================
function editorPlayPause() {
    const video = document.getElementById('editorVideoPreview');
    if (video.paused) {
        video.play();
        document.getElementById('editorPlayBtn').textContent = '⏸️';
    } else {
        video.pause();
        document.getElementById('editorPlayBtn').textContent = '▶️';
    }
}

function editorStop() {
    const video = document.getElementById('editorVideoPreview');
    video.pause();
    video.currentTime = 0;
    document.getElementById('editorPlayBtn').textContent = '▶️';
}

function editorMute() {
    const video = document.getElementById('editorVideoPreview');
    video.muted = !video.muted;
    document.getElementById('editorMuteBtn').textContent = video.muted ? '🔇' : '🔊';
}

// Update time display
document.addEventListener('DOMContentLoaded', () => {
    const video = document.getElementById('editorVideoPreview');
    if (video) {
        video.addEventListener('timeupdate', () => {
            const current = formatTime(video.currentTime);
            const total = formatTime(video.duration);
            document.getElementById('editorTimeDisplay').textContent = `${current} / ${total}`;

            const progress = (video.currentTime / video.duration) * 100;
            document.getElementById('editorSeekFill').style.width = progress + '%';
        });
    }
});

function formatTime(seconds) {
    if (isNaN(seconds)) return '0:00';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
}

// =============================================================================
// EDITOR - TIMELINE
// =============================================================================
function updateEditorTimeline() {
    const track = document.getElementById('editorTimelineTrack');
    track.innerHTML = '';

    appState.editorClips.forEach((clip, index) => {
        const clipEl = document.createElement('div');
        clipEl.className = 'clip';
        clipEl.innerHTML = `
            <div class="clip-info">Clip ${index + 1}</div>
            <div class="clip-duration">${formatTime(clip.duration)}</div>
        `;
        clipEl.onclick = () => selectClip(index);
        track.appendChild(clipEl);
    });

    // Update stats
    document.getElementById('editorClipCount').textContent = `${appState.editorClips.length} clips`;
    const totalDuration = appState.editorClips.reduce((sum, clip) => sum + clip.duration, 0);
    document.getElementById('editorTotalDuration').textContent = `Total: ${formatTime(totalDuration)}`;
}

function selectClip(index) {
    appState.selectedClip = index;
    document.querySelectorAll('.clip').forEach((el, i) => {
        el.classList.toggle('selected', i === index);
    });
}

// =============================================================================
// EDITOR - EDIT OPERATIONS
// =============================================================================
function editorSplit() {
    if (appState.selectedClip === null) {
        alert('Please select a clip first');
        return;
    }

    const video = document.getElementById('editorVideoPreview');
    const splitTime = video.currentTime;
    const clip = appState.editorClips[appState.selectedClip];

    if (splitTime <= clip.start || splitTime >= clip.end) {
        alert('Playhead must be within the selected clip');
        return;
    }

    // Create two new clips
    const clip1 = {...clip, end: splitTime, duration: splitTime - clip.start};
    const clip2 = {...clip, id: `clip-${Date.now()}`, start: splitTime, duration: clip.end - splitTime};

    // Replace original clip
    appState.editorClips.splice(appState.selectedClip, 1, clip1, clip2);
    updateEditorTimeline();
}

function editorDelete() {
    if (appState.selectedClip === null) {
        alert('Please select a clip first');
        return;
    }

    if (confirm('Delete this clip?')) {
        appState.editorClips.splice(appState.selectedClip, 1);
        appState.selectedClip = null;
        updateEditorTimeline();
    }
}

function editorMoveLeft() {
    if (appState.selectedClip === null || appState.selectedClip === 0) return;

    const temp = appState.editorClips[appState.selectedClip];
    appState.editorClips[appState.selectedClip] = appState.editorClips[appState.selectedClip - 1];
    appState.editorClips[appState.selectedClip - 1] = temp;
    appState.selectedClip--;
    updateEditorTimeline();
}

function editorMoveRight() {
    if (appState.selectedClip === null || appState.selectedClip === appState.editorClips.length - 1) return;

    const temp = appState.editorClips[appState.selectedClip];
    appState.editorClips[appState.selectedClip] = appState.editorClips[appState.selectedClip + 1];
    appState.editorClips[appState.selectedClip + 1] = temp;
    appState.selectedClip++;
    updateEditorTimeline();
}

// =============================================================================
// EDITOR - OVERLAY
// =============================================================================
function editorShowOverlay() {
    document.getElementById('editorOverlaySection').style.display = 'block';
}

function editorCancelOverlay() {
    document.getElementById('editorOverlaySection').style.display = 'none';
}

function editorConfirmOverlay() {
    if (appState.selectedClip === null) {
        alert('Please select a clip first');
        return;
    }

    const overlay = {
        text: document.getElementById('overlayText').value,
        x: parseInt(document.getElementById('overlayX').value),
        y: parseInt(document.getElementById('overlayY').value),
        size: parseInt(document.getElementById('overlaySize').value),
        color: document.getElementById('overlayColor').value,
        start: parseFloat(document.getElementById('overlayStart').value),
        duration: parseFloat(document.getElementById('overlayDuration').value)
    };

    appState.editorClips[appState.selectedClip].overlay = overlay;
    editorCancelOverlay();
    alert('✅ Overlay added to clip');
}

// =============================================================================
// EDITOR - EXPORT
// =============================================================================
async function editorExport() {
    if (appState.editorClips.length === 0) {
        alert('No clips to export');
        return;
    }

    const quality = document.querySelector('input[name="editorQuality"]:checked').value;
    const progressBox = document.getElementById('editorExportProgress');

    progressBox.style.display = 'block';
    progressBox.innerHTML = '<p>🎬 Exporting video...</p>';

    try {
        const response = await fetch('/api/editor/process', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                clips: appState.editorClips,
                quality: quality
            })
        });

        const data = await response.json();

        if (data.success) {
            progressBox.innerHTML = `
                <p>✅ Export complete!</p>
                <button onclick="window.location.href='/api/download/${data.output_path.split('/').pop()}'" class="btn-success">
                    📥 Download Video
                </button>
            `;
        } else {
            progressBox.innerHTML = `<p>❌ Error: ${data.error}</p>`;
        }
    } catch (error) {
        progressBox.innerHTML = `<p>❌ Error: ${error.message}</p>`;
    }
}

// =============================================================================
// OUTPUT FILES
// =============================================================================
async function refreshOutputFiles() {
    const container = document.getElementById('outputFileList');
    container.innerHTML = '<p class="loading">Loading files...</p>';

    try {
        const response = await fetch('/api/output-files');
        const data = await response.json();

        if (data.success && data.files.length > 0) {
            container.innerHTML = '';
            data.files.forEach(file => {
                const fileEl = document.createElement('div');
                fileEl.className = 'file-item';
                fileEl.innerHTML = `
                    <p><strong>${file.name}</strong></p>
                    <p>Size: ${file.size} | Modified: ${file.modified}</p>
                    <button onclick="window.location.href='/api/download/${file.name}'" class="btn-primary">
                        📥 Download
                    </button>
                `;
                container.appendChild(fileEl);
            });
        } else {
            container.innerHTML = '<p>No output files found</p>';
        }
    } catch (error) {
        container.innerHTML = `<p>Error loading files: ${error.message}</p>`;
    }
}

// =============================================================================
// INITIALIZATION
// =============================================================================
document.addEventListener('DOMContentLoaded', () => {
    // Setup settings button
    document.getElementById('settingsBtn').onclick = openSettings;

    // Close modal when clicking outside
    document.getElementById('settingsModal').onclick = (e) => {
        if (e.target.id === 'settingsModal') {
            closeSettings();
        }
    };

    // Load initial tab
    showTab('dashboard');

    console.log('🎬 AI Video Studio initialized');
});
