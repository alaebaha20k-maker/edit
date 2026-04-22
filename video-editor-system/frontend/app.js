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
    lastGenerationTime: 0,
    generationCooldown: 15000,
    scriptLibrary: {},        // { en: {text, filename, chars, title}, fr: {...}, ... }
    multiLangVoiceConfig: {}  // { en: 'Dennis', fr: 'Mathieu', es: 'Diego', de: 'Josef' }
};

// Language metadata for multi-language features
const LANG_META = {
    en: { label: 'English',    flag: '🇺🇸', langCode: 'en-US', prefix: 'en-' },
    fr: { label: 'French',     flag: '🇫🇷', langCode: 'fr-FR', prefix: 'fr-' },
    es: { label: 'Spanish',    flag: '🇪🇸', langCode: 'es-ES', prefix: 'es-' },
    de: { label: 'German',     flag: '🇩🇪', langCode: 'de-DE', prefix: 'de-' },
    ar: { label: 'Arabic',     flag: '🇸🇦', langCode: 'ar-SA', prefix: 'ar-' },
    pt: { label: 'Portuguese', flag: '🇧🇷', langCode: 'pt-BR', prefix: 'pt-' },
    ru: { label: 'Russian',    flag: '🇷🇺', langCode: 'ru-RU', prefix: 'ru-' },
    zh: { label: 'Chinese',    flag: '🇨🇳', langCode: 'zh-CN', prefix: 'zh-' },
    it: { label: 'Italian',    flag: '🇮🇹', langCode: 'it-IT', prefix: 'it-' },
    nl: { label: 'Dutch',      flag: '🇳🇱', langCode: 'nl-NL', prefix: 'nl-' },
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
    // Store script internally but do NOT put it back in the textarea
    window.videoData.script = scriptData.script;
    appState.generatedScript = scriptData.script;

    // Auto-detect language and store in library (accessible via Script Library cards)
    if (scriptData.script) {
        storeScriptAutoDetect(scriptData.script, scriptData.script_filename || 'script.txt');
    }

    // Keep scriptStats, scriptDownloadSection, and voiceGenerationSection hidden —
    // the user wants a clean page on load; the script is accessible via the library.
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
    // Always re-sync API keys from backend when opening settings
    fetch('/api/alae-baha/saved-settings')
        .then(r => r.ok ? r.json() : null)
        .then(data => { if (data && data.success && data.api_keys) _applyApiKeysToForm(data.api_keys); })
        .catch(() => {});
    loadSettings();
}

function closeSettings() {
    const modal = document.getElementById('settingsModal');
    modal.classList.remove('show');
}

function _applyApiKeysToForm(api_keys) {
    const setField = (id, val) => { const el = document.getElementById(id); if (el && val) el.value = val; };
    setField('geminiKey',           api_keys.gemini);
    setField('directorGeminiKey',   api_keys.director_gemini);
    setField('geminiImageKey',      api_keys.gemini_image);
    setField('replicateKey',        api_keys.replicate);
    setField('inworldKey',          api_keys.inworld);
    setField('inworldSecret',       api_keys.inworld_secret);
    setField('pexelsKey',           api_keys.pexels);
    setField('pixabayKey',          api_keys.pixabay);
    setField('unsplashKey',         api_keys.unsplash);
    setField('braveSearchKey',      api_keys.brave_search);
    setField('serperKey',           api_keys.serper);
    setField('googleSearchKey',     api_keys.google_search);
    setField('videvoKey',           api_keys.videvo);
    setField('coverrKey',           api_keys.coverr);
    setField('geminiTranslate1Key', api_keys.gemini_translate_1);
    setField('geminiTranslate2Key', api_keys.gemini_translate_2);
    setField('geminiPromptsKey',    api_keys.gemini_prompts);
    setField('geminiSeoKey',        api_keys.gemini_seo);
    setField('claudeKey',           api_keys.claude_key);
}

const loadSettings = () => {
    // Step 1: Load formulas + niche selection from localStorage (fast, local-only data)
    try {
        const saved = localStorage.getItem('videoToolSettings');
        if (saved) {
            const settings = JSON.parse(saved);
            appState.settings = settings;

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
            if (settings.selectedNiche) {
                appState.selectedNiche = settings.selectedNiche;
            }
        }
    } catch (error) {
        console.warn('localStorage read failed:', error);
    }

    // Step 2: Always fetch API keys from backend — permanently saved on server.
    fetch('/api/alae-baha/saved-settings')
        .then(r => r.ok ? r.json() : null)
        .then(data => {
            if (data && data.success && data.api_keys) {
                _applyApiKeysToForm(data.api_keys);
                const stored = JSON.parse(localStorage.getItem('videoToolSettings') || '{}');
                stored.api_keys = Object.assign(stored.api_keys || {}, data.api_keys);
                localStorage.setItem('videoToolSettings', JSON.stringify(stored));
                console.log('✅ API keys synced from server');
            }
        })
        .catch(() => {});

    // Step 3: Load Auto Images Formula from backend
    fetch('/api/settings/formulas/auto_images')
        .then(r => r.ok ? r.json() : null)
        .then(data => {
            const el = document.getElementById('autoImagesFormulaText');
            if (el && data && data.formula) el.value = data.formula;
        })
        .catch(() => {});

    // Step 4: Load dynamic data from backend
    loadNiches();
};

// Debug: diagnose niche loading
window._debugNiches = async () => {
    const el = document.getElementById('generatorNicheSelect');
    const el2 = document.getElementById('nicheSelect');
    console.log('generatorNicheSelect element:', el ? 'FOUND' : 'NOT FOUND');
    console.log('nicheSelect element:', el2 ? 'FOUND' : 'NOT FOUND');
    const r = await fetch('/api/niches').catch(e => ({ ok: false, error: e }));
    if (!r.ok) { console.error('API error:', r.error); return; }
    const d = await r.json();
    console.log('API returned niches count:', d.niches ? d.niches.length : 0);
    console.log('First niche:', d.niches ? d.niches[0] : 'none');
    if (el) { el.innerHTML = '<option value="">DEBUG: ' + d.niches.length + ' niches loaded</option>'; }
    if (el2) { el2.innerHTML = '<option value="">DEBUG: ' + d.niches.length + ' niches loaded</option>'; }
};

const saveSettings = async () => {
    try {
        const settings = {
            api_keys: {
                gemini: document.getElementById('geminiKey')?.value || '',
                director_gemini: document.getElementById('directorGeminiKey')?.value || '',
                gemini_image: document.getElementById('geminiImageKey')?.value || '',
                replicate: document.getElementById('replicateKey')?.value || '',
                inworld: document.getElementById('inworldKey')?.value || '',
                inworld_secret: document.getElementById('inworldSecret')?.value || '',
                pexels: document.getElementById('pexelsKey')?.value || '',
                pixabay: document.getElementById('pixabayKey')?.value || '',
                unsplash: document.getElementById('unsplashKey')?.value || '',
                brave_search: document.getElementById('braveSearchKey')?.value || '',
                serper: document.getElementById('serperKey')?.value || '',
                google_search: document.getElementById('googleSearchKey')?.value || '',
                videvo: document.getElementById('videvoKey')?.value || '',
                coverr: document.getElementById('coverrKey')?.value || '',
                gemini_translate_1: document.getElementById('geminiTranslate1Key')?.value || '',
                gemini_translate_2: document.getElementById('geminiTranslate2Key')?.value || '',
                gemini_prompts:     document.getElementById('geminiPromptsKey')?.value || '',
                gemini_seo:         document.getElementById('geminiSeoKey')?.value || '',
                claude_key:         document.getElementById('claudeKey')?.value || ''
            },
            title_formulas: appState.titleFormulas || [],
            script_formulas: appState.scriptFormulas || [],
            selectedNiche: appState.selectedNiche || ''
        };

        // Save to localStorage
        localStorage.setItem('videoToolSettings', JSON.stringify(settings));
        appState.settings = settings;

        // Save ALL API keys to backend
        try {
            const response = await fetch('/api/settings/api-keys', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    gemini: settings.api_keys.gemini,
                    director_gemini: settings.api_keys.director_gemini,
                    gemini_image: settings.api_keys.gemini_image,
                    replicate: settings.api_keys.replicate,
                    inworld: settings.api_keys.inworld,
                    inworld_secret: settings.api_keys.inworld_secret,
                    pexels: settings.api_keys.pexels,
                    pixabay: settings.api_keys.pixabay,
                    unsplash: settings.api_keys.unsplash,
                    brave_search: settings.api_keys.brave_search,
                    serper: settings.api_keys.serper,
                    google_search: settings.api_keys.google_search,
                    videvo: settings.api_keys.videvo,
                    coverr: settings.api_keys.coverr,
                    gemini_translate_1: settings.api_keys.gemini_translate_1,
                    gemini_translate_2: settings.api_keys.gemini_translate_2,
                    gemini_prompts: settings.api_keys.gemini_prompts,
                    gemini_seo: settings.api_keys.gemini_seo,
                    claude_key: settings.api_keys.claude_key
                })
            });
            if (!response.ok) console.warn('Failed to save API keys to backend');
        } catch (error) {
            console.warn('Failed to save API keys to backend:', error);
        }

        // Save Auto Images Formula to backend
        const autoImagesFormulaEl = document.getElementById('autoImagesFormulaText');
        if (autoImagesFormulaEl && autoImagesFormulaEl.value.trim()) {
            try {
                await fetch('/api/settings/formulas', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ auto_images_formula: autoImagesFormulaEl.value })
                });
            } catch (e) { console.warn('Failed to save Auto Images Formula:', e); }
        }

        showNotification('✅ Settings saved successfully!', 'success');
        closeSettings();

    } catch (error) {
        console.error('Save failed:', error);
        showNotification('❌ Failed to save: ' + error.message, 'error');
    }
};

async function resetAutoImagesFormula() {
    if (!confirm('Reset the Auto Images Formula to the built-in default?')) return;
    try {
        const r = await fetch('/api/settings/formulas/auto_images/reset', { method: 'POST' });
        const data = await r.json();
        const el = document.getElementById('autoImagesFormulaText');
        if (el && data.formula) el.value = data.formula;
        showNotification('✅ Auto Images Formula reset to default', 'success');
    } catch (e) {
        showNotification('❌ Reset failed: ' + e.message, 'error');
    }
}

// =============================================================================
// NICHE MANAGEMENT SYSTEM
// =============================================================================
// ── Niche localStorage backup ─────────────────────────────────────────────────
// Niches are saved to the backend JSON file, but we also cache them in
// localStorage so the UI stays populated even if the server data directory
// is ephemeral (e.g. container restart). On every successful load we overwrite
// the cache; if the backend returns empty but the cache has data we restore it.
const NICHES_CACHE_KEY = 'video_tool_niches_cache';

function _saveNichesCache(niches) {
    try {
        localStorage.setItem(NICHES_CACHE_KEY, JSON.stringify(niches));
        localStorage.setItem('niches_cache_updated', Date.now().toString());
    } catch(_) {}
}
function _loadNichesCache() {
    try { return JSON.parse(localStorage.getItem(NICHES_CACHE_KEY) || '[]'); } catch(_) { return []; }
}

