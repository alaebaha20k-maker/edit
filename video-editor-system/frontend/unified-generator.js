// Global state
let niches = [];
let styles = [];
let generatedScript = '';
let generatedImages = [];
let uploadedImages = [];
let uploadedVideos = [];
let mixedMedia = [];
let uploadedAudio = [];

// Initialize on page load
window.addEventListener('DOMContentLoaded', async () => {
    await loadAPIStatus();
    await loadNiches();
    await loadStyles();
});

// =============================================================================
// API CONFIGURATION
// =============================================================================

async function loadAPIStatus() {
    try {
        const response = await fetch('/api/config');
        const data = await response.json();

        const indicator = document.getElementById('api-status-indicator');
        const text = document.getElementById('api-status-text');

        if (data.gemini_configured && data.replicate_configured) {
            indicator.className = 'status-indicator status-ok';
            text.textContent = 'API Keys Configured ✓';
        } else {
            indicator.className = 'status-indicator status-missing';
            text.textContent = 'API Keys Not Configured';
        }
    } catch (error) {
        console.error('Error loading API status:', error);
    }
}

async function saveAPIConfig() {
    const geminiKey = document.getElementById('gemini-key').value.trim();
    const replicateToken = document.getElementById('replicate-token').value.trim();

    if (!geminiKey && !replicateToken) {
        showAlert('generation-alerts', 'Please enter at least one API key', 'error');
        return;
    }

    try {
        const response = await fetch('/api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                gemini_api_key: geminiKey,
                replicate_api_token: replicateToken
            })
        });

        const data = await response.json();

        if (data.success) {
            showAlert('generation-alerts', '✅ API configuration saved successfully!', 'success');
            document.getElementById('gemini-key').value = '';
            document.getElementById('replicate-token').value = '';
            await loadAPIStatus();
        } else {
            showAlert('generation-alerts', '❌ Error: ' + data.error, 'error');
        }
    } catch (error) {
        showAlert('generation-alerts', '❌ Error: ' + error.message, 'error');
    }
}

// =============================================================================
// NICHE MANAGEMENT
// =============================================================================

async function loadNiches() {
    try {
        const response = await fetch('/api/niches');
        const data = await response.json();
        niches = data.niches || [];

        displayNiches();
        updateNicheDropdown();
    } catch (error) {
        console.error('Error loading niches:', error);
    }
}

function displayNiches() {
    const list = document.getElementById('niches-list');

    if (niches.length === 0) {
        list.innerHTML = '<p style="color: #666;">No niches yet. Add your first niche above.</p>';
        return;
    }

    list.innerHTML = niches.map(niche => `
        <div class="item">
            <div>
                <strong>${niche.name}</strong> (${niche.language})
            </div>
            <div class="item-actions">
                <button class="btn btn-danger" onclick="deleteNiche('${niche.id}')">Delete</button>
            </div>
        </div>
    `).join('');
}

function updateNicheDropdown() {
    const select = document.getElementById('gen-niche-select');
    select.innerHTML = '<option value="">-- Select Niche --</option>' +
        niches.map(n => `<option value="${n.id}">${n.name} (${n.language})</option>`).join('');
}

function toggleAddNiche() {
    const form = document.getElementById('add-niche-form');
    form.classList.toggle('active');
}

async function saveNiche() {
    const name = document.getElementById('new-niche-name').value.trim();
    const language = document.getElementById('new-niche-language').value.trim();
    const guidelines = document.getElementById('new-niche-guidelines').value.trim();

    if (!name || !language || !guidelines) {
        alert('Please fill all fields');
        return;
    }

    try {
        const response = await fetch('/api/niches', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: name,
                language: language,
                writing_guidelines: guidelines
            })
        });

        const data = await response.json();

        if (data.success) {
            showAlert('generation-alerts', '✅ Niche saved successfully!', 'success');
            document.getElementById('new-niche-name').value = '';
            document.getElementById('new-niche-language').value = '';
            document.getElementById('new-niche-guidelines').value = '';
            toggleAddNiche();
            await loadNiches();
        } else {
            alert('Error: ' + data.error);
        }
    } catch (error) {
        alert('Error: ' + error.message);
    }
}

async function deleteNiche(nicheId) {
    if (!confirm('Delete this niche?')) return;

    try {
        const response = await fetch(`/api/niches/${nicheId}`, {
            method: 'DELETE'
        });

        if (response.ok) {
            showAlert('generation-alerts', '✅ Niche deleted', 'success');
            await loadNiches();
        }
    } catch (error) {
        alert('Error: ' + error.message);
    }
}

// =============================================================================
// IMAGE STYLE MANAGEMENT
// =============================================================================

