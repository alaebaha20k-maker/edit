// Global state
const state = {
    visualMedia: [],
    audioFiles: [],
    uploadedFiles: new Map()
};

const API_BASE = 'http://localhost:5000/api';

// Initialize app
document.addEventListener('DOMContentLoaded', () => {
    initializeFileInputs();
    initializeDragAndDrop();
});

// Initialize file input handlers
function initializeFileInputs() {
    const visualInput = document.getElementById('visual-file-input');
    const audioInput = document.getElementById('audio-file-input');

    visualInput.addEventListener('change', (e) => {
        handleFileSelection(e.target.files, 'visual');
        e.target.value = ''; // Reset input
    });

    audioInput.addEventListener('change', (e) => {
        handleFileSelection(e.target.files, 'audio');
        e.target.value = ''; // Reset input
    });
}

// Initialize drag and drop
function initializeDragAndDrop() {
    const visualDropzone = document.getElementById('visual-dropzone');
    const audioDropzone = document.getElementById('audio-dropzone');

    setupDropzone(visualDropzone, 'visual');
    setupDropzone(audioDropzone, 'audio');
}

function setupDropzone(element, type) {
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        element.addEventListener(eventName, preventDefaults, false);
    });

    ['dragenter', 'dragover'].forEach(eventName => {
        element.addEventListener(eventName, () => {
            element.classList.add('dragover');
        });
    });

    ['dragleave', 'drop'].forEach(eventName => {
        element.addEventListener(eventName, () => {
            element.classList.remove('dragover');
        });
    });

    element.addEventListener('drop', (e) => {
        const files = e.dataTransfer.files;
        handleFileSelection(files, type);
    });
}

function preventDefaults(e) {
    e.preventDefault();
    e.stopPropagation();
}

// Handle file selection
async function handleFileSelection(files, type) {
    const fileArray = Array.from(files);

    for (const file of fileArray) {
        await uploadFile(file, type);
    }

    updateDisplay();
    updateDurationCalculation();
}

// Upload file to server
async function uploadFile(file, mediaType) {
    try {
        const formData = new FormData();
        formData.append('file', file);

        // Determine file type
        let fileType;
        if (mediaType === 'visual') {
            if (file.type.startsWith('video/')) {
                fileType = 'video';
            } else if (file.type.startsWith('image/')) {
                fileType = 'image';
            } else {
                showError(`Unsupported file type: ${file.name}`);
                return;
            }
        } else {
            fileType = 'audio';
        }

        formData.append('type', fileType);

        showProgress('Uploading ' + file.name + '...');

        const response = await fetch(`${API_BASE}/upload`, {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Upload failed');
        }

        const result = await response.json();

        // Store file info
        const fileInfo = {
            fileId: result.file_id,
            filename: result.filename,
            path: result.path,
            size: result.size,
            type: fileType,
            rank: mediaType === 'visual' ? state.visualMedia.length + 1 : state.audioFiles.length + 1
        };

        state.uploadedFiles.set(result.file_id, fileInfo);

        if (mediaType === 'visual') {
            state.visualMedia.push(fileInfo);
        } else {
            state.audioFiles.push(fileInfo);
        }

        hideProgress();
        console.log('Uploaded:', fileInfo);

    } catch (error) {
        console.error('Upload error:', error);
        showError('Failed to upload ' + file.name + ': ' + error.message);
        hideProgress();
    }
}

// Update display
function updateDisplay() {
    updateVisualMediaList();
    updateAudioList();
}

function updateVisualMediaList() {
    const container = document.getElementById('visual-media-list');
    container.innerHTML = '';

    if (state.visualMedia.length === 0) {
        return;
    }

    state.visualMedia.forEach((file, index) => {
        const fileItem = createFileItem(file, index, 'visual');
        container.appendChild(fileItem);
    });
}

function updateAudioList() {
    const container = document.getElementById('audio-list');
    container.innerHTML = '';

    if (state.audioFiles.length === 0) {
        return;
    }

    state.audioFiles.forEach((file, index) => {
        const fileItem = createFileItem(file, index, 'audio');
        container.appendChild(fileItem);
    });
}

function createFileItem(file, index, mediaType) {
    const div = document.createElement('div');
    div.className = 'file-item';

    const icon = file.type === 'video' ? '🎥' : file.type === 'image' ? '🖼️' : '🎵';

    div.innerHTML = `
        <div class="file-info">
            <div class="file-icon">${icon}</div>
            <div class="file-details">
                <div class="file-name">${file.filename}</div>
                <div class="file-meta">${file.type} • ${file.size}</div>
            </div>
        </div>
        <div class="file-controls">
            <div class="rank-control">
                <label>Rank:</label>
                <input type="number" class="rank-input" value="${file.rank}" min="1"
                       onchange="updateRank('${mediaType}', ${index}, this.value)">
            </div>
            <button class="btn btn-danger" onclick="removeFile('${mediaType}', ${index})">Remove</button>
        </div>
    `;

    return div;
}

// Update rank
function updateRank(mediaType, index, newRank) {
    newRank = parseInt(newRank);

    if (isNaN(newRank) || newRank < 1) {
        alert('Rank must be a positive number');
        updateDisplay();
        return;
    }

    const array = mediaType === 'visual' ? state.visualMedia : state.audioFiles;
    array[index].rank = newRank;

    // Re-sort by rank
    array.sort((a, b) => a.rank - b.rank);

    updateDisplay();
    updateDurationCalculation();
}

// Remove file
function removeFile(mediaType, index) {
    const array = mediaType === 'visual' ? state.visualMedia : state.audioFiles;
    const file = array[index];

    // Remove from uploaded files
    state.uploadedFiles.delete(file.fileId);

    // Remove from array
    array.splice(index, 1);

    // Renumber ranks
    array.forEach((f, i) => {
        f.rank = i + 1;
    });

    updateDisplay();
    updateDurationCalculation();
}

// Update duration calculation
async function updateDurationCalculation() {
    // This is a simplified client-side preview
    // Actual calculation happens on server

    const totalAudioEl = document.getElementById('total-audio');
    const totalVideoEl = document.getElementById('total-video');
    const imageDurationEl = document.getElementById('image-duration');

    if (state.audioFiles.length === 0) {
        totalAudioEl.textContent = '0:00';
        totalVideoEl.textContent = '0:00';
        imageDurationEl.textContent = '0:00';
        return;
    }

    // For preview purposes, we'll just show counts
    const videoCount = state.visualMedia.filter(f => f.type === 'video').length;
    const imageCount = state.visualMedia.filter(f => f.type === 'image').length;

    totalAudioEl.textContent = `${state.audioFiles.length} file(s)`;
    totalVideoEl.textContent = `${videoCount} clip(s)`;
    imageDurationEl.textContent = `${imageCount} image(s)`;
}

// Process video
async function processVideo() {
    try {
        // Validate input
        if (state.visualMedia.length === 0) {
            showError('Please upload at least one video or image');
            return;
        }

        if (state.audioFiles.length === 0) {
            showError('Please upload at least one audio file');
            return;
        }

        // Disable button
        const processBtn = document.getElementById('process-btn');
        processBtn.disabled = true;
        processBtn.textContent = '⏳ Processing...';

        // Show progress section
        showProgressSection();

        // Prepare request data
        const visualMedia = state.visualMedia.map(f => ({
            rank: f.rank,
            type: f.type,
            file_id: f.fileId
        }));

        const audioFiles = state.audioFiles.map(f => ({
            rank: f.rank,
            file_id: f.fileId
        }));

        const outputFilename = document.getElementById('output-filename').value || undefined;

        const requestData = {
            visual_media: visualMedia,
            audio_files: audioFiles,
            output_filename: outputFilename
        };

        updateProgressText('Sending request to server...');

        const response = await fetch(`${API_BASE}/process`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestData)
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Processing failed');
        }

        const result = await response.json();

        if (result.success) {
            updateProgressBar(100);
            updateProgressText('Processing complete!');

            // Show result
            showResult(result.result);
        } else {
            throw new Error(result.error || 'Processing failed');
        }

    } catch (error) {
        console.error('Processing error:', error);
        showError('Processing failed: ' + error.message);
        hideProgressSection();

        // Re-enable button
        const processBtn = document.getElementById('process-btn');
        processBtn.disabled = false;
        processBtn.textContent = '🚀 Create Video';
    }
}