async function loadNiches() {
    console.log('[loadNiches] starting...');
    // ── 1. Immediately show cached niches so the UI is never blank ────────────
    const cached = _loadNichesCache();
    console.log('[loadNiches] cached count:', cached.length);
    if (cached.length > 0) {
        appState.niches = cached;
        renderNichesList(cached);
        updateNicheDropdown(cached);
    }

    // ── 2. Fetch from backend ─────────────────────────────────────────────────
    try {
        const response = await fetch('/api/niches');
        console.log('[loadNiches] fetch response.ok:', response.ok, 'status:', response.status);
        const data = await response.json();
        console.log('[loadNiches] data.niches count:', data.niches ? data.niches.length : 0);

        if (data.niches && data.niches.length > 0) {
            // Backend has data → use it and update cache
            appState.niches = data.niches;
            renderNichesList(data.niches);
            updateNicheDropdown(data.niches);
            _saveNichesCache(data.niches);
            console.log('[loadNiches] dropdown updated with backend data');

        } else if (cached.length > 0 && (!data.niches || data.niches.length === 0)) {
            // Backend empty but cache has data → auto-restore to backend
            console.warn('[loadNiches] backend empty, restoring from cache...');
            let restored = 0;
            for (const niche of cached) {
                try {
                    await fetch('/api/niches', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({
                            name: niche.name,
                            language: niche.language,
                            writing_guidelines: niche.writing_guidelines,
                        })
                    });
                    restored++;
                } catch(_) {}
            }
            if (restored > 0) {
                showNotification(`♻️ Restored ${restored} niche(s) from local backup`, 'success');
                // Reload from backend now that they're restored
                const r2 = await fetch('/api/niches');
                const d2 = await r2.json();
                if (d2.niches && d2.niches.length > 0) {
                    appState.niches = d2.niches;
                    renderNichesList(d2.niches);
                    updateNicheDropdown(d2.niches);
                    _saveNichesCache(d2.niches);
                }
            }
        }
    } catch (error) {
        console.error('[loadNiches] FAILED:', error);
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

        // Reload niches (also updates localStorage cache)
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
    console.log('[updateNicheDropdown] called with', niches ? niches.length : 0, 'niches');
    // Update settings dropdown
    const dropdown = document.getElementById('nicheSelect');
    console.log('[updateNicheDropdown] nicheSelect element:', dropdown ? 'FOUND' : 'NOT FOUND');
    if (dropdown) {
        dropdown.innerHTML = '<option value="">-- Select a niche --</option>';
        if (niches && niches.length > 0) {
            niches.forEach(n => {
                const selected = appState.selectedNiche === n.id ? 'selected' : '';
                dropdown.innerHTML += `<option value="${n.id}">${n.name} (${n.language})</option>`;
            });
        }
    }

    // ALSO update generator dropdown (for script generation page)
    const generatorDropdown = document.getElementById('generatorNicheSelect');
    console.log('[updateNicheDropdown] generatorNicheSelect element:', generatorDropdown ? 'FOUND' : 'NOT FOUND');
    if (generatorDropdown) {
        generatorDropdown.innerHTML = '<option value="">-- Select a niche --</option>';
        if (niches && niches.length > 0) {
            niches.forEach(n => {
                const selected = appState.selectedNiche === n.id ? 'selected' : '';
                generatorDropdown.innerHTML += `<option value="${n.id}">${n.name} (${n.language})</option>`;
            });
        }
    }

    // ALSO update Batch Script Writer dropdown
    const batchDropdown = document.getElementById('batchNicheSelect');
    if (batchDropdown) {
        batchDropdown.innerHTML = '<option value="">-- Select a niche --</option>';
        if (niches && niches.length > 0) {
            niches.forEach(n => {
                batchDropdown.innerHTML += `<option value="${n.id}">${n.name} (${n.language})</option>`;
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

        // Auto-detect language and store in Script Library
        storeScriptAutoDetect(text, file.name);

        // Show download + translate section
        const dlSection = document.getElementById('scriptDownloadSection');
        if (dlSection) dlSection.style.display = 'block';

        showNotification('✅ Script loaded from file', 'success');
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

        // Detect chosen AI engine
        const engineRadio = document.querySelector('input[name="aiEngine"]:checked');
        const provider    = engineRadio ? engineRadio.value : 'gemini';
        const engineLabel = provider === 'claude' ? '🔮 Claude Sonnet' : '🤖 Gemini 2.5 Pro';

        if (resultBox) {
            resultBox.innerHTML = `<p>${engineLabel} — Generating script (3-Chunk Mode)…</p>
                <p style="color:#888;font-size:0.9em;">Using niche writing guidelines. Please wait…</p>`;
        }

        appState.lastGenerationTime = Date.now();

            const response = await fetch('/api/generate-script', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    title: title,
                    niche_id: selectedNicheId,
                    length: selectedLength,
                    provider: provider
                })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || 'Script generation failed');
            }

            // Store script internally (not displayed — user downloads it)
            window.videoData.script = data.script;
            appState.generatedScript = data.script;

            // AI-generated scripts are always English; update checkboxes accordingly
            storeScriptInLibrary('en', data.script, data.script_filename || 'script_en.txt');
            updateTranslationCheckboxes('en');

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
                            <strong>📦 Chunks:</strong><br>${data.chunks_used} chunks
                        </div>
                        <div>
                            <strong>⏱️ Time:</strong><br>${data.time.toFixed(1)}s
                        </div>
                        <div>
                            <strong>📄 File:</strong><br>${data.script_filename || 'script.txt'}
                        </div>
                    </div>
                    <div style="margin-top:12px; padding:10px; background:rgba(0,0,0,0.04); border-radius:6px; font-size:12px; color:#555; border-left:3px solid #4CAF50;">
                        <strong>✅ Script loaded in textarea below (${data.length.toLocaleString()} chars after cleaning):</strong><br>
                        <em>${(data.script || '').substring(0, 120).replace(/</g,'&lt;')}…</em>
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
    window.videoData.selectedVoiceIndex = window.videoData.voiceLibrary.length - 1;
    renderVoiceLibrary();
    renderMultiLangExportSection();
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
                            ${voice.langCode ? `<span style="background:#1e3a2e; color:#10b981; padding:1px 6px; border-radius:4px; font-size:11px; font-weight:700;">${(LANG_META[voice.langCode]?.flag || '') + ' ' + (LANG_META[voice.langCode]?.label || voice.langCode.toUpperCase())}</span>` : ''}
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
        renderMultiLangExportSection();
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

// ---------------------------------------------------------------------------
// Language detection — uses first ~600 chars to score against word lists
// ---------------------------------------------------------------------------
function detectScriptLanguage(text) {
    if (!text || text.trim().length === 0) return 'en';

    // ── Fast Unicode-range detection for non-Latin scripts ──────────────────
    const sample2k = text.slice(0, 2000);
    const arabicCount  = (sample2k.match(/[\u0600-\u06FF]/g) || []).length;
    const cyrillicCount = (sample2k.match(/[\u0400-\u04FF]/g) || []).length;
    const cjkCount     = (sample2k.match(/[\u4E00-\u9FFF\u3040-\u30FF]/g) || []).length;
    const charTotal    = sample2k.replace(/\s/g, '').length || 1;
    if (arabicCount  / charTotal > 0.15) return 'ar';
    if (cyrillicCount / charTotal > 0.15) return 'ru';
    if (cjkCount     / charTotal > 0.15) return 'zh';

    // ── Frequency-based detection for Latin-script languages ────────────────
    // Use first 3000 chars, count how often each marker word appears (not just presence)
    const lower = text.slice(0, 3000).toLowerCase().replace(/[^a-zàâäéèêëîïôùûüœçñáéíóúüßãõ\s]/g, ' ');
    const words = lower.match(/\b[a-zàâäéèêëîïôùûüœçñáéíóúüßãõ]{2,}\b/g) || [];
    const freq = {};
    words.forEach(w => { freq[w] = (freq[w] || 0) + 1; });
    const totalWords = words.length || 1;

    // Distinctive markers — words that are strongly characteristic of each language
    const markers = {
        fr: ['je', 'vous', 'nous', 'elle', 'est', 'les', 'des', 'une', 'ce', 'mais', 'bien', 'pour', 'sur', 'avec', 'dans', 'qui', 'que', 'du', 'au', 'très', 'aussi', 'tout', 'cette', 'sont', 'pas', 'était', 'comme', 'leur', 'dont', 'cela'],
        es: ['los', 'las', 'del', 'por', 'como', 'pero', 'más', 'este', 'para', 'también', 'sus', 'muy', 'cuando', 'hay', 'todo', 'era', 'sobre', 'qué', 'él', 'han', 'ser', 'una', 'esto', 'bien', 'aquí'],
        de: ['der', 'die', 'das', 'ein', 'eine', 'ist', 'und', 'für', 'auf', 'mit', 'nicht', 'von', 'dem', 'den', 'ich', 'wir', 'dass', 'haben', 'auch', 'werden', 'durch', 'nach', 'über', 'war', 'beim', 'zur', 'zum', 'zu', 'aber', 'wenn'],
        pt: ['os', 'as', 'do', 'da', 'dos', 'das', 'que', 'com', 'por', 'uma', 'para', 'não', 'mais', 'ele', 'ela', 'nos', 'mas', 'seu', 'sua', 'isso', 'também', 'porque', 'quando', 'foram', 'está'],
        en: ['the', 'and', 'was', 'were', 'of', 'or', 'but', 'it', 'he', 'she', 'they', 'this', 'that', 'for', 'with', 'you', 'your', 'have', 'been', 'will', 'their', 'from', 'what', 'when', 'there'],
    };

    const scores = {};
    for (const [lang, list] of Object.entries(markers)) {
        // Sum frequencies of all marker words, normalized by total word count
        scores[lang] = list.reduce((sum, w) => sum + (freq[w] || 0), 0) / totalWords;
    }

    const best = Object.entries(scores).sort((a, b) => b[1] - a[1]);
    // Return best match only if score is meaningfully above zero
    return best[0][1] > 0.005 ? best[0][0] : 'en';
}

// Update translation checkboxes — hide the detected language, show the rest
function updateTranslationCheckboxes(detectedLang) {
    const allLangs = { en: 'translateEN', fr: 'translateFR', es: 'translateES', de: 'translateDE' };
    for (const [lang, checkboxId] of Object.entries(allLangs)) {
        const label = document.getElementById(checkboxId)?.closest('label');
        if (!label) continue;
        if (lang === detectedLang) {
            label.style.opacity = '0.35';
            label.style.pointerEvents = 'none';
            label.title = `Already in ${LANG_META[lang]?.label || lang}`;
            document.getElementById(checkboxId).checked = false;
        } else {
            label.style.opacity = '';
            label.style.pointerEvents = '';
            label.title = '';
        }
    }

    // Show detected-language badge next to the download button
    const badge = document.getElementById('detectedLangBadge');
    if (badge) {
        const meta = LANG_META[detectedLang];
        badge.textContent = `${meta?.flag || ''} Detected: ${meta?.label || detectedLang}`;
        badge.style.display = 'inline-block';
    }
}

// Store script in library with auto-detection of language
function storeScriptAutoDetect(text, filename) {
    const lang = detectScriptLanguage(text);
    storeScriptInLibrary(lang, text, filename);
    updateTranslationCheckboxes(lang);
    return lang;
}

async function translateAndDownload() {
    // Read from the detected-language slot, then textarea, then videoData
    const detectedLang = appState.detectedScriptLang || 'en';
    const script = (appState.scriptLibrary[detectedLang]?.text)
                || document.getElementById('scriptInput')?.value?.trim()
                || window.videoData.script
                || appState.generatedScript;
    if (!script || script.trim().length === 0) {
        showNotification('⚠️ No script available to translate. Generate or paste a script first.', 'warning');
        return;
    }
    // Make sure the full script is synced to videoData before translating
    window.videoData.script = script;
    appState.generatedScript = script;

    const langMap = { en: 'translateEN', fr: 'translateFR', es: 'translateES', de: 'translateDE' };
    const selected = Object.entries(langMap)
        .filter(([lang, id]) => lang !== detectedLang && document.getElementById(id)?.checked)
        .map(([code]) => code);

    if (selected.length === 0) {
        showNotification('⚠️ Select at least one language to translate', 'warning');
        return;
    }

    const progressEl = document.getElementById('translateProgress');
    if (progressEl) {
        progressEl.style.display = 'block';
        progressEl.textContent = `⏳ Translating to ${selected.map(l => l.toUpperCase()).join(', ')}… This may take a minute.`;
    }

    try {
        const res = await fetch('/api/translate-script', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ script, languages: selected })
        });
        const data = await res.json();

        if (!res.ok || !data.success) {
            throw new Error(data.error || 'Translation failed');
        }

        const title = document.getElementById('titleInput')?.value || window.videoData.title || 'script';
        const baseFilename = title.replace(/[^a-z0-9]/gi, '_').toLowerCase();

        const langLabels = { fr: 'french', es: 'spanish', de: 'german' };
        let stored = 0;
        for (const [lang, text] of Object.entries(data.translations)) {
            if (!text) continue;
            const filename = `${baseFilename}_${langLabels[lang] || lang}.txt`;
            // Store in Script Library (also auto-downloads)
            storeScriptInLibrary(lang, text, filename);
            // Also trigger browser download
            const blob = new Blob([text], { type: 'text/plain' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url; a.download = filename;
            document.body.appendChild(a); a.click();
            document.body.removeChild(a); URL.revokeObjectURL(url);
            stored++;
        }

        const errCount = Object.keys(data.errors || {}).length;
        if (progressEl) {
            progressEl.textContent = `✅ ${stored} translated script(s) saved to library${errCount ? ` · ⚠️ ${errCount} error(s)` : ''}`;
        }
        showNotification(`✅ ${stored} translations done — see Script Library below!`, 'success');

    } catch (err) {
        if (progressEl) progressEl.textContent = `❌ ${err.message}`;
        showNotification('❌ Translation failed: ' + err.message, 'error');
    }
}

// =============================================================================
// SCRIPT LIBRARY
// =============================================================================

function storeScriptInLibrary(langCode, text, filename) {
    const title = document.getElementById('titleInput')?.value || window.videoData.title || 'script';
    appState.scriptLibrary[langCode] = { text, filename, chars: text.length, title };
    // Track the "source" language so translateAndDownload reads from the right slot
    if (!appState.detectedScriptLang || langCode !== 'en') {
        // A non-EN store is always the source; EN only sets it if nothing else did
        if (langCode !== 'en' || !appState.detectedScriptLang) {
            appState.detectedScriptLang = langCode;
        }
    }
    renderScriptLibrary();
    renderMultiLangVoiceSection();
    renderMultiLangExportSection();
}

function renderScriptLibrary() {
    const section = document.getElementById('scriptLibrarySection');
    const container = document.getElementById('scriptLibraryList');
    if (!container) return;

    const langs = Object.keys(appState.scriptLibrary);
    if (langs.length === 0) {
        if (section) section.style.display = 'none';
        return;
    }
    if (section) section.style.display = 'block';

    container.innerHTML = langs.map(lang => {
        const s = appState.scriptLibrary[lang];
        const meta = LANG_META[lang] || { flag: '🌍', label: lang.toUpperCase() };
        const previewText = s.text.substring(0, 1500) + (s.text.length > 1500 ? '\n...' : '');
        return `
        <div style="border:1px solid #374151; border-radius:9px; padding:13px; margin-bottom:9px; background:rgba(255,255,255,0.02);">
            <div style="display:flex; align-items:center; justify-content:space-between; gap:8px; flex-wrap:wrap;">
                <div style="display:flex; align-items:center; gap:10px;">
                    <span style="font-size:1.5em;">${meta.flag}</span>
                    <div>
                        <strong style="color:#e2e8f0; font-size:13px;">${meta.label}</strong>
                        <div style="color:#6b7280; font-size:11px;">${s.chars.toLocaleString()} chars · ${s.filename}</div>
                    </div>
                </div>
                <div style="display:flex; gap:5px; flex-shrink:0;">
                    <button onclick="toggleScriptView('${lang}')" style="padding:5px 10px; background:#374151; border:none; border-radius:5px; color:#e2e8f0; cursor:pointer; font-size:11px;">👁 View</button>
                    <button onclick="downloadScriptFromLibrary('${lang}')" style="padding:5px 10px; background:#16a34a; border:none; border-radius:5px; color:white; cursor:pointer; font-size:11px;">📥 Download</button>
                    <button onclick="deleteScriptFromLibrary('${lang}')" style="padding:5px 10px; background:#dc2626; border:none; border-radius:5px; color:white; cursor:pointer; font-size:11px;">🗑</button>
                </div>
            </div>
            <div id="scriptView_${lang}" style="display:none; margin-top:10px;">
                <textarea readonly style="width:100%; height:140px; resize:vertical; background:#0f172a; color:#d1d5db; border:1px solid #374151; border-radius:6px; padding:8px; font-size:11px; font-family:monospace; box-sizing:border-box;">${previewText}</textarea>
            </div>
        </div>`;
    }).join('');
}

function toggleScriptView(lang) {
    const el = document.getElementById(`scriptView_${lang}`);
    if (el) el.style.display = el.style.display === 'none' ? 'block' : 'none';
}

function downloadScriptFromLibrary(lang) {
    const s = appState.scriptLibrary[lang];
    if (!s) return;
    const blob = new Blob([s.text], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = s.filename;
    document.body.appendChild(a); a.click();
    document.body.removeChild(a); URL.revokeObjectURL(url);
    showNotification(`📥 Downloaded: ${s.filename}`, 'success');
}

function deleteScriptFromLibrary(lang) {
    const meta = LANG_META[lang] || { label: lang };
    if (!confirm(`Delete ${meta.label} script from library?`)) return;
    delete appState.scriptLibrary[lang];
    renderScriptLibrary();
    renderMultiLangVoiceSection();
    renderMultiLangExportSection();
}

// =============================================================================
// MULTI-LANGUAGE VOICE PACK
// =============================================================================

function renderMultiLangVoiceSection() {
    const section = document.getElementById('multiLangVoiceSection');
    const list = document.getElementById('multiLangVoiceList');
    if (!section || !list) return;

    const langs = Object.keys(appState.scriptLibrary);
    if (langs.length === 0) { section.style.display = 'none'; return; }
    section.style.display = 'block';

    list.innerHTML = langs.map(lang => {
        const meta = LANG_META[lang] || { flag: '🌍', label: lang.toUpperCase(), prefix: 'en-', langCode: lang + '-' + lang.toUpperCase() };
        const allVoices = [...(VOICE_CATALOGUE.male || []), ...(VOICE_CATALOGUE.female || [])];
        // Voices matching this language; fall back to English voices if none available for language
        let langVoices = allVoices.filter(v => (v.lang || 'en-US').startsWith(meta.prefix));
        const usingFallback = langVoices.length === 0;
        if (usingFallback) langVoices = allVoices.filter(v => (v.lang || 'en-US').startsWith('en-'));
        const stored = appState.multiLangVoiceConfig[lang] || (langVoices[0]?.id || '');
        if (!appState.multiLangVoiceConfig[lang] && langVoices[0]) {
            appState.multiLangVoiceConfig[lang] = langVoices[0].id;
        }
        const fallbackNote = usingFallback ? `<span style="color:#f59e0b; font-size:10px; margin-left:4px;">⚠ using EN voices (no ${meta.label} voices in catalogue)</span>` : '';
        const options = langVoices.map(v =>
            `<option value="${v.id}" ${v.id === stored ? 'selected' : ''}>${v.id} — ${v.desc}</option>`
        ).join('');

        const voiceLibrary = window.videoData.voiceLibrary || [];
        const hasVoice = voiceLibrary.some(v => v.langCode === lang);
        const doneTag = hasVoice ? '<span style="color:#10b981; font-size:11px; margin-left:4px;">✅ Done</span>' : '';

        return `
        <div style="display:flex; align-items:center; gap:10px; padding:9px 10px; background:rgba(255,255,255,0.03); border-radius:7px; margin-bottom:7px; border:1px solid #2d1b69; flex-wrap:wrap;">
            <span style="font-size:1.2em; flex-shrink:0;">${meta.flag}</span>
            <strong style="min-width:62px; color:#e2e8f0; font-size:12px;">${meta.label}${doneTag}${fallbackNote}</strong>
            <select id="multiLangVoice_${lang}" onchange="appState.multiLangVoiceConfig['${lang}']=this.value"
                style="flex:1; min-width:140px; background:#1e1e2e; color:#e2e8f0; border:1px solid #374151; border-radius:6px; padding:5px; font-size:12px;">
                ${options}
            </select>
            <button onclick="generateSingleLanguageVoice('${lang}')"
                style="padding:5px 12px; background:#667eea; border:none; border-radius:6px; color:white; cursor:pointer; font-size:11px; white-space:nowrap; flex-shrink:0;">
                🎙 Generate
            </button>
        </div>`;
    }).join('');
}

async function generateSingleLanguageVoice(lang) {
    const s = appState.scriptLibrary[lang];
    if (!s) { showNotification(`⚠️ No ${lang} script in library`, 'warning'); return false; }

    const meta = LANG_META[lang] || { label: lang.toUpperCase(), langCode: lang + '-' + lang.toUpperCase(), flag: '🌍' };
    const voiceId = document.getElementById(`multiLangVoice_${lang}`)?.value
                 || appState.multiLangVoiceConfig[lang] || 'Olivia';

    const progressEl = document.getElementById('multiLangVoiceProgress');
    if (progressEl) { progressEl.style.display = 'block'; progressEl.textContent = `⏳ Generating ${meta.flag} ${meta.label} voice (${voiceId})…`; }

    try {
        const res = await fetch('/api/generate-voice', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                script: s.text,
                voice_id: voiceId,
                model_id: 'inworld-tts-1.5-mini',
                language: meta.langCode,
                speaking_rate: parseFloat(document.getElementById('speakingRate')?.value || '1.0')
            })
        });
        const data = await res.json();
        if (!res.ok || !data.success) throw new Error(data.error || 'Voice generation failed');

        addVoiceToLibrary({
            url: data.audio_url,
            path: data.audio_path,
            filename: data.audio_filename,
            duration: data.duration_seconds,
            chunks: data.chunks_count,
            voice: voiceId,
            language: meta.langCode,
            model: 'inworld-tts-1.5-mini',
            speed: parseFloat(document.getElementById('speakingRate')?.value || '1.0'),
            type: 'ai',
            langCode: lang
        });

        const mins = Math.floor(data.duration_seconds / 60);
        const secs = Math.floor(data.duration_seconds % 60);
        if (progressEl) progressEl.textContent = `✅ ${meta.flag} ${meta.label} voice done: ${mins}m ${secs}s`;
        showNotification(`✅ ${meta.label} voice generated!`, 'success');
        renderMultiLangVoiceSection();
        renderMultiLangExportSection();
        return true;
    } catch (err) {
        if (progressEl) progressEl.textContent = `❌ ${meta.label} failed: ${err.message}`;
        showNotification(`❌ ${meta.label} voice failed: ${err.message}`, 'error');
        return false;
    }
}

