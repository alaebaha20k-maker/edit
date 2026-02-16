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
    mediaLibrary: [],
    niches: [],
    selectedNiche: '',
    lastGenerationTime: 0,  // Track last API call for rate limiting
    generationCooldown: 15000  // 15 seconds cooldown between generations
};

// Global video data
window.videoData = {
    title: '',
    script: '',
    mediaFiles: [],
    mediaLibrary: [], // Media library reference
    audioFile: null,
    backgroundMusic: null // Background music file
};

// Selection state for multi-select
const selectionState = {
    selectedMedia: new Set(),
    selectedVoices: new Set(),
    isSelectionMode: false
};

// Global editor data
window.editorData = {
    originalFile: null,
    url: null,
    clips: []
};

// =============================================================================
// UTILITY FUNCTIONS
// =============================================================================
const escapeHtml = (text) => {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
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
    } else if (tabName === 'generator') {
        checkForExistingScript();
    }
}

// Check for existing script file when AI Generator tab is opened
async function checkForExistingScript() {
    try {
        const response = await fetch('/api/check-script');
        const data = await response.json();

        if (data.success && data.has_script) {
            // Script exists - populate the UI
            displayExistingScript(data);
        } else {
            // No script exists - make sure UI is in generation mode
            ensureGenerationMode();
        }
    } catch (error) {
        console.error('Error checking for script:', error);
        // On error, just ensure generation mode is available
        ensureGenerationMode();
    }
}

// Display existing script in the UI
function displayExistingScript(scriptData) {
    // Populate script input
    const scriptInput = document.getElementById('scriptInput');
    if (scriptInput) {
        scriptInput.value = scriptData.script;
        window.videoData.script = scriptData.script;
        appState.generatedScript = scriptData.script;
    }

    // Show script stats
    const statsBox = document.getElementById('scriptStats');
    if (statsBox) {
        statsBox.style.display = 'block';
        statsBox.innerHTML = `
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 15px;">
                <div>
                    <strong>📏 Length:</strong><br>${scriptData.length.toLocaleString()} chars
                </div>
                <div>
                    <strong>📝 Words:</strong><br>${scriptData.words.toLocaleString()}
                </div>
                <div>
                    <strong>📄 File:</strong><br>${scriptData.script_filename || 'script.txt'}
                </div>
                <div>
                    <strong>📅 Modified:</strong><br>${scriptData.modified || 'Recently'}
                </div>
            </div>
        `;
    }

    // Show download button
    const downloadSection = document.getElementById('scriptDownloadSection');
    if (downloadSection) {
        downloadSection.style.display = 'block';
    }

    // Show voice generation section
    const voiceSection = document.getElementById('voiceGenerationSection');
    if (voiceSection) {
        voiceSection.style.display = 'block';
    }
}

// Ensure the UI is in generation mode (when no script exists)
function ensureGenerationMode() {
    // Make sure script input is empty or in manual mode
    const scriptManualSection = document.getElementById('scriptManualSection');
    const scriptAutoSection = document.getElementById('scriptAutoSection');

    // Check which mode is selected
    const scriptMode = document.querySelector('input[name="scriptMode"]:checked')?.value || 'manual';

    if (scriptMode === 'manual') {
        if (scriptManualSection) scriptManualSection.style.display = 'block';
        if (scriptAutoSection) scriptAutoSection.style.display = 'none';
    } else {
        if (scriptManualSection) scriptManualSection.style.display = 'none';
        if (scriptAutoSection) scriptAutoSection.style.display = 'block';
    }

    // Hide voice generation section until script is ready
    const voiceSection = document.getElementById('voiceGenerationSection');
    if (voiceSection && (!window.videoData.script || window.videoData.script.trim() === '')) {
        voiceSection.style.display = 'none';
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
                const directorGeminiKey = document.getElementById('directorGeminiKey');
                const replicateKey = document.getElementById('replicateKey');
                const inworldKey = document.getElementById('inworldKey');
                const inworldSecret = document.getElementById('inworldSecret');
                const pexelsKey = document.getElementById('pexelsKey');
                const pixabayKey = document.getElementById('pixabayKey');
                const unsplashKey = document.getElementById('unsplashKey');

                if (geminiKey) geminiKey.value = settings.api_keys.gemini || '';
                if (directorGeminiKey) directorGeminiKey.value = settings.api_keys.director_gemini || '';
                if (replicateKey) replicateKey.value = settings.api_keys.replicate || '';
                if (inworldKey) inworldKey.value = settings.api_keys.inworld || '';
                if (inworldSecret) inworldSecret.value = settings.api_keys.inworld_secret || '';
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

            // Load selected niche
            if (settings.selectedNiche) {
                appState.selectedNiche = settings.selectedNiche;
            }

            // Load niches from backend
            loadNiches();

            console.log('✅ Settings loaded from localStorage');
        }
    } catch (error) {
        console.error('Load settings failed:', error);
        showNotification('⚠️ Error loading settings', 'warning');
    }
};

const saveSettings = async () => {
    try {
        const settings = {
            api_keys: {
                gemini: document.getElementById('geminiKey')?.value || '',
                director_gemini: document.getElementById('directorGeminiKey')?.value || '',
                replicate: document.getElementById('replicateKey')?.value || '',
                inworld: document.getElementById('inworldKey')?.value || '',
                inworld_secret: document.getElementById('inworldSecret')?.value || '',
                pexels: document.getElementById('pexelsKey')?.value || '',
                pixabay: document.getElementById('pixabayKey')?.value || '',
                unsplash: document.getElementById('unsplashKey')?.value || ''
            },
            title_formulas: appState.titleFormulas || [],
            script_formulas: appState.scriptFormulas || [],
            selectedNiche: appState.selectedNiche || ''
        };

        // Save to localStorage
        localStorage.setItem('videoToolSettings', JSON.stringify(settings));
        appState.settings = settings;

        // Save ALL API keys to backend via the correct endpoint
        try {
            const response = await fetch('/api/settings/api-keys', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    gemini: settings.api_keys.gemini,
                    director_gemini: settings.api_keys.director_gemini,
                    replicate: settings.api_keys.replicate,
                    inworld: settings.api_keys.inworld,
                    inworld_secret: settings.api_keys.inworld_secret,
                    pexels: settings.api_keys.pexels,
                    pixabay: settings.api_keys.pixabay
                })
            });

            if (!response.ok) {
                console.warn('Failed to save to backend:', await response.text());
            } else {
                console.log('✅ All API keys saved to backend successfully');
            }
        } catch (error) {
            console.warn('Failed to save to backend:', error);
        }

        showNotification('✅ Settings saved successfully!', 'success');
        closeSettings();

    } catch (error) {
        console.error('Save failed:', error);
        showNotification('❌ Failed to save: ' + error.message, 'error');
    }
};

// =============================================================================
// NICHE MANAGEMENT SYSTEM
// =============================================================================
async function loadNiches() {
    try {
        const response = await fetch('/api/niches');
        const data = await response.json();

        if (data.niches) {
            appState.niches = data.niches;
            renderNichesList(data.niches);
            updateNicheDropdown(data.niches);
        }
    } catch (error) {
        console.error('Failed to load niches:', error);
    }
}

async function createNiche() {
    const name = document.getElementById('newNicheName')?.value.trim();
    const language = document.getElementById('newNicheLanguage')?.value;
    const guidelines = document.getElementById('newNicheGuidelines')?.value.trim();

    if (!name || !language || !guidelines) {
        showNotification('⚠️ Please fill all niche fields', 'warning');
        return;
    }

    if (guidelines.length < 100) {
        showNotification('⚠️ Writing guidelines must be at least 100 characters', 'warning');
        return;
    }

    try {
        const response = await fetch('/api/niches', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                name: name,
                language: language,
                writing_guidelines: guidelines
            })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Failed to create niche');
        }

        showNotification('✅ Niche created successfully!', 'success');

        // Clear inputs
        document.getElementById('newNicheName').value = '';
        document.getElementById('newNicheGuidelines').value = '';

        // Reload niches
        await loadNiches();

        // Auto-select the new niche
        appState.selectedNiche = data.niche.id;
        const settings = JSON.parse(localStorage.getItem('videoToolSettings') || '{}');
        settings.selectedNiche = data.niche.id;
        localStorage.setItem('videoToolSettings', JSON.stringify(settings));

        updateNicheDropdown(appState.niches);

    } catch (error) {
        console.error('Create niche failed:', error);
        showNotification('❌ Failed to create niche: ' + error.message, 'error');
    }
}

function selectNiche() {
    const select = document.getElementById('nicheSelect');
    const nicheId = select?.value;

    if (nicheId) {
        appState.selectedNiche = nicheId;
        const settings = JSON.parse(localStorage.getItem('videoToolSettings') || '{}');
        settings.selectedNiche = nicheId;
        localStorage.setItem('videoToolSettings', JSON.stringify(settings));

        showNotification('✅ Niche selected!', 'success');
    }
}

async function deleteNiche(nicheId) {
    if (!confirm('Delete this niche? This cannot be undone.')) return;

    try {
        const response = await fetch(`/api/niches/${nicheId}`, {
            method: 'DELETE'
        });

        if (!response.ok) {
            throw new Error('Failed to delete niche');
        }

        showNotification('✅ Niche deleted', 'success');

        // If this was the selected niche, clear selection
        if (appState.selectedNiche === nicheId) {
            appState.selectedNiche = '';
            const settings = JSON.parse(localStorage.getItem('videoToolSettings') || '{}');
            settings.selectedNiche = '';
            localStorage.setItem('videoToolSettings', JSON.stringify(settings));
        }

        // Reload niches
        await loadNiches();

    } catch (error) {
        console.error('Delete niche failed:', error);
        showNotification('❌ Failed to delete niche: ' + error.message, 'error');
    }
}