async function loadStyles() {
    try {
        const response = await fetch('/api/image-styles');
        const data = await response.json();
        styles = data.styles || [];

        displayStyles();
        updateStyleDropdown();
    } catch (error) {
        console.error('Error loading styles:', error);
    }
}

function displayStyles() {
    const list = document.getElementById('styles-list');

    if (styles.length === 0) {
        list.innerHTML = '<p style="color: #666;">No styles yet. Add your first style above.</p>';
        return;
    }

    list.innerHTML = styles.map(style => `
        <div class="item">
            <div>
                <strong>${style.name}</strong> (${style.prompts.length} prompts)
            </div>
            <div class="item-actions">
                <button class="btn btn-danger" onclick="deleteStyle('${style.id}')">Delete</button>
            </div>
        </div>
    `).join('');
}

function updateStyleDropdown() {
    const select = document.getElementById('gen-style-select');
    select.innerHTML = '<option value="">-- Select Style --</option>' +
        styles.map(s => `<option value="${s.id}">${s.name}</option>`).join('');
}

function toggleAddStyle() {
    const form = document.getElementById('add-style-form');
    form.classList.toggle('active');
}

async function saveStyle() {
    const name = document.getElementById('new-style-name').value.trim();
    const prompts = [
        document.getElementById('new-style-prompt1').value.trim(),
        document.getElementById('new-style-prompt2').value.trim(),
        document.getElementById('new-style-prompt3').value.trim(),
        document.getElementById('new-style-prompt4').value.trim(),
        document.getElementById('new-style-prompt5').value.trim(),
        document.getElementById('new-style-prompt6').value.trim()
    ];

    if (!name || prompts.some(p => !p)) {
        alert('Please fill all fields');
        return;
    }

    try {
        const response = await fetch('/api/image-styles', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: name,
                prompts: prompts
            })
        });

        const data = await response.json();

        if (data.success) {
            showAlert('generation-alerts', '✅ Image style saved successfully!', 'success');
            for (let i = 1; i <= 6; i++) {
                document.getElementById(`new-style-prompt${i}`).value = '';
            }
            document.getElementById('new-style-name').value = '';
            toggleAddStyle();
            await loadStyles();
        } else {
            alert('Error: ' + data.error);
        }
    } catch (error) {
        alert('Error: ' + error.message);
    }
}

async function deleteStyle(styleId) {
    if (!confirm('Delete this style?')) return;

    try {
        const response = await fetch(`/api/image-styles/${styleId}`, {
            method: 'DELETE'
        });

        if (response.ok) {
            showAlert('generation-alerts', '✅ Style deleted', 'success');
            await loadStyles();
        }
    } catch (error) {
        alert('Error: ' + error.message);
    }
}

// =============================================================================
// MEDIA OPTION SELECTION
// =============================================================================

function selectMediaOption(option) {
    // Update radio button
    document.querySelectorAll('.radio-option').forEach(el => el.classList.remove('active'));
    document.querySelector(`#opt-${option}`).parentElement.classList.add('active');
    document.querySelector(`#opt-${option}`).checked = true;

    // Show/hide relevant sections
    document.getElementById('ai-images-section').classList.add('hidden');
    document.getElementById('manual-images-section').classList.add('hidden');
    document.getElementById('manual-videos-section').classList.add('hidden');
    document.getElementById('mixed-section').classList.add('hidden');

    if (option === 'ai-images') {
        document.getElementById('ai-images-section').classList.remove('hidden');
    } else if (option === 'manual-images') {
        document.getElementById('manual-images-section').classList.remove('hidden');
    } else if (option === 'manual-videos') {
        document.getElementById('manual-videos-section').classList.remove('hidden');
    } else if (option === 'mixed') {
        document.getElementById('mixed-section').classList.remove('hidden');
    }
}

// =============================================================================
// SCRIPT GENERATION
// =============================================================================

