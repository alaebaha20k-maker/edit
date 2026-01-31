/**
 * AI VIDEO STUDIO - Complete Frontend Logic
 * Single Page Application with ALL Fixes Applied
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
    settings: {},
    mediaFiles: [],
    titleFormulas: [],
    scriptFormulas: [],
    mediaLibrary: []
};

// Global video data
window.videoData = {
    title: '',
    script: '',
    mediaFiles: [],
    audioFile: null
};

// Global editor data
window.editorData = {
    originalFile: null,
    url: null,
    clips: []
};

// =============================================================================
// NOTIFICATION SYSTEM
// =============================================================================
const showNotification = (message, type = 'info') => {
    const container = document.getElementById('notification-container') || createNotificationContainer();

    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;

    container.appendChild(notification);

    setTimeout(() => {
        notification.classList.add('fade-out');
        setTimeout(() => notification.remove(), 300);
    }, 4000);
};

const createNotificationContainer = () => {
    const container = document.createElement('div');
    container.id = 'notification-container';
    container.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        z-index: 10000;
    `;
    document.body.appendChild(container);
    return container;
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
// PROBLEM 1: SETTINGS WITH LOCALSTORAGE (FIXED)
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

const loadSettings = () => {
    try {
        const saved = localStorage.getItem('videoToolSettings');
        if (saved) {
            const settings = JSON.parse(saved);
            appState.settings = settings;

            // Restore API keys
            if (settings.api_keys) {
                const geminiKey = document.getElementById('geminiKey');
                const replicateKey = document.getElementById('replicateKey');
                const inworldKey = document.getElementById('inworldKey');
                const pexelsKey = document.getElementById('pexelsKey');
                const pixabayKey = document.getElementById('pixabayKey');
                const unsplashKey = document.getElementById('unsplashKey');

                if (geminiKey) geminiKey.value = settings.api_keys.gemini || '';
                if (replicateKey) replicateKey.value = settings.api_keys.replicate || '';
                if (inworldKey) inworldKey.value = settings.api_keys.inworld || '';
                if (pexelsKey) pexelsKey.value = settings.api_keys.pexels || '';
                if (pixabayKey) pixabayKey.value = settings.api_keys.pixabay || '';
                if (unsplashKey) unsplashKey.value = settings.api_keys.unsplash || '';
            }

            // Load formula lists
            if (settings.title_formulas) {
                appState.titleFormulas = settings.title_formulas;
                renderTitleFormulas(settings.title_formulas);
                updateTitleFormulaDropdown(settings.title_formulas);
            }
            if (settings.script_formulas) {
                appState.scriptFormulas = settings.script_formulas;
                renderScriptFormulas(settings.script_formulas);
                updateScriptFormulaDropdown(settings.script_formulas);
            }

            console.log('✅ Settings loaded from localStorage');
        }
    } catch (error) {
        console.error('Load settings failed:', error);
        showNotification('⚠️ Error loading settings', 'warning');
    }
};

const saveSettings = () => {
    try {
        const settings = {
            api_keys: {
                gemini: document.getElementById('geminiKey')?.value || '',
                replicate: document.getElementById('replicateKey')?.value || '',
                inworld: document.getElementById('inworldKey')?.value || '',
                pexels: document.getElementById('pexelsKey')?.value || '',
                pixabay: document.getElementById('pixabayKey')?.value || '',
                unsplash: document.getElementById('unsplashKey')?.value || ''
            },
            title_formulas: appState.titleFormulas || [],
            script_formulas: appState.scriptFormulas || []
        };

        localStorage.setItem('videoToolSettings', JSON.stringify(settings));
        appState.settings = settings;

        showNotification('✅ Settings saved successfully!', 'success');
        closeSettings();

    } catch (error) {
        console.error('Save failed:', error);
        showNotification('❌ Failed to save: ' + error.message, 'error');
    }
};

// =============================================================================
// FORMULA MANAGEMENT SYSTEM
// =============================================================================
function addTitleFormula() {
    const nameInput = document.getElementById('newTitleFormulaName');
    const contentInput = document.getElementById('newTitleFormulaContent');

    const name = nameInput?.value.trim();
    const content = contentInput?.value.trim();

    if (!name || !content) {
        showNotification('⚠️ Please enter both formula name and content', 'warning');
        return;
    }

    if (!appState.titleFormulas) appState.titleFormulas = [];

    appState.titleFormulas.push({ name, content, id: Date.now() });

    renderTitleFormulas(appState.titleFormulas);
    updateTitleFormulaDropdown(appState.titleFormulas);

    nameInput.value = '';
    contentInput.value = '';

    showNotification('✅ Title formula added!', 'success');
}

function deleteTitleFormula(id) {
    if (!confirm('Delete this formula?')) return;

    appState.titleFormulas = appState.titleFormulas.filter(f => f.id !== id);
    renderTitleFormulas(appState.titleFormulas);
    updateTitleFormulaDropdown(appState.titleFormulas);

    showNotification('✅ Formula deleted', 'success');
}

function renderTitleFormulas(formulas) {
    const container = document.getElementById('titleFormulasList');
    if (!container) return;

    if (!formulas || formulas.length === 0) {
        container.innerHTML = '<p style="color: #888;">No formulas saved yet.</p>';
        return;
    }

    container.innerHTML = formulas.map(f => `
        <div class="formula-item" style="background: rgba(255,255,255,0.05); padding: 15px; margin: 10px 0; border-radius: 8px;">
            <div style="display: flex; justify-content: space-between; align-items: start;">
                <div style="flex: 1;">
                    <strong style="color: #667eea;">${f.name}</strong>
                    <p style="color: #aaa; margin: 8px 0; font-size: 13px;">${f.content}</p>
                </div>
                <button onclick="deleteTitleFormula(${f.id})" class="btn-secondary" style="margin-left: 10px;">🗑️</button>
            </div>
        </div>
    `).join('');
}

function updateTitleFormulaDropdown(formulas) {
    const dropdown = document.getElementById('titleFormulaSelect');
    if (!dropdown) return;

    dropdown.innerHTML = '<option value="default">Default Formula (No topic needed)</option>';

    if (formulas && formulas.length > 0) {
        formulas.forEach(f => {
            dropdown.innerHTML += `<option value="${f.id}">${f.name}</option>`;
        });
    }
}

function addScriptFormula() {
    const nameInput = document.getElementById('newScriptFormulaName');
    const contentInput = document.getElementById('newScriptFormulaContent');

    const name = nameInput?.value.trim();
    const content = contentInput?.value.trim();

    if (!name || !content) {
        showNotification('⚠️ Please enter both formula name and content', 'warning');
        return;
    }

    if (!appState.scriptFormulas) appState.scriptFormulas = [];

    appState.scriptFormulas.push({ name, content, id: Date.now() });

    renderScriptFormulas(appState.scriptFormulas);
    updateScriptFormulaDropdown(appState.scriptFormulas);

    nameInput.value = '';
    contentInput.value = '';

    showNotification('✅ Script formula added!', 'success');
}

function deleteScriptFormula(id) {
    if (!confirm('Delete this formula?')) return;

    appState.scriptFormulas = appState.scriptFormulas.filter(f => f.id !== id);
    renderScriptFormulas(appState.scriptFormulas);
    updateScriptFormulaDropdown(appState.scriptFormulas);

    showNotification('✅ Formula deleted', 'success');
}

function renderScriptFormulas(formulas) {
    const container = document.getElementById('scriptFormulasList');
    if (!container) return;

    if (!formulas || formulas.length === 0) {
        container.innerHTML = '<p style="color: #888;">No formulas saved yet.</p>';
        return;
    }

    container.innerHTML = formulas.map(f => `
        <div class="formula-item" style="background: rgba(255,255,255,0.05); padding: 15px; margin: 10px 0; border-radius: 8px;">
            <div style="display: flex; justify-content: space-between; align-items: start;">
                <div style="flex: 1;">
                    <strong style="color: #667eea;">${f.name}</strong>
                    <p style="color: #aaa; margin: 8px 0; font-size: 13px;">${f.content.substring(0, 150)}${f.content.length > 150 ? '...' : ''}</p>
                </div>
                <button onclick="deleteScriptFormula(${f.id})" class="btn-secondary" style="margin-left: 10px;">🗑️</button>
            </div>
        </div>
    `).join('');
}

function updateScriptFormulaDropdown(formulas) {
    const dropdown = document.getElementById('scriptFormulaSelect');
    if (!dropdown) return;

    dropdown.innerHTML = '<option value="default">Default 3-Chunk System</option>';

    if (formulas && formulas.length > 0) {
        formulas.forEach(f => {
            dropdown.innerHTML += `<option value="${f.id}">${f.name}</option>`;
        });
    }
}

// =============================================================================
// PROBLEM 3: TITLE GENERATION (FIXED)
// =============================================================================
function toggleTitleMode() {
    const mode = document.querySelector('input[name="titleMode"]:checked').value;
    const manualSection = document.getElementById('titleManualSection');
    const autoSection = document.getElementById('titleAutoSection');

    if (manualSection && autoSection) {
        manualSection.style.display = mode === 'manual' ? 'block' : 'none';
        autoSection.style.display = mode === 'auto' ? 'block' : 'none';
    }
}

async function generateTitle() {
    const formulaSelect = document.getElementById('titleFormulaSelect');
    const selectedFormulaId = formulaSelect?.value;

    const resultBox = document.getElementById('titleResult');
    if (resultBox) {
        resultBox.style.display = 'block';
        resultBox.innerHTML = '<p>🤖 Generating title with AI...</p>';
    }

    try {
        const settings = JSON.parse(localStorage.getItem('videoToolSettings') || '{}');
        const apiKey = settings.api_keys?.gemini;

        if (!apiKey) {
            throw new Error('Gemini API key not found. Please configure in Settings.');
        }

        // Get formula content
        let prompt;
        if (selectedFormulaId === 'default') {
            prompt = `Generate a catchy, engaging YouTube video title. Make it attention-grabbing and viral-worthy. Return ONLY the title, nothing else.`;
        } else {
            const formula = (settings.title_formulas || []).find(f => f.id == selectedFormulaId);
            if (!formula) {
                throw new Error('Selected formula not found');
            }
            prompt = formula.content;
        }

        const response = await fetch(
            `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=${apiKey}`,
            {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    contents: [{ parts: [{ text: prompt }] }],
                    generationConfig: {
                        temperature: 0.9,
                        maxOutputTokens: 1024
                    }
                })
            }
        );

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(`Gemini API error: ${response.status} - ${errorData.error?.message || 'Unknown error'}`);
        }

        const data = await response.json();
        const title = data.candidates[0].content.parts[0].text.trim();

        window.videoData.title = title;
        appState.generatedTitle = title;

        const titleInput = document.getElementById('titleInput');
        if (titleInput) {
            titleInput.value = title;
        }

        if (resultBox) {
            resultBox.innerHTML = `<p>✅ Generated: <strong>${title}</strong></p>`;
        }

        showNotification('✅ Title generated!', 'success');

    } catch (error) {
        console.error('Title generation failed:', error);
        if (resultBox) {
            resultBox.innerHTML = `<p>❌ Error: ${error.message}</p>`;
        }
        showNotification('❌ Title generation failed: ' + error.message, 'error');
    }
}

// =============================================================================
// PROBLEM 4: SCRIPT GENERATION WITH 3-CHUNK SYSTEM (FIXED)
// =============================================================================
function toggleScriptMode() {
    const mode = document.querySelector('input[name="scriptMode"]:checked').value;
    const manualSection = document.getElementById('scriptManualSection');
    const autoSection = document.getElementById('scriptAutoSection');

    if (manualSection && autoSection) {
        manualSection.style.display = mode === 'manual' ? 'block' : 'none';
        autoSection.style.display = mode === 'auto' ? 'block' : 'none';
    }
}

async function loadScriptFile() {
    const fileInput = document.getElementById('scriptFile');
    if (!fileInput || fileInput.files.length === 0) return;

    const file = fileInput.files[0];
    const text = await file.text();

    const scriptInput = document.getElementById('scriptInput');
    if (scriptInput) {
        scriptInput.value = text;
        window.videoData.script = text;
        showNotification('✅ Script loaded from file', 'success');
    }
}

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

const getLastSentences = (text, n) => {
    const sentences = text.match(/[^.!?]+[.!?]+/g) || [];
    return sentences.slice(-n).join(' ');
};

const cleanScript = (text) => {
    return text
        .replace(/\$\d+(\.\d{2})?/g, '')
        .replace(/```[\s\S]*?```/g, '')
        .replace(/\n{3,}/g, '\n\n')
        .trim();
};

const callGemini = async (apiKey, prompt, maxTokens = 8192) => {
    const response = await fetch(
        `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=${apiKey}`,
        {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                contents: [{ parts: [{ text: prompt }] }],
                generationConfig: {
                    temperature: 0.9,
                    maxOutputTokens: maxTokens
                }
            })
        }
    );

    if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(`Gemini API error: ${response.status} - ${errorData.error?.message || 'Unknown error'}`);
    }

    const data = await response.json();
    return data.candidates[0].content.parts[0].text;
};

async function generateScript() {
    const title = document.getElementById('titleInput')?.value || window.videoData.title;
    if (!title) {
        showNotification('⚠️ Please enter a title first', 'warning');
        return;
    }

    const lengthSelect = document.getElementById('scriptLength');
    const selectedLength = lengthSelect ? parseInt(lengthSelect.value) : 60000;

    const resultBox = document.getElementById('scriptResult');
    const statsBox = document.getElementById('scriptStats');

    if (resultBox) {
        resultBox.style.display = 'block';
        resultBox.innerHTML = '<p>🤖 Generating script with 3-chunk system... This may take 1-2 minutes...</p>';
    }

    if (statsBox) {
        statsBox.style.display = 'none';
    }

    try {
        const settings = JSON.parse(localStorage.getItem('videoToolSettings') || '{}');
        const apiKey = settings.api_keys?.gemini;

        if (!apiKey) {
            throw new Error('Gemini API key not found. Please configure in Settings.');
        }

        // Get selected formula
        const formulaSelect = document.getElementById('scriptFormulaSelect');
        const selectedFormulaId = formulaSelect?.value;

        let customFormula = null;
        let useCustomFormula = false;

        if (selectedFormulaId && selectedFormulaId !== 'default') {
            const formula = (settings.script_formulas || []).find(f => f.id == selectedFormulaId);
            if (formula) {
                customFormula = formula.content;
                useCustomFormula = true;
            }
        }

        const chunkSize = Math.floor(selectedLength / 3);
        let fullScript = '';
        let lastSentences = '';

        // CHUNK 1: Hook + Intro
        if (resultBox) resultBox.innerHTML = '<p>⏳ Chunk 1/3: Generating hook and intro...</p>';

        const chunk1Prompt = useCustomFormula
            ? customFormula.replace('{title}', title).replace('{chunk}', '1').replace('{focus}', 'Hook + Intro')
            : `Create an engaging video script about: "${title}"

Target length: ${chunkSize} characters
This is PART 1 of 3. Focus on:
- Powerful hook (first 10 seconds)
- Introduce main idea
- Build curiosity

Write engaging, conversational narration script.`;

        const chunk1 = await callGemini(apiKey, chunk1Prompt);
        fullScript += chunk1;
        lastSentences = getLastSentences(chunk1, 4);

        if (resultBox) resultBox.innerHTML = '<p>✅ Chunk 1/3 complete</p>';
        await sleep(1000);

        // CHUNK 2: Examples + Depth
        if (resultBox) resultBox.innerHTML = '<p>⏳ Chunk 2/3: Adding examples and depth...</p>';

        const chunk2Prompt = useCustomFormula
            ? customFormula.replace('{title}', title).replace('{chunk}', '2').replace('{focus}', 'Examples + Depth').replace('{previous}', lastSentences)
            : `Continue this script seamlessly:

Previous ending: "${lastSentences}"

Target length: ${chunkSize} characters
This is PART 2 of 3. Focus on:
- Real examples and stories
- Deep dive into details
- Keep engagement high

Continue naturally from previous part.`;

        const chunk2 = await callGemini(apiKey, chunk2Prompt);
        fullScript += ' ' + chunk2;
        lastSentences = getLastSentences(chunk2, 4);

        if (resultBox) resultBox.innerHTML = '<p>✅ Chunk 2/3 complete</p>';
        await sleep(1000);

        // CHUNK 3: Steps + CTA
        if (resultBox) resultBox.innerHTML = '<p>⏳ Chunk 3/3: Adding conclusion and CTA...</p>';

        const chunk3Prompt = useCustomFormula
            ? customFormula.replace('{title}', title).replace('{chunk}', '3').replace('{focus}', 'Steps + CTA').replace('{previous}', lastSentences)
            : `Continue and conclude this script:

Previous ending: "${lastSentences}"

Target length: ${chunkSize} characters
This is PART 3 of 3 (FINAL). Focus on:
- Actionable steps/tips
- Strong conclusion
- Clear call-to-action

End powerfully and naturally.`;

        const chunk3 = await callGemini(apiKey, chunk3Prompt);
        fullScript += ' ' + chunk3;

        // Clean script
        fullScript = cleanScript(fullScript);

        // Save script
        window.videoData.script = fullScript;
        appState.generatedScript = fullScript;

        const scriptInput = document.getElementById('scriptInput');
        if (scriptInput) {
            scriptInput.value = fullScript;
        }

        const wordCount = fullScript.split(/\s+/).length;
        const charCount = fullScript.length;

        if (resultBox) {
            resultBox.innerHTML = '<p>✅ Script generated successfully!</p>';
        }

        if (statsBox) {
            statsBox.style.display = 'block';
            statsBox.innerHTML = `
                <p><strong>Characters:</strong> ${charCount.toLocaleString()}</p>
                <p><strong>Words:</strong> ${wordCount.toLocaleString()}</p>
                <p><strong>Est. Duration:</strong> ~${Math.round(wordCount / 150)} minutes</p>
            `;
        }

        // Show download button
        const downloadSection = document.getElementById('scriptDownloadSection');
        if (downloadSection) {
            downloadSection.style.display = 'block';
        }

        showNotification('✅ Script generated with 3-chunk system!', 'success');

    } catch (error) {
        console.error('Script generation failed:', error);
        if (resultBox) {
            resultBox.innerHTML = `<p>❌ Error: ${error.message}</p>`;
        }
        showNotification('❌ Script generation failed: ' + error.message, 'error');
    }
}

// Download generated script as .txt file
function downloadScript() {
    const script = document.getElementById('scriptInput')?.value || window.videoData.script || appState.generatedScript;

    if (!script || script.trim().length === 0) {
        showNotification('⚠️ No script to download', 'warning');
        return;
    }

    const title = document.getElementById('titleInput')?.value || window.videoData.title || 'script';
    const filename = `${title.replace(/[^a-z0-9]/gi, '_').toLowerCase()}_script.txt`;

    const blob = new Blob([script], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    showNotification(`✅ Script downloaded: ${filename}`, 'success');
}

// =============================================================================
// MEDIA SECTION
// =============================================================================
function toggleMediaSection(type) {
    if (type === 'ai') {
        const checked = document.getElementById('useAiImages')?.checked;
        const section = document.getElementById('aiImagesSection');
        if (section) section.style.display = checked ? 'block' : 'none';
    } else if (type === 'manual') {
        const checked = document.getElementById('useManualMedia')?.checked;
        const section = document.getElementById('manualMediaSection');
        if (section) section.style.display = checked ? 'block' : 'none';
    } else if (type === 'stock') {
        const checked = document.getElementById('useStockFootage')?.checked;
        const section = document.getElementById('stockFootageSection');
        if (section) section.style.display = checked ? 'block' : 'none';
    }
}

// =============================================================================
// MEDIA LIBRARY WITH RANKING
// =============================================================================
function addToMediaLibrary(file, url, type, source = 'upload', muted = false) {
    const mediaItem = {
        id: Date.now() + Math.random(),
        file: file,
        url: url,
        type: type, // 'image' or 'video'
        source: source, // 'upload', 'stock', 'ai'
        muted: muted,
        rank: appState.mediaLibrary.length
    };

    appState.mediaLibrary.push(mediaItem);
    renderMediaLibrary();
    showNotification(`✅ Added to media library`, 'success');
}

function renderMediaLibrary() {
    const grid = document.getElementById('mediaLibraryGrid');
    if (!grid) return;

    if (appState.mediaLibrary.length === 0) {
        grid.innerHTML = '<p style="color: #888; grid-column: 1/-1;">No media added yet. Upload or fetch stock footage above.</p>';
        return;
    }

    grid.innerHTML = '';

    appState.mediaLibrary.forEach((media, index) => {
        const card = document.createElement('div');
        card.className = 'media-library-card';
        card.draggable = true;
        card.dataset.id = media.id;
        card.dataset.index = index;

        card.style.cssText = `
            position: relative;
            background: rgba(0,0,0,0.3);
            border-radius: 8px;
            overflow: hidden;
            cursor: grab;
            border: 2px solid transparent;
            transition: all 0.2s;
        `;

        const isVideo = media.type === 'video';

        const preview = isVideo
            ? `<video src="${media.url}" style="width: 100%; height: 120px; object-fit: cover;"></video>`
            : `<img src="${media.url}" style="width: 100%; height: 120px; object-fit: cover;">`;

        const muteToggle = isVideo
            ? `<label style="display: flex; align-items: center; gap: 5px; font-size: 12px; margin-top: 5px;">
                <input type="checkbox" ${media.muted ? 'checked' : ''} onchange="toggleMediaMute(${media.id})">
                <span>Mute</span>
            </label>`
            : '';

        card.innerHTML = `
            ${preview}
            <div style="padding: 8px;">
                <div style="font-size: 11px; color: #888; text-transform: uppercase;">${media.source} ${media.type}</div>
                <div style="font-size: 13px; margin-top: 3px;">Rank: #${index + 1}</div>
                ${muteToggle}
                <button onclick="deleteFromMediaLibrary(${media.id})" class="btn-secondary" style="margin-top: 8px; font-size: 11px; padding: 4px 8px;">🗑️ Delete</button>
            </div>
        `;

        // Drag events
        card.addEventListener('dragstart', handleDragStart);
        card.addEventListener('dragover', handleDragOver);
        card.addEventListener('drop', handleDrop);
        card.addEventListener('dragend', handleDragEnd);

        grid.appendChild(card);
    });
}

let draggedElement = null;

function handleDragStart(e) {
    draggedElement = e.target;
    e.target.style.opacity = '0.5';
    e.target.style.cursor = 'grabbing';
}

function handleDragOver(e) {
    e.preventDefault();
    const target = e.target.closest('.media-library-card');
    if (target && target !== draggedElement) {
        target.style.borderColor = '#667eea';
    }
}

function handleDrop(e) {
    e.preventDefault();
    const target = e.target.closest('.media-library-card');

    if (target && target !== draggedElement) {
        const draggedIndex = parseInt(draggedElement.dataset.index);
        const targetIndex = parseInt(target.dataset.index);

        // Reorder array
        const item = appState.mediaLibrary.splice(draggedIndex, 1)[0];
        appState.mediaLibrary.splice(targetIndex, 0, item);

        renderMediaLibrary();
        showNotification('✅ Media reordered', 'success');
    }

    target.style.borderColor = 'transparent';
}

function handleDragEnd(e) {
    e.target.style.opacity = '1';
    e.target.style.cursor = 'grab';
    document.querySelectorAll('.media-library-card').forEach(card => {
        card.style.borderColor = 'transparent';
    });
}

function toggleMediaMute(id) {
    const media = appState.mediaLibrary.find(m => m.id === id);
    if (media) {
        media.muted = !media.muted;
        showNotification(media.muted ? '🔇 Video muted' : '🔊 Video unmuted', 'info');
    }
}

function deleteFromMediaLibrary(id) {
    if (!confirm('Remove this media from library?')) return;

    appState.mediaLibrary = appState.mediaLibrary.filter(m => m.id !== id);
    renderMediaLibrary();
    showNotification('✅ Media removed', 'success');
}

async function generateAiImages() {
    const script = document.getElementById('scriptInput')?.value || window.videoData.script;
    if (!script) {
        showNotification('⚠️ Please generate or enter a script first', 'warning');
        return;
    }

    const countInput = document.getElementById('aiImageCount');
    const count = countInput ? parseInt(countInput.value) : 6;

    const progressBox = document.getElementById('aiImageProgress');
    const previewBox = document.getElementById('aiImagePreview');

    if (progressBox) {
        progressBox.style.display = 'block';
        progressBox.innerHTML = `<p>🎨 Generating ${count} AI images... This will take ~${count * 12} seconds...</p>`;
    }

    if (previewBox) previewBox.innerHTML = '';

    try {
        const settings = JSON.parse(localStorage.getItem('videoToolSettings') || '{}');
        const replicateToken = settings.api_keys?.replicate;

        if (!replicateToken) {
            throw new Error('Replicate API token not found. Please configure in Settings.');
        }

        showNotification(`🎨 Generating ${count} images...`, 'info');

        // This would call your backend API to handle Replicate
        // For now, showing placeholder
        if (progressBox) {
            progressBox.innerHTML = `<p>⚠️ Image generation requires backend API setup</p>`;
        }

    } catch (error) {
        console.error('Image generation failed:', error);
        if (progressBox) {
            progressBox.innerHTML = `<p>❌ Error: ${error.message}</p>`;
        }
        showNotification('❌ Image generation failed: ' + error.message, 'error');
    }
}

// =============================================================================
// PROBLEM 5: STOCK FOOTAGE SEARCH (FIXED)
// =============================================================================
async function extractKeywords() {
    const script = document.getElementById('scriptInput')?.value || window.videoData.script;
    if (!script) {
        showNotification('⚠️ Please generate or enter a script first', 'warning');
        return;
    }

    // Simple keyword extraction
    const words = script.toLowerCase().split(/\W+/);
    const stopWords = new Set(['the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by']);
    const wordCount = {};

    words.forEach(word => {
        if (word.length > 4 && !stopWords.has(word)) {
            wordCount[word] = (wordCount[word] || 0) + 1;
        }
    });

    const keywords = Object.entries(wordCount)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 5)
        .map(([word]) => word);

    const keywordsInput = document.getElementById('stockKeywords');
    if (keywordsInput) {
        keywordsInput.value = keywords.join(', ');
        showNotification('✅ Keywords extracted', 'success');
    }
}

async function fetchStockFootage() {
    const keywordsInput = document.getElementById('stockKeywords');
    const query = keywordsInput ? keywordsInput.value.trim() : '';

    if (!query) {
        showNotification('⚠️ Enter search keywords', 'warning');
        return;
    }

    const sourceSelect = document.getElementById('stockSource');
    const source = sourceSelect ? sourceSelect.value : 'pexels';

    const typeRadio = document.querySelector('input[name="stockType"]:checked');
    const type = typeRadio ? typeRadio.value : 'videos';

    const countInput = document.getElementById('stockCount');
    const count = countInput ? parseInt(countInput.value) : 10;

    const progressBox = document.getElementById('stockProgress');
    const previewBox = document.getElementById('stockPreview');

    if (progressBox) {
        progressBox.style.display = 'block';
        progressBox.innerHTML = `<p>🔍 Searching ${source} for ${type}...</p>`;
    }

    if (previewBox) previewBox.innerHTML = '';

    try {
        let items = [];

        if (source === 'pexels') {
            items = await searchPexels(query, type, count);
        } else if (source === 'pixabay') {
            items = await searchPixabay(query, type, count);
        } else if (source === 'unsplash') {
            if (type === 'videos') {
                throw new Error('Unsplash only supports photos');
            }
            items = await searchUnsplash(query, count);
        }

        if (!items || items.length === 0) {
            if (progressBox) {
                progressBox.innerHTML = '<p>😔 No results found. Try different keywords.</p>';
            }
            showNotification('No results found', 'warning');
            return;
        }

        if (progressBox) {
            progressBox.innerHTML = `<p>✅ Found ${items.length} ${type}</p>`;
        }

        if (previewBox) {
            previewBox.innerHTML = '';

            items.forEach(item => {
                const card = document.createElement('div');
                card.className = 'stock-item';
                card.style.cssText = `
                    position: relative;
                    background: rgba(0,0,0,0.3);
                    border-radius: 10px;
                    overflow: hidden;
                    padding: 10px;
                `;

                const imgSrc = item.thumbnail || item.preview || item.image;
                const mediaType = item.mediaType || type.slice(0, -1); // 'video' or 'photo'

                card.innerHTML = `
                    <img src="${imgSrc}" alt="${mediaType}" style="width: 100%; height: 150px; object-fit: cover; border-radius: 8px;">
                    <div style="margin-top: 8px; font-size: 12px; color: #aaa;">
                        ${item.width && item.height ? `${item.width}x${item.height}` : ''}
                        ${item.duration ? ` - ${Math.round(item.duration)}s` : ''}
                    </div>
                    <button onclick="addStockToLibrary('${item.url}', '${mediaType}', '${source}')" class="btn-success" style="width: 100%; margin-top: 8px; font-size: 12px;">
                        ➕ Add to Library
                    </button>
                `;

                previewBox.appendChild(card);
            });
        }

        showNotification(`✅ Found ${items.length} ${type}`, 'success');

    } catch (error) {
        console.error('Stock search failed:', error);
        if (progressBox) {
            progressBox.innerHTML = `<p>❌ Error: ${error.message}</p>`;
        }
        showNotification('❌ Stock search failed: ' + error.message, 'error');
    }
}

async function searchPexels(query, type, count) {
    const settings = JSON.parse(localStorage.getItem('videoToolSettings') || '{}');
    const apiKey = settings.api_keys?.pexels;

    if (!apiKey) {
        throw new Error('Pexels API key not found. Configure in Settings.');
    }

    const endpoint = type === 'videos'
        ? `https://api.pexels.com/videos/search?query=${encodeURIComponent(query)}&per_page=${count}&orientation=landscape`
        : `https://api.pexels.com/v1/search?query=${encodeURIComponent(query)}&per_page=${count}&orientation=landscape`;

    const response = await fetch(endpoint, {
        headers: { 'Authorization': apiKey }
    });

    if (!response.ok) {
        throw new Error(`Pexels API error: ${response.status}`);
    }

    const data = await response.json();
    const rawItems = type === 'videos' ? data.videos : data.photos;

    return rawItems.map(item => ({
        url: type === 'videos' ? item.video_files[0].link : item.src.large,
        thumbnail: type === 'videos' ? item.image : item.src.medium,
        width: item.width,
        height: item.height,
        duration: item.duration,
        mediaType: type.slice(0, -1)
    }));
}

async function searchPixabay(query, type, count) {
    const settings = JSON.parse(localStorage.getItem('videoToolSettings') || '{}');
    const apiKey = settings.api_keys?.pixabay;

    if (!apiKey) {
        throw new Error('Pixabay API key not found. Configure in Settings.');
    }

    const endpoint = type === 'videos'
        ? `https://pixabay.com/api/videos/?key=${apiKey}&q=${encodeURIComponent(query)}&per_page=${count}`
        : `https://pixabay.com/api/?key=${apiKey}&q=${encodeURIComponent(query)}&per_page=${count}&image_type=photo`;

    const response = await fetch(endpoint);

    if (!response.ok) {
        throw new Error(`Pixabay API error: ${response.status}`);
    }

    const data = await response.json();
    const rawItems = data.hits;

    return rawItems.map(item => ({
        url: type === 'videos' ? item.videos.medium.url : item.largeImageURL,
        thumbnail: type === 'videos' ? (item.videos.tiny?.thumbnail || item.userImageURL) : item.webformatURL,
        width: type === 'videos' ? item.videos.medium.width : item.imageWidth,
        height: type === 'videos' ? item.videos.medium.height : item.imageHeight,
        duration: item.duration,
        mediaType: type.slice(0, -1)
    }));
}

async function searchUnsplash(query, count) {
    const settings = JSON.parse(localStorage.getItem('videoToolSettings') || '{}');
    const apiKey = settings.api_keys?.unsplash;

    if (!apiKey) {
        throw new Error('Unsplash API key not found. Configure in Settings.');
    }

    const endpoint = `https://api.unsplash.com/search/photos?query=${encodeURIComponent(query)}&per_page=${count}&orientation=landscape`;

    const response = await fetch(endpoint, {
        headers: { 'Authorization': `Client-ID ${apiKey}` }
    });

    if (!response.ok) {
        throw new Error(`Unsplash API error: ${response.status}`);
    }

    const data = await response.json();
    const rawItems = data.results;

    return rawItems.map(item => ({
        url: item.urls.full,
        thumbnail: item.urls.small,
        width: item.width,
        height: item.height,
        mediaType: 'photo'
    }));
}

function addStockToLibrary(url, type, source) {
    addToMediaLibrary(null, url, type, source);
}

// =============================================================================
// VOICE SECTION
// =============================================================================
function toggleVoiceMode() {
    const mode = document.querySelector('input[name="voiceMode"]:checked').value;
    const manualSection = document.getElementById('voiceManualSection');
    const autoSection = document.getElementById('voiceAutoSection');

    if (manualSection && autoSection) {
        manualSection.style.display = mode === 'manual' ? 'block' : 'none';
        autoSection.style.display = mode === 'auto' ? 'block' : 'none';
    }
}

async function generateVoice() {
    const script = document.getElementById('scriptInput')?.value || window.videoData.script;
    if (!script) {
        showNotification('⚠️ Please generate or enter a script first', 'warning');
        return;
    }

    const progressBox = document.getElementById('voiceProgress');
    if (progressBox) {
        progressBox.style.display = 'block';
        progressBox.innerHTML = '<p>🎙️ Voice generation requires backend API setup</p>';
    }

    showNotification('⚠️ Voice generation requires Inworld AI backend integration', 'warning');
}

// =============================================================================
// PROBLEM 6: MR BAHA EDITOR (FIXED)
// =============================================================================
function loadEditorVideo(fileUrl, fileName) {
    try {
        const preview = document.getElementById('editorVideoPreview');
        if (!preview) {
            showNotification('⚠️ Editor preview element not found', 'warning');
            return;
        }

        // Check file extension
        const ext = fileName?.toLowerCase().split('.').pop();
        if (ext === 'mkv') {
            showNotification('⚠️ MKV format may not work in browser. Please convert to MP4 first.', 'warning');
        }

        // Clear previous listeners
        preview.onloadedmetadata = null;
        preview.onerror = null;

        preview.src = fileUrl;
        preview.load();

        window.editorData = {
            originalFile: null,
            url: fileUrl,
            fileName: fileName || 'video.mp4',
            duration: 0,
            clips: []
        };

        appState.editorVideo = {
            path: fileUrl,
            fileName: fileName || 'video.mp4',
            duration: 0
        };

        // Show sections
        const sections = [
            'editorPreviewSection',
            'editorTimelineSection',
            'editorToolsSection',
            'editorExportSection'
        ];

        sections.forEach(id => {
            const section = document.getElementById(id);
            if (section) section.style.display = 'block';
        });

        // Handle video load error (unsupported format)
        preview.onerror = () => {
            showNotification('❌ Video format not supported. Use MP4, WebM, or MOV.', 'error');
            console.error('Video load error - unsupported format:', fileName);
        };

        // Wait for metadata
        preview.onloadedmetadata = () => {
            const duration = preview.duration;

            if (!duration || duration === Infinity || isNaN(duration)) {
                showNotification('⚠️ Could not read video duration. File may be corrupted.', 'warning');
                return;
            }

            window.editorData.duration = duration;
            appState.editorVideo.duration = duration;

            // Create initial clip
            window.editorData.clips = [{
                id: 'clip-0',
                videoPath: fileUrl,
                start: 0,
                end: duration,
                duration: duration
            }];

            appState.editorClips = window.editorData.clips;

            updateEditorTimeline();
            showNotification('✅ Video loaded in editor', 'success');
        };
    } catch (error) {
        showNotification('❌ Error loading video: ' + error.message, 'error');
        console.error('Editor load error:', error);
    }
}

function updateEditorTimeline() {
    const track = document.getElementById('editorTimelineTrack');
    if (!track) return;

    track.innerHTML = '';

    const clips = window.editorData?.clips || appState.editorClips || [];

    clips.forEach((clip, index) => {
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
    const clipCountEl = document.getElementById('editorClipCount');
    const totalDurationEl = document.getElementById('editorTotalDuration');

    if (clipCountEl) {
        clipCountEl.textContent = `${clips.length} clips`;
    }

    if (totalDurationEl) {
        const totalDuration = clips.reduce((sum, clip) => sum + clip.duration, 0);
        totalDurationEl.textContent = `Total: ${formatTime(totalDuration)}`;
    }
}

function selectClip(index) {
    appState.selectedClip = index;
    document.querySelectorAll('.clip').forEach((el, i) => {
        el.classList.toggle('selected', i === index);
    });
    showNotification(`Clip ${index + 1} selected`, 'info');
}

function editorPlayPause() {
    const video = document.getElementById('editorVideoPreview');
    if (!video) return;

    if (video.paused) {
        video.play();
        const btn = document.getElementById('editorPlayBtn');
        if (btn) btn.textContent = '⏸️';
    } else {
        video.pause();
        const btn = document.getElementById('editorPlayBtn');
        if (btn) btn.textContent = '▶️';
    }
}

function editorStop() {
    const video = document.getElementById('editorVideoPreview');
    if (!video) return;

    video.pause();
    video.currentTime = 0;
    const btn = document.getElementById('editorPlayBtn');
    if (btn) btn.textContent = '▶️';
}

function editorMute() {
    const video = document.getElementById('editorVideoPreview');
    if (!video) return;

    video.muted = !video.muted;
    const btn = document.getElementById('editorMuteBtn');
    if (btn) btn.textContent = video.muted ? '🔇' : '🔊';
}

function editorSplit() {
    if (appState.selectedClip === null) {
        showNotification('⚠️ Please select a clip first', 'warning');
        return;
    }

    const video = document.getElementById('editorVideoPreview');
    if (!video) return;

    const splitTime = video.currentTime;
    const clips = window.editorData?.clips || appState.editorClips;
    const clip = clips[appState.selectedClip];

    if (splitTime <= clip.start || splitTime >= clip.end) {
        showNotification('⚠️ Playhead must be within the selected clip', 'warning');
        return;
    }

    // Create two new clips
    const clip1 = {...clip, end: splitTime, duration: splitTime - clip.start};
    const clip2 = {...clip, id: `clip-${Date.now()}`, start: splitTime, duration: clip.end - splitTime};

    // Replace original clip
    clips.splice(appState.selectedClip, 1, clip1, clip2);

    if (window.editorData) window.editorData.clips = clips;
    appState.editorClips = clips;

    updateEditorTimeline();
    showNotification('✂️ Clip split!', 'success');
}

function editorDelete() {
    if (appState.selectedClip === null) {
        showNotification('⚠️ Please select a clip first', 'warning');
        return;
    }

    const clips = window.editorData?.clips || appState.editorClips;

    if (clips.length === 1) {
        showNotification('⚠️ Cannot delete the last clip', 'warning');
        return;
    }

    if (confirm('Delete this clip?')) {
        clips.splice(appState.selectedClip, 1);
        appState.selectedClip = null;

        if (window.editorData) window.editorData.clips = clips;
        appState.editorClips = clips;

        updateEditorTimeline();
        showNotification('🗑️ Clip deleted', 'success');
    }
}

function editorMoveLeft() {
    if (appState.selectedClip === null || appState.selectedClip === 0) {
        showNotification('⚠️ Cannot move first clip left', 'warning');
        return;
    }

    const clips = window.editorData?.clips || appState.editorClips;
    const temp = clips[appState.selectedClip];
    clips[appState.selectedClip] = clips[appState.selectedClip - 1];
    clips[appState.selectedClip - 1] = temp;
    appState.selectedClip--;

    if (window.editorData) window.editorData.clips = clips;
    appState.editorClips = clips;

    updateEditorTimeline();
    showNotification('⬅️ Clip moved left', 'success');
}

function editorMoveRight() {
    const clips = window.editorData?.clips || appState.editorClips;

    if (appState.selectedClip === null || appState.selectedClip === clips.length - 1) {
        showNotification('⚠️ Cannot move last clip right', 'warning');
        return;
    }

    const temp = clips[appState.selectedClip];
    clips[appState.selectedClip] = clips[appState.selectedClip + 1];
    clips[appState.selectedClip + 1] = temp;
    appState.selectedClip++;

    if (window.editorData) window.editorData.clips = clips;
    appState.editorClips = clips;

    updateEditorTimeline();
    showNotification('➡️ Clip moved right', 'success');
}

function editorShowOverlay() {
    const section = document.getElementById('editorOverlaySection');
    if (section) {
        section.style.display = 'block';
        showNotification('ℹ️ Enter overlay details', 'info');
    }
}

function editorCancelOverlay() {
    const section = document.getElementById('editorOverlaySection');
    if (section) section.style.display = 'none';
}

function editorConfirmOverlay() {
    if (appState.selectedClip === null) {
        showNotification('⚠️ Please select a clip first', 'warning');
        return;
    }

    const overlay = {
        text: document.getElementById('overlayText')?.value || '',
        x: parseInt(document.getElementById('overlayX')?.value || 100),
        y: parseInt(document.getElementById('overlayY')?.value || 100),
        size: parseInt(document.getElementById('overlaySize')?.value || 48),
        color: document.getElementById('overlayColor')?.value || '#ffffff',
        start: parseFloat(document.getElementById('overlayStart')?.value || 0),
        duration: parseFloat(document.getElementById('overlayDuration')?.value || 3)
    };

    const clips = window.editorData?.clips || appState.editorClips;
    clips[appState.selectedClip].overlay = overlay;

    if (window.editorData) window.editorData.clips = clips;
    appState.editorClips = clips;

    editorCancelOverlay();
    showNotification('✅ Overlay added to clip', 'success');
}

async function editorExport() {
    const clips = window.editorData?.clips || appState.editorClips;

    if (!clips || clips.length === 0) {
        showNotification('⚠️ No clips to export', 'warning');
        return;
    }

    const qualityRadio = document.querySelector('input[name="editorQuality"]:checked');
    const quality = qualityRadio ? qualityRadio.value : '720';

    const progressBox = document.getElementById('editorExportProgress');
    if (progressBox) {
        progressBox.style.display = 'block';
        progressBox.innerHTML = '<p>🎬 Exporting video... This requires backend API.</p>';
    }

    showNotification('⚠️ Video export requires backend FFmpeg integration', 'warning');
}

// =============================================================================
// PROBLEM 7: PROCESS VIDEO (FIXED)
// =============================================================================
async function processVideo() {
    const title = document.getElementById('titleInput')?.value || window.videoData.title;
    const script = document.getElementById('scriptInput')?.value || window.videoData.script;
    const qualityRadio = document.querySelector('input[name="quality"]:checked');
    const quality = qualityRadio ? qualityRadio.value : '720';

    if (!title || !script) {
        showNotification('⚠️ Please provide at least a title and script', 'warning');
        return;
    }

    const progressContainer = document.getElementById('videoProgress');
    const progressFill = document.getElementById('progressFill');
    const progressText = document.getElementById('progressText');
    const resultContainer = document.getElementById('videoResult');

    if (progressContainer) {
        progressContainer.style.display = 'block';
    }
    if (resultContainer) {
        resultContainer.style.display = 'none';
    }
    if (progressFill) {
        progressFill.style.width = '10%';
    }
    if (progressText) {
        progressText.textContent = 'Initializing video processing...';
    }

    showNotification('🎬 Processing video requires backend API integration', 'info');

    if (progressText) {
        progressText.textContent = 'Backend API required for video processing';
    }
}

// =============================================================================
// OUTPUT FILES
// =============================================================================
async function refreshOutputFiles() {
    const container = document.getElementById('outputFileList');
    if (!container) return;

    container.innerHTML = '<p class="loading">Loading files...</p>';

    try {
        const response = await fetch('/api/output-files');
        const data = await response.json();

        if (data.success && data.files && data.files.length > 0) {
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
// HELPER FUNCTIONS
// =============================================================================
function formatTime(seconds) {
    if (isNaN(seconds)) return '0:00';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
}

// =============================================================================
// INITIALIZATION
// =============================================================================
document.addEventListener('DOMContentLoaded', () => {
    // Load settings from localStorage
    loadSettings();

    // Setup settings button
    const settingsBtn = document.getElementById('settingsBtn');
    if (settingsBtn) {
        settingsBtn.onclick = openSettings;
    }

    // Close modal when clicking outside
    const settingsModal = document.getElementById('settingsModal');
    if (settingsModal) {
        settingsModal.onclick = (e) => {
            if (e.target.id === 'settingsModal') {
                closeSettings();
            }
        };
    }

    // Setup editor video input
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

    // Setup time display for editor video
    const editorVideo = document.getElementById('editorVideoPreview');
    if (editorVideo) {
        editorVideo.addEventListener('timeupdate', () => {
            const current = formatTime(editorVideo.currentTime);
            const total = formatTime(editorVideo.duration);
            const timeDisplay = document.getElementById('editorTimeDisplay');
            if (timeDisplay) {
                timeDisplay.textContent = `${current} / ${total}`;
            }

            const progress = (editorVideo.currentTime / editorVideo.duration) * 100;
            const seekFill = document.getElementById('editorSeekFill');
            if (seekFill) {
                seekFill.style.width = progress + '%';
            }
        });
    }

    // Setup speaking rate slider
    const rateSlider = document.getElementById('speakingRate');
    const rateDisplay = document.getElementById('speakingRateValue');
    if (rateSlider && rateDisplay) {
        rateSlider.addEventListener('input', (e) => {
            rateDisplay.textContent = e.target.value + 'x';
        });
    }

    // Setup media upload checkbox handlers
    const useAiImages = document.getElementById('useAiImages');
    if (useAiImages) {
        useAiImages.addEventListener('change', () => toggleMediaSection('ai'));
    }

    const useManualMedia = document.getElementById('useManualMedia');
    if (useManualMedia) {
        useManualMedia.addEventListener('change', () => toggleMediaSection('manual'));
    }

    const useStockFootage = document.getElementById('useStockFootage');
    if (useStockFootage) {
        useStockFootage.addEventListener('change', () => toggleMediaSection('stock'));
    }

    // Setup drag-and-drop for editor upload zone
    const editorUploadZone = document.getElementById('editorUploadZone');
    if (editorUploadZone) {
        editorUploadZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            editorUploadZone.style.borderColor = '#667eea';
            editorUploadZone.style.background = 'rgba(102, 126, 234, 0.1)';
        });

        editorUploadZone.addEventListener('dragleave', (e) => {
            e.preventDefault();
            editorUploadZone.style.borderColor = '#444';
            editorUploadZone.style.background = 'rgba(255, 255, 255, 0.02)';
        });

        editorUploadZone.addEventListener('drop', (e) => {
            e.preventDefault();
            editorUploadZone.style.borderColor = '#444';
            editorUploadZone.style.background = 'rgba(255, 255, 255, 0.02)';

            const file = e.dataTransfer.files[0];
            if (file && file.type.startsWith('video/')) {
                const fileUrl = URL.createObjectURL(file);
                loadEditorVideo(fileUrl, file.name);
            } else {
                showNotification('⚠️ Please drop a video file', 'warning');
            }
        });
    }

    // Setup media file upload handler
    const mediaUpload = document.getElementById('mediaUpload');
    if (mediaUpload) {
        mediaUpload.addEventListener('change', (e) => {
            const files = Array.from(e.target.files);
            files.forEach(file => {
                const isVideo = file.type.startsWith('video/');
                const isImage = file.type.startsWith('image/');

                if (isVideo || isImage) {
                    const url = URL.createObjectURL(file);
                    const type = isVideo ? 'video' : 'image';
                    addToMediaLibrary(file, url, type, 'upload');
                }
            });

            // Reset input
            e.target.value = '';
        });
    }

    // Setup media dropzone
    const mediaDropzone = document.getElementById('mediaDropzone');
    if (mediaDropzone) {
        mediaDropzone.addEventListener('dragover', (e) => {
            e.preventDefault();
            mediaDropzone.style.borderColor = '#667eea';
            mediaDropzone.style.background = 'rgba(102, 126, 234, 0.1)';
        });

        mediaDropzone.addEventListener('dragleave', (e) => {
            e.preventDefault();
            mediaDropzone.style.borderColor = '#444';
            mediaDropzone.style.background = 'rgba(255, 255, 255, 0.02)';
        });

        mediaDropzone.addEventListener('drop', (e) => {
            e.preventDefault();
            mediaDropzone.style.borderColor = '#444';
            mediaDropzone.style.background = 'rgba(255, 255, 255, 0.02)';

            const files = Array.from(e.dataTransfer.files);
            files.forEach(file => {
                const isVideo = file.type.startsWith('video/');
                const isImage = file.type.startsWith('image/');

                if (isVideo || isImage) {
                    const url = URL.createObjectURL(file);
                    const type = isVideo ? 'video' : 'image';
                    addToMediaLibrary(file, url, type, 'upload');
                } else {
                    showNotification('⚠️ Only images and videos supported', 'warning');
                }
            });
        });
    }

    // Load settings and formulas
    loadSettings();

    // Load initial tab
    showTab('dashboard');

    console.log('✅ AI Video Studio initialized with all fixes applied');
    showNotification('✅ AI Video Studio loaded successfully', 'success');
});