async function editNiche(nicheId) {
    try {
        const res = await fetch(`/api/niches/${nicheId}`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Failed to load niche');
        const n = data.niche;

        document.getElementById('editNicheId').value = n.id;
        document.getElementById('editNicheName').value = n.name || '';
        document.getElementById('editNicheLanguage').value = n.language || 'English';
        document.getElementById('editNicheGuidelines').value = n.writing_guidelines || '';
        updateEditNicheCharCount();

        const form = document.getElementById('nicheEditForm');
        form.style.display = 'block';
        form.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    } catch (error) {
        showNotification('❌ Failed to load niche: ' + error.message, 'error');
    }
}

function updateEditNicheCharCount() {
    const val = document.getElementById('editNicheGuidelines').value;
    const el = document.getElementById('editNicheCharCount');
    if (el) {
        el.textContent = val.length.toLocaleString() + ' chars';
        el.style.color = val.length < 100 ? '#f87171' : '#4ade80';
    }
}

async function saveNicheEdit() {
    const nicheId = document.getElementById('editNicheId').value;
    const name = document.getElementById('editNicheName').value.trim();
    const language = document.getElementById('editNicheLanguage').value;
    const guidelines = document.getElementById('editNicheGuidelines').value.trim();

    if (!name) { showNotification('⚠️ Niche name is required', 'warning'); return; }
    if (guidelines.length < 100) { showNotification('⚠️ Writing guidelines must be at least 100 characters', 'warning'); return; }

    try {
        const res = await fetch(`/api/niches/${nicheId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, language, writing_guidelines: guidelines })
        });
        const data = await res.json();
        if (!res.ok || !data.success) throw new Error(data.error || 'Update failed');

        showNotification(`✅ Niche "${name}" updated!`, 'success');
        cancelNicheEdit();
        await loadNiches();
    } catch (error) {
        showNotification('❌ Failed to update niche: ' + error.message, 'error');
    }
}

function cancelNicheEdit() {
    const form = document.getElementById('nicheEditForm');
    if (form) form.style.display = 'none';
}

function renderNichesList(niches) {
    const container = document.getElementById('nichesList');
    if (!container) return;

    if (!niches || niches.length === 0) {
        container.innerHTML = '<p style="color: #888;">No niches created yet. Create one above to get started!</p>';
        return;
    }

    container.innerHTML = `
        <h4 style="margin-bottom: 10px;">Existing Niches:</h4>
        ${niches.map(n => `
            <div class="formula-item" style="background: rgba(102, 126, 234, 0.1); padding: 15px; margin: 10px 0; border-radius: 8px; border-left: 4px solid ${appState.selectedNiche === n.id ? '#667eea' : '#ccc'};">
                <div style="display: flex; justify-content: space-between; align-items: start; gap: 10px;">
                    <div style="flex: 1; min-width: 0;">
                        <strong style="color: #667eea;">${n.name}</strong>
                        ${appState.selectedNiche === n.id ? ' <span style="background: #667eea; color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px;">ACTIVE</span>' : ''}
                        <p style="color: #aaa; margin: 5px 0; font-size: 13px;">Language: ${n.language} &nbsp;·&nbsp; ${n.writing_guidelines ? n.writing_guidelines.length.toLocaleString() : 0} chars</p>
                        <p style="color: #999; font-size: 12px; margin-top: 8px;">${(n.writing_guidelines || '').substring(0, 150)}${(n.writing_guidelines || '').length > 150 ? '...' : ''}</p>
                    </div>
                    <div style="display:flex; gap:8px; flex-shrink:0;">
                        <button onclick="editNiche('${n.id}')" class="btn-secondary" style="padding: 6px 12px; font-size: 13px;">✏️ Edit</button>
                        <button onclick="deleteNiche('${n.id}')" class="btn-secondary" style="padding: 6px 12px; font-size: 13px; background: rgba(239,68,68,0.2); color: #fca5a5;">🗑️</button>
                    </div>
                </div>
            </div>
        `).join('')}
    `;
}

function updateNicheDropdown(niches) {
    // Update settings dropdown
    const dropdown = document.getElementById('nicheSelect');
    if (dropdown) {
        dropdown.innerHTML = '<option value="">-- Select a niche --</option>';
        if (niches && niches.length > 0) {
            niches.forEach(n => {
                const selected = appState.selectedNiche === n.id ? 'selected' : '';
                dropdown.innerHTML += `<option value="${n.id}" ${selected}>${n.name} (${n.language})</option>`;
            });
        }
    }

    // ALSO update generator dropdown (for script generation page)
    const generatorDropdown = document.getElementById('generatorNicheSelect');
    if (generatorDropdown) {
        generatorDropdown.innerHTML = '<option value="">-- Select a niche --</option>';
        if (niches && niches.length > 0) {
            niches.forEach(n => {
                const selected = appState.selectedNiche === n.id ? 'selected' : '';
                generatorDropdown.innerHTML += `<option value="${n.id}" ${selected}>${n.name} (${n.language})</option>`;
            });
        }
    }
}

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
        appState.generatedScript = text;
        showNotification('✅ Script loaded from file', 'success');

        // Show voice section when script is uploaded
        showVoiceSectionIfScriptAvailable();
    }
}

// Helper function to show voice section when script is available
function showVoiceSectionIfScriptAvailable() {
    const script = window.videoData.script || appState.generatedScript;
    const voiceSection = document.getElementById('voiceGenerationSection');

    if (script && script.trim().length > 0 && voiceSection) {
        voiceSection.style.display = 'block';
        console.log('✅ Voice section shown - script available');
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

    // CHECK RATE LIMIT COOLDOWN
    const now = Date.now();
    const timeSinceLastGeneration = now - appState.lastGenerationTime;
    const remainingCooldown = appState.generationCooldown - timeSinceLastGeneration;

    if (appState.lastGenerationTime > 0 && remainingCooldown > 0) {
        const secondsLeft = Math.ceil(remainingCooldown / 1000);
        showNotification(`⏳ Please wait ${secondsLeft} seconds to avoid rate limits (Free tier: 5 videos/min max)`, 'warning');
        return;
    }

    const lengthSelect = document.getElementById('scriptLength');
    const selectedLength = lengthSelect ? parseInt(lengthSelect.value) : 10000;

    const resultBox = document.getElementById('scriptResult');
    const statsBox = document.getElementById('scriptStats');

    if (resultBox) {
        resultBox.style.display = 'block';
    }

    if (statsBox) {
        statsBox.style.display = 'none';
    }

    try {
        // Get niche from generator dropdown
        const nicheDropdown = document.getElementById('generatorNicheSelect');
        const selectedNicheId = nicheDropdown ? nicheDropdown.value : '';

        if (!selectedNicheId) {
            throw new Error('Please select a content niche first. Create niches in Settings.');
        }

        // 3-CHUNK MODE (Backend handles chunking with niche guidelines)
        if (resultBox) {
            resultBox.innerHTML = `<p>🤖 Generating script (3-Chunk Mode)...</p>
                <p style="color: #888; font-size: 0.9em;">Using niche writing guidelines. Please wait...</p>`;
        }

        // Update last generation time BEFORE making the call
        appState.lastGenerationTime = Date.now();

            const response = await fetch('/api/generate-script', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    title: title,
                    niche_id: selectedNicheId,
                    length: selectedLength
                })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || 'Script generation failed');
            }

            // Store script in both window.videoData AND the textarea input
            window.videoData.script = data.script;
            appState.generatedScript = data.script;

            // CRITICAL FIX: Populate the scriptInput textarea so it's available for all features
            const scriptInput = document.getElementById('scriptInput');
            if (scriptInput) {
                scriptInput.value = data.script;
            }

            // DON'T display full script (can be very long - just show success message)
            if (resultBox) {
                resultBox.innerHTML = `
                    <div style="text-align: center; padding: 30px; background: linear-gradient(135deg, rgba(76, 175, 80, 0.1), rgba(33, 150, 243, 0.1)); border-radius: 12px; margin: 20px 0;">
                        <div style="font-size: 48px; margin-bottom: 10px;">✅</div>
                        <h3 style="color: #4CAF50; margin-bottom: 10px;">Script Generated Successfully!</h3>
                        <p style="color: #888; margin-bottom: 20px;">Your script is ready for download below.</p>
                    </div>
                `;
            }

            // Display stats
            if (statsBox) {
                statsBox.style.display = 'block';
                statsBox.innerHTML = `
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px;">
                        <div>
                            <strong>📏 Length:</strong><br>${data.length.toLocaleString()} chars
                        </div>
                        <div>
                            <strong>📝 Words:</strong><br>${data.words.toLocaleString()}
                        </div>
                        <div>
                            <strong>📦 Chunks:</strong><br>${data.chunks_used} chunks (30/40/30)
                        </div>
                        <div>
                            <strong>⏱️ Time:</strong><br>${data.time.toFixed(1)}s
                        </div>
                        <div>
                            <strong>📄 File:</strong><br>${data.script_filename || 'script.txt'}
                        </div>
                    </div>
                `;
            }

            showNotification(`✅ Script generated! ${data.length.toLocaleString()} characters`, 'success');

            // Show download button
            const downloadSection = document.getElementById('scriptDownloadSection');
            if (downloadSection) {
                downloadSection.style.display = 'block';
            }

            // Show voice generation section
            const voiceSection = document.getElementById('voiceGenerationSection');
            if (voiceSection) {
                voiceSection.style.display = 'block';
            }

    } catch (error) {
        console.error('Script generation failed:', error);
        if (resultBox) {
            resultBox.innerHTML = `<p>❌ Error: ${error.message}</p>`;
        }
        showNotification('❌ Script generation failed: ' + error.message, 'error');
    }
}

// =============================================================================
// VOICE GENERATION
// =============================================================================
async function generateVoice() {
    const script = window.videoData.script || appState.generatedScript;

    if (!script) {
        showNotification('⚠️ Please generate a script first', 'warning');
        return;
    }

    // Try to get values from BOTH voice sections (Voice Generation Section OR Audio & Voice Section)
    const voiceModel = document.getElementById('voiceModel')?.value ||
                      document.getElementById('voiceSelectModel')?.value ||
                      'inworld-tts-1.5-max';

    const voiceId = document.getElementById('voiceId')?.value ||
                   document.getElementById('voiceSelect')?.value ||
                   'Hana';

    const voiceLanguage = document.getElementById('voiceLanguage')?.value ||
                         document.getElementById('voiceSelectLanguage')?.value ||
                         'en-US';

    const speakingRate = parseFloat(document.getElementById('speakingRate')?.value || '1.0');

    const progressBox = document.getElementById('voiceProgress');
    const resultBox = document.getElementById('voiceResult');
    const statsBox = document.getElementById('voiceStats');
    const voiceSection = document.getElementById('voiceGenerationSection');

    // Show voice section if hidden
    if (voiceSection) {
        voiceSection.style.display = 'block';
    }

    // Show progress
    if (progressBox) {
        progressBox.style.display = 'block';
        progressBox.innerHTML = `<p>🎙️ Generating voice...</p>
            <p style="color: #888; font-size: 0.9em;">Voice: ${voiceId} | Language: ${voiceLanguage} | Speed: ${speakingRate}x</p>
            <p style="color: #888; font-size: 0.9em;">This may take a minute for long scripts. Please wait...</p>`;
    }

    if (resultBox) {
        resultBox.style.display = 'none';
    }

    try {
        const response = await fetch('/api/generate-voice', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                script: script,
                voice_id: voiceId,
                model_id: voiceModel,
                language: voiceLanguage,
                speaking_rate: speakingRate
            })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Voice generation failed');
        }

        // Hide progress
        if (progressBox) {
            progressBox.style.display = 'none';
        }

        // Add to voice library
        addVoiceToLibrary({
            url: data.audio_url,
            path: data.audio_path,
            filename: data.audio_filename,
            duration: data.duration_seconds,
            chunks: data.chunks_count,
            voice: voiceId,
            language: voiceLanguage,
            model: voiceModel,
            speed: speakingRate,
            type: 'ai'
        });

        showNotification(`✅ Voice generated! Duration: ${Math.floor(data.duration_seconds / 60)}m ${Math.floor(data.duration_seconds % 60)}s`, 'success');

        // Update assembly stats
        updateAssemblyStats(data.duration_seconds);

    } catch (error) {
        console.error('Voice generation failed:', error);
        if (progressBox) {
            progressBox.innerHTML = `<p>❌ Error: ${error.message}</p>`;
        }
        showNotification('❌ Voice generation failed: ' + error.message, 'error');
    }
}

// =============================================================================
// VOICE LIBRARY MANAGEMENT
// =============================================================================

// Initialize voice library
if (!window.videoData.voiceLibrary) {
    window.videoData.voiceLibrary = [];
}

// Helper function to upload voice file to server
async function uploadVoiceToServer(file) {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('type', 'audio');

    const response = await fetch('/api/upload', {
        method: 'POST',
        body: formData
    });

    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || 'Voice upload failed');
    }

    return await response.json();
}

// Helper function to upload media file (image/video) to server
async function uploadMediaToServer(file, type) {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('type', type); // 'image' or 'video'

    const response = await fetch('/api/upload', {
        method: 'POST',
        body: formData
    });

    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || 'Media upload failed');
    }

    return await response.json();
}

// Toggle voice sections
function toggleVoiceSection(type) {
    if (type === 'ai') {
        const checked = document.getElementById('useAiVoice')?.checked;
        const section = document.getElementById('aiVoiceSection');
        if (section) section.style.display = checked ? 'block' : 'none';
    } else if (type === 'upload') {
        const checked = document.getElementById('useUploadVoice')?.checked;
        const section = document.getElementById('uploadVoiceSection');
        if (section) section.style.display = checked ? 'block' : 'none';
    }
}

// Add voice to library
function addVoiceToLibrary(voiceData) {
    window.videoData.voiceLibrary.push(voiceData);
    window.videoData.selectedVoiceIndex = window.videoData.voiceLibrary.length - 1; // Auto-select new voice
    renderVoiceLibrary();
}

// Render voice library with ranking (Step 2 only - All-in-one)
function renderVoiceLibrary() {
    const container = document.getElementById('voiceLibraryList');
    if (!container) return;

    const voices = window.videoData.voiceLibrary || [];

    if (voices.length === 0) {
        container.innerHTML = '<p style="color: #888; text-align: center; padding: 20px 0;">No voices yet. Generate AI voice or upload your own above.</p>';
        updateVoiceSelectionButtons();
        return;
    }

    // Calculate total duration of all voices
    const totalDuration = voices.reduce((sum, v) => sum + (parseFloat(v.duration) || 0), 0);
    const totalMinutes = Math.floor(totalDuration / 60);
    const totalSeconds = Math.floor(totalDuration % 60);

    container.innerHTML = `
        <div style="background: rgba(76, 175, 80, 0.1); padding: 12px; border-radius: 8px; margin-bottom: 15px; text-align: center;">
            <strong style="color: #4caf50;">📊 Total Voice Duration: ${totalMinutes}m ${totalSeconds}s</strong>
            <span style="color: #888; margin-left: 10px;">(${voices.length} voice${voices.length > 1 ? 's' : ''})</span>
        </div>
        ${voices.map((voice, index) => {
            const isSelected = selectionState.selectedVoices.has(index);
            const selectCheckbox = selectionState.isSelectionMode ? `
                <input type="checkbox" ${isSelected ? 'checked' : ''}
                    onchange="toggleVoiceSelection(${index})"
                    style="width: 20px; height: 20px; cursor: pointer; margin-right: 10px;">
            ` : '';
            const isPlaying = currentPlayingIndex === index;
            const duration = parseFloat(voice.duration);
            const isValidDuration = !isNaN(duration) && duration > 0;
            const minutes = isValidDuration ? Math.floor(duration / 60) : 0;
            const seconds = isValidDuration ? Math.floor(duration % 60) : 0;
            const durationStr = isValidDuration ? `${minutes}:${seconds.toString().padStart(2, '0')}` : '0:00';

            const typeLabel = voice.type === 'ai' ? '🤖 AI Generated' : '📤 Uploaded';
            const modelLabel = voice.model ? (voice.model.includes('max') ? 'Max Quality' : 'Mini Quality') : '';

            return `
                <div class="voice-item-draggable" draggable="${!selectionState.isSelectionMode}" data-index="${index}" style="
                    background: linear-gradient(135deg, rgba(102, 126, 234, 0.1), rgba(118, 75, 162, 0.1));
                    border: 2px solid ${isSelected ? '#ff4757' : '#667eea'};
                    padding: 15px;
                    border-radius: 8px;
                    display: flex;
                    align-items: center;
                    gap: 15px;
                    cursor: ${selectionState.isSelectionMode ? 'pointer' : 'grab'};
                    transition: all 0.3s;
                " ${selectionState.isSelectionMode ? `onclick="toggleVoiceSelection(${index})"` : ''}>
                    ${selectCheckbox}
                    <div style="
                        background: #667eea;
                        color: white;
                        width: 40px;
                        height: 40px;
                        border-radius: 50%;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        font-weight: bold;
                        font-size: 16px;
                        flex-shrink: 0;
                    ">#${index + 1}</div>
                    <button onclick="event.stopPropagation(); playVoicePreview(${index})" style="
                        background: ${isPlaying ? '#ff4757' : '#667eea'};
                        color: white;
                        border: none;
                        border-radius: 50%;
                        width: 50px;
                        height: 50px;
                        font-size: 20px;
                        cursor: pointer;
                        transition: all 0.3s;
                        flex-shrink: 0;
                    ">${isPlaying ? '⏹️' : '▶️'}</button>
                    <div style="flex: 1; min-width: 0;">
                        <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 5px; flex-wrap: wrap;">
                            <strong>${typeLabel}</strong>
                            ${voice.voice ? `<span style="color: #667eea;">• ${voice.voice}</span>` : ''}
                            ${voice.language ? `<span style="color: #888;">• ${voice.language}</span>` : ''}
                            ${modelLabel ? `<span style="color: #888;">• ${modelLabel}</span>` : ''}
                        </div>
                        <div style="color: #666; font-size: 0.9em;">
                            ⏱️ ${durationStr} ${voice.speed ? `• ${voice.speed}x speed` : ''} ${voice.chunks ? `• ${voice.chunks} chunks` : ''}
                        </div>
                        <div style="color: #888; font-size: 0.85em; margin-top: 3px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                            📄 ${voice.filename}
                        </div>
                    </div>
                    ${!selectionState.isSelectionMode ? `
                    <button onclick="event.stopPropagation(); downloadVoice(${index})" style="
                        background: #4caf50;
                        color: white;
                        border: none;
                        border-radius: 5px;
                        padding: 8px 12px;
                        cursor: pointer;
                        flex-shrink: 0;
                        font-size: 16px;
                    " title="Download voice">💾</button>
                    <button onclick="event.stopPropagation(); removeVoiceFromLibrary(${index})" style="
                        background: #ff4757;
                        color: white;
                        border: none;
                        border-radius: 5px;
                        padding: 8px 12px;
                        cursor: pointer;
                        flex-shrink: 0;
                    ">🗑️</button>
                    ` : ''}
                </div>
            `;
        }).join('')}
    `;

    // Add drag and drop event listeners (only when not in selection mode)
    if (!selectionState.isSelectionMode) {
        setupVoiceDragAndDrop();
    }

    // Update assembly stats with total duration
    if (totalDuration > 0) {
        updateAssemblyStats(totalDuration);
    }

    // Update selection buttons
    updateVoiceSelectionButtons();
}

// Remove voice from library
function removeVoiceFromLibrary(index) {
    if (confirm('Delete this voice from library?')) {
        window.videoData.voiceLibrary.splice(index, 1);
        renderVoiceLibrary();
        showNotification('✅ Voice deleted', 'success');
    }
}

// Multi-select functions for voices
function toggleVoiceSelectionMode() {
    selectionState.isSelectionMode = !selectionState.isSelectionMode;
    if (!selectionState.isSelectionMode) {
        selectionState.selectedVoices.clear();
    }
    renderVoiceLibrary();
}

function toggleVoiceSelection(index) {
    if (selectionState.selectedVoices.has(index)) {
        selectionState.selectedVoices.delete(index);
    } else {
        selectionState.selectedVoices.add(index);
    }
    renderVoiceLibrary();
}

function selectAllVoices() {
    const voices = window.videoData.voiceLibrary || [];
    voices.forEach((_, index) => {
        selectionState.selectedVoices.add(index);
    });
    renderVoiceLibrary();
}

function deleteSelectedVoices() {
    const count = selectionState.selectedVoices.size;
    if (count === 0) {
        showNotification('⚠️ No voices selected', 'warning');
        return;
    }

    if (!confirm(`Delete ${count} selected voice(s)?`)) return;

    // Convert Set to array and sort in descending order to delete from end first
    const indicesToDelete = Array.from(selectionState.selectedVoices).sort((a, b) => b - a);

    indicesToDelete.forEach(index => {
        window.videoData.voiceLibrary.splice(index, 1);
    });

    selectionState.selectedVoices.clear();
    selectionState.isSelectionMode = false;

    renderVoiceLibrary();
    showNotification(`✅ Deleted ${count} voice(s)`, 'success');
}

function updateVoiceSelectionButtons() {
    const container = document.getElementById('voiceSelectionButtons');
    if (!container) return;

    const voices = window.videoData.voiceLibrary || [];
    const hasVoices = voices.length > 0;
    const selectedCount = selectionState.selectedVoices.size;

    if (!hasVoices) {
        container.innerHTML = '';
        return;
    }

    if (selectionState.isSelectionMode) {
        container.innerHTML = `
            <div style="display: flex; gap: 10px; flex-wrap: wrap; padding: 10px; background: rgba(255, 71, 87, 0.1); border-radius: 8px;">
                <button onclick="selectAllVoices()" class="btn-secondary" style="font-size: 13px;">✅ Select All</button>
                <button onclick="deleteSelectedVoices()" class="btn-secondary" style="font-size: 13px;">🗑️ Delete Selected (${selectedCount})</button>
                <button onclick="toggleVoiceSelectionMode()" class="btn-secondary" style="font-size: 13px;">✖️ Cancel</button>
            </div>
        `;
    } else {
        container.innerHTML = `
            <button onclick="toggleVoiceSelectionMode()" class="btn-primary" style="font-size: 13px;">📋 Select Multiple</button>
        `;
    }
}

// Download voice from library
function downloadVoice(index) {
    const voice = window.videoData.voiceLibrary[index];
    if (!voice || !voice.url) {
        showNotification('❌ Voice file not found', 'error');
        return;
    }

    // Create a temporary link and trigger download
    const link = document.createElement('a');
    link.href = voice.url;
    link.download = voice.filename || 'voice.mp3';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    showNotification('💾 Downloading voice...', 'success');
}

// Play voice preview
let currentAudio = null;
let currentPlayingIndex = null;

function stopVoicePreview() {
    if (currentAudio) {
        currentAudio.pause();
        currentAudio.currentTime = 0;
        currentAudio = null;
        currentPlayingIndex = null;
        renderVoiceLibrary(); // Re-render to update button states
        showNotification('⏹️ Playback stopped', 'info');
    }
}

function playVoicePreview(index) {
    const voice = window.videoData.voiceLibrary[index];
    if (!voice || !voice.url) {
        showNotification('❌ Voice file not found', 'error');
        return;
    }

    // If clicking on currently playing voice, stop it
    if (currentPlayingIndex === index && currentAudio) {
        stopVoicePreview();
        return;
    }

    // Stop any currently playing audio
    if (currentAudio) {
        currentAudio.pause();
        currentAudio.currentTime = 0;
    }

    // Create and play new audio
    currentAudio = new Audio(voice.url);
    currentPlayingIndex = index;

    currentAudio.play()
        .then(() => {
            console.log('Playing voice preview:', voice.filename);
            showNotification(`▶️ Playing: ${voice.filename}`, 'info');
            renderVoiceLibrary(); // Update UI to show stop button
        })
        .catch(error => {
            console.error('Error playing audio:', error);
            showNotification('❌ Could not play audio. Try downloading it instead.', 'error');
            currentPlayingIndex = null;
        });

    // Auto-cleanup when finished
    currentAudio.addEventListener('ended', () => {
        currentAudio = null;
        currentPlayingIndex = null;
        renderVoiceLibrary(); // Re-render to update button states
        showNotification('⏹️ Playback finished', 'info');
    });
}

// Setup drag and drop for voice ranking
let draggedVoiceElement = null;

function setupVoiceDragAndDrop() {
    const voiceItems = document.querySelectorAll('.voice-item-draggable');

    voiceItems.forEach(item => {
        item.addEventListener('dragstart', (e) => {
            draggedVoiceElement = e.target;
            e.target.style.opacity = '0.5';
            e.target.style.cursor = 'grabbing';
        });

        item.addEventListener('dragover', (e) => {
            e.preventDefault();
            if (e.target.classList.contains('voice-item-draggable') && e.target !== draggedVoiceElement) {
                e.target.style.borderColor = '#4caf50';
                e.target.style.borderWidth = '3px';
            }
        });

        item.addEventListener('dragleave', (e) => {
            if (e.target.classList.contains('voice-item-draggable')) {
                e.target.style.borderColor = '#667eea';
                e.target.style.borderWidth = '2px';
            }
        });

        item.addEventListener('drop', (e) => {
            e.preventDefault();
            const target = e.target.closest('.voice-item-draggable');

            if (target && target !== draggedVoiceElement) {
                const draggedIndex = parseInt(draggedVoiceElement.dataset.index);
                const targetIndex = parseInt(target.dataset.index);

                // Reorder voices array
                const voice = window.videoData.voiceLibrary.splice(draggedIndex, 1)[0];
                window.videoData.voiceLibrary.splice(targetIndex, 0, voice);

                renderVoiceLibrary();
                showNotification(`✅ Voice reordered: now rank #${targetIndex + 1}`, 'success');
            }

            target.style.borderColor = '#667eea';
            target.style.borderWidth = '2px';
        });

        item.addEventListener('dragend', (e) => {
            e.target.style.opacity = '1';
            e.target.style.cursor = 'grab';
            voiceItems.forEach(item => {
                item.style.borderColor = '#667eea';
                item.style.borderWidth = '2px';
            });
        });
    });
}