async function generateAllLanguageVoices() {
    const langs = Object.keys(appState.scriptLibrary);
    if (langs.length === 0) { showNotification('⚠️ Generate scripts first', 'warning'); return; }

    const btn = document.getElementById('generateAllVoicesBtn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Generating…'; }

    const progressEl = document.getElementById('multiLangVoiceProgress');
    if (progressEl) { progressEl.style.display = 'block'; progressEl.textContent = ''; }

    let done = 0;
    for (let i = 0; i < langs.length; i++) {
        const lang = langs[i];
        const meta = LANG_META[lang] || { label: lang };
        if (progressEl) progressEl.textContent = `⏳ [${i+1}/${langs.length}] Generating ${meta.label} voice…`;
        const ok = await generateSingleLanguageVoice(lang);
        if (ok) done++;
        if (i < langs.length - 1) await new Promise(r => setTimeout(r, 3000));
    }

    if (btn) { btn.disabled = false; btn.textContent = '🎙️ Generate All Language Voices (one by one)'; }
    if (progressEl) progressEl.textContent = `✅ Finished: ${done}/${langs.length} voices generated.`;
    showNotification(`✅ ${done}/${langs.length} voices done!`, done > 0 ? 'success' : 'warning');
}

// =============================================================================
// MULTI-LANGUAGE VIDEO EXPORT
// =============================================================================