// Show progress section
function showProgressSection() {
    const section = document.getElementById('progress-section');
    section.classList.remove('hidden');
    updateProgressBar(10);
    updateProgressText('Initializing...');
}

function hideProgressSection() {
    const section = document.getElementById('progress-section');
    section.classList.add('hidden');
}

function updateProgressBar(percentage) {
    const fill = document.getElementById('progress-fill');
    fill.style.width = percentage + '%';
}

function updateProgressText(text) {
    const textEl = document.getElementById('progress-text');
    textEl.textContent = text;

    // Simulate progress updates
    if (text.includes('Initializing')) {
        setTimeout(() => updateProgressBar(20), 500);
        setTimeout(() => updateProgressText('Validating files...'), 1000);
    } else if (text.includes('Validating')) {
        setTimeout(() => updateProgressBar(30), 500);
        setTimeout(() => updateProgressText('Processing video clips...'), 1000);
    } else if (text.includes('Processing video')) {
        setTimeout(() => updateProgressBar(50), 1000);
        setTimeout(() => updateProgressText('Generating captions...'), 2000);
    } else if (text.includes('Generating captions')) {
        setTimeout(() => updateProgressBar(70), 2000);
        setTimeout(() => updateProgressText('Creating final video...'), 4000);
    } else if (text.includes('Creating final')) {
        setTimeout(() => updateProgressBar(90), 2000);
    }
}

// Show result
function showResult(result) {
    hideProgressSection();

    const section = document.getElementById('result-section');
    const infoDiv = document.getElementById('result-info');

    // Use output_filename from backend (works on all platforms)
    const outputFilename = result.output_filename || result.output_path.split('/').pop().split('\\').pop();

    infoDiv.innerHTML = `
        <p><strong>Output File:</strong> ${outputFilename}</p>
        <p><strong>Duration:</strong> ${result.duration.toFixed(2)} seconds</p>
        <p><strong>File Size:</strong> ${result.file_size}</p>
    `;

    section.classList.remove('hidden');

    // Setup download button
    const downloadBtn = document.getElementById('download-btn');
    downloadBtn.onclick = () => {
        window.location.href = `${API_BASE}/download/${outputFilename}`;
    };

    // Re-enable process button
    const processBtn = document.getElementById('process-btn');
    processBtn.disabled = false;
    processBtn.textContent = '🚀 Create Video';
}

// Show error message
function showError(message) {
    alert('ERROR: ' + message);
    console.error(message);
}

// Show progress message
function showProgress(message) {
    console.log('Progress:', message);
}

function hideProgress() {
    // Could implement a progress indicator here
}

// Utility: Format time
function formatTime(seconds) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);

    if (hours > 0) {
        return `${hours}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    } else {
        return `${minutes}:${secs.toString().padStart(2, '0')}`;
    }
}