// Update assembly stats display
function updateAssemblyStats(voiceDuration) {
    const statsSection = document.getElementById('assemblyStats');
    const voiceDurationDisplay = document.getElementById('voiceDurationDisplay');
    const mediaCountDisplay = document.getElementById('mediaCountDisplay');
    const perMediaDuration = document.getElementById('perMediaDuration');

    if (statsSection) {
        statsSection.style.display = 'block';
    }

    // Format voice duration
    if (voiceDuration) {
        const minutes = Math.floor(voiceDuration / 60);
        const seconds = Math.floor(voiceDuration % 60);
        if (voiceDurationDisplay) {
            voiceDurationDisplay.textContent = `${minutes}m ${seconds}s`;
        }
    }

    // Count media items from library (use appState.mediaLibrary which is the actual data)
    const mediaCount = appState.mediaLibrary?.length || 0;

    if (mediaCountDisplay) {
        mediaCountDisplay.textContent = mediaCount;
    }

    if (voiceDuration && perMediaDuration && mediaCount > 0) {
        const durationPerMedia = voiceDuration / mediaCount;
        const perMin = Math.floor(durationPerMedia / 60);
        const perSec = Math.floor(durationPerMedia % 60);
        perMediaDuration.textContent = `${perMin}m ${perSec}s`;
    } else if (perMediaDuration) {
        perMediaDuration.textContent = mediaCount === 0 ? 'Add media first' : 'Generate voice first';
    }
}