function renderMultiLangExportSection() {
    const section = document.getElementById('multiLangExportSection');
    const list = document.getElementById('multiLangExportList');
    if (!section || !list) return;

    const scriptLangs = Object.keys(appState.scriptLibrary);
    const voiceLibrary = window.videoData.voiceLibrary || [];
    const readyLangs = scriptLangs.filter(lang => voiceLibrary.some(v => v.langCode === lang));

    if (readyLangs.length === 0) { section.style.display = 'none'; return; }
    section.style.display = 'block';

    list.innerHTML = readyLangs.map(lang => {
        const meta = LANG_META[lang] || { flag: '🌍', label: lang };
        const voices = voiceLibrary.filter(v => v.langCode === lang);
        const totalDur = voices.reduce((s, v) => s + (parseFloat(v.duration) || 0), 0);
        const durStr = `${Math.floor(totalDur/60)}m ${Math.floor(totalDur%60)}s`;
        return `
        <div style="display:flex; align-items:center; gap:10px; padding:8px 10px; background:rgba(255,255,255,0.03); border-radius:7px; margin-bottom:6px; border:1px solid #1e3a2e;">
            <input type="checkbox" id="exportLang_${lang}" checked style="width:15px; height:15px; cursor:pointer;">
            <span style="font-size:1.2em;">${meta.flag}</span>
            <strong style="color:#e2e8f0; font-size:13px;">${meta.label}</strong>
            <span style="color:#6b7280; font-size:11px;">· ${voices.length} voice(s) · ${durStr}</span>
        </div>`;
    }).join('');
}

async function generateMultiLangVideos() {
    const mediaLibrary = appState.mediaLibrary || [];
    if (mediaLibrary.length === 0) {
        showNotification('⚠️ Add media first (Step 3)', 'warning');
        return;
    }

    const qualityRadio = document.querySelector('input[name="quality"]:checked');
    const quality = qualityRadio ? qualityRadio.value : '720';
    const resolution = quality === '1080' ? '1920x1080' : '1280x720';
    const useKenBurns = document.getElementById('useKenBurns')?.checked || false;
    const mediaPaths = mediaLibrary.map(m => m.path || m.url).filter(Boolean);
    const voiceLibrary = window.videoData.voiceLibrary || [];

    const scriptLangs = Object.keys(appState.scriptLibrary);
    const selectedLangs = scriptLangs.filter(lang => {
        const cb = document.getElementById(`exportLang_${lang}`);
        return cb ? cb.checked : false;
    }).filter(lang => voiceLibrary.some(v => v.langCode === lang));

    if (selectedLangs.length === 0) {
        showNotification('⚠️ No languages ready (need scripts + voices)', 'warning');
        return;
    }

    const btn = document.getElementById('generateMultiLangBtn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Generating…'; }

    const progressEl = document.getElementById('multiLangExportProgress');
    const resultsEl = document.getElementById('multiLangExportResults');
    if (progressEl) { progressEl.style.display = 'block'; progressEl.innerHTML = ''; }
    if (resultsEl) resultsEl.innerHTML = '';

    let done = 0;
    const title = document.getElementById('titleInput')?.value || window.videoData.title || 'video';

    for (let i = 0; i < selectedLangs.length; i++) {
        const lang = selectedLangs[i];
        const meta = LANG_META[lang] || { flag: '🌍', label: lang };
        const langVoices = voiceLibrary.filter(v => v.langCode === lang);
        const voicePaths = langVoices.map(v => v.path).filter(Boolean);

        const logLine = (html) => { if (progressEl) progressEl.innerHTML += `<div>${html}</div>`; };
        logLine(`⏳ [${i+1}/${selectedLangs.length}] Assembling ${meta.flag} ${meta.label} video…`);

        try {
            const res = await fetch('/api/assemble-video', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    voice_paths: voicePaths,
                    media_paths: mediaPaths,
                    title: `${title} [${meta.label}]`,
                    resolution,
                    use_ken_burns: useKenBurns,
                    background_music_path: window.videoData.backgroundMusic?.path || null
                })
            });
            const data = await res.json();
            if (!res.ok || !data.success) throw new Error(data.error || 'Assembly failed');

            done++;
            logLine(`<span style="color:#10b981;">✅ ${meta.flag} ${meta.label} done!</span>`);
            if (resultsEl) resultsEl.innerHTML += `
            <div style="padding:11px; border:1px solid #1e3a2e; border-radius:8px; margin-bottom:7px; background:rgba(16,185,129,0.06);">
                <div style="display:flex; justify-content:space-between; align-items:center; gap:8px; flex-wrap:wrap;">
                    <strong style="color:#10b981;">${meta.flag} ${meta.label} ✅</strong>
                    <button onclick="window.location.href='${data.download_url}'"
                        style="padding:5px 14px; background:#10b981; border:none; border-radius:5px; color:white; cursor:pointer; font-size:12px;">
                        📥 Download
                    </button>
                </div>
                <div style="color:#6b7280; font-size:11px; margin-top:4px;">
                    ${data.output_filename} · ${data.duration_formatted} · ${(data.file_size_mb||0).toFixed(1)} MB
                </div>
            </div>`;
        } catch (err) {
            logLine(`<span style="color:#ef4444;">❌ ${meta.flag} ${meta.label}: ${err.message}</span>`);
        }
        if (i < selectedLangs.length - 1) await new Promise(r => setTimeout(r, 2000));
    }

    if (btn) { btn.disabled = false; btn.textContent = '🚀 Generate All Language Videos'; }
    showNotification(`✅ ${done}/${selectedLangs.length} videos assembled`, done > 0 ? 'success' : 'warning');
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
                        ⏱️ ${minutes}:${seconds.toString().padStart(2, '0')} • Will loop at 5% volume
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
    backgroundMusicAudio.volume = 0.05; // Preview at 5% volume
    backgroundMusicAudio.play();
    showNotification('▶️ Playing music preview at 5% volume...', 'info');

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
        if (section) {
            section.style.display = checked ? 'block' : 'none';
            if (checked) {
                loadAutoImageStyles(); // Load styles (including custom) when section opens
            }
        }
    } else if (type === 'localimages') {
        const checked = document.getElementById('useLocalImagesMix')?.checked;
        const section = document.getElementById('localImagesMixSection');
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
            ? `<video src="${media.url}" style="width: 100%; height: 120px; object-fit: cover;" ${media.muted ? 'muted' : ''}></video>`
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
        renderMediaLibrary();
    }
}

function muteAllVideos() {
    const videos = appState.mediaLibrary.filter(m => m.type === 'video');
    if (videos.length === 0) {
        showNotification('No videos in media library', 'info');
        return;
    }
    const allMuted = videos.every(m => m.muted);
    // Toggle: if all already muted → unmute all; otherwise → mute all
    const newState = !allMuted;
    videos.forEach(m => { m.muted = newState; });
    window.videoData.mediaLibrary = appState.mediaLibrary;
    renderMediaLibrary();
    showNotification(newState ? `🔇 ${videos.length} video(s) muted` : `🔊 ${videos.length} video(s) unmuted`, 'info');
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

// Cache all loaded styles for full-object lookup
window._cachedAutoImageStyles = [];

// Load and populate style selector(s)
async function loadAutoImageStyles() {
    try {
        const response = await fetch('/api/auto-images/styles');
        const data = await response.json();

        if (data.success && data.styles) {
            // Cache the full style objects
            window._cachedAutoImageStyles = data.styles;

            // Populate all style dropdowns: Auto Images AI, Auto Avatar Mix, Prompts Generator, Mixed
            ['autoImageStyle', 'autoAvatarImageStyle', 'pgStyleSelect', 'mixedImageStyleSelect'].forEach(selectId => {
                const styleSelect = document.getElementById(selectId);
                if (styleSelect) {
                    const currentVal = styleSelect.value;
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
                    // Restore previous selection if still available
                    if (currentVal) styleSelect.value = currentVal;
                }
            });
        }
    } catch (error) {
        console.error('Error loading styles:', error);
    }
}

// =============================================================================
// PROMPTS GENERATOR — image or video prompts, scene-by-scene from script
// =============================================================================

let _pgMode = 'image'; // 'image' | 'video' | 'mixed'

function pgSetMode(mode) {
    _pgMode = mode;
    const isMixed = mode === 'mixed';
    const isVideo = mode === 'video';

    // Tabs
    const tabCfg = {
        image: { bg: 'linear-gradient(135deg,#8b5cf6,#6d28d9)', col: '#fff' },
        video: { bg: 'linear-gradient(135deg,#dc2626,#7f1d1d)', col: '#fff' },
        mixed: { bg: 'linear-gradient(135deg,#f59e0b,#92400e)', col: '#fff' },
        off:   { bg: '#1e1e2e', col: '#888' },
    };
    ['image','video','mixed'].forEach(t => {
        const el = document.getElementById(`pgTab${t.charAt(0).toUpperCase()+t.slice(1)}`);
        if (!el) return;
        const active = t === mode ? tabCfg[t] : tabCfg.off;
        el.style.background = active.bg;
        el.style.color      = active.col;
    });

    // Show/hide single-mode vs mixed-mode panels
    document.getElementById('pgSingleModeWrap').style.display = isMixed ? 'none' : '';
    document.getElementById('pgMixedModeWrap').style.display  = isMixed ? '' : 'none';

    if (!isMixed) {
        // Style selectors in single mode
        document.getElementById('pgImageStyleWrap').style.display = isVideo ? 'none' : '';
        document.getElementById('pgVideoStyleWrap').style.display = isVideo ? '' : 'none';

        const btn = document.getElementById('pgGenerateBtn');
        if (btn) {
            btn.textContent = isVideo ? '🎬 Generate Video Prompts' : '🎨 Generate Image Prompts';
            btn.style.background = isVideo
                ? 'linear-gradient(135deg,#dc2626,#7f1d1d)'
                : 'linear-gradient(135deg,#8b5cf6,#6d28d9)';
        }
        const lbl = document.getElementById('pgResultLabel');
        if (lbl) lbl.childNodes[0].textContent = isVideo ? 'Generated Video Prompts ' : 'Generated Image Prompts ';
    } else {
        // Mixed mode: populate both dropdowns and update stats
        _populateMixedDropdowns();
        mixedUpdateSplit(document.getElementById('mixedSplitSlider')?.value || 50);
        mixedUpdateStats();
    }

    document.getElementById('pgResultSection').style.display = 'none';
    document.getElementById('pgProgressBox').style.display   = 'none';

    if (isVideo) loadVideoStylesSelect();
}

async function loadVideoStylesSelect() {
    try {
        const r = await fetch('/api/video-styles');
        const d = await r.json();
        if (!d.success) return;
        // Single-mode selector
        const sel = document.getElementById('pgVideoStyleSelect');
        if (sel) {
            const cur = sel.value;
            sel.innerHTML = d.styles.map(s =>
                `<option value="${s.id}">${s.built_in ? '🎬' : '✨'} ${s.name}</option>`
            ).join('');
            if (cur) sel.value = cur;
        }
        // Mixed-mode video selector
        const msel = document.getElementById('mixedVideoStyleSelect');
        if (msel) {
            const cur2 = msel.value;
            msel.innerHTML = d.styles.map(s =>
                `<option value="${s.id}">${s.built_in ? '🎬' : '✨'} ${s.name}</option>`
            ).join('');
            if (cur2) msel.value = cur2;
        }
    } catch (e) { console.warn('Could not load video styles:', e); }
}

async function _populateMixedDropdowns() {
    // Populate video styles
    await loadVideoStylesSelect();
    // Populate image styles in mixed image selector
    if (window._cachedAutoImageStyles) {
        const sel = document.getElementById('mixedImageStyleSelect');
        if (sel) {
            const cur = sel.value;
            sel.innerHTML = window._cachedAutoImageStyles.map(s => {
                const icon = s.id === 'cinematic' ? '🎬' : s.id === 'photorealistic' ? '📷' : s.id === 'artistic' ? '🎨' : s.id === 'animated' ? '🎭' : '✨';
                return `<option value="${s.id}">${icon} ${s.name}</option>`;
            }).join('');
            if (cur) sel.value = cur;
        }
    }
}

function mixedUpdateSplit(pct) {
    const script = document.getElementById('scriptInput')?.value || '';
    const totalChars = script.length;
    const splitPos   = Math.round(totalChars * (pct / 100));
    document.getElementById('mixedSplitLabel').textContent = pct + '%';
    if (totalChars > 0) {
        document.getElementById('mixedSplitChars').textContent =
            ` · first ${splitPos.toLocaleString()} chars → video · last ${(totalChars - splitPos).toLocaleString()} chars → images`;
    }
    mixedUpdateStats();
}

function mixedUpdateStats() {
    const vCount = parseInt(document.getElementById('mixedVideoCount')?.value) || 0;
    const durMin = ((vCount * 10) / 60).toFixed(1);
    const el = document.getElementById('mixedVideoDuration');
    if (el) el.textContent = `≈ ${durMin} min of video (${vCount} × 10s)`;
}

async function generateMixedPrompts() {
    const script = (document.getElementById('scriptInput')?.value || '').trim();
    if (!script) { showNotification('⚠️ Enter or generate a script first', 'warning'); return; }

    const pct            = parseInt(document.getElementById('mixedSplitSlider')?.value) || 50;
    const splitPos       = Math.round(script.length * (pct / 100));
    const vidStyleId     = document.getElementById('mixedVideoStyleSelect')?.value;
    const imgStyleId     = document.getElementById('mixedImageStyleSelect')?.value;
    const videoCount     = parseInt(document.getElementById('mixedVideoCount')?.value) || 20;
    const imageCount     = parseInt(document.getElementById('mixedImageCount')?.value) || 20;

    if (!vidStyleId) { showNotification('⚠️ Select a video style', 'warning'); return; }
    if (!imgStyleId) { showNotification('⚠️ Select an image style', 'warning'); return; }

    const progressBox   = document.getElementById('pgProgressBox');
    const resultSection = document.getElementById('pgResultSection');
    progressBox.style.display = 'block';
    progressBox.style.borderLeftColor = '#f59e0b';
    const durMin = ((videoCount * 10) / 60).toFixed(1);
    progressBox.innerHTML = `<p>🎬+🖼️ Generating mixed prompts…<br>
        <small style="color:#888;">Step 1/2: ${videoCount} video prompts (first ${pct}% of script = ~${durMin} min) → then ${imageCount} image prompts</small></p>`;
    resultSection.style.display = 'none';
    document.getElementById('pgOutputText').value = '';

    try {
        const r = await fetch('/api/generate-mixed-prompts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                script,
                split_char_pos: splitPos,
                video_style_id: vidStyleId,
                video_count:    videoCount,
                style_id:       imgStyleId,
                image_count:    imageCount,
            })
        });
        const d = await r.json();
        if (!r.ok || !d.success) throw new Error(d.error || 'Generation failed');

        // Build combined output
        const lines = [
            `${'═'.repeat(60)}`,
            `🎬 VIDEO PROMPTS (${d.video_count}) — Style: ${d.vid_style_name}`,
            `Script: first ${pct}% (${d.split_pos.toLocaleString()} chars) · ≈ ${d.video_duration_min} min of video (each ~10s)`,
            `${'═'.repeat(60)}`,
            '',
            d.video_prompts.join('\n\n'),
            '',
            `${'═'.repeat(60)}`,
            `🖼️ IMAGE PROMPTS (${d.image_count}) — Style: ${d.img_style_name}`,
            `Script: last ${100-pct}% (${(d.total_chars - d.split_pos).toLocaleString()} chars)`,
            `${'═'.repeat(60)}`,
            '',
            d.image_prompts.join('\n\n'),
        ];
        const combined = lines.join('\n');
        document.getElementById('pgOutputText').value = combined;
        document.getElementById('pgCountLabel').textContent =
            `(${d.video_count} video + ${d.image_count} image prompts)`;
        document.getElementById('pgResultLabel').childNodes[0].textContent = '🎬+🖼️ Mixed Prompts ';

        progressBox.innerHTML = `<p style="color:#22c55e;">✅ ${d.video_count} video + ${d.image_count} image prompts ready!</p>`;
        resultSection.style.display = 'block';
        resultSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
        showNotification(`✅ Mixed: ${d.video_count} video + ${d.image_count} image prompts!`, 'success');
    } catch (e) {
        progressBox.innerHTML = `<p style="color:#ef4444;">❌ ${e.message}</p>`;
        showNotification('❌ ' + e.message, 'error');
    }
}