async function generateScript() {
    const nicheId = document.getElementById('gen-niche-select').value;
    const title = document.getElementById('gen-title').value.trim();
    const statusDiv = document.getElementById('script-status');

    // Get selected script length (30K, 60K, or 100K)
    const lengthRadio = document.querySelector('input[name="script-length"]:checked');
    const length = lengthRadio ? parseInt(lengthRadio.value) : 60000; // Default 60K

    if (!nicheId) {
        statusDiv.innerHTML = '<div class="alert alert-error">Please select a niche</div>';
        return;
    }

    if (!title) {
        statusDiv.innerHTML = '<div class="alert alert-error">Please enter a video title</div>';
        return;
    }

    const lengthLabel = length === 30000 ? 'Medium (30K)' : length === 100000 ? 'Epic (100K)' : 'Full (60K)';
    statusDiv.innerHTML = `<div class="alert alert-info">🤖 Generating ${lengthLabel} script with Gemini AI... This may take 1-2 minutes...</div>`;

    try {
        const response = await fetch('/api/generate-script', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title, niche_id: nicheId, length })
        });

        const data = await response.json();

        if (data.success) {
            generatedScript = data.script;
            const words = Math.round(data.length / 4.5); // Approximate word count

            // Build quality details
            let qualityDetails = '';

            // Show issues if any
            if (data.issues && data.issues.length > 0) {
                qualityDetails += '<div style="margin-top: 10px; padding: 10px; background: #fff3cd; border-left: 4px solid #ffc107; font-size: 13px;">';
                qualityDetails += '<strong>⚠️ Issues Fixed:</strong><br>';
                data.issues.forEach(issue => {
                    qualityDetails += `• ${issue}<br>`;
                });
                qualityDetails += '</div>';
            }

            // Show suggestions if any
            if (data.suggestions && data.suggestions.length > 0) {
                qualityDetails += '<div style="margin-top: 10px; padding: 10px; background: #d1ecf1; border-left: 4px solid #17a2b8; font-size: 13px;">';
                qualityDetails += '<strong>💡 Suggestions for Next Time:</strong><br>';
                data.suggestions.forEach(suggestion => {
                    qualityDetails += `${suggestion}<br>`;
                });
                qualityDetails += '</div>';
            }

            // Create success message with download button
            statusDiv.innerHTML = `
                <div class="alert alert-success">
                    ✅ Script generated! ${data.length.toLocaleString()} characters (~${words.toLocaleString()} words)<br>
                    <strong style="color: ${data.quality === 'HIGH' ? '#28a745' : data.quality === 'MEDIUM' ? '#ffc107' : '#dc3545'};">
                        Quality: ${data.quality || 'GOOD'}
                    </strong> | Narrative: ${data.approach || 'N/A'}<br>
                    <a href="/api/download/${data.script_filename}"
                       class="btn btn-primary"
                       style="margin-top: 10px; display: inline-block; text-decoration: none;"
                       download="${data.script_filename}">
                        📥 Download Script
                    </a>
                    ${qualityDetails}
                </div>
            `;
        } else {
            statusDiv.innerHTML = `<div class="alert alert-error">❌ Error: ${data.error}</div>`;
        }
    } catch (error) {
        statusDiv.innerHTML = `<div class="alert alert-error">❌ Error: ${error.message}</div>`;
    }
}

// =============================================================================
// IMAGE GENERATION
// =============================================================================

async function generateImages() {
    const styleId = document.getElementById('gen-style-select').value;
    const title = document.getElementById('gen-title').value.trim();
    const statusDiv = document.getElementById('images-status');

    if (!styleId) {
        statusDiv.innerHTML = '<div class="alert alert-error">Please select an image style</div>';
        return;
    }

    if (!title) {
        statusDiv.innerHTML = '<div class="alert alert-error">Please enter a video title</div>';
        return;
    }

    if (!generatedScript) {
        statusDiv.innerHTML = '<div class="alert alert-error">Please generate script first</div>';
        return;
    }

    statusDiv.innerHTML = '<div class="alert alert-info">🎨 Generating 6 images with Replicate...<br>⏱️ Due to rate limits, this will take ~60 seconds<br>Please be patient while we generate your images!</div>';

    try {
        const response = await fetch('/api/generate-images', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                title,
                script: generatedScript,
                style_id: styleId
            })
        });

        const data = await response.json();

        if (data.success) {
            generatedImages = data.image_urls;
            statusDiv.innerHTML = `<div class="alert alert-success">✅ Generated ${data.count} images!</div>`;
        } else {
            statusDiv.innerHTML = `<div class="alert alert-error">❌ Error: ${data.error}</div>`;
        }
    } catch (error) {
        statusDiv.innerHTML = `<div class="alert alert-error">❌ Error: ${error.message}</div>`;
    }
}

// =============================================================================
// MEDIA UPLOADS
// =============================================================================

async function handleImageUpload(event) {
    const files = Array.from(event.target.files);
    for (const file of files) {
        await uploadFile(file, 'image', 'uploaded-images-list', uploadedImages);
    }
}

async function handleVideoUpload(event) {
    const files = Array.from(event.target.files);
    for (const file of files) {
        await uploadFile(file, 'video', 'uploaded-videos-list', uploadedVideos);
    }
}

