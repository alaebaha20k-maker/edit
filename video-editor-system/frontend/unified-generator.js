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

    if (!nicheId) {
        statusDiv.innerHTML = '<div class="alert alert-error">Please select a niche</div>';
        return;
    }

    if (!title) {
        statusDiv.innerHTML = '<div class="alert alert-error">Please enter a video title</div>';
        return;
    }

    statusDiv.innerHTML = '<div class="alert alert-info">🤖 Generating script with Gemini AI... This may take 1-2 minutes...</div>';

    try {
        const response = await fetch('/api/generate-script', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title, niche_id: nicheId })
        });

        const data = await response.json();

        if (data.success) {
            generatedScript = data.script;
            statusDiv.innerHTML = `<div class="alert alert-success">✅ Script generated! (${data.length} characters)</div>`;
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

    statusDiv.innerHTML = '<div class="alert alert-info">🎨 Generating 6 images with Replicate... This may take 1-2 minutes...</div>';

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