async function generatePromptsOnly() {
    const script = (document.getElementById('scriptInput')?.value || window.videoData?.script || '').trim();
    if (!script) {
        showNotification('⚠️ Please enter or generate a script first', 'warning');
        return;
    }

    const count = parseInt(document.getElementById('pgCount')?.value) || 20;
    if (count < 1 || count > 200) {
        showNotification('⚠️ Number of prompts must be between 1 and 200', 'warning');
        return;
    }

    const isVideo     = _pgMode === 'video';
    const styleId     = document.getElementById('pgStyleSelect')?.value;
    const vidStyleId  = document.getElementById('pgVideoStyleSelect')?.value;

    if (!isVideo && !styleId) {
        showNotification('⚠️ Please select an image style', 'warning');
        return;
    }
    if (isVideo && !vidStyleId) {
        showNotification('⚠️ Please select a video style', 'warning');
        return;
    }

    const progressBox   = document.getElementById('pgProgressBox');
    const resultSection = document.getElementById('pgResultSection');
    const outputEl      = document.getElementById('pgOutputText');
    const countLabel    = document.getElementById('pgCountLabel');

    progressBox.style.display = 'block';
    progressBox.style.borderLeftColor = isVideo ? '#dc2626' : '#8b5cf6';
    progressBox.innerHTML = `<p>${isVideo ? '🎬' : '🎨'} Generating <strong>${count}</strong> ${isVideo ? 'video' : 'image'} prompts with Director Gemini…<br>
        <small style="color:#888;">${count > 15 ? 'Sending in chunks of 15 — please wait' : 'Single call — almost done'}</small></p>`;
    resultSection.style.display = 'none';
    if (outputEl) outputEl.value = '';

    try {
        const body = {
            script,
            count,
            mode: _pgMode,
            style_id:       styleId,
            video_style_id: vidStyleId,
        };

        const response = await fetch('/api/generate-prompts-only', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });

        const data = await response.json();

        if (!response.ok || !data.success) {
            throw new Error(data.error || 'Prompts generation failed');
        }

        const text = data.prompts.join('\n\n');
        if (outputEl) outputEl.value = text;
        if (countLabel) countLabel.textContent = `(${data.prompts.length} prompts · ${data.style_name})`;

        progressBox.innerHTML = `<p style="color:#22c55e;">✅ ${data.prompts.length} ${isVideo ? 'video' : 'image'} prompts generated!</p>`;
        resultSection.style.display = 'block';
        showNotification(`✅ ${data.prompts.length} prompts ready!`, 'success');

    } catch (error) {
        progressBox.innerHTML = `<p style="color:#ef4444;">❌ ${error.message}</p>`;
        showNotification('❌ Prompts generation failed: ' + error.message, 'error');
    }
}

function downloadPromptsText() {
    const text = document.getElementById('pgOutputText')?.value;
    if (!text) return;
    const blob = new Blob([text], { type: 'text/plain' });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href     = url;
    a.download = _pgMode === 'video' ? 'video_prompts.txt' : 'image_prompts.txt';
    a.click();
    URL.revokeObjectURL(url);
}

// =============================================================================
// VIDEO STYLES — Settings management
// =============================================================================

async function loadVideoStylesList() {
    try {
        const r = await fetch('/api/video-styles');
        const d = await r.json();
        if (!d.success) return;
        _renderVideoStylesList(d.styles);
    } catch (e) { console.warn('Could not load video styles:', e); }
}

function _renderVideoStylesList(styles) {
    const container = document.getElementById('videoStylesList');
    if (!container) return;
    const custom = styles.filter(s => !s.built_in);
    if (custom.length === 0) {
        container.innerHTML = '<p style="color:#666; font-size:14px;">No custom video styles yet. Create your first one!</p>';
        return;
    }
    container.innerHTML = custom.map(s => `
        <div style="padding:10px 14px; margin:5px 0; background:#1a0a0a; border:1px solid #7f1d1d; border-radius:8px; display:flex; justify-content:space-between; align-items:flex-start;">
            <div style="flex:1; min-width:0;">
                <strong style="color:#f87171;">✨ ${s.name}</strong>
                <p style="margin:3px 0 0; color:#666; font-size:12px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${(s.style_formula||'').substring(0,100).replace(/\n/g,' ')}…</p>
            </div>
            <div style="display:flex; gap:6px; margin-left:10px; flex-shrink:0;">
                <button onclick="editVideoStyle('${s.id}')" style="background:#7f1d1d; color:#fca5a5; border:none; border-radius:6px; padding:4px 10px; font-size:12px; cursor:pointer;">✏️ Edit</button>
                <button onclick="deleteVideoStyle('${s.id}')" style="background:#450a0a; color:#fca5a5; border:none; border-radius:6px; padding:4px 10px; font-size:12px; cursor:pointer;">🗑️</button>
            </div>
        </div>`).join('');
}

function openVideoStyleCreator() {
    document.getElementById('editingVideoStyleId').value = '';
    document.getElementById('videoStyleCreatorTitle').textContent = '➕ New Video Style';
    document.getElementById('newVideoStyleName').value = '';
    document.getElementById('newVideoStyleFormula').value = '';
    document.getElementById('newVideoStyleDesc').value = '';
    document.getElementById('videoStyleCreatorSection').style.display = 'block';
    document.getElementById('videoStyleCreatorSection').scrollIntoView({ behavior:'smooth', block:'start' });
}

function closeVideoStyleCreator() {
    document.getElementById('videoStyleCreatorSection').style.display = 'none';
    document.getElementById('editingVideoStyleId').value = '';
}

async function editVideoStyle(styleId) {
    try {
        const r = await fetch('/api/video-styles');
        const d = await r.json();
        const s = (d.styles || []).find(x => x.id === styleId);
        if (!s) return;
        document.getElementById('editingVideoStyleId').value = styleId;
        document.getElementById('videoStyleCreatorTitle').textContent = '✏️ Edit: ' + s.name;
        document.getElementById('newVideoStyleName').value    = s.name || '';
        document.getElementById('newVideoStyleFormula').value = s.style_formula || '';
        document.getElementById('newVideoStyleDesc').value    = s.description || '';
        document.getElementById('videoStyleCreatorSection').style.display = 'block';
        document.getElementById('videoStyleCreatorSection').scrollIntoView({ behavior:'smooth', block:'start' });
    } catch (e) { showNotification('❌ Could not load style', 'error'); }
}

async function saveVideoStylePreset() {
    const editingId    = document.getElementById('editingVideoStyleId').value.trim();
    const name         = document.getElementById('newVideoStyleName').value.trim();
    const style_formula = document.getElementById('newVideoStyleFormula').value.trim();
    const description  = document.getElementById('newVideoStyleDesc').value.trim();

    if (!name)         { showNotification('❌ Style name is required', 'error'); return; }
    if (!style_formula || style_formula.length < 10) { showNotification('❌ Formula is required', 'error'); return; }

    try {
        const isEdit = editingId !== '';
        const url    = isEdit ? `/api/video-styles/${editingId}` : '/api/video-styles';
        const method = isEdit ? 'PUT' : 'POST';
        const r = await fetch(url, {
            method, headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, style_formula, description })
        });
        const d = await r.json();
        if (d.success) {
            showNotification(isEdit ? '✅ Video style updated!' : '✅ Video style saved!', 'success');
            closeVideoStyleCreator();
            await loadVideoStylesList();
            loadVideoStylesSelect();
        } else {
            showNotification('❌ ' + (d.error || 'Save failed'), 'error');
        }
    } catch (e) { showNotification('❌ ' + e.message, 'error'); }
}