async function handleMixedImageUpload(event) {
    const files = Array.from(event.target.files);
    for (const file of files) {
        await uploadFile(file, 'image', 'mixed-media-list', mixedMedia);
    }
}

async function handleMixedVideoUpload(event) {
    const files = Array.from(event.target.files);
    for (const file of files) {
        await uploadFile(file, 'video', 'mixed-media-list', mixedMedia);
    }
}

async function uploadFile(file, type, listId, targetArray) {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('type', type);

    try {
        const response = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (data.success) {
            targetArray.push({
                file_id: data.file_id,
                filename: data.filename,
                type: type,
                rank: targetArray.length + 1
            });

            displayMediaList(listId, targetArray);
        } else {
            alert('Upload failed: ' + data.error);
        }
    } catch (error) {
        alert('Upload error: ' + error.message);
    }
}

function displayMediaList(listId, mediaArray) {
    const list = document.getElementById(listId);

    if (mediaArray.length === 0) {
        list.innerHTML = '';
        return;
    }

    list.innerHTML = mediaArray.map((item, index) => `
        <div class="media-item">
            <div class="media-info">
                <strong>${item.filename}</strong> (${item.type})
            </div>
            <input type="number" class="media-rank" value="${item.rank}"
                   onchange="updateRank('${listId}', ${index}, this.value)" min="1">
            <button class="btn btn-danger" onclick="removeMedia('${listId}', ${index})">Remove</button>
        </div>
    `).join('');
}

function updateRank(listId, index, newRank) {
    const targetArray = getArrayByListId(listId);
    targetArray[index].rank = parseInt(newRank);
}

function removeMedia(listId, index) {
    const targetArray = getArrayByListId(listId);
    targetArray.splice(index, 1);
    displayMediaList(listId, targetArray);
}

function getArrayByListId(listId) {
    if (listId === 'uploaded-images-list') return uploadedImages;
    if (listId === 'uploaded-videos-list') return uploadedVideos;
    if (listId === 'mixed-media-list') return mixedMedia;
    return [];
}

// =============================================================================
// AUDIO UPLOADS
// =============================================================================

async function handleAudioUpload(event) {
    const files = Array.from(event.target.files);
    for (const file of files) {
        await uploadAudio(file);
    }
}

async function uploadAudio(file) {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('type', 'audio');

    try {
        const response = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (data.success) {
            uploadedAudio.push({
                file_id: data.file_id,
                filename: data.filename,
                rank: uploadedAudio.length + 1
            });

            displayAudioList();
        } else {
            alert('Upload failed: ' + data.error);
        }
    } catch (error) {
        alert('Upload error: ' + error.message);
    }
}

function displayAudioList() {
    const list = document.getElementById('uploaded-audio-list');

    if (uploadedAudio.length === 0) {
        list.innerHTML = '';
        return;
    }

    list.innerHTML = uploadedAudio.map((item, index) => `
        <div class="media-item">
            <div class="media-info">
                <strong>${item.filename}</strong>
            </div>
            <input type="number" class="media-rank" value="${item.rank}"
                   onchange="updateAudioRank(${index}, this.value)" min="1">
            <button class="btn btn-danger" onclick="removeAudio(${index})">Remove</button>
        </div>
    `).join('');
}

function updateAudioRank(index, newRank) {
    uploadedAudio[index].rank = parseInt(newRank);
}

function removeAudio(index) {
    uploadedAudio.splice(index, 1);
    displayAudioList();
}

// =============================================================================
// VIDEO PROCESSING
// =============================================================================

async function processVideo() {
    // Validation
    const selectedOption = document.querySelector('input[name="media-option"]:checked');

    if (!selectedOption) {
        showAlert('generation-alerts', '❌ Please select a visual media option', 'error');
        return;
    }

    if (uploadedAudio.length === 0) {
        showAlert('generation-alerts', '❌ Please upload at least one audio file', 'error');
        return;
    }

    // Prepare data based on selected option
    const option = selectedOption.value;
    const title = document.getElementById('gen-title').value.trim() || 'AI Generated Video';
    const nicheId = document.getElementById('gen-niche-select').value;
    const styleId = document.getElementById('gen-style-select').value;

    // Sort by rank
    const sortedAudio = uploadedAudio.sort((a, b) => a.rank - b.rank);

    let requestData = {
        title: title,
        audio_files: sortedAudio,
        niche_id: nicheId || null,
        style_id: styleId || null,
        script: generatedScript || null
    };

    if (option === 'ai-images') {
        // AI-generated images
        if (generatedImages.length !== 6) {
            showAlert('generation-alerts', '❌ Please generate 6 images first', 'error');
            return;
        }

        requestData.image_urls = generatedImages;

        // Use AI video processing endpoint
        await processAIVideo(requestData);

    } else {
        // Manual upload (images, videos, or mixed)
        let visualMedia = [];

        if (option === 'manual-images') {
            visualMedia = uploadedImages.sort((a, b) => a.rank - b.rank);
        } else if (option === 'manual-videos') {
            visualMedia = uploadedVideos.sort((a, b) => a.rank - b.rank);
        } else if (option === 'mixed') {
            visualMedia = mixedMedia.sort((a, b) => a.rank - b.rank);
        }

        if (visualMedia.length === 0) {
            showAlert('generation-alerts', '❌ Please upload at least one image or video', 'error');
            return;
        }

        requestData.visual_media = visualMedia;

        // Use manual processing endpoint (existing one)
        await processManualVideo(requestData);
    }
}