// Update media count display without voice duration
function updateMediaCount() {
    const mediaCountDisplay = document.getElementById('mediaCountDisplay');
    const mediaCount = appState.mediaLibrary?.length || 0;

    if (mediaCountDisplay) {
        mediaCountDisplay.textContent = mediaCount;
    }

    // If we have voice duration, recalculate per-media duration
    const selectedVoice = window.videoData.voiceLibrary?.[window.videoData.selectedVoiceIndex];
    if (selectedVoice && selectedVoice.duration) {
        updateAssemblyStats(selectedVoice.duration);
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
// BACKGROUND MUSIC
// =============================================================================
function toggleBackgroundMusicUpload() {
    const checked = document.getElementById('enableBackgroundMusic')?.checked;
    const section = document.getElementById('backgroundMusicUploadSection');
    if (section) {
        section.style.display = checked ? 'block' : 'none';
    }

    // Clear background music if disabled
    if (!checked) {
        window.videoData.backgroundMusic = null;
        const preview = document.getElementById('backgroundMusicPreview');
        if (preview) preview.style.display = 'none';
    }
}

function renderBackgroundMusicPreview(musicData) {
    const preview = document.getElementById('backgroundMusicPreview');
    if (!preview) return;

    const minutes = Math.floor(musicData.duration / 60);
    const seconds = Math.floor(musicData.duration % 60);

    preview.innerHTML = `
        <div style="background: rgba(255, 152, 0, 0.15); padding: 15px; border-radius: 8px; border: 2px solid #ff9800;">
            <div style="display: flex; align-items: center; gap: 15px;">
                <button onclick="playBackgroundMusicPreview()" style="
                    background: #ff9800;
                    color: white;
                    border: none;
                    border-radius: 50%;
                    width: 50px;
                    height: 50px;
                    font-size: 20px;
                    cursor: pointer;
                ">▶️</button>
                <div style="flex: 1;">
                    <strong style="color: #ff9800;">🎵 ${musicData.filename}</strong>
                    <div style="color: #666; font-size: 0.9em; margin-top: 3px;">
                        ⏱️ ${minutes}:${seconds.toString().padStart(2, '0')} • Will loop at 10% volume
                    </div>
                </div>
                <button onclick="removeBackgroundMusic()" style="
                    background: #ff4757;
                    color: white;
                    border: none;
                    border-radius: 5px;
                    padding: 8px 12px;
                    cursor: pointer;
                ">🗑️ Remove</button>
            </div>
        </div>
    `;
    preview.style.display = 'block';
}

let backgroundMusicAudio = null;

function playBackgroundMusicPreview() {
    if (!window.videoData.backgroundMusic) return;

    if (backgroundMusicAudio && !backgroundMusicAudio.paused) {
        backgroundMusicAudio.pause();
        backgroundMusicAudio = null;
        showNotification('⏹️ Music preview stopped', 'info');
        return;
    }

    backgroundMusicAudio = new Audio(window.videoData.backgroundMusic.url);
    backgroundMusicAudio.volume = 0.1; // Preview at 10% volume
    backgroundMusicAudio.play();
    showNotification('▶️ Playing music preview at 10% volume...', 'info');

    backgroundMusicAudio.addEventListener('ended', () => {
        showNotification('⏹️ Music preview ended', 'info');
    });
}

function removeBackgroundMusic() {
    if (confirm('Remove background music?')) {
        window.videoData.backgroundMusic = null;
        document.getElementById('backgroundMusicPreview').style.display = 'none';
        document.getElementById('enableBackgroundMusic').checked = false;
        showNotification('✅ Background music removed', 'success');
    }
}

// =============================================================================
// MEDIA SECTION
// =============================================================================
function toggleMediaSection(type) {
    if (type === 'auto') {
        const checked = document.getElementById('useAutoImages')?.checked;
        const section = document.getElementById('autoImagesSection');
        if (section) {
            section.style.display = checked ? 'block' : 'none';
            if (checked) {
                loadAutoImageStyles(); // Load styles when section opens
            }
        }
    } else if (type === 'manual') {
        const checked = document.getElementById('useManualMedia')?.checked;
        const section = document.getElementById('manualMediaSection');
        if (section) section.style.display = checked ? 'block' : 'none';
    } else if (type === 'stock') {
        const checked = document.getElementById('useStockFootage')?.checked;
        const section = document.getElementById('stockFootageSection');
        if (section) section.style.display = checked ? 'block' : 'none';
    } else if (type === 'autovideos') {
        const checked = document.getElementById('useAutoVideos')?.checked;
        const section = document.getElementById('autoVideosSection');
        if (section) section.style.display = checked ? 'block' : 'none';
    } else if (type === 'autoavatar') {
        const checked = document.getElementById('useAutoAvatar')?.checked;
        const section = document.getElementById('autoAvatarSection');
        if (section) section.style.display = checked ? 'block' : 'none';
    }
}

// =============================================================================
// MEDIA LIBRARY WITH RANKING
// =============================================================================
function addToMediaLibrary(file, url, type, source = 'upload', muted = false, serverPath = null) {
    const mediaItem = {
        id: Date.now() + Math.random(),
        file: file,
        url: url,  // Blob URL for preview
        path: serverPath || url,  // Server path for assembly (fallback to url for stock/AI)
        type: type, // 'image' or 'video'
        source: source, // 'upload', 'stock', 'ai'
        muted: muted,
        rank: appState.mediaLibrary.length
    };

    appState.mediaLibrary.push(mediaItem);

    // Sync to window.videoData for assembly
    window.videoData.mediaLibrary = appState.mediaLibrary;

    renderMediaLibrary();
    updateMediaCount(); // Update the media count display
    showNotification(`✅ Added to media library`, 'success');
}

function renderMediaLibrary() {
    const grid = document.getElementById('mediaLibraryGrid');
    if (!grid) return;

    if (appState.mediaLibrary.length === 0) {
        grid.innerHTML = '<p style="color: #888; grid-column: 1/-1;">No media added yet. Upload or fetch stock footage above.</p>';
        updateMediaSelectionButtons();
        return;
    }

    grid.innerHTML = '';

    appState.mediaLibrary.forEach((media, index) => {
        const card = document.createElement('div');
        card.className = 'media-library-card';
        card.draggable = !selectionState.isSelectionMode;
        card.dataset.id = media.id;
        card.dataset.index = index;

        const isSelected = selectionState.selectedMedia.has(media.id);

        card.style.cssText = `
            position: relative;
            background: rgba(0,0,0,0.3);
            border-radius: 8px;
            overflow: hidden;
            cursor: ${selectionState.isSelectionMode ? 'pointer' : 'grab'};
            border: 2px solid ${isSelected ? '#667eea' : 'transparent'};
            transition: all 0.2s;
        `;

        const isVideo = media.type === 'video';

        const preview = isVideo
            ? `<video src="${media.url}" style="width: 100%; height: 120px; object-fit: cover;"></video>`
            : `<img src="${media.url}" style="width: 100%; height: 120px; object-fit: cover;">`;

        const selectCheckbox = selectionState.isSelectionMode
            ? `<input type="checkbox" ${isSelected ? 'checked' : ''}
                onchange="toggleMediaSelection(${media.id})"
                style="position: absolute; top: 8px; left: 8px; width: 20px; height: 20px; cursor: pointer; z-index: 10;">`
            : '';

        const muteToggle = isVideo && !selectionState.isSelectionMode
            ? `<label style="display: flex; align-items: center; gap: 5px; font-size: 12px; margin-top: 5px;">
                <input type="checkbox" ${media.muted ? 'checked' : ''} onchange="toggleMediaMute(${media.id})">
                <span>Mute</span>
            </label>`
            : '';

        const actionButtons = !selectionState.isSelectionMode
            ? `<div style="display: flex; gap: 5px; margin-top: 8px;">
                <button onclick="downloadMedia(${media.id})" class="btn-secondary" style="flex: 1; font-size: 11px; padding: 4px 8px;">💾</button>
                <button onclick="deleteFromMediaLibrary(${media.id})" class="btn-secondary" style="flex: 1; font-size: 11px; padding: 4px 8px;">🗑️</button>
            </div>`
            : '';

        card.innerHTML = `
            ${selectCheckbox}
            ${preview}
            <div style="padding: 8px;">
                <div style="font-size: 11px; color: #888; text-transform: uppercase;">${media.source} ${media.type}</div>
                <div style="font-size: 13px; margin-top: 3px;">Rank: #${index + 1}</div>
                ${muteToggle}
                ${actionButtons}
            </div>
        `;

        // Click to select in selection mode
        if (selectionState.isSelectionMode) {
            card.addEventListener('click', () => toggleMediaSelection(media.id));
        }

        // Drag events (only when not in selection mode)
        if (!selectionState.isSelectionMode) {
            card.addEventListener('dragstart', handleDragStart);
            card.addEventListener('dragover', handleDragOver);
            card.addEventListener('drop', handleDrop);
            card.addEventListener('dragend', handleDragEnd);
        }

        grid.appendChild(card);
    });

    updateMediaSelectionButtons();
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

        // Sync to window.videoData
        window.videoData.mediaLibrary = appState.mediaLibrary;

        renderMediaLibrary();
        showNotification('✅ Media reordered', 'success');
    }

    if (target) target.style.borderColor = 'transparent';
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

function downloadMedia(id) {
    const media = appState.mediaLibrary.find(m => m.id === id);
    if (!media) {
        showNotification('⚠️ Media not found', 'warning');
        return;
    }

    // Generate filename based on source
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, -5);
    const extension = media.type === 'video' ? 'mp4' : 'jpg';
    const sourcePrefix = media.source === 'ai' ? 'generated' : media.source;
    const filename = `${sourcePrefix}_${media.type}_${timestamp}.${extension}`;

    // Create download link
    const link = document.createElement('a');
    link.href = media.url;
    link.download = filename;
    link.style.display = 'none';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    showNotification(`💾 Downloading ${filename}...`, 'success');
}

function deleteFromMediaLibrary(id) {
    if (!confirm('Remove this media from library?')) return;

    appState.mediaLibrary = appState.mediaLibrary.filter(m => m.id !== id);

    // Sync to window.videoData
    window.videoData.mediaLibrary = appState.mediaLibrary;

    renderMediaLibrary();
    updateMediaCount(); // Update the media count display
    showNotification('✅ Media removed', 'success');
}

// Multi-select functions for media
function toggleMediaSelectionMode() {
    selectionState.isSelectionMode = !selectionState.isSelectionMode;
    if (!selectionState.isSelectionMode) {
        selectionState.selectedMedia.clear();
    }
    renderMediaLibrary();
}

function toggleMediaSelection(id) {
    if (selectionState.selectedMedia.has(id)) {
        selectionState.selectedMedia.delete(id);
    } else {
        selectionState.selectedMedia.add(id);
    }
    renderMediaLibrary();
}

function selectAllMedia() {
    appState.mediaLibrary.forEach(media => {
        selectionState.selectedMedia.add(media.id);
    });
    renderMediaLibrary();
}

function deleteSelectedMedia() {
    const count = selectionState.selectedMedia.size;
    if (count === 0) {
        showNotification('⚠️ No media selected', 'warning');
        return;
    }

    if (!confirm(`Delete ${count} selected media item(s)?`)) return;

    appState.mediaLibrary = appState.mediaLibrary.filter(m => !selectionState.selectedMedia.has(m.id));
    window.videoData.mediaLibrary = appState.mediaLibrary;

    selectionState.selectedMedia.clear();
    selectionState.isSelectionMode = false;

    renderMediaLibrary();
    updateMediaCount();
    showNotification(`✅ Deleted ${count} media item(s)`, 'success');
}

function updateMediaSelectionButtons() {
    const container = document.getElementById('mediaSelectionButtons');
    if (!container) return;

    const hasMedia = appState.mediaLibrary.length > 0;
    const selectedCount = selectionState.selectedMedia.size;

    if (!hasMedia) {
        container.innerHTML = '';
        return;
    }

    if (selectionState.isSelectionMode) {
        container.innerHTML = `
            <div style="display: flex; gap: 10px; flex-wrap: wrap; padding: 10px; background: rgba(102, 126, 234, 0.1); border-radius: 8px;">
                <button onclick="selectAllMedia()" class="btn-secondary" style="font-size: 13px;">✅ Select All</button>
                <button onclick="deleteSelectedMedia()" class="btn-secondary" style="font-size: 13px;">🗑️ Delete Selected (${selectedCount})</button>
                <button onclick="toggleMediaSelectionMode()" class="btn-secondary" style="font-size: 13px;">✖️ Cancel</button>
            </div>
        `;
    } else {
        container.innerHTML = `
            <button onclick="toggleMediaSelectionMode()" class="btn-primary" style="font-size: 13px;">📋 Select Multiple</button>
        `;
    }
}

// =============================================================================
// AUTO IMAGES AI - SEPARATE DIRECTOR GEMINI + REPLICATE
// =============================================================================

let autoImagesTimeline = null;

// Load and populate style selector
async function loadAutoImageStyles() {
    try {
        const response = await fetch('/api/auto-images/styles');
        const data = await response.json();

        if (data.success && data.styles) {
            const styleSelect = document.getElementById('autoImageStyle');
            if (styleSelect) {
                styleSelect.innerHTML = '';
                data.styles.forEach(style => {
                    const option = document.createElement('option');
                    option.value = style.id;
                    const icon = style.id === 'cinematic' ? '🎬' :
                                 style.id === 'photorealistic' ? '📷' :
                                 style.id === 'artistic' ? '🎨' :
                                 style.id === 'animated' ? '🎭' : '✨';
                    option.textContent = `${icon} ${style.name}`;
                    styleSelect.appendChild(option);
                });
            }
        }
    } catch (error) {
        console.error('Error loading styles:', error);
    }
}

async function generateAutoImages() {
    const script = document.getElementById('scriptInput')?.value || window.videoData.script;
    if (!script) {
        showNotification('⚠️ Please generate or enter a script first', 'warning');
        return;
    }

    const styleSelect = document.getElementById('autoImageStyle');
    const countInput = document.getElementById('autoImageCount');
    const useWhisperCheckbox = document.getElementById('useWhisperTiming');

    const style_id = styleSelect ? styleSelect.value : 'cinematic';
    const n_images = countInput ? parseInt(countInput.value) : 10;
    const use_whisper_timing = useWhisperCheckbox ? useWhisperCheckbox.checked : false;

    const progressBox = document.getElementById('autoImageProgress');
    const timelineSection = document.getElementById('autoImageTimeline');

    // Check if Whisper timing is requested but no voice exists
    const selectedVoiceIndex = window.videoData.selectedVoiceIndex ?? (window.videoData.voiceLibrary?.length > 0 ? 0 : -1);
    const selectedVoice = window.videoData.voiceLibrary?.[selectedVoiceIndex];

    if (use_whisper_timing && (!selectedVoice || !selectedVoice.path)) {
        showNotification('⚠️ Whisper timing requires voice to be generated or uploaded first. Generate/upload voice first, then generate images.', 'warning');
        return;
    }

    if (progressBox) {
        progressBox.style.display = 'block';
        const timingMode = use_whisper_timing ? '🎤 with Whisper timestamps' : 'with even distribution';
        progressBox.innerHTML = `<p>🎬 Director AI planning ${n_images} scenes ${timingMode}...</p>`;
    }

    try {
        showNotification(`🤖 Starting Auto Images AI (Director + Replicate)...`, 'info');

        // Prepare request payload
        const payload = {
            script: script,
            style_id: style_id,
            n_images: n_images,
            aspect_ratio: '16:9'
        };

        // Add Whisper timing if enabled
        if (use_whisper_timing && selectedVoice && selectedVoice.path) {
            payload.use_whisper_timing = true;
            payload.voice_path = selectedVoice.path;
        }

        // Call backend API
        const response = await fetch('/api/auto-images/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || `Server error: ${response.status}`);
        }

        const data = await response.json();

        if (!data.success) {
            throw new Error(data.error || 'Auto Images generation failed');
        }

        autoImagesTimeline = data.timeline;

        if (progressBox) {
            const timingInfo = data.whisper_used ? ' (with Whisper STT perfect timing)' : '';
            progressBox.innerHTML = `<p>✅ Generated ${data.stats.generated}/${data.stats.requested} images${timingInfo}!</p>`;
        }

        // Render timeline
        if (timelineSection) {
            timelineSection.style.display = 'block';
        }
        renderAutoImageTimeline();

        // Auto-add to media library
        if (autoImagesTimeline && autoImagesTimeline.items) {
            for (const item of autoImagesTimeline.items) {
                await addAutoImageToLibrary(item);
            }
        }

        showNotification(`✅ Auto Images: ${data.stats.generated}/${data.stats.requested} generated!`, 'success');

    } catch (error) {
        console.error('Auto Images generation failed:', error);
        if (progressBox) {
            progressBox.innerHTML = `<p>❌ Error: ${error.message}</p>`;
        }
        showNotification('❌ Auto Images failed: ' + error.message, 'error');
    }
}

function renderAutoImageTimeline() {
    const listContainer = document.getElementById('autoImageTimelineList');
    if (!listContainer || !autoImagesTimeline || !autoImagesTimeline.items) return;

    listContainer.innerHTML = '';

    autoImagesTimeline.items.forEach((item, index) => {
        const card = document.createElement('div');
        card.style.cssText = `
            background: linear-gradient(135deg, rgba(102, 126, 234, 0.1), rgba(118, 75, 162, 0.1));
            border: 2px solid #667eea;
            padding: 15px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            gap: 15px;
        `;

        const sourceIcon = item.source_type === 'generated' ? '🤖' : (item.source_type === 'local' ? '📁' : '📹');
        const sourceLabel = item.source_type === 'generated' ? 'AI Generated' : (item.source_type === 'local' ? 'Local' : 'Stock');

        card.innerHTML = `
            <div style="background: #667eea; color: white; width: 40px; height: 40px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: bold; flex-shrink: 0;">
                #${index + 1}
            </div>
            <div style="flex: 1;">
                <div><strong>${sourceIcon} ${sourceLabel}</strong></div>
                ${item.scene_id ? `<div style="color: #666; font-size: 0.9em;">Scene ${item.scene_id}</div>` : ''}
                <div style="color: #888; font-size: 0.85em; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                    ${item.path}
                </div>
            </div>
            <button onclick="deleteAutoImageFromTimeline(${index})" style="background: #ff4757; color: white; border: none; border-radius: 5px; padding: 8px 12px; cursor: pointer;">
                🗑️
            </button>
        `;

        listContainer.appendChild(card);
    });
}

async function addAutoImageToLibrary(item) {
    if (!item || !item.path) return;

    // Upload to server if needed, or use existing path
    // For now, assume path is already server-accessible
    appState.mediaLibrary.push({
        id: item.id,
        type: 'image',
        source: item.source_type,
        url: item.path,
        path: item.path,
        scene_id: item.scene_id
    });

    updateMediaCount();
    renderMediaLibrary();
}

async function deleteAutoImageFromTimeline(index) {
    if (!confirm('Delete this image from timeline?')) return;

    try {
        const response = await fetch('/api/auto-images/timeline/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ index: index })
        });

        const data = await response.json();
        if (data.success) {
            autoImagesTimeline = data.timeline;
            renderAutoImageTimeline();
            showNotification('✅ Image deleted from timeline', 'success');
        } else {
            throw new Error(data.error);
        }
    } catch (error) {
        showNotification('❌ Failed to delete: ' + error.message, 'error');
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
// =============================================================================
// VIDEO ASSEMBLY - Match voice duration exactly
// =============================================================================
async function assembleVideo() {
    const title = document.getElementById('titleInput')?.value || window.videoData.title;
    const voiceLibrary = window.videoData.voiceLibrary || [];
    const mediaLibrary = appState.mediaLibrary || [];
    const qualityRadio = document.querySelector('input[name="quality"]:checked');
    const quality = qualityRadio ? qualityRadio.value : '720';

    // Validation
    if (!title) {
        showNotification('⚠️ Please generate a title first (Step 1)', 'warning');
        return;
    }

    if (voiceLibrary.length === 0) {
        showNotification('⚠️ Please add voices first (Step 2 - generate or upload)', 'warning');
        return;
    }

    if (mediaLibrary.length === 0) {
        showNotification('⚠️ Please add media (images/videos) first (Step 3)', 'warning');
        return;
    }

    const progressContainer = document.getElementById('videoProgress');
    const progressFill = document.getElementById('progressFill');
    const progressText = document.getElementById('progressText');
    const resultContainer = document.getElementById('videoResult');
    const videoInfo = document.getElementById('videoInfo');
    const downloadBtn = document.getElementById('downloadBtn');

    // Show progress
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
        progressText.textContent = 'Preparing media clips...';
    }

    try {
        // Extract media paths from library (in ranked order)
        // Prioritize server path over blob URL
        const mediaPaths = mediaLibrary.map(item => item.path || item.url);

        // Extract voice paths from voice library (in ranked order)
        const voicePaths = voiceLibrary.map(voice => voice.path).filter(p => p);

        console.log('🎬 Assembling video...');
        console.log('   Voices:', voiceLibrary.length, 'ranked voices');
        console.log('   Voice paths:', voicePaths);
        console.log('   Media:', mediaPaths.length, 'files');
        console.log('   Media paths:', mediaPaths);

        if (progressText) {
            progressText.textContent = `Merging ${voiceLibrary.length} voice(s) and ${mediaPaths.length} media clips...`;
        }
        if (progressFill) {
            progressFill.style.width = '30%';
        }

        // Prepare API payload
        const payload = {
            voice_paths: voicePaths,  // Array of voice paths in ranked order
            media_paths: mediaPaths,
            title: title,
            resolution: quality === '1080' ? '1920x1080' : '1280x720'
        };

        // Add background music if enabled
        if (window.videoData.backgroundMusic && window.videoData.backgroundMusic.path) {
            payload.background_music_path = window.videoData.backgroundMusic.path;
        }

        // Add Ken Burns effect if enabled
        const useKenBurns = document.getElementById('useKenBurns');
        if (useKenBurns && useKenBurns.checked) {
            payload.use_ken_burns = true;
        }

        // Call assembly API with multiple voices
        const response = await fetch('/api/assemble-video', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Video assembly failed');
        }

        if (progressText) {
            progressText.textContent = 'Finalizing video...';
        }
        if (progressFill) {
            progressFill.style.width = '90%';
        }

        // Success!
        if (progressFill) {
            progressFill.style.width = '100%';
        }

        setTimeout(() => {
            if (progressContainer) {
                progressContainer.style.display = 'none';
            }

            // Show result
            if (resultContainer) {
                resultContainer.style.display = 'block';
            }

            if (videoInfo) {
                videoInfo.innerHTML = `
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin: 20px 0;">
                        <div style="text-align: center; padding: 15px; background: rgba(76, 175, 80, 0.1); border-radius: 8px;">
                            <div style="font-size: 24px; margin-bottom: 5px;">⏱️</div>
                            <strong>Duration</strong><br>
                            <span style="font-size: 1.2em;">${data.duration_formatted}</span>
                        </div>
                        <div style="text-align: center; padding: 15px; background: rgba(33, 150, 243, 0.1); border-radius: 8px;">
                            <div style="font-size: 24px; margin-bottom: 5px;">🎨</div>
                            <strong>Media Items</strong><br>
                            <span style="font-size: 1.2em;">${data.media_count}</span>
                        </div>
                        <div style="text-align: center; padding: 15px; background: rgba(156, 39, 176, 0.1); border-radius: 8px;">
                            <div style="font-size: 24px; margin-bottom: 5px;">💾</div>
                            <strong>File Size</strong><br>
                            <span style="font-size: 1.2em;">${data.file_size_mb.toFixed(1)} MB</span>
                        </div>
                        <div style="text-align: center; padding: 15px; background: rgba(255, 152, 0, 0.1); border-radius: 8px;">
                            <div style="font-size: 24px; margin-bottom: 5px;">⚡</div>
                            <strong>Processing Time</strong><br>
                            <span style="font-size: 1.2em;">${data.processing_time.toFixed(1)}s</span>
                        </div>
                    </div>
                    <p style="text-align: center; color: #888; margin-top: 10px;">
                        📁 ${data.output_filename}
                    </p>
                `;
            }

            if (downloadBtn) {
                downloadBtn.onclick = () => {
                    window.location.href = data.download_url;
                };
            }

            showNotification(`✅ Video assembled! Duration: ${data.duration_formatted}`, 'success');

        }, 500);

    } catch (error) {
        console.error('Video assembly failed:', error);

        if (progressContainer) {
            progressContainer.style.display = 'none';
        }

        if (progressText) {
            progressText.textContent = 'Assembly failed';
        }

        showNotification('❌ Video assembly failed: ' + error.message, 'error');
    }
}

// Legacy function for compatibility
async function processVideo() {
    return assembleVideo();
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
    const rateDisplay = document.getElementById('speakingRateDisplay');
    if (rateSlider && rateDisplay) {
        rateSlider.addEventListener('input', (e) => {
            rateDisplay.textContent = e.target.value + 'x';
        });
    }

    // Setup manual script input listener - show voice section when script is entered
    const scriptInput = document.getElementById('scriptInput');
    if (scriptInput) {
        scriptInput.addEventListener('input', (e) => {
            const script = e.target.value.trim();
            if (script.length > 50) { // Only show if script has substantial content
                window.videoData.script = script;
                appState.generatedScript = script;
                showVoiceSectionIfScriptAvailable();
            }
        });

        // Also check on blur (when user clicks away)
        scriptInput.addEventListener('blur', (e) => {
            const script = e.target.value.trim();
            if (script.length > 0) {
                window.videoData.script = script;
                appState.generatedScript = script;
                showVoiceSectionIfScriptAvailable();
            }
        });
    }

    // Setup audio file upload handler
    const audioUpload = document.getElementById('audioUpload');
    if (audioUpload) {
        audioUpload.addEventListener('change', (e) => {
            const files = Array.from(e.target.files);
            const audioListEl = document.getElementById('audioList');

            if (!audioListEl) return;

            files.forEach(file => {
                if (file.type.startsWith('audio/')) {
                    const audioCard = document.createElement('div');
                    audioCard.style.cssText = `
                        background: rgba(102, 126, 234, 0.1);
                        padding: 15px;
                        border-radius: 8px;
                        margin: 10px 0;
                        display: flex;
                        justify-content: space-between;
                        align-items: center;
                    `;

                    const url = URL.createObjectURL(file);

                    audioCard.innerHTML = `
                        <div>
                            <div style="font-weight: bold; margin-bottom: 5px;">🎵 ${file.name}</div>
                            <audio controls src="${url}" style="width: 300px; height: 30px;"></audio>
                        </div>
                        <button onclick="this.parentElement.remove()" class="btn-secondary">🗑️ Remove</button>
                    `;

                    audioListEl.appendChild(audioCard);

                    // Store in app state
                    if (!appState.audioFiles) appState.audioFiles = [];
                    appState.audioFiles.push({ file, url, name: file.name });
                }
            });

            showNotification(`✅ Added ${files.length} audio file(s)`, 'success');
            e.target.value = ''; // Reset input
        });
    }

    // Setup voice upload and drag & drop
    const voiceUpload = document.getElementById('voiceUpload');
    if (voiceUpload) {
        voiceUpload.addEventListener('change', async (e) => {
            const files = Array.from(e.target.files);

            for (const file of files) {
                if (file.type.startsWith('audio/')) {
                    try {
                        // Create blob URL for preview
                        const blobUrl = URL.createObjectURL(file);
                        const audio = new Audio(blobUrl);

                        // Wait for metadata to get duration
                        await new Promise((resolve) => {
                            audio.addEventListener('loadedmetadata', resolve);
                        });

                        // Upload to server to get server path
                        showNotification(`⏳ Uploading ${file.name}...`, 'info');
                        const uploadResult = await uploadVoiceToServer(file);

                        // Add to library with server path for assembly and blob URL for preview
                        addVoiceToLibrary({
                            url: blobUrl,  // Blob URL for preview playback
                            path: uploadResult.path,  // Server path for video assembly
                            filename: file.name,
                            duration: audio.duration,
                            type: 'upload'
                        });

                        showNotification(`✅ Voice uploaded: ${file.name}`, 'success');
                    } catch (error) {
                        console.error('Voice upload failed:', error);
                        showNotification(`❌ Upload failed: ${error.message}`, 'error');
                    }
                }
            }

            voiceUpload.value = '';
        });
    }

    // Setup voice dropzone
    const voiceDropzone = document.getElementById('voiceDropzone');
    if (voiceDropzone) {
        voiceDropzone.addEventListener('dragover', (e) => {
            e.preventDefault();
            voiceDropzone.style.borderColor = '#667eea';
            voiceDropzone.style.background = 'rgba(102, 126, 234, 0.1)';
        });
        voiceDropzone.addEventListener('dragleave', () => {
            voiceDropzone.style.borderColor = '#ddd';
            voiceDropzone.style.background = '';
        });
        voiceDropzone.addEventListener('drop', async (e) => {
            e.preventDefault();
            voiceDropzone.style.borderColor = '#ddd';
            voiceDropzone.style.background = '';

            const files = Array.from(e.dataTransfer.files);

            for (const file of files) {
                if (file.type.startsWith('audio/')) {
                    try {
                        // Create blob URL for preview
                        const blobUrl = URL.createObjectURL(file);
                        const audio = new Audio(blobUrl);

                        // Wait for metadata to get duration
                        await new Promise((resolve) => {
                            audio.addEventListener('loadedmetadata', resolve);
                        });

                        // Upload to server to get server path
                        showNotification(`⏳ Uploading ${file.name}...`, 'info');
                        const uploadResult = await uploadVoiceToServer(file);

                        // Add to library with server path for assembly and blob URL for preview
                        addVoiceToLibrary({
                            url: blobUrl,  // Blob URL for preview playback
                            path: uploadResult.path,  // Server path for video assembly
                            filename: file.name,
                            duration: audio.duration,
                            type: 'upload'
                        });

                        showNotification(`✅ Voice uploaded: ${file.name}`, 'success');
                    } catch (error) {
                        console.error('Voice upload failed:', error);
                        showNotification(`❌ Upload failed: ${error.message}`, 'error');
                    }
                }
            }
        });
    }

    // Setup background music upload
    const backgroundMusicUpload = document.getElementById('backgroundMusicUpload');
    if (backgroundMusicUpload) {
        backgroundMusicUpload.addEventListener('change', async (e) => {
            const file = e.target.files[0];
            if (!file) return;

            if (file.type.startsWith('audio/')) {
                try {
                    // Create blob URL for preview
                    const blobUrl = URL.createObjectURL(file);
                    const audio = new Audio(blobUrl);

                    // Wait for metadata to get duration
                    await new Promise((resolve) => {
                        audio.addEventListener('loadedmetadata', resolve);
                    });

                    // Upload to server
                    showNotification(`⏳ Uploading background music...`, 'info');
                    const uploadResult = await uploadVoiceToServer(file);

                    // Store background music data
                    window.videoData.backgroundMusic = {
                        url: blobUrl,
                        path: uploadResult.path,
                        filename: file.name,
                        duration: audio.duration
                    };

                    renderBackgroundMusicPreview(window.videoData.backgroundMusic);
                    showNotification(`✅ Background music added: ${file.name}`, 'success');
                } catch (error) {
                    console.error('Background music upload failed:', error);
                    showNotification(`❌ Upload failed: ${error.message}`, 'error');
                }
            }

            backgroundMusicUpload.value = '';
        });
    }

    // Setup background music dropzone
    const backgroundMusicDropzone = document.getElementById('backgroundMusicDropzone');
    if (backgroundMusicDropzone) {
        backgroundMusicDropzone.addEventListener('dragover', (e) => {
            e.preventDefault();
            backgroundMusicDropzone.style.borderColor = '#ff9800';
            backgroundMusicDropzone.style.background = 'rgba(255, 152, 0, 0.1)';
        });
        backgroundMusicDropzone.addEventListener('dragleave', () => {
            backgroundMusicDropzone.style.borderColor = '#ddd';
            backgroundMusicDropzone.style.background = '';
        });
        backgroundMusicDropzone.addEventListener('drop', async (e) => {
            e.preventDefault();
            backgroundMusicDropzone.style.borderColor = '#ddd';
            backgroundMusicDropzone.style.background = '';

            const file = e.dataTransfer.files[0];
            if (!file) return;

            if (file.type.startsWith('audio/')) {
                try {
                    // Create blob URL for preview
                    const blobUrl = URL.createObjectURL(file);
                    const audio = new Audio(blobUrl);

                    // Wait for metadata to get duration
                    await new Promise((resolve) => {
                        audio.addEventListener('loadedmetadata', resolve);
                    });

                    // Upload to server
                    showNotification(`⏳ Uploading background music...`, 'info');
                    const uploadResult = await uploadVoiceToServer(file);

                    // Store background music data
                    window.videoData.backgroundMusic = {
                        url: blobUrl,
                        path: uploadResult.path,
                        filename: file.name,
                        duration: audio.duration
                    };

                    renderBackgroundMusicPreview(window.videoData.backgroundMusic);
                    showNotification(`✅ Background music added: ${file.name}`, 'success');
                } catch (error) {
                    console.error('Background music upload failed:', error);
                    showNotification(`❌ Upload failed: ${error.message}`, 'error');
                }
            }
        });
    }

    // Setup voice model description update + reload voices on model change
    const voiceModel = document.getElementById('voiceModel');
    if (voiceModel) {
        voiceModel.addEventListener('change', () => {
            const descElement = document.getElementById('modelDescription');
            if (descElement) {
                const model = voiceModel.value;
                if (model.includes('max')) {
                    descElement.textContent = 'Max: Best quality, more realistic, takes more time';
                } else {
                    descElement.textContent = 'Mini: Good quality, faster generation, lower cost';
                }
            }
            loadVoiceList();
        });
        // Auto-load voices on page init
        loadVoiceList();
    }

    // Setup voice model description update for Audio & Voice section
    const voiceSelectModel = document.getElementById('voiceSelectModel');
    if (voiceSelectModel) {
        voiceSelectModel.addEventListener('change', () => {
            const descElement = document.getElementById('voiceSelectModelDesc');
            if (descElement) {
                const model = voiceSelectModel.value;
                if (model.includes('max')) {
                    descElement.textContent = 'Max: Best quality, more realistic, takes more time';
                } else {
                    descElement.textContent = 'Mini: Good quality, faster generation, lower cost';
                }
            }
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
        mediaUpload.addEventListener('change', async (e) => {
            const files = Array.from(e.target.files);

            for (const file of files) {
                const isVideo = file.type.startsWith('video/');
                const isImage = file.type.startsWith('image/');

                if (isVideo || isImage) {
                    try {
                        const type = isVideo ? 'video' : 'image';
                        const blobUrl = URL.createObjectURL(file);

                        // Upload to server
                        showNotification(`⏳ Uploading ${file.name}...`, 'info');
                        const uploadResult = await uploadMediaToServer(file, type);

                        // Add to library with blob URL for preview and server path for assembly
                        addToMediaLibrary(file, blobUrl, type, 'upload', false, uploadResult.path);
                        showNotification(`✅ ${type} uploaded: ${file.name}`, 'success');
                    } catch (error) {
                        console.error('Media upload failed:', error);
                        showNotification(`❌ Upload failed: ${error.message}`, 'error');
                    }
                }
            }

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

        mediaDropzone.addEventListener('drop', async (e) => {
            e.preventDefault();
            mediaDropzone.style.borderColor = '#444';
            mediaDropzone.style.background = 'rgba(255, 255, 255, 0.02)';

            const files = Array.from(e.dataTransfer.files);

            for (const file of files) {
                const isVideo = file.type.startsWith('video/');
                const isImage = file.type.startsWith('image/');

                if (isVideo || isImage) {
                    try {
                        const type = isVideo ? 'video' : 'image';
                        const blobUrl = URL.createObjectURL(file);

                        // Upload to server
                        showNotification(`⏳ Uploading ${file.name}...`, 'info');
                        const uploadResult = await uploadMediaToServer(file, type);

                        // Add to library with blob URL for preview and server path for assembly
                        addToMediaLibrary(file, blobUrl, type, 'upload', false, uploadResult.path);
                        showNotification(`✅ ${type} uploaded: ${file.name}`, 'success');
                    } catch (error) {
                        console.error('Media upload failed:', error);
                        showNotification(`❌ Upload failed: ${error.message}`, 'error');
                    }
                } else {
                    showNotification('⚠️ Only images and videos supported', 'warning');
                }
            }
        });
    }

    // Load settings and formulas
    loadSettings();

    // Load initial tab
    showTab('dashboard');

    console.log('✅ AI Video Studio initialized with all fixes applied');
    showNotification('✅ AI Video Studio loaded successfully', 'success');
});


// =============================================================================
// MR BAHA EDITOR - Backend FFmpeg Timeline Editor
// =============================================================================

// Timeline state
const timelineState = {
    clips: [], // {id, fileId, file, type, url, name, duration, transition, uploaded}
    selectedClips: [], // Array of selected clip indices
    currentClipIndex: null,
    selectedTransitionIndex: null,
    zoom: 1,
    isPlaying: false,
    currentTime: 0,
    totalDuration: 0
};

// File selection handlers
function timelineSelectFiles(event) {
    const files = Array.from(event.target.files);
    uploadTimelineFiles(files);
}

function timelineDragOver(event) {
    event.preventDefault();
    event.stopPropagation();
    event.dataTransfer.dropEffect = 'copy';
}

function timelineDropFiles(event) {
    event.preventDefault();
    event.stopPropagation();
    const files = Array.from(event.dataTransfer.files);
    uploadTimelineFiles(files);
}

// Upload files to backend
async function uploadTimelineFiles(files) {
    if (!files || files.length === 0) return;

    showNotification('⏳ Uploading ' + files.length + ' file(s)...', 'info');

    for (const file of files) {
        const isVideo = file.type.startsWith('video/');
        const isImage = file.type.startsWith('image/');

        if (!isVideo && !isImage) {
            showNotification('⚠️ Skipping unsupported file: ' + file.name, 'warning');
            continue;
        }

        try {
            // Upload to backend
            const formData = new FormData();
            formData.append('file', file);
            formData.append('type', isVideo ? 'video' : 'image');

            const response = await fetch('/api/upload', {
                method: 'POST',
                body: formData
            });

            const data = await response.json();

            if (data.success) {
                const url = URL.createObjectURL(file);
                let duration = isImage ? 5.0 : 0; // Default 5s for images

                // Get video duration if video file
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

                const clip = {
                    id: Date.now() + Math.random(),
                    fileId: data.file_id,
                    file: file,
                    type: isVideo ? 'video' : 'image',
                    url: url,
                    name: file.name,
                    duration: duration,
                    transition: 'fade',
                    uploaded: true
                };

                timelineState.clips.push(clip);
            } else {
                showNotification('❌ Upload failed: ' + file.name, 'error');
            }
        } catch (error) {
            console.error('Upload error:', error);
            showNotification('❌ Upload error: ' + error.message, 'error');
        }
    }

    renderTimeline();
    updateTimelineInfo();
    showNotification('✅ Added ' + files.length + ' file(s) to timeline', 'success');
}

// Render timeline
function renderTimeline() {
    const track = document.getElementById('timelineTrack');
    const emptyMsg = document.getElementById('timelineEmptyMessage');

    if (timelineState.clips.length === 0) {
        track.innerHTML = '';
        if (emptyMsg) {
            emptyMsg.style.display = 'block';
        }
        return;
    }

    if (emptyMsg) emptyMsg.style.display = 'none';

    track.innerHTML = '';

    timelineState.clips.forEach((clip, index) => {
        // Create clip element
        const clipEl = document.createElement('div');
        clipEl.className = 'timeline-clip';
        if (timelineState.selectedClips.includes(index)) {
            clipEl.classList.add('selected');
        }
        clipEl.draggable = true;
        clipEl.dataset.index = index;

        const width = Math.max(120, clip.duration * 60 * timelineState.zoom);
        clipEl.style.width = width + 'px';
        clipEl.style.height = '80px';

        const typeIcon = clip.type === 'image' ? '🖼️' : '📹';
        clipEl.innerHTML = '<div class="clip-name">' + typeIcon + ' ' + clip.name + '</div>' +
            '<div class="clip-duration">' + formatTime(clip.duration) + '</div>' +
            '<button class="clip-delete" onclick="deleteClip(' + index + ')">×</button>';

        clipEl.addEventListener('dragstart', handleClipDragStart);
        clipEl.addEventListener('dragover', handleClipDragOver);
        clipEl.addEventListener('drop', handleClipDrop);
        clipEl.addEventListener('dragend', handleClipDragEnd);
        clipEl.addEventListener('click', (e) => {
            if (e.ctrlKey || e.metaKey) {
                toggleClipSelection(index);
            } else {
                selectClip(index);
            }
        });

        track.appendChild(clipEl);

        // Add transition icon between clips
        if (index < timelineState.clips.length - 1) {
            const transEl = document.createElement('div');
            transEl.className = 'timeline-transition';
            transEl.dataset.index = index;
            transEl.innerHTML = '<div class="transition-icon">' + getTransitionIcon(clip.transition) + '</div>' +
                '<div class="transition-label">' + clip.transition + '</div>';
            transEl.addEventListener('click', () => openTransitionSelector(index));
            track.appendChild(transEl);
        }
    });

    updateEditStatus();
}

// Clip drag-and-drop handlers
let draggedClipIndex = null;

function handleClipDragStart(event) {
    draggedClipIndex = parseInt(event.target.dataset.index);
    event.target.style.opacity = '0.4';
}

function handleClipDragOver(event) {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
}

function handleClipDrop(event) {
    event.preventDefault();
    event.stopPropagation();

    const target = event.target.closest('.timeline-clip');
    if (!target) return;

    const targetIndex = parseInt(target.dataset.index);

    if (draggedClipIndex !== null && draggedClipIndex !== targetIndex) {
        const draggedClip = timelineState.clips.splice(draggedClipIndex, 1)[0];
        timelineState.clips.splice(targetIndex, 0, draggedClip);
        renderTimeline();
        updateTimelineInfo();
        showNotification('✅ Clip reordered', 'success');
    }
}

function handleClipDragEnd(event) {
    event.target.style.opacity = '1';
    draggedClipIndex = null;
}

// Delete clip
function deleteClip(index) {
    const clip = timelineState.clips[index];
    URL.revokeObjectURL(clip.url);
    timelineState.clips.splice(index, 1);
    timelineState.selectedClips = timelineState.selectedClips.filter(i => i !== index);
    renderTimeline();
    updateTimelineInfo();
    showNotification('✅ Clip deleted', 'success');
}

// Select clip
function selectClip(index) {
    timelineState.currentClipIndex = index;
    timelineState.selectedClips = [index];
    renderTimeline();
}

function toggleClipSelection(index) {
    const idx = timelineState.selectedClips.indexOf(index);
    if (idx > -1) {
        timelineState.selectedClips.splice(idx, 1);
    } else {
        timelineState.selectedClips.push(index);
    }
    renderTimeline();
}

// Transition selector
function openTransitionSelector(index) {
    timelineState.selectedTransitionIndex = index;
    document.getElementById('transitionModal').style.display = 'block';
    document.getElementById('transitionModalOverlay').style.display = 'block';
}

function closeTransitionModal() {
    document.getElementById('transitionModal').style.display = 'none';
    document.getElementById('transitionModalOverlay').style.display = 'none';
    timelineState.selectedTransitionIndex = null;
}

function selectTransition(type) {
    if (timelineState.selectedTransitionIndex !== null) {
        timelineState.clips[timelineState.selectedTransitionIndex].transition = type;
        renderTimeline();
        showNotification('✅ Transition changed to ' + type, 'success');
    }
    closeTransitionModal();
}

function getTransitionIcon(type) {
    const icons = {
        fade: '🌅',
        dissolve: '✨',
        wipe: '➡️',
        slide: '🔄',
        zoom: '🔍',
        none: '⚡'
    };
    return icons[type] || '🌅';
}

// Update edit status
function updateEditStatus() {
    const status = document.getElementById('editStatus');
    if (!status) return;

    if (timelineState.selectedClips.length === 0) {
        status.textContent = 'Select a clip to edit';
        status.style.color = '#aaa';
    } else if (timelineState.selectedClips.length === 1) {
        const clip = timelineState.clips[timelineState.selectedClips[0]];
        status.textContent = 'Selected: ' + clip.name + ' (' + clip.type + ')';
        status.style.color = '#667eea';
    } else if (timelineState.selectedClips.length === 2) {
        status.textContent = '2 clips selected - Ready to merge';
        status.style.color = '#10b981';
    } else {
        status.textContent = timelineState.selectedClips.length + ' clips selected';
        status.style.color = '#f59e0b';
    }
}

// Timeline info updates
function updateTimelineInfo() {
    const count = timelineState.clips.length;
    const total = timelineState.clips.reduce((sum, clip) => sum + clip.duration, 0);

    document.getElementById('timelineClipCount').textContent = count + ' clip' + (count !== 1 ? 's' : '');
    document.getElementById('timelineTotalDuration').textContent = 'Total: ' + formatTime(total);

    timelineState.totalDuration = total;
}

// Zoom controls
function timelineZoomIn() {
    timelineState.zoom = Math.min(timelineState.zoom * 1.5, 5);
    renderTimeline();
}

function timelineZoomOut() {
    timelineState.zoom = Math.max(timelineState.zoom / 1.5, 0.2);
    renderTimeline();
}

// Trim selected clip
async function trimSelectedClip() {
    if (timelineState.selectedClips.length !== 1) {
        showNotification('⚠️ Please select exactly 1 clip to trim', 'warning');
        return;
    }

    const index = timelineState.selectedClips[0];
    const clip = timelineState.clips[index];

    if (clip.type === 'image') {
        showNotification('⚠️ Cannot trim image clips. Use "Set Duration" instead.', 'warning');
        return;
    }

    const startTime = parseFloat(document.getElementById('trimStart').value);
    const endTime = parseFloat(document.getElementById('trimEnd').value);

    if (startTime >= endTime) {
        showNotification('⚠️ End time must be after start time', 'warning');
        return;
    }

    if (endTime > clip.duration) {
        showNotification('⚠️ End time exceeds clip duration', 'warning');
        return;
    }

    try {
        showNotification('⏳ Trimming clip...', 'info');

        const response = await fetch('/api/timeline/trim', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                file_id: clip.fileId,
                start_time: startTime,
                end_time: endTime
            })
        });

        const data = await response.json();

        if (data.success) {
            // Update clip with trimmed version
            clip.fileId = data.trimmed_file_id;
            clip.duration = data.duration;
            clip.name = clip.name.replace('.', '_trimmed.');

            renderTimeline();
            updateTimelineInfo();
            showNotification('✅ Clip trimmed successfully!', 'success');
        } else {
            showNotification('❌ Trim failed: ' + data.error, 'error');
        }
    } catch (error) {
        showNotification('❌ Trim error: ' + error.message, 'error');
    }
}

// Set image duration
async function setImageDuration() {
    if (timelineState.selectedClips.length !== 1) {
        showNotification('⚠️ Please select exactly 1 image clip', 'warning');
        return;
    }

    const index = timelineState.selectedClips[0];
    const clip = timelineState.clips[index];

    if (clip.type !== 'image') {
        showNotification('⚠️ Selected clip is not an image', 'warning');
        return;
    }

    const duration = parseFloat(document.getElementById('imageDuration').value);

    if (duration <= 0 || duration > 30) {
        showNotification('⚠️ Duration must be between 1 and 30 seconds', 'warning');
        return;
    }

    try {
        showNotification('⏳ Converting image to video...', 'info');

        const response = await fetch('/api/timeline/image-to-video', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                file_id: clip.fileId,
                duration: duration
            })
        });

        const data = await response.json();

        if (data.success) {
            // Update clip to video type
            clip.type = 'video';
            clip.fileId = data.video_file_id;
            clip.duration = duration;
            clip.name = clip.name.replace(/\.(jpg|jpeg|png|gif)$/i, '_' + duration + 's.mp4');

            renderTimeline();
            updateTimelineInfo();
            showNotification('✅ Image converted to ' + duration + 's video!', 'success');
        } else {
            showNotification('❌ Conversion failed: ' + data.error, 'error');
        }
    } catch (error) {
        showNotification('❌ Conversion error: ' + error.message, 'error');
    }
}