async function deleteVideoStyle(styleId) {
    if (!confirm('Delete this video style?')) return;
    try {
        const r = await fetch(`/api/video-styles/${styleId}`, { method: 'DELETE' });
        const d = await r.json();
        if (d.success) {
            showNotification('✅ Video style deleted', 'success');
            await loadVideoStylesList();
            loadVideoStylesSelect();
        } else {
            showNotification('❌ ' + (d.error || 'Delete failed'), 'error');
        }
    } catch (e) { showNotification('❌ ' + e.message, 'error'); }
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
    // Also call loadNiches directly to ensure it runs
    loadNiches();

    // Sync manual scriptInput textarea → videoData + library (debounced)
    const scriptInputEl = document.getElementById('scriptInput');
    if (scriptInputEl) {
        let _scriptSyncTimer = null;
        scriptInputEl.addEventListener('input', () => {
            clearTimeout(_scriptSyncTimer);
            _scriptSyncTimer = setTimeout(() => {
                const txt = scriptInputEl.value.trim();
                if (txt.length > 50) {
                    window.videoData.script = txt;
                    appState.generatedScript = txt;
                    // Show download/translate section
                    const dlSection = document.getElementById('scriptDownloadSection');
                    if (dlSection) dlSection.style.display = 'block';
                    // Auto-detect language and store in library
                    storeScriptAutoDetect(txt, 'pasted_script.txt');
                    showVoiceSectionIfScriptAvailable();
                }
            }, 1200);
        });
    }

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

    // Pre-load image styles so both Auto Images and Auto Avatar dropdowns are ready
    loadAutoImageStyles();

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

    container.innerHTML = customStyles.map(style => {
        const preview = style.style_formula
            ? style.style_formula.substring(0, 120).replace(/\n/g, ' ') + (style.style_formula.length > 120 ? '…' : '')
            : (style.description || '');
        return `
        <div style="padding: 12px; margin: 6px 0; background: #1a1a2e; border: 1px solid #4c1d95; border-radius: 8px;">
            <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                <div style="flex:1; min-width:0;">
                    <strong style="color:#a78bfa;">${style.name}</strong>
                    ${style.style_formula ? '<span style="font-size:11px; color:#7c3aed; margin-left:8px; background:#2d1b69; padding:1px 6px; border-radius:10px;">formula</span>' : ''}
                    <p style="margin: 4px 0 0; color:#888; font-size:12px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${preview}</p>
                </div>
                <div style="display:flex; gap:6px; margin-left:10px; flex-shrink:0;">
                    <button onclick="editCustomStyle('${style.id}')" style="background:#4c1d95; color:#e2e8f0; border:none; border-radius:6px; padding:4px 10px; font-size:12px; cursor:pointer;">✏️ Edit</button>
                    <button onclick="deleteCustomStyle('${style.id}')" style="background:#7f1d1d; color:#fca5a5; border:none; border-radius:6px; padding:4px 10px; font-size:12px; cursor:pointer;">🗑️</button>
                </div>
            </div>
        </div>`;
    }).join('');
}

function openStyleCreator() {
    document.getElementById('editingStyleId').value = '';
    document.getElementById('styleCreatorTitle').textContent = '✏️ Create New Style';
    document.getElementById('newStyleName').value = '';
    document.getElementById('newStyleFormula').value = '';
    document.getElementById('newStyleDescription').value = '';
    document.getElementById('newStyleVisualRules').value = '';
    document.getElementById('newStyleNegativeRules').value = '';
    document.getElementById('newStyleComposition').value = '';
    document.getElementById('newStyleLighting').value = '';
    document.getElementById('newStyleColors').value = '';
    document.getElementById('styleCreatorSection').style.display = 'block';
    document.getElementById('styleCreatorSection').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function editCustomStyle(styleId) {
    // Find the style in the loaded list
    fetch(`/api/auto-images/styles/${styleId}`)
        .then(r => r.json())
        .then(data => {
            const s = data.style;
            if (!s) return;
            document.getElementById('editingStyleId').value = styleId;
            document.getElementById('styleCreatorTitle').textContent = '✏️ Edit Style: ' + s.name;
            document.getElementById('newStyleName').value = s.name || '';
            document.getElementById('newStyleFormula').value = s.style_formula || '';
            document.getElementById('newStyleDescription').value = s.description || '';
            document.getElementById('newStyleVisualRules').value = (s.visual_rules || []).join('\n');
            document.getElementById('newStyleNegativeRules').value = (s.negative_rules || []).join('\n');
            document.getElementById('newStyleComposition').value = s.composition || '';
            document.getElementById('newStyleLighting').value = s.lighting || '';
            document.getElementById('newStyleColors').value = (s.color_palette || []).join('\n');
            document.getElementById('styleCreatorSection').style.display = 'block';
            document.getElementById('styleCreatorSection').scrollIntoView({ behavior: 'smooth', block: 'start' });
        })
        .catch(() => showNotification('❌ Could not load style', 'error'));
}

function closeStyleCreator() {
    document.getElementById('styleCreatorSection').style.display = 'none';
    document.getElementById('editingStyleId').value = '';
}

async function saveNewStyle() {
    const editingId = document.getElementById('editingStyleId').value.trim();
    const name         = document.getElementById('newStyleName').value.trim();
    const style_formula = document.getElementById('newStyleFormula').value.trim();
    const description  = document.getElementById('newStyleDescription').value.trim();
    const visual_rules = document.getElementById('newStyleVisualRules').value.trim().split('\n').map(s=>s.trim()).filter(Boolean);
    const negative_rules = document.getElementById('newStyleNegativeRules').value.trim().split('\n').map(s=>s.trim()).filter(Boolean);
    const composition  = document.getElementById('newStyleComposition').value.trim();
    const lighting     = document.getElementById('newStyleLighting').value.trim();
    const color_palette = document.getElementById('newStyleColors').value.trim().split('\n').map(s=>s.trim()).filter(Boolean);

    if (!name) { showNotification('❌ Style Name is required', 'error'); return; }
    if (!style_formula && (visual_rules.length < 3 || negative_rules.length < 2)) {
        showNotification('❌ Fill the Style Formula OR provide 3+ visual rules and 2+ negative rules', 'error');
        return;
    }

    const body = { name, style_formula, description, visual_rules, negative_rules, composition, lighting, color_palette };

    try {
        const isEdit = editingId !== '';
        const url    = isEdit ? `/api/auto-images/styles/${editingId}` : '/api/auto-images/styles';
        const method = isEdit ? 'PUT' : 'POST';

        const response = await fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        const data = await response.json();

        if (data.success) {
            showNotification(isEdit ? '✅ Style updated!' : '✅ Style created!', 'success');
            closeStyleCreator();
            await loadCustomStyles();
        } else {
            showNotification('❌ ' + (data.error || 'Unknown error'), 'error');
        }
    } catch (error) {
        showNotification('❌ ' + error.message, 'error');
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
    const avatarScriptEl = document.getElementById('avatarScriptInput');
    const script = (avatarScriptEl ? avatarScriptEl.value : '') ||
                   window.videoData.script ||
                   appState.generatedScript ||
                   document.getElementById('scriptInput')?.value || '';

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

    const imageStyleId = document.getElementById('autoAvatarImageStyle')?.value || 'cinematic';
    // Resolve full style object from cache (so Gemini Director gets visual_rules, lighting, etc.)
    const imageStyleObj = (window._cachedAutoImageStyles || []).find(s => s.id === imageStyleId) || { id: imageStyleId, name: imageStyleId };

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
                image_style: imageStyleObj,
                image_provider: 'gemini',
                use_whisper: useWhisper  // timing method (default: false = fast Gemini)
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
        // English
        { id: 'Dennis',   desc: 'Deep · Authoritative · News anchor',   lang: 'en-US' },
        { id: 'Mark',     desc: 'Professional · Clear · Corporate',      lang: 'en-US' },
        { id: 'Theodore', desc: 'Warm · Friendly · Storytelling',        lang: 'en-US' },
        { id: 'Craig',    desc: 'Strong · Confident · Documentary',      lang: 'en-US' },
        { id: 'Edward',   desc: 'Refined · Calm · Narration',            lang: 'en-US' },
        { id: 'Timothy',  desc: 'Young · Energetic · Casual',            lang: 'en-US' },
        { id: 'Simon',    desc: 'Smooth · Articulate · Podcast',         lang: 'en-US' },
        { id: 'Oliver',   desc: 'Clear · Engaging · Explainer',          lang: 'en-US' },
        { id: 'Elliott',  desc: 'Rich · Measured · Drama',               lang: 'en-US' },
        { id: 'James',    desc: 'Classic · Trustworthy · Broadcast',     lang: 'en-US' },
        { id: 'Liam',     desc: 'Bright · Conversational · Friendly',    lang: 'en-US' },
        { id: 'Noah',     desc: 'Deep · Calm · Meditation',              lang: 'en-US' },
        { id: 'Ethan',    desc: 'Upbeat · Modern · Tech',                lang: 'en-US' },
        { id: 'Ryan',     desc: 'Casual · Relatable · Everyday',         lang: 'en-US' },
        { id: 'Logan',    desc: 'Bold · Dynamic · Promo',                lang: 'en-US' },
        { id: 'Blake',    desc: 'Smooth · Cool · Modern',                lang: 'en-US' },
        { id: 'Clive',    desc: 'Deep · Calm · Authoritative',           lang: 'en-US' },
        // French
        { id: 'Mathieu',  desc: 'Naturel · Professionnel · FR',          lang: 'fr-FR' },
        { id: 'Étienne',  desc: 'Chaleureux · Storytelling · FR',        lang: 'fr-FR' },
        { id: 'Alain',    desc: 'Profond · Autoritaire · FR',            lang: 'fr-FR' },
        // German
        { id: 'Josef',    desc: 'Klar · Professionell · DE',             lang: 'de-DE' },
        // Spanish
        { id: 'Diego',    desc: 'Suave · Calmado · Narración · ES',      lang: 'es-ES' },
        { id: 'Miguel',   desc: 'Cálido · Storytelling · ES',            lang: 'es-ES' },
        { id: 'Rafael',   desc: 'Profundo · Sereno · Narración · ES',    lang: 'es-ES' },
    ],
    female: [
        // English
        { id: 'Olivia',    desc: 'Elegant · Smooth · Premium',           lang: 'en-US' },
        { id: 'Sarah',     desc: 'Warm · Engaging · Conversational',     lang: 'en-US' },
        { id: 'Ashley',    desc: 'Energetic · Bright · Upbeat',          lang: 'en-US' },
        { id: 'Elizabeth', desc: 'Professional · Clear · Corporate',     lang: 'en-US' },
        { id: 'Wendy',     desc: 'Soft · Gentle · Soothing',             lang: 'en-US' },
        // French
        { id: 'Hélène',   desc: 'Douce · Élégante · FR',                lang: 'fr-FR' },
        // German
        { id: 'Johanna',   desc: 'Ruhig · Tief · Smoky · DE',           lang: 'de-DE' },
        // Spanish
        { id: 'Lupita',    desc: 'Vibrante · Energética · ES',           lang: 'es-ES' },
    ],
};

function getVoiceLang(voiceId) {
    const all = [...(VOICE_CATALOGUE.male || []), ...(VOICE_CATALOGUE.female || [])];
    const entry = all.find(v => v.id === voiceId);
    return (entry && entry.lang) ? entry.lang : 'en-US';
}

// Track active language/gender filters
let _activeGender = 'male';
let _activeLang = 'en';  // 'en' | 'fr' | 'de' | 'es'
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

function renderVoiceDropdown(gender, lang) {
    if (gender) _activeGender = gender;
    if (lang)   _activeLang   = lang;

    const voiceSelect = document.getElementById('voiceId');
    if (!voiceSelect) return;

    // Update gender button styles
    const btnMale   = document.getElementById('genderBtnMale');
    const btnFemale = document.getElementById('genderBtnFemale');
    if (btnMale && btnFemale) {
        const activeStyle   = 'flex:1; padding:7px 0; border-radius:6px; border:2px solid #667eea; background:#667eea; color:#fff; font-weight:600; cursor:pointer; font-size:0.9em;';
        const inactiveStyle = 'flex:1; padding:7px 0; border-radius:6px; border:2px solid #667eea; background:transparent; color:#667eea; font-weight:600; cursor:pointer; font-size:0.9em;';
        btnMale.style.cssText   = _activeGender === 'male'   ? activeStyle : inactiveStyle;
        btnFemale.style.cssText = _activeGender === 'female' ? activeStyle : inactiveStyle;
    }

    // Update language button styles
    const langMap = { en: 'voiceLangEn', fr: 'voiceLangFr', de: 'voiceLangDe', es: 'voiceLangEs' };
    Object.entries(langMap).forEach(([lc, btnId]) => {
        const btn = document.getElementById(btnId);
        if (btn) {
            btn.style.background = (_activeLang === lc) ? '#667eea' : 'transparent';
            btn.style.color      = (_activeLang === lc) ? '#fff'    : '#667eea';
        }
    });

    // Filter voices by language
    const langPrefixMap = { en: 'en-', fr: 'fr-', de: 'de-', es: 'es-' };
    const prefix = langPrefixMap[_activeLang] || 'en-';
    const allForGender = VOICE_CATALOGUE[_activeGender] || [];
    const voices = allForGender.filter(v => (v.lang || 'en-US').startsWith(prefix));

    voiceSelect.innerHTML = '';
    voices.forEach(v => {
        const opt = document.createElement('option');
        opt.value = v.id;
        opt.textContent = `${v.id}  —  ${v.desc}`;
        voiceSelect.appendChild(opt);
    });

    if (voiceSelect.options.length === 0) {
        const opt = document.createElement('option');
        opt.value = '';
        opt.textContent = '— No voices for this combination —';
        voiceSelect.appendChild(opt);
    } else {
        voiceSelect.selectedIndex = 0;
    }
    updateVoiceDescription();
}

function filterVoicesByGender(gender) {
    renderVoiceDropdown(gender, null);
}

function filterVoicesByLang(lang) {
    renderVoiceDropdown(null, lang);
}

function updateVoiceDescription() {
    const voiceSelect = document.getElementById('voiceId');
    const descEl = document.getElementById('voiceDescription');
    if (!voiceSelect || !descEl) return;

    const selected = voiceSelect.value;
    const allVoices = [...(VOICE_CATALOGUE.male || []), ...(VOICE_CATALOGUE.female || [])];
    const entry = allVoices.find(v => v.id === selected);
    descEl.textContent = entry ? entry.desc : '';

    // Keep the hidden language input in sync so generation uses the right locale
    const langInput = document.getElementById('voiceLanguage');
    if (langInput) langInput.value = getVoiceLang(selected);
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
    const language = getVoiceLang(voice_id);

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

// =============================================================================
// LOCAL IMAGES MIX — Avatar + user's own images, no AI generation
// =============================================================================

// Stores avatar path (server-side, muted) for local mix
window.localMixAvatarData = null;
// Stores uploaded image paths from server
window.localMixImagePaths = [];

async function handleLocalMixAvatarUpload(event) {
    const file = event.target.files[0];
    if (!file) return;

    showNotification('📤 Uploading and muting avatar video...', 'info');
    const preview = document.getElementById('localMixAvatarPreview');
    preview.innerHTML = '<p style="color:#888;">Uploading...</p>';

    try {
        const formData = new FormData();
        formData.append('avatar', file);

        const res = await fetch('/api/avatar/upload-avatar', { method: 'POST', body: formData });
        const data = await res.json();
        if (!data.success) throw new Error(data.error || 'Upload failed');

        window.localMixAvatarData = { path: data.path, duration: data.duration };

        preview.innerHTML = `
            <div style="background:rgba(76,175,80,0.1); padding:10px; border-radius:5px;">
                ✅ <strong>${file.name}</strong> (${(data.duration || 0).toFixed(1)}s, muted)
                <button onclick="window.localMixAvatarData=null; document.getElementById('localMixAvatarPreview').innerHTML='';"
                    style="float:right; background:#f44336; color:white; border:none; padding:4px 10px; border-radius:3px; cursor:pointer;">Remove</button>
            </div>`;
        showNotification('✅ Avatar uploaded!', 'success');
    } catch (err) {
        preview.innerHTML = '';
        showNotification('❌ Failed to upload avatar: ' + err.message, 'error');
    }
}

async function handleLocalImagesUpload(event) {
    const files = Array.from(event.target.files);
    if (!files.length) return;

    const preview = document.getElementById('localImagesPreview');
    preview.innerHTML = '<p style="color:#888;">Uploading images...</p>';
    showNotification(`📤 Uploading ${files.length} image(s)...`, 'info');

    try {
        const formData = new FormData();
        files.forEach(f => formData.append('images', f));

        const res = await fetch('/api/avatar/upload-local-images', { method: 'POST', body: formData });
        const data = await res.json();
        if (!data.success) throw new Error(data.error || 'Upload failed');

        window.localMixImagePaths = data.images.map(i => i.path);

        preview.innerHTML = `
            <div style="background:rgba(103,58,183,0.1); padding:10px; border-radius:5px; text-align:left;">
                ✅ <strong>${data.count} image(s) ready</strong>
                <button onclick="window.localMixImagePaths=[]; document.getElementById('localImagesPreview').innerHTML='';"
                    style="float:right; background:#f44336; color:white; border:none; padding:4px 10px; border-radius:3px; cursor:pointer;">Clear</button>
                <div style="margin-top:8px; font-size:12px; color:#666;">
                    ${data.images.map(i => `• ${i.name}`).join('<br>')}
                </div>
            </div>`;
        showNotification(`✅ ${data.count} image(s) uploaded!`, 'success');
    } catch (err) {
        preview.innerHTML = '';
        showNotification('❌ Failed to upload images: ' + err.message, 'error');
    }
}

async function generateLocalImagesMix() {
    if (!window.localMixAvatarData) {
        showNotification('⚠️ Please upload an avatar video first', 'warning'); return;
    }
    if (!window.localMixImagePaths || window.localMixImagePaths.length === 0) {
        showNotification('⚠️ Please upload at least one image', 'warning'); return;
    }

    const voiceLibrary = window.videoData?.voiceLibrary || [];
    if (voiceLibrary.length === 0) {
        showNotification('⚠️ Please generate or upload voice first (Step 2)', 'warning'); return;
    }

    const progressDiv = document.getElementById('localImagesMixProgress');
    progressDiv.style.display = 'block';
    progressDiv.innerHTML = `<div style="padding:15px;">
        ⚡ Assembling video — ${window.localMixImagePaths.length} image(s) + avatar loop...<br>
        <small style="color:#888;">Smart timing: 30s avatar → 5s image (no AI needed)</small>
    </div>`;

    try {
        const voicePaths = voiceLibrary.map(v => v.path).filter(Boolean);
        const backgroundMusic = window.videoData?.backgroundMusic || null;

        const res = await fetch('/api/avatar/generate-local-mix', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                avatar_video: window.localMixAvatarData.path,
                audio: voicePaths[0],
                voice_paths: voicePaths,
                image_paths: window.localMixImagePaths,
                background_music: backgroundMusic
            })
        });

        const result = await res.json();
        if (!result.success) throw new Error(result.error || 'Generation failed');

        const videoFilename = result.video_path.split('/').pop();
        const imagesMsg = result.images_used < result.total_images
            ? `${result.images_used}/${result.total_images} images used (avatar loops for remaining time)`
            : `All ${result.total_images} images used`;

        progressDiv.innerHTML = `
            <div style="padding:20px; background:rgba(103,58,183,0.1); border-radius:8px;">
                <h3 style="color:#673ab7; margin:0 0 15px 0;">✅ Local Images Mix Ready!</h3>
                <p><strong>Duration:</strong> ${(result.audio_duration || 0).toFixed(1)}s</p>
                <p><strong>Images:</strong> ${imagesMsg}</p>
                <p><strong>Timing:</strong> ${(result.avatar_gap || 30).toFixed(0)}s avatar + 5s image per cycle</p>
                <p><strong>Done in:</strong> ${(result.generation_time || 0).toFixed(1)}s</p>
                <video controls style="width:100%; max-width:800px; aspect-ratio:16/9; margin:15px 0; border-radius:8px; background:#000;">
                    <source src="/api/download/${videoFilename}" type="video/mp4">
                </video>
                <div>
                    <button class="btn-primary" onclick="window.location.href='/api/download/${videoFilename}'">📥 Download Video (MP4)</button>
                </div>
            </div>`;
        showNotification('✅ Local Images Mix video ready!', 'success');

    } catch (err) {
        console.error('Local Images Mix error:', err);
        progressDiv.innerHTML = `<div style="padding:15px; background:rgba(244,67,54,0.1); color:#f44336;">❌ ${err.message}</div>`;
        showNotification('❌ Failed to generate Local Images Mix', 'error');
    }
}