async function processAIVideo(data) {
    showProcessing('Processing AI-generated video...');

    try {
        const response = await fetch('/api/process-ai-video', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        const result = await response.json();

        if (result.success) {
            showVideoResult(result.result);
        } else {
            showAlert('generation-alerts', '❌ Error: ' + result.error, 'error');
            hideProcessing();
        }
    } catch (error) {
        showAlert('generation-alerts', '❌ Error: ' + error.message, 'error');
        hideProcessing();
    }
}

async function processManualVideo(data) {
    showProcessing('Processing video...');

    try {
        const response = await fetch('/api/process', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        const result = await response.json();

        if (result.success) {
            showVideoResult(result.result);
        } else {
            showAlert('generation-alerts', '❌ Error: ' + result.error, 'error');
            hideProcessing();
        }
    } catch (error) {
        showAlert('generation-alerts', '❌ Error: ' + error.message, 'error');
        hideProcessing();
    }
}

function showProcessing(message) {
    const statusDiv = document.getElementById('processing-status');
    const messageDiv = document.getElementById('processing-message');

    statusDiv.classList.remove('hidden');
    messageDiv.textContent = message;

    // Simulate progress
    let progress = 0;
    const interval = setInterval(() => {
        progress += 5;
        if (progress >= 95) {
            clearInterval(interval);
        }
        updateProgress(progress);
    }, 1000);
}

function updateProgress(percent) {
    const fill = document.getElementById('progress-fill');
    fill.style.width = percent + '%';
    fill.textContent = percent + '%';
}

function hideProcessing() {
    document.getElementById('processing-status').classList.add('hidden');
    updateProgress(0);
}

function showVideoResult(result) {
    hideProcessing();

    const resultDiv = document.getElementById('video-result');
    resultDiv.innerHTML = `
        <div class="alert alert-success">
            <h3>🎉 Video Generated Successfully!</h3>
            <p><strong>Filename:</strong> ${result.output_filename}</p>
            <p><strong>Duration:</strong> ${result.duration.toFixed(2)}s</p>
            <p><strong>Size:</strong> ${result.file_size}</p>
            <a href="/api/download/${result.output_filename}" class="btn btn-primary" style="display: inline-block; margin-top: 15px;">
                📥 Download Video
            </a>
        </div>
    `;
    resultDiv.classList.remove('hidden');

    // Scroll to result
    resultDiv.scrollIntoView({ behavior: 'smooth' });
}

// =============================================================================
// UTILITY FUNCTIONS
// =============================================================================

function showAlert(containerId, message, type) {
    const container = document.getElementById(containerId);
    const alertClass = type === 'success' ? 'alert-success' : type === 'error' ? 'alert-error' : 'alert-info';
    container.innerHTML = `<div class="alert ${alertClass}">${message}</div>`;

    // Auto-hide after 5 seconds
    setTimeout(() => {
        container.innerHTML = '';
    }, 5000);
}


// =============================================================================
// 📚 DIGITAL CREATE — Ebook Generator
// =============================================================================

let _ebookJobId = null;
let _ebookPollInterval = null;

async function generateEbook() {
    const statusDiv  = document.getElementById('ebook-status');
    const title      = (document.getElementById('ebook-title').value || '').trim();
    const details    = (document.getElementById('ebook-details').value || '').trim();
    const pages      = parseInt(document.getElementById('ebook-pages').value) || 50;

    if (!title) {
        statusDiv.innerHTML = '<div class="alert alert-error">❌ Please enter an ebook title.</div>';
        return;
    }
    if (!details || details.length < 20) {
        statusDiv.innerHTML = '<div class="alert alert-error">❌ Please describe what you want inside the ebook (at least 20 characters).</div>';
        return;
    }

    statusDiv.innerHTML = `
        <div class="alert alert-info" style="padding:16px;">
            <strong>📚 Starting ebook generation…</strong><br>
            <small>Phase 1: Deep research &amp; chapter outline with Gemini 2.5 Pro</small>
            <div style="margin-top:10px;background:#e2e8f0;border-radius:4px;height:8px;overflow:hidden;">
                <div id="ebook-progress-bar" style="height:100%;background:linear-gradient(90deg,#667eea,#764ba2);width:5%;transition:width 2s;border-radius:4px;"></div>
            </div>
            <small id="ebook-progress-text" style="color:#718096;margin-top:4px;display:block;">Sending request…</small>
        </div>`;

    try {
        const res  = await fetch('/api/ebook/generate', {
            method : 'POST',
            headers: { 'Content-Type': 'application/json' },
            body   : JSON.stringify({ title, details, pages }),
        });
        const data = await res.json();
        if (!data.success) {
            statusDiv.innerHTML = `<div class="alert alert-error">❌ ${data.error}</div>`;
            return;
        }
        _ebookJobId = data.job_id;
        _ebookPollInterval = setInterval(_pollEbookStatus, 4000);
        _updateEbookProgress(10, 'Research in progress…');
    } catch (err) {
        statusDiv.innerHTML = `<div class="alert alert-error">❌ Error: ${err.message}</div>`;
    }
}

async function _pollEbookStatus() {
    if (!_ebookJobId) return;
    try {
        const res  = await fetch(`/api/ebook/status/${_ebookJobId}`);
        const data = await res.json();

        if (data.status === 'running') {
            // Animate progress bar forward each poll
            const bar = document.getElementById('ebook-progress-bar');
            if (bar) {
                const cur = parseInt(bar.style.width) || 10;
                const nxt = Math.min(cur + 6, 90);
                bar.style.width = nxt + '%';
            }
            _updateEbookProgress(null, data.progress || 'Writing chapters…');
            return;
        }

        clearInterval(_ebookPollInterval);
        _ebookPollInterval = null;

        if (data.status === 'done') {
            const r = data.result || {};
            document.getElementById('ebook-status').innerHTML = `
                <div class="alert alert-success" style="padding:18px;">
                    <strong>✅ Ebook Generated Successfully!</strong><br><br>
                    📖 <strong>${r.chapters} chapters</strong> written<br>
                    📝 <strong>${(r.total_words || 0).toLocaleString()} words</strong><br>
                    ⏱️ Generated in <strong>${r.elapsed}s</strong><br><br>
                    <a href="${data.download_url}" download
                       class="btn btn-success"
                       style="display:inline-block;margin-top:8px;text-decoration:none;font-size:15px;padding:12px 28px;">
                        ⬇️ Download PDF
                    </a>
                </div>`;
        } else {
            document.getElementById('ebook-status').innerHTML =
                `<div class="alert alert-error">❌ Generation failed: ${data.error || 'Unknown error'}</div>`;
        }
    } catch (err) {
        console.error('Poll error:', err);
    }
}

function _updateEbookProgress(pct, message) {
    const bar  = document.getElementById('ebook-progress-bar');
    const text = document.getElementById('ebook-progress-text');
    if (bar && pct !== null) bar.style.width = pct + '%';
    if (text && message)    text.textContent = message;
}

// =============================================================================
// BATCH SCRIPT WRITER
// =============================================================================

let _batchRowCount = 0;
let _batchJobId = null;
let _batchPollInterval = null;
let _batchResults = [];
let _batchNiches = [];

function toggleBatchWriter() {
    const body = document.getElementById('batchWriterBody');
    const icon = document.getElementById('batchToggleIcon');
    const isOpen = body.style.display !== 'none';
    body.style.display = isOpen ? 'none' : 'block';
    icon.textContent = isOpen ? '▼' : '▲';
    if (!isOpen) {
        // Load niches on first open
        loadBatchNiches();
        // Add initial 3 empty rows
        if (_batchRowCount === 0) {
            addBatchRow();
            addBatchRow();
            addBatchRow();
        }
    }
}

async function loadBatchNiches() {
    if (_batchNiches.length > 0) return;
    try {
        const resp = await fetch('/api/niches');
        const data = await resp.json();
        _batchNiches = data.niches || [];
        const sel = document.getElementById('batch-niche-select');
        if (!sel) return;
        sel.innerHTML = '<option value="">— Select Niche —</option>';
        _batchNiches.forEach(n => {
            const opt = document.createElement('option');
            opt.value = n.id;
            opt.textContent = n.name;
            sel.appendChild(opt);
        });
    } catch (e) { console.error(e); }
}

function addBatchRow(title = '', engine = '') {
    _batchRowCount++;
    const container = document.getElementById('batch-rows-container');
    const rowNum = _batchRowCount;

    const row = document.createElement('div');
    row.id = `batch-row-${rowNum}`;
    row.style.cssText = 'display:grid; grid-template-columns:auto 1fr 110px 40px; gap:8px; margin-bottom:6px; align-items:center;';
    row.innerHTML = `
        <span style="font-size:13px; color:#6b7280; min-width:22px; text-align:right;">${rowNum}.</span>
        <input type="text" id="batch-title-${rowNum}" class="input-large" style="font-size:13px; padding:7px 10px;" placeholder="Enter video title…" value="${_escapeHtmlAttr(title)}">
        <select id="batch-eng-${rowNum}" class="input-large" style="font-size:12px; padding:7px 6px;">
            <option value="gemini" ${engine === 'gemini' ? 'selected' : ''}>🤖 Gemini</option>
            <option value="claude" ${engine === 'claude' ? 'selected' : ''}>🔮 Claude</option>
        </select>
        <button onclick="removeBatchRow(${rowNum})" style="background:none; border:none; color:#ef4444; cursor:pointer; font-size:18px; padding:4px; text-align:center;" title="Remove">×</button>
    `;
    container.appendChild(row);
}

function removeBatchRow(rowNum) {
    const row = document.getElementById(`batch-row-${rowNum}`);
    if (row) row.remove();
}

async function startBatchScripts() {
    const nicheId  = document.getElementById('batch-niche-select').value;
    const length   = parseInt(document.getElementById('batch-length').value);
    const delaySec = parseInt(document.getElementById('batch-delay').value);

    if (!nicheId) {
        alert('Please select a Content Niche first.');
        return;
    }

    // Collect all rows
    const rows = document.querySelectorAll('[id^="batch-row-"]');
    const titles = [];
    const titlesEngines = [];

    rows.forEach(row => {
        const id = row.id.replace('batch-row-', '');
        const titleInput = document.getElementById(`batch-title-${id}`);
        const engSelect  = document.getElementById(`batch-eng-${id}`);
        if (!titleInput || !engSelect) return;
        const title = titleInput.value.trim();
        if (!title) return;
        titles.push(title);
        titlesEngines.push(engSelect.value);
    });

    if (titles.length === 0) {
        alert('Please add at least one title.');
        return;
    }

    // Show progress
    document.getElementById('batch-progress').style.display = 'block';
    document.getElementById('batch-start-btn').disabled = true;
    document.getElementById('batch-download-all-btn').style.display = 'none';
    _batchResults = [];
    _updateBatchProgressUI(0, `Starting ${titles.length} scripts — processing one by one with ${delaySec}s delay…`);
    document.getElementById('batch-rows-container').style.opacity = '0.6';

    try {
        // One-by-one staggered: delay between each script to avoid rate limits
        const resp = await fetch('/api/batch-generate-scripts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ titles, titles_engines: titlesEngines, niche_id: nicheId, length, parallel: false, delay_seconds: delaySec })
        });
        const data = await resp.json();
        if (!data.success) {
            _updateBatchStatus('❌ Error: ' + data.error);
            document.getElementById('batch-start-btn').disabled = false;
            document.getElementById('batch-rows-container').style.opacity = '1';
            return;
        }

        _batchJobId = data.job_id;
        _updateBatchStatus('🚀 Batch started — polling for live results…');
        _batchPollInterval = setInterval(_pollBatchStatus, 4000);
        _pollBatchStatus();

    } catch (err) {
        _updateBatchStatus('❌ Error: ' + err.message);
        document.getElementById('batch-start-btn').disabled = false;
        document.getElementById('batch-rows-container').style.opacity = '1';
    }
}

async function _pollBatchStatus() {
    if (!_batchJobId) return;
    try {
        const resp = await fetch(`/api/batch-status/${_batchJobId}`);
        const data = await resp.json();

        if (data.error) {
            clearInterval(_batchPollInterval);
            _updateBatchStatus('❌ ' + data.error);
            document.getElementById('batch-start-btn').disabled = false;
            document.getElementById('batch-rows-container').style.opacity = '1';
            return;
        }

        const pct = data.progress_pct || 0;
        _updateBatchProgressUI(pct, `Completed ${data.completed}/${data.total} — ${data.engine_note}`);

        // Update each row individually
        const results = Object.values(data.results || {});
        results.forEach(r => {
            _updateBatchRowUI(r.index, r);
        });

        if (data.status === 'done') {
            clearInterval(_batchPollInterval);
            _batchPollInterval = null;
            _batchResults = results;
            const done = results.filter(r => r.status === 'done');
            const failed = results.filter(r => r.status === 'failed');
            _updateBatchStatus('✅ All done! ' + done.length + ' successful' + (failed.length ? ', ' + failed.length + ' failed' : ''));
            document.getElementById('batch-start-btn').disabled = false;
            document.getElementById('batch-rows-container').style.opacity = '1';
            if (done.length > 0) {
                document.getElementById('batch-download-all-btn').style.display = 'inline-block';
            }
        }
    } catch (err) {
        console.error('Batch poll error:', err);
    }
}

function _updateBatchRowUI(index, r) {
    const row = document.getElementById(`batch-row-${index + 1}`);
    if (!row) return;
    const engSel = document.getElementById(`batch-eng-${index + 1}`);
    if (engSel) engSel.disabled = true;

    if (r.status === 'done') {
        row.style.background = 'rgba(16,185,129,0.08)';
        row.style.borderRadius = '6px';
        row.style.border = '1px solid rgba(16,185,129,0.3)';
        row.style.padding = '6px 8px';
        row.innerHTML = `
            <span style="font-size:13px; color:#6ee7b7; min-width:22px; text-align:right;">✅</span>
            <div>
                <div style="font-size:13px; color:#6ee7b7; font-weight:600;">${_escapeHtml(r.title)}</div>
                <div style="font-size:11px; color:#9ca3af; margin-top:2px;">${r.chars.toLocaleString()} chars · ${r.time}s · ${r.chunks} chunks</div>
            </div>
            <span style="font-size:11px; color:#10b981; text-align:center;">${r.chars.toLocaleString()} chars</span>
            <button onclick="removeBatchRow(${index + 1})" style="background:none; border:none; color:#ef4444; cursor:pointer; font-size:18px; padding:4px;">×</button>
        `;
    } else if (r.status === 'failed') {
        row.style.background = 'rgba(239,68,68,0.06)';
        row.style.borderRadius = '6px';
        row.style.border = '1px solid rgba(239,68,68,0.3)';
        row.style.padding = '6px 8px';
        row.innerHTML = `
            <span style="font-size:13px; color:#f87171; min-width:22px; text-align:right;">❌</span>
            <div>
                <div style="font-size:13px; color:#f87171; font-weight:600;">${_escapeHtml(r.title)}</div>
                <div style="font-size:11px; color:#f87171; margin-top:2px;">${_escapeHtml(r.error || 'Unknown error')}</div>
            </div>
            <span></span>
            <button onclick="removeBatchRow(${index + 1})" style="background:none; border:none; color:#ef4444; cursor:pointer; font-size:18px; padding:4px;">×</button>
        `;
    } else {
        const engLabel = r.engine === 'claude' ? '🔮' : '🤖';
        const engName  = r.engine === 'claude' ? 'Claude' : 'Gemini';
        row.style.background = 'rgba(251,191,36,0.06)';
        row.style.borderRadius = '6px';
        row.style.border = '1px solid rgba(251,191,36,0.2)';
        row.style.padding = '6px 8px';
        row.innerHTML = `
            <span style="font-size:13px; color:#fbbf24; min-width:22px; text-align:right;">⏳</span>
            <div>
                <div style="font-size:13px; color:#fbbf24; font-weight:600;">${_escapeHtml(r.title)}</div>
                <div style="font-size:11px; color:#6b7280; margin-top:2px;">${engLabel} ${engName} — Generating…</div>
            </div>
            <span style="font-size:11px; color:#6b7280; text-align:center;">⏳</span>
            <span></span>
        `;
    }
}

function _updateBatchProgressUI(pct, message) {
    const bar = document.getElementById('batch-progress-bar');
    const text = document.getElementById('batch-status-text');
    const pctText = document.getElementById('batch-pct-text');
    if (bar) bar.style.width = pct + '%';
    if (text) text.textContent = message;
    if (pctText) pctText.textContent = pct + '%';
}

function _updateBatchStatus(message) {
    const text = document.getElementById('batch-status-text');
    if (text) text.textContent = message;
}

async function downloadAllBatchScripts() {
    if (!_batchResults.length) return;
    const done = _batchResults.filter(r => r.status === 'done' && r.filename);
    if (!done.length) return;
    for (const r of done) {
        const a = document.createElement('a');
        a.href = '/api/download/' + r.filename;
        a.download = r.filename;
        a.target = '_blank';
        a.click();
        await new Promise(res => setTimeout(res, 300));
    }
}

function _escapeHtml(str) {
    const d = document.createElement('div');
    d.textContent = str || '';
    return d.innerHTML;
}

function _escapeHtmlAttr(str) {
    return (str || '').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