// Merge selected clips
async function mergeSelectedClips() {
    if (timelineState.selectedClips.length !== 2) {
        showNotification('⚠️ Please select exactly 2 clips to merge', 'warning');
        return;
    }

    const [idx1, idx2] = timelineState.selectedClips.sort((a, b) => a - b);
    const clip1 = timelineState.clips[idx1];
    const clip2 = timelineState.clips[idx2];

    const transition = document.getElementById('mergeTransition').value;

    try {
        showNotification('⏳ Merging clips with ' + transition + ' transition...', 'info');

        const response = await fetch('/api/timeline/merge', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                clip1_id: clip1.fileId,
                clip2_id: clip2.fileId,
                transition: transition,
                transition_duration: 1.0
            })
        });

        const data = await response.json();

        if (data.success) {
            // Replace both clips with merged clip
            const mergedClip = {
                id: Date.now() + Math.random(),
                fileId: data.merged_file_id,
                file: null,
                type: 'video',
                url: '',
                name: clip1.name + ' + ' + clip2.name,
                duration: clip1.duration + clip2.duration,
                transition: 'fade',
                uploaded: true
            };

            // Remove the 2 original clips and add merged clip
            timelineState.clips.splice(idx2, 1);
            timelineState.clips.splice(idx1, 1);
            timelineState.clips.splice(idx1, 0, mergedClip);

            timelineState.selectedClips = [];
            renderTimeline();
            updateTimelineInfo();
            showNotification('✅ Clips merged successfully!', 'success');
        } else {
            showNotification('❌ Merge failed: ' + data.error, 'error');
        }
    } catch (error) {
        showNotification('❌ Merge error: ' + error.message, 'error');
    }
}