// =============================================================================
// SEO GENERATOR
// =============================================================================

// ---- Presets management (Settings) ----

async function loadSeoFormulas() {
    try {
        const r = await fetch('/api/seo-formulas');
        const d = await r.json();
        if (!d.success) return;
        _renderSeoFormulasList(d.formulas);
        _populateSeoFormulaSelect(d.formulas);
    } catch (e) { console.warn('Could not load SEO formulas:', e); }
}

function _renderSeoFormulasList(formulas) {
    const container = document.getElementById('seoFormulasList');
    if (!container) return;
    if (!formulas || formulas.length === 0) {
        container.innerHTML = '<p style="color:#666; font-size:14px;">No saved formulas yet. Create your first one!</p>';
        return;
    }
    container.innerHTML = formulas.map(f => `
        <div style="padding:10px 14px; margin:5px 0; background:#0f1a15; border:1px solid #065f46; border-radius:8px; display:flex; justify-content:space-between; align-items:flex-start;">
            <div style="flex:1; min-width:0;">
                <strong style="color:#10b981;">${f.name}</strong>
                <p style="margin:3px 0 0; color:#666; font-size:12px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${f.formula.substring(0,100).replace(/\n/g,' ')}…</p>
            </div>
            <div style="display:flex; gap:6px; margin-left:10px; flex-shrink:0;">
                <button onclick="editSeoFormula('${f.id}')" style="background:#065f46; color:#d1fae5; border:none; border-radius:6px; padding:4px 10px; font-size:12px; cursor:pointer;">✏️ Edit</button>
                <button onclick="deleteSeoFormula('${f.id}')" style="background:#7f1d1d; color:#fca5a5; border:none; border-radius:6px; padding:4px 10px; font-size:12px; cursor:pointer;">🗑️</button>
            </div>
        </div>`).join('');
}

function _populateSeoFormulaSelect(formulas) {
    const sel = document.getElementById('seoFormulaSelect');
    if (!sel) return;
    const current = sel.value;
    sel.innerHTML = '<option value="">⚙️ Default formula</option>' +
        (formulas || []).map(f => `<option value="${f.id}">${f.name}</option>`).join('');
    if (current) sel.value = current;
}

function openSeoFormulaCreator() {
    document.getElementById('editingSeoFormulaId').value = '';
    document.getElementById('seoFormulaCreatorTitle').textContent = '➕ New SEO Formula';
    document.getElementById('newSeoFormulaName').value = '';
    document.getElementById('newSeoFormulaText').value = '';
    document.getElementById('seoFormulaCreatorSection').style.display = 'block';
    document.getElementById('seoFormulaCreatorSection').scrollIntoView({ behavior:'smooth', block:'start' });
}

function closeSeoFormulaCreator() {
    document.getElementById('seoFormulaCreatorSection').style.display = 'none';
    document.getElementById('editingSeoFormulaId').value = '';
}

async function editSeoFormula(formulaId) {
    try {
        const r = await fetch('/api/seo-formulas');
        const d = await r.json();
        const f = (d.formulas || []).find(x => x.id === formulaId);
        if (!f) return;
        document.getElementById('editingSeoFormulaId').value = formulaId;
        document.getElementById('seoFormulaCreatorTitle').textContent = '✏️ Edit: ' + f.name;
        document.getElementById('newSeoFormulaName').value = f.name;
        document.getElementById('newSeoFormulaText').value = f.formula;
        document.getElementById('seoFormulaCreatorSection').style.display = 'block';
        document.getElementById('seoFormulaCreatorSection').scrollIntoView({ behavior:'smooth', block:'start' });
    } catch (e) { showNotification('❌ Could not load formula', 'error'); }
}