// Preview playback (simplified)
function timelinePlayPause() {
    const video = document.getElementById('editorVideoPreview');
    const placeholder = document.getElementById('editorPlaceholder');

    if (timelineState.clips.length === 0) {
        showNotification('⚠️ Add clips to timeline first', 'warning');
        return;
    }

    if (!timelineState.isPlaying) {
        if (timelineState.currentClipIndex === null) {
            timelineState.currentClipIndex = 0;
        }

        const clip = timelineState.clips[timelineState.currentClipIndex];
        video.src = clip.url;
        video.style.display = 'block';
        placeholder.style.display = 'none';
        video.play();
        timelineState.isPlaying = true;

        video.onended = () => {
            if (timelineState.currentClipIndex < timelineState.clips.length - 1) {
                timelineState.currentClipIndex++;
                const nextClip = timelineState.clips[timelineState.currentClipIndex];
                video.src = nextClip.url;
                video.play();
            } else {
                timelineStop();
            }
        };
    } else {
        video.pause();
        timelineState.isPlaying = false;
    }
}

function timelineStop() {
    const video = document.getElementById('editorVideoPreview');
    video.pause();
    video.currentTime = 0;
    timelineState.isPlaying = false;
    timelineState.currentClipIndex = 0;
}

function timelineToggleMute() {
    const video = document.getElementById('editorVideoPreview');
    const btn = document.getElementById('timelineMuteBtn');
    video.muted = !video.muted;
    btn.textContent = video.muted ? '🔇' : '🔊';
}

function timelineSeek(event) {
    const video = document.getElementById('editorVideoPreview');
    const seekBar = document.getElementById('timelineSeekBar');
    const rect = seekBar.getBoundingClientRect();
    const percent = (event.clientX - rect.left) / rect.width;

    if (timelineState.clips.length > 0 && timelineState.currentClipIndex !== null) {
        const clip = timelineState.clips[timelineState.currentClipIndex];
        video.currentTime = clip.duration * percent;
    }
}

// Update time display
setInterval(() => {
    const video = document.getElementById('editorVideoPreview');
    const display = document.getElementById('timelineTimeDisplay');
    const fill = document.getElementById('timelineSeekFill');

    if (video && !video.paused) {
        const current = video.currentTime;
        const duration = video.duration || 0;
        display.textContent = formatTime(current) + ' / ' + formatTime(duration);

        if (duration > 0) {
            fill.style.width = (current / duration * 100) + '%';
        }
    }
}, 100);

// Export timeline
async function exportTimeline() {
    if (timelineState.clips.length === 0) {
        showNotification('⚠️ Add clips to timeline first', 'warning');
        return;
    }

    const exportBtn = document.getElementById('exportBtn');
    const exportProgress = document.getElementById('exportProgress');
    const statusText = document.getElementById('exportStatusText');
    const progressBar = document.getElementById('exportProgressBar');
    const progressText = document.getElementById('exportProgressText');

    try {
        exportBtn.disabled = true;
        exportBtn.textContent = '⏳ Exporting...';
        exportProgress.style.display = 'block';
        statusText.textContent = 'Preparing timeline data...';
        progressBar.style.width = '10%';
        progressText.textContent = '10%';

        // Prepare clips data for backend
        const clipsData = timelineState.clips.map(clip => ({
            file_id: clip.fileId,
            type: clip.type,
            duration: clip.duration,
            transition: clip.transition,
            transition_duration: 0.5
        }));

        statusText.textContent = 'Processing ' + timelineState.clips.length + ' clips...';
        progressBar.style.width = '30%';
        progressText.textContent = '30%';

        const response = await fetch('/api/timeline/process', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                clips: clipsData,
                output_quality: document.getElementById('exportQuality').value
            })
        });

        statusText.textContent = 'Merging clips with transitions...';
        progressBar.style.width = '60%';
        progressText.textContent = '60%';

        const data = await response.json();

        if (data.success) {
            statusText.textContent = 'Finalizing export...';
            progressBar.style.width = '90%';
            progressText.textContent = '90%';

            // Download the file
            window.open(data.download_url, '_blank');

            progressBar.style.width = '100%';
            progressText.textContent = '100%';
            statusText.textContent = '✅ Export complete!';

            showNotification('✅ Video exported successfully! (' + data.file_size + ')', 'success');

            setTimeout(() => {
                exportProgress.style.display = 'none';
            }, 3000);
        } else {
            throw new Error(data.error);
        }
    } catch (error) {
        console.error('Export error:', error);
        showNotification('❌ Export failed: ' + error.message, 'error');
        statusText.textContent = '❌ Export failed';
    } finally {
        exportBtn.disabled = false;
        exportBtn.textContent = '🚀 Export Final Video';
    }
}

// Helper function for time formatting
function formatTime(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return mins + ':' + (secs < 10 ? '0' : '') + secs;
}

// =============================================================================
// IMAGE STYLES MANAGEMENT (Auto Images AI)
// =============================================================================

async function loadCustomStyles() {
    try {
        const response = await fetch('/api/auto-images/styles');
        const data = await response.json();

        if (data.success) {
            renderCustomStyles(data.styles);
        }
    } catch (error) {
        console.error('Error loading custom styles:', error);
    }
}

function renderCustomStyles(styles) {
    const container = document.getElementById('customStylesList');
    if (!container) return;

    const customStyles = styles.filter(s => !s.built_in);

    if (customStyles.length === 0) {
        container.innerHTML = '<p style="color: #666; font-size: 14px;">No custom styles yet. Create your first style!</p>';
        return;
    }

    container.innerHTML = customStyles.map(style => `
        <div style="padding: 10px; margin: 5px 0; background: #fff; border: 1px solid #ddd; border-radius: 5px; display: flex; justify-content: space-between; align-items: center;">
            <div>
                <strong>${style.name}</strong>
                <p style="margin: 5px 0 0 0; color: #666; font-size: 13px;">${style.description}</p>
            </div>
            <button onclick="deleteCustomStyle('${style.id}')" class="btn-secondary" style="padding: 5px 10px; font-size: 13px;">🗑️ Delete</button>
        </div>
    `).join('');
}

function openStyleCreator() {
    const section = document.getElementById('styleCreatorSection');
    if (section) {
        section.style.display = 'block';
        // Clear form
        document.getElementById('newStyleName').value = '';
        document.getElementById('newStyleDescription').value = '';
        document.getElementById('newStyleVisualRules').value = '';
        document.getElementById('newStyleNegativeRules').value = '';
        document.getElementById('newStyleComposition').value = '';
        document.getElementById('newStyleLighting').value = '';
        document.getElementById('newStyleColors').value = '';
    }
}

function closeStyleCreator() {
    const section = document.getElementById('styleCreatorSection');
    if (section) {
        section.style.display = 'none';
    }
}

async function saveNewStyle() {
    const name = document.getElementById('newStyleName').value.trim();
    const description = document.getElementById('newStyleDescription').value.trim();
    const visualRulesText = document.getElementById('newStyleVisualRules').value.trim();
    const negativeRulesText = document.getElementById('newStyleNegativeRules').value.trim();
    const composition = document.getElementById('newStyleComposition').value.trim();
    const lighting = document.getElementById('newStyleLighting').value.trim();
    const colorsText = document.getElementById('newStyleColors').value.trim();

    // Parse textarea inputs (one per line)
    const visual_rules = visualRulesText.split('\n').map(s => s.trim()).filter(s => s.length > 0);
    const negative_rules = negativeRulesText.split('\n').map(s => s.trim()).filter(s => s.length > 0);
    const color_palette = colorsText.split('\n').map(s => s.trim()).filter(s => s.length > 0);

    // Validation
    if (!name || !description || visual_rules.length < 3 || negative_rules.length < 2 || !composition || !lighting || color_palette.length < 3) {
        showNotification('❌ Please fill all fields. Min: 3 visual rules, 2 negative rules, 3 colors', 'error');
        return;
    }

    try {
        const response = await fetch('/api/auto-images/styles', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name,
                description,
                visual_rules,
                negative_rules,
                composition,
                lighting,
                color_palette
            })
        });

        const data = await response.json();

        if (data.success) {
            showNotification('✅ Style created successfully!', 'success');
            closeStyleCreator();
            await loadCustomStyles();
        } else {
            showNotification('❌ Error: ' + data.error, 'error');
        }
    } catch (error) {
        showNotification('❌ Error creating style: ' + error.message, 'error');
    }
}

async function deleteCustomStyle(styleId) {
    if (!confirm('Delete this custom style?')) {
        return;
    }

    try {
        const response = await fetch(`/api/auto-images/styles/${styleId}`, {
            method: 'DELETE'
        });

        const data = await response.json();

        if (data.success) {
            showNotification('✅ Style deleted successfully!', 'success');
            await loadCustomStyles();
        } else {
            showNotification('❌ Error: ' + data.error, 'error');
        }
    } catch (error) {
        showNotification('❌ Error deleting style: ' + error.message, 'error');
    }
}

// Load custom styles when settings modal opens
const originalOpenSettings = window.openSettings;
window.openSettings = function() {
    if (originalOpenSettings) originalOpenSettings();
    loadCustomStyles();
};

console.log('✅ MR BAHA Editor with backend FFmpeg initialized');

// ============================================================================
// AVATAR AI FUNCTIONALITY
// ============================================================================

let avatarVideoPath = null;
let avatarAudioPath = null;
let selectedAvatarMode = 'ai_images';

// Handle avatar video upload
async function handleAvatarUpload(event) {
    const file = event.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    try {
        showNotification('Uploading avatar video...', 'info');

        const response = await fetch('/api/avatar/upload-avatar', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (data.success) {
            avatarVideoPath = data.file_path;

            // Update UI
            document.getElementById('avatarUploadZone').classList.add('uploaded');
            document.getElementById('avatarUploadZone').innerHTML = `
                <div class="upload-icon">✅</div>
                <div class="upload-text">
                    <p><strong>Avatar uploaded</strong></p>
                    <p class="hint">${file.name}</p>
                </div>
            `;

            document.getElementById('avatarFileName').textContent = data.filename;
            document.getElementById('avatarFilePath').textContent = data.file_path;
            document.getElementById('avatarInfo').style.display = 'block';

            showNotification('✅ Avatar video uploaded!', 'success');
            checkAvatarReadyToGenerate();
        } else {
            showNotification('❌ Upload failed: ' + data.error, 'error');
        }
    } catch (error) {
        showNotification('❌ Upload error: ' + error.message, 'error');
    }
}

// Handle audio upload for avatar
async function handleAudioUploadAvatar(event) {
    const file = event.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    try {
        showNotification('Uploading audio...', 'info');

        const response = await fetch('/api/avatar/upload-audio', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (data.success) {
            avatarAudioPath = data.file_path;

            // Update UI
            document.getElementById('audioUploadZone').classList.add('uploaded');
            document.getElementById('audioUploadZone').innerHTML = `
                <div class="upload-icon">✅</div>
                <div class="upload-text">
                    <p><strong>Audio uploaded</strong></p>
                    <p class="hint">${file.name}</p>
                </div>
            `;

            document.getElementById('audioFileNameAvatar').textContent = data.filename;
            document.getElementById('audioFilePathAvatar').textContent = data.file_path;
            document.getElementById('audioInfoAvatar').style.display = 'block';

            showNotification('✅ Audio uploaded!', 'success');
            checkAvatarReadyToGenerate();
        } else {
            showNotification('❌ Upload failed: ' + data.error, 'error');
        }
    } catch (error) {
        showNotification('❌ Upload error: ' + error.message, 'error');
    }
}

// Select avatar mode
function selectAvatarMode(mode) {
    selectedAvatarMode = mode;

    // Update UI
    document.getElementById('modeAiImages').classList.remove('selected');
    document.getElementById('modeStockVideos').classList.remove('selected');

    if (mode === 'ai_images') {
        document.getElementById('modeAiImages').classList.add('selected');
    } else {
        document.getElementById('modeStockVideos').classList.add('selected');
    }
}

// Check if ready to generate
function checkAvatarReadyToGenerate() {
    if (avatarVideoPath && avatarAudioPath) {
        document.getElementById('avatarGenerateBtn').disabled = false;
    }
}

// Generate avatar video
async function generateAvatarVideo() {
    const script = document.getElementById('avatarScriptInput').value;

    // Disable button and show progress
    document.getElementById('avatarGenerateBtn').disabled = true;
    document.getElementById('avatarProgress').style.display = 'block';
    document.getElementById('avatarResult').style.display = 'none';

    updateAvatarProgress(10, 'Analyzing audio with Whisper...', 'This may take 2-3 minutes...');

    try {
        const response = await fetch('/api/avatar/generate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                avatar_video: avatarVideoPath,
                audio: avatarAudioPath,
                mode: selectedAvatarMode,
                script: script,
                stock_apis: ['pexels', 'pixabay'],
                background_music_path: (window.videoData.backgroundMusic && window.videoData.backgroundMusic.path) ? window.videoData.backgroundMusic.path : null
            })
        });

        const data = await response.json();

        if (data.success) {
            updateAvatarProgress(100, 'Complete!', 'Video generated successfully');

            setTimeout(() => {
                // Hide progress and show result
                document.getElementById('avatarProgress').style.display = 'none';
                document.getElementById('avatarResult').style.display = 'block';

                // Populate result
                document.getElementById('avatarResultPath').textContent = data.video_path;
                document.getElementById('avatarResultDuration').textContent = formatDuration(data.audio_duration);
                document.getElementById('avatarResultTime').textContent = formatTime(data.generation_time);

                // Set video source
                const video = document.getElementById('avatarResultVideo');
                video.src = '/' + data.video_path;

                // Set download link
                const downloadLink = document.getElementById('avatarDownloadLink');
                downloadLink.href = '/' + data.video_path;

                // Re-enable button
                document.getElementById('avatarGenerateBtn').disabled = false;

                showNotification('✅ Avatar video generated!', 'success');
            }, 500);
        } else {
            showNotification('❌ Generation failed: ' + data.error, 'error');
            document.getElementById('avatarProgress').style.display = 'none';
            document.getElementById('avatarGenerateBtn').disabled = false;
        }
    } catch (error) {
        showNotification('❌ Error: ' + error.message, 'error');
        document.getElementById('avatarProgress').style.display = 'none';
        document.getElementById('avatarGenerateBtn').disabled = false;
    }
}

// Update avatar progress
function updateAvatarProgress(percent, text, details = '') {
    document.getElementById('avatarProgressBar').style.width = percent + '%';
    document.getElementById('avatarProgressText').textContent = text;
    document.getElementById('avatarProgressDetails').textContent = details;
}

// Format duration (seconds to MM:SS)
function formatDuration(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
}