async function saveSeoFormulaPreset() {
    const editingId = document.getElementById('editingSeoFormulaId').value.trim();
    const name    = document.getElementById('newSeoFormulaName').value.trim();
    const formula = document.getElementById('newSeoFormulaText').value.trim();

    if (!name) { showNotification('❌ Formula name is required', 'error'); return; }
    if (!formula || formula.length < 10) { showNotification('❌ Formula text is required', 'error'); return; }

    try {
        const isEdit = editingId !== '';
        const url    = isEdit ? `/api/seo-formulas/${editingId}` : '/api/seo-formulas';
        const method = isEdit ? 'PUT' : 'POST';
        const r = await fetch(url, {
            method, headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, formula })
        });
        const d = await r.json();
        if (d.success) {
            showNotification(isEdit ? '✅ Formula updated!' : '✅ Formula saved!', 'success');
            closeSeoFormulaCreator();
            await loadSeoFormulas();
        } else {
            showNotification('❌ ' + (d.error || 'Save failed'), 'error');
        }
    } catch (e) { showNotification('❌ ' + e.message, 'error'); }
}

async function deleteSeoFormula(formulaId) {
    if (!confirm('Delete this SEO formula?')) return;
    try {
        const r = await fetch(`/api/seo-formulas/${formulaId}`, { method: 'DELETE' });
        const d = await r.json();
        if (d.success) {
            showNotification('✅ Formula deleted', 'success');
            await loadSeoFormulas();
        } else {
            showNotification('❌ ' + (d.error || 'Delete failed'), 'error');
        }
    } catch (e) { showNotification('❌ ' + e.message, 'error'); }
}

function saveSeoDefaultLink() {
    const link = document.getElementById('seoDefaultLink')?.value.trim() || '';
    if (link) localStorage.setItem('seoDefaultLink', link);
    showNotification('✅ Default link saved', 'success');
}

// ---- SEO Generator (main section) ----

function seoAutoFill() {
    // Use the real element IDs from the main page
    const titleEl  = document.getElementById('titleInput');
    const scriptEl = document.getElementById('scriptInput');

    const seoTitleEl  = document.getElementById('seoTitle');
    const seoScriptEl = document.getElementById('seoScript');

    if (seoTitleEl  && titleEl  && titleEl.value)  seoTitleEl.value  = titleEl.value;
    if (seoScriptEl && scriptEl && scriptEl.value) seoScriptEl.value = scriptEl.value;

    // Pre-fill link from saved default (only when empty)
    const seoLinkEl = document.getElementById('seoLink');
    if (seoLinkEl && !seoLinkEl.value) {
        const savedLink = localStorage.getItem('seoDefaultLink');
        if (savedLink) seoLinkEl.value = savedLink;
    }

    // Reload formula dropdown in case new presets were saved
    loadSeoFormulas();
}

async function generateSeo() {
    const title      = document.getElementById('seoTitle').value.trim();
    const script     = document.getElementById('seoScript').value.trim();
    const link       = document.getElementById('seoLink').value.trim();
    const formula_id = document.getElementById('seoFormulaSelect')?.value || '';

    if (!title && !script) {
        showNotification('❌ Enter a title or script first', 'error');
        return;
    }

    const progressBox   = document.getElementById('seoProgressBox');
    const resultSection = document.getElementById('seoResultSection');
    progressBox.style.display   = 'block';
    resultSection.style.display = 'none';

    try {
        const r = await fetch('/api/seo-generator', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title, script, link, formula_id })
        });
        const d = await r.json();
        progressBox.style.display = 'none';

        if (!d.success) { showNotification('❌ ' + (d.error || 'Generation failed'), 'error'); return; }

        document.getElementById('seoDescription').value = d.description;
        document.getElementById('seoTags').value        = d.tags;

        const badge = document.getElementById('seoLangBadge');
        if (badge && d.language) badge.textContent = '(' + d.language + ')';

        const tlen  = (d.tags || '').length;
        const lenEl = document.getElementById('seoTagsLength');
        const warn  = document.getElementById('seoTagsWarning');
        if (lenEl) lenEl.textContent = tlen + ' / 400 chars';
        if (warn)  warn.style.display = tlen > 400 ? 'block' : 'none';

        resultSection.style.display = 'block';
        resultSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
        showNotification('✅ Description & tags generated!', 'success');
    } catch (e) {
        progressBox.style.display = 'none';
        showNotification('❌ ' + e.message, 'error');
    }
}

function copySeoDescription() {
    const v = document.getElementById('seoDescription')?.value;
    if (!v) return;
    navigator.clipboard.writeText(v).then(() => showNotification('📋 Description copied!', 'success'));
}

function copySeoTags() {
    const v = document.getElementById('seoTags')?.value;
    if (!v) return;
    navigator.clipboard.writeText(v).then(() => showNotification('📋 Tags copied!', 'success'));
}

// Load SEO formulas + Video styles when settings open
(function() {
    const _orig = window.openSettings;
    window.openSettings = function() {
        if (_orig) _orig.apply(this, arguments);
        loadSeoFormulas();
        loadVideoStylesList();
        const saved = localStorage.getItem('seoDefaultLink');
        if (saved) {
            const el = document.getElementById('seoDefaultLink');
            if (el && !el.value) el.value = saved;
        }
    };
})();

// Auto-fill SEO fields when the section scrolls into view
(function() {
    const seoSection = document.getElementById('seoGeneratorStep');
    if (!seoSection || !('IntersectionObserver' in window)) return;
    const io = new IntersectionObserver(entries => {
        if (entries[0].isIntersecting) seoAutoFill();
    }, { threshold: 0.1 });
    io.observe(seoSection);
})();


// ─────────────────────────────────────────────────────────────────────────────
// SUPER AUTO EDITOR
// ─────────────────────────────────────────────────────────────────────────────

let _saeAvatarFile  = null;   // File object from <input>
let _saeJobId       = null;   // current job ID
let _saePollTimer   = null;   // setInterval handle
let _saeDownloadUrl = null;   // final download URL

// ── Drop-zone helpers ─────────────────────────────────────────────────────────

function saeDrop(e, type) {
    e.preventDefault();
    const zone = document.getElementById('saeAvatarDropZone');
    if (zone) zone.style.borderColor = 'rgba(139,92,246,0.4)';
    const file = e.dataTransfer?.files?.[0];
    if (!file) return;
    if (type === 'avatar') _saeSetAvatar(file);
}

function saePickAvatar(e) {
    const file = e.target.files?.[0];
    if (file) _saeSetAvatar(file);
}

function _saeSetAvatar(file) {
    _saeAvatarFile = file;
    const label = document.getElementById('saeAvatarLabel');
    const zone  = document.getElementById('saeAvatarDropZone');
    if (label) label.innerHTML = `<strong style="color:#a78bfa">${file.name}</strong><br><span style="font-size:11px;color:#6b7280">${(file.size/1048576).toFixed(1)} MB</span>`;
    if (zone)  zone.style.borderColor = '#7c3aed';
}

// ── Start job ─────────────────────────────────────────────────────────────────

async function saeStartJob() {
    const script = (document.getElementById('saeScript')?.value || '').trim();
    const title  = (document.getElementById('saeTitle')?.value  || '').trim();

    if (!_saeAvatarFile) {
        showNotification('Please upload an avatar video first.', 'error');
        return;
    }
    if (!script) {
        showNotification('Please paste your script first.', 'error');
        return;
    }

    // Reset UI
    _saeReset();
    document.getElementById('saeProgress').style.display = 'block';
    document.getElementById('saeGenerateBtn').disabled = true;

    // Build multipart form
    const fd = new FormData();
    fd.append('avatar_file', _saeAvatarFile);
    fd.append('script', script);
    if (title) fd.append('title', title);

    try {
        const res  = await fetch('/api/super-auto-editor/start', { method: 'POST', body: fd });
        const raw  = await res.text();
        let data;
        try {
            data = raw ? JSON.parse(raw) : {};
        } catch {
            throw new Error(raw ? raw.slice(0, 180) : `HTTP ${res.status}`);
        }
        if (!res.ok || !data.success) throw new Error(data.error || `HTTP ${res.status}`);
        _saeJobId = data.job_id;
        _saePollStatus();
    } catch (err) {
        _saeShowError('Failed to start: ' + err.message);
    }
}

// ── Polling ───────────────────────────────────────────────────────────────────

function _saePollStatus() {
    if (_saePollTimer) clearInterval(_saePollTimer);
    _saePollTimer = setInterval(_saeFetchStatus, 3000);
    _saeFetchStatus(); // immediate first check
}

async function _saeFetchStatus() {
    if (!_saeJobId) return;
    try {
        const res  = await fetch(`/api/super-auto-editor/status/${_saeJobId}`);
        const raw  = await res.text();
        let data;
        try {
            data = raw ? JSON.parse(raw) : {};
        } catch {
            throw new Error(raw ? raw.slice(0, 180) : `HTTP ${res.status}`);
        }
        if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);

        // Update progress bar
        const pct = data.progress || 0;
        const bar = document.getElementById('saeBar');
        const pctEl = document.getElementById('saePct');
        const msgEl = document.getElementById('saeMsg');
        if (bar)   bar.style.width   = pct + '%';
        if (pctEl) pctEl.textContent = pct + '%';
        if (msgEl) msgEl.textContent = data.message || '';

        if (data.status === 'done') {
            clearInterval(_saePollTimer);
            _saePollTimer = null;
            _saeDownloadUrl = data.download_url || `/api/super-auto-editor/download/${_saeJobId}`;
            _saeShowResult(data.result || {});
        } else if (data.status === 'error') {
            clearInterval(_saePollTimer);
            _saePollTimer = null;
            _saeShowError(data.error || data.message || 'Job failed');
        }
    } catch (err) {
        console.warn('SAE poll error:', err);
    }
}

// ── Result / Error display ────────────────────────────────────────────────────

function _saeShowResult(result) {
    document.getElementById('saeProgress').style.display = 'none';
    document.getElementById('saeGenerateBtn').disabled = false;

    const infoEl = document.getElementById('saeInfo');
    if (infoEl) {
        infoEl.innerHTML = [
            result.duration_fmt  ? `⏱ Duration: <strong>${result.duration_fmt}</strong>` : '',
            result.file_size_mb  ? `💾 Size: <strong>${result.file_size_mb} MB</strong>` : '',
            result.scenes_count  ? `🎬 Scenes: <strong>${result.scenes_count}</strong>` : '',
            result.broll_count   ? `🖼 B-roll clips: <strong>${result.broll_count}</strong>` : '',
        ].filter(Boolean).join('&nbsp;&nbsp;•&nbsp;&nbsp;');
    }

    document.getElementById('saeResult').style.display = 'block';
    showNotification('✅ Super Auto Video ready!', 'success');
}

function _saeShowError(msg) {
    document.getElementById('saeProgress').style.display = 'none';
    document.getElementById('saeGenerateBtn').disabled = false;
    const el = document.getElementById('saeError');
    if (el) { el.textContent = '❌ ' + msg; el.style.display = 'block'; }
}

function _saeReset() {
    document.getElementById('saeResult').style.display = 'none';
    document.getElementById('saeError').style.display  = 'none';
    const bar = document.getElementById('saeBar');
    const pctEl = document.getElementById('saePct');
    const msgEl = document.getElementById('saeMsg');
    if (bar)   bar.style.width   = '0%';
    if (pctEl) pctEl.textContent = '0%';
    if (msgEl) msgEl.textContent = 'Starting…';
    if (_saePollTimer) { clearInterval(_saePollTimer); _saePollTimer = null; }
}

// ── Download ──────────────────────────────────────────────────────────────────

function saeDownload() {
    if (!_saeDownloadUrl) return;
    const a = document.createElement('a');
    a.href = _saeDownloadUrl;
    a.download = '';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
}