// Format time (seconds to Xm Ys)
function formatTime(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}m ${secs}s`;
}

// =============================================================================
// AUTO VIDEOS AI & AUTO AVATAR MIX (INTEGRATED INTO QUICK GENERATOR)
// =============================================================================

// Global state for avatar videos
window.autoVideosAvatarData = null;
window.autoAvatarVideoData = null;

/**
 * Handle Auto Videos AI avatar upload (auto-muted)
 */
async function handleAutoVideosAvatarUpload(event) {
    const file = event.target.files[0];
    if (!file) return;

    showNotification('📤 Uploading and auto-muting avatar video...', 'info');

    try {
        // Upload to server and auto-mute
        const formData = new FormData();
        formData.append('avatar', file);

        const response = await fetch('/api/avatar/upload-avatar', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            throw new Error('Failed to upload avatar video');
        }

        const result = await response.json();

        // Store avatar data
        window.autoVideosAvatarData = {
            path: result.path,
            filename: file.name,
            duration: result.duration || 0
        };

        // Show preview
        const preview = document.getElementById('autoVideosAvatarPreview');
        preview.innerHTML = `
            <div style="background: rgba(76, 175, 80, 0.1); padding: 10px; border-radius: 5px; margin-top: 10px;">
                ✅ <strong>${file.name}</strong> (${(result.duration || 0).toFixed(1)}s, auto-muted)
                <button onclick="clearAutoVideosAvatar()" style="float: right; background: #f44336; color: white; border: none; padding: 5px 10px; border-radius: 3px; cursor: pointer;">Remove</button>
            </div>
        `;

        showNotification('✅ Avatar video uploaded and auto-muted!', 'success');
    } catch (error) {
        console.error('Error uploading avatar:', error);
        showNotification('❌ Failed to upload avatar video', 'error');
    }
}

/**
 * Handle Auto Avatar Mix video upload (auto-muted)
 */
async function handleAutoAvatarVideoUpload(event) {
    const file = event.target.files[0];
    if (!file) return;

    showNotification('📤 Uploading and auto-muting avatar video...', 'info');

    try {
        // Upload to server and auto-mute
        const formData = new FormData();
        formData.append('avatar', file);

        const response = await fetch('/api/avatar/upload-avatar', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            throw new Error('Failed to upload avatar video');
        }

        const result = await response.json();

        // Store avatar data
        window.autoAvatarVideoData = {
            path: result.path,
            filename: file.name,
            duration: result.duration || 0
        };

        // Show preview
        const preview = document.getElementById('autoAvatarVideoPreview');
        preview.innerHTML = `
            <div style="background: rgba(76, 175, 80, 0.1); padding: 10px; border-radius: 5px; margin-top: 10px;">
                ✅ <strong>${file.name}</strong> (${(result.duration || 0).toFixed(1)}s, auto-muted)
                <button onclick="clearAutoAvatarVideo()" style="float: right; background: #f44336; color: white; border: none; padding: 5px 10px; border-radius: 3px; cursor: pointer;">Remove</button>
            </div>
        `;

        showNotification('✅ Avatar video uploaded and auto-muted!', 'success');
    } catch (error) {
        console.error('Error uploading avatar:', error);
        showNotification('❌ Failed to upload avatar video', 'error');
    }
}

/**
 * Clear Auto Videos AI avatar
 */
function clearAutoVideosAvatar() {
    window.autoVideosAvatarData = null;
    document.getElementById('autoVideosAvatarPreview').innerHTML = '';
    document.getElementById('autoVideosAvatarUpload').value = '';
    showNotification('Avatar video removed', 'info');
}

/**
 * Clear Auto Avatar Mix video
 */
function clearAutoAvatarVideo() {
    window.autoAvatarVideoData = null;
    document.getElementById('autoAvatarVideoPreview').innerHTML = '';
    document.getElementById('autoAvatarVideoUpload').value = '';
    showNotification('Avatar video removed', 'info');
}

/**
 * Generate Auto Videos AI (Avatar + Stock Videos)
 * Uses Whisper + Gemini Director to automatically create mixed video
 */
async function generateAutoVideos() {
    // Validation
    if (!window.autoVideosAvatarData) {
        showNotification('⚠️ Please upload an avatar video first', 'warning');
        return;
    }

    // Check voice library (voices already generated in Step 2)
    const voiceLibrary = window.videoData.voiceLibrary || [];
    if (voiceLibrary.length === 0) {
        showNotification('⚠️ Please generate or upload voice first (Step 2 - Voice Library)', 'warning');
        return;
    }

    const script = document.getElementById('scriptInput')?.value;
    if (!script || script.trim().length === 0) {
        showNotification('⚠️ Please generate a script first (Step 2)', 'warning');
        return;
    }

    const stockAPI = document.getElementById('autoVideosStockAPI')?.value || 'both';

    // Get timing method
    const useWhisper = document.getElementById('autoVideosUseWhisper')?.checked || false;

    const progressDiv = document.getElementById('autoVideosProgress');
    progressDiv.style.display = 'block';
    progressDiv.innerHTML = `<div style="padding: 15px;">🤖 ${useWhisper ? 'Analyzing voice with Whisper STT (slow)...' : 'Using fast Gemini planning...'}</div>`;

    try {
        // Get all voice paths (they will be merged in sequence)
        const voicePaths = voiceLibrary.map(voice => voice.path).filter(p => p);

        // Get background music if enabled
        const backgroundMusic = window.videoData.backgroundMusic || null;

        // Call Avatar AI backend (Gemini calculates count automatically)
        const response = await fetch('/api/avatar/generate', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                avatar_video: window.autoVideosAvatarData.path,
                audio: voicePaths[0], // Use first voice (or we can merge server-side)
                voice_paths: voicePaths, // All voices in library
                background_music: backgroundMusic, // Include background music
                mode: 'stock_videos',
                script: script,
                stock_apis: stockAPI === 'both' ? ['pexels', 'pixabay'] : [stockAPI],
                use_whisper: useWhisper  // NEW: timing method (default: false = fast Gemini)
                // No media_count - Gemini calculates automatically!
            })
        });

        if (!response.ok) {
            throw new Error('Generation failed');
        }

        const result = await response.json();

        // Show final video result (backend auto-assembled it!)
        if (result.success && result.video_path) {
            const videoFilename = result.video_path.split('/').pop();
            progressDiv.innerHTML = `
                <div style="padding: 20px; background: rgba(76, 175, 80, 0.1); border-radius: 8px;">
                    <h3 style="color: #4CAF50; margin: 0 0 15px 0;">✅ Avatar Video Generated Successfully!</h3>
                    <p><strong>Duration:</strong> ${(result.audio_duration || 0).toFixed(1)}s</p>
                    <p><strong>Generation Time:</strong> ${(result.generation_time || 0).toFixed(1)}s</p>
                    <video controls style="width: 100%; max-width: 800px; aspect-ratio: 16/9; margin: 15px 0; border-radius: 8px; background: #000;">
                        <source src="/api/download/${videoFilename}" type="video/mp4">
                    </video>
                    <div>
                        <button class="btn-primary" style="margin-top: 10px;" onclick="window.location.href='/api/download/${videoFilename}'">📥 Download Video (MP4)</button>
                    </div>
                </div>
            `;

            showNotification('✅ Avatar video generated and assembled!', 'success');
        }

    } catch (error) {
        console.error('Auto Videos generation error:', error);
        progressDiv.innerHTML = '<div style="padding: 15px; background: rgba(244, 67, 54, 0.1); color: #f44336;">❌ Generation failed. Check console for details.</div>';
        showNotification('❌ Failed to generate auto videos', 'error');
    }
}

/**
 * Generate Auto Avatar Mix (Avatar + AI Images)
 * Uses Whisper + Gemini Director + Flux.1 to automatically create mixed video
 */
async function generateAutoAvatar() {
    // Validation
    if (!window.autoAvatarVideoData) {
        showNotification('⚠️ Please upload an avatar video first', 'warning');
        return;
    }

    // Check voice library (voices already generated in Step 2)
    const voiceLibrary = window.videoData.voiceLibrary || [];
    if (voiceLibrary.length === 0) {
        showNotification('⚠️ Please generate or upload voice first (Step 2 - Voice Library)', 'warning');
        return;
    }

    const script = document.getElementById('scriptInput')?.value;
    if (!script || script.trim().length === 0) {
        showNotification('⚠️ Please generate a script first (Step 2)', 'warning');
        return;
    }

    const imageStyle = document.getElementById('autoAvatarImageStyle')?.value || 'cinematic';

    // Get timing method
    const useWhisper = document.getElementById('autoAvatarUseWhisper')?.checked || false;

    const progressDiv = document.getElementById('autoAvatarProgress');
    progressDiv.style.display = 'block';
    progressDiv.innerHTML = `<div style="padding: 15px;">🤖 ${useWhisper ? 'Analyzing voice with Whisper STT (slow)...' : 'Using fast Gemini planning...'}</div>`;

    try {
        // Get all voice paths (they will be merged in sequence)
        const voicePaths = voiceLibrary.map(voice => voice.path).filter(p => p);

        // Get background music if enabled
        const backgroundMusic = window.videoData.backgroundMusic || null;

        // Call Avatar AI backend (Gemini calculates count automatically)
        const response = await fetch('/api/avatar/generate', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                avatar_video: window.autoAvatarVideoData.path,
                audio: voicePaths[0], // Use first voice (or we can merge server-side)
                voice_paths: voicePaths, // All voices in library
                background_music: backgroundMusic, // Include background music
                mode: 'ai_images',
                script: script,
                image_style: imageStyle,
                use_whisper: useWhisper  // NEW: timing method (default: false = fast Gemini)
                // No media_count - Gemini calculates automatically!
            })
        });

        if (!response.ok) {
            throw new Error('Generation failed');
        }

        const result = await response.json();

        // Show final video result (backend auto-assembled it!)
        if (result.success && result.video_path) {
            const videoFilename = result.video_path.split('/').pop();
            progressDiv.innerHTML = `
                <div style="padding: 20px; background: rgba(255, 152, 0, 0.1); border-radius: 8px;">
                    <h3 style="color: #FF9800; margin: 0 0 15px 0;">✅ Avatar Mix Video Generated Successfully!</h3>
                    <p><strong>Duration:</strong> ${(result.audio_duration || 0).toFixed(1)}s</p>
                    <p><strong>Generation Time:</strong> ${(result.generation_time || 0).toFixed(1)}s</p>
                    <video controls style="width: 100%; max-width: 800px; aspect-ratio: 16/9; margin: 15px 0; border-radius: 8px; background: #000;">
                        <source src="/api/download/${videoFilename}" type="video/mp4">
                    </video>
                    <div>
                        <button class="btn-primary" style="margin-top: 10px;" onclick="window.location.href='/api/download/${videoFilename}'">📥 Download Video (MP4)</button>
                    </div>
                </div>
            `;

            showNotification('✅ Avatar mix video generated and assembled!', 'success');
        }

    } catch (error) {
        console.error('Auto Avatar generation error:', error);
        progressDiv.innerHTML = '<div style="padding: 15px; background: rgba(244, 67, 54, 0.1); color: #f44336;">❌ Generation failed. Check console for details.</div>';
        showNotification('❌ Failed to generate auto avatar mix', 'error');
    }
}

console.log('✅ Avatar AI functionality loaded');

// ─── Voice List & Preview ────────────────────────────────────────────────────

// Static US-English voice catalogue with descriptions
// Loaded from API on init; fallback to this if API fails.
const VOICE_CATALOGUE = {
    male: [
        { id: 'Dennis',   desc: 'Deep · Authoritative · News anchor' },
        { id: 'Mark',     desc: 'Professional · Clear · Corporate' },
        { id: 'Theodore', desc: 'Warm · Friendly · Storytelling' },
        { id: 'Craig',    desc: 'Strong · Confident · Documentary' },
        { id: 'Edward',   desc: 'Refined · Calm · Narration' },
        { id: 'Timothy',  desc: 'Young · Energetic · Casual' },
        { id: 'Simon',    desc: 'Smooth · Articulate · Podcast' },
        { id: 'Oliver',   desc: 'Clear · Engaging · Explainer' },
        { id: 'Elliott',  desc: 'Rich · Measured · Drama' },
        { id: 'James',    desc: 'Classic · Trustworthy · Broadcast' },
        { id: 'Liam',     desc: 'Bright · Conversational · Friendly' },
        { id: 'Noah',     desc: 'Deep · Calm · Meditation' },
        { id: 'Ethan',    desc: 'Upbeat · Modern · Tech' },
        { id: 'Ryan',     desc: 'Casual · Relatable · Everyday' },
        { id: 'Logan',    desc: 'Bold · Dynamic · Promo' },
    ],
    female: [
        { id: 'Olivia',    desc: 'Elegant · Smooth · Premium' },
        { id: 'Sarah',     desc: 'Warm · Engaging · Conversational' },
        { id: 'Ashley',    desc: 'Energetic · Bright · Upbeat' },
        { id: 'Elizabeth', desc: 'Professional · Clear · Corporate' },
        { id: 'Wendy',     desc: 'Soft · Gentle · Soothing' },
    ],
};

// Track which gender is currently active
let _activeGender = 'male';
// Full voice list fetched from API (keyed by id)
let _apiVoiceMap = {};

async function loadVoiceList() {
    const statusEl = document.getElementById('voiceLoadStatus');

    try {
        const res = await fetch('/api/list-voices');
        const data = await res.json();
        if (data.success && data.voices && data.voices.length > 0) {
            data.voices.forEach(v => { _apiVoiceMap[v.id] = v; });
        }
    } catch (_) { /* silent — we fall back to catalogue */ }

    // Render default gender (male)
    renderVoiceDropdown('male');
    if (statusEl) { statusEl.textContent = ''; }
}

function renderVoiceDropdown(gender) {
    _activeGender = gender;

    const voiceSelect = document.getElementById('voiceId');
    if (!voiceSelect) return;

    // Update toggle button styles
    const btnMale   = document.getElementById('genderBtnMale');
    const btnFemale = document.getElementById('genderBtnFemale');
    if (btnMale && btnFemale) {
        const activeStyle   = 'flex:1; padding:7px 0; border-radius:6px; border:2px solid #667eea; background:#667eea; color:#fff; font-weight:600; cursor:pointer; font-size:0.9em;';
        const inactiveStyle = 'flex:1; padding:7px 0; border-radius:6px; border:2px solid #667eea; background:transparent; color:#667eea; font-weight:600; cursor:pointer; font-size:0.9em;';
        btnMale.style.cssText   = gender === 'male'   ? activeStyle : inactiveStyle;
        btnFemale.style.cssText = gender === 'female' ? activeStyle : inactiveStyle;
    }

    const voices = VOICE_CATALOGUE[gender] || [];
    voiceSelect.innerHTML = '';
    voices.forEach(v => {
        const opt = document.createElement('option');
        opt.value = v.id;
        opt.textContent = `${v.id}  —  ${v.desc}`;
        voiceSelect.appendChild(opt);
    });

    if (voiceSelect.options.length > 0) voiceSelect.selectedIndex = 0;
    updateVoiceDescription();
}

function filterVoicesByGender(gender) {
    renderVoiceDropdown(gender);
}

function updateVoiceDescription() {
    const voiceSelect = document.getElementById('voiceId');
    const descEl = document.getElementById('voiceDescription');
    if (!voiceSelect || !descEl) return;

    const selected = voiceSelect.value;
    const list = VOICE_CATALOGUE[_activeGender] || [];
    const entry = list.find(v => v.id === selected);
    descEl.textContent = entry ? entry.desc : '';
}

async function previewVoice() {
    const voiceSelect = document.getElementById('voiceId');
    const modelSelect = document.getElementById('voiceModel');
    const btn = document.getElementById('previewVoiceBtn');
    const audio = document.getElementById('voicePreviewAudio');
    const statusEl = document.getElementById('voiceLoadStatus');

    if (!voiceSelect || !audio) return;

    const voice_id = voiceSelect.value;
    const model_id = modelSelect ? modelSelect.value : 'inworld-tts-1.5-mini';
    const language = 'en-US';

    btn.disabled = true;
    btn.textContent = '⏳…';
    if (statusEl) statusEl.textContent = `Generating preview for "${voice_id}"…`;

    try {
        const res = await fetch('/api/preview-voice', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ voice_id, model_id, language })
        });
        const data = await res.json();

        if (!data.success) {
            showNotification(`❌ Preview failed: ${data.error}`, 'error');
            if (statusEl) statusEl.textContent = '';
            return;
        }

        audio.src = `data:audio/mp3;base64,${data.audio_base64}`;
        audio.style.display = 'none';
        audio.play();
        if (statusEl) statusEl.textContent = `▶ Playing: ${voice_id}`;
        audio.onended = () => { if (statusEl) statusEl.textContent = ''; };

    } catch (err) {
        showNotification('❌ Preview request failed', 'error');
        if (statusEl) statusEl.textContent = '';
        console.error('previewVoice error:', err);
    } finally {
        btn.disabled = false;
        btn.textContent = '▶ Preview';
    }
}
