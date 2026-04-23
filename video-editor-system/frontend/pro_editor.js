// =============================================================================
// PRO MULTI-LAYER EDITOR — Timeline + Smart FFmpeg Export
// =============================================================================
// Data model:
//   proState.tracks = [{ id, type:'video'|'overlay'|'text'|'audio', clips:[...] }]
//   Clip: { id, source, start, duration, trim_in, trim_out, is_image, props:{...} }
// =============================================================================

const proState = {
    tracks: [
        { id: 'v0', type: 'video',   name: '🎬 Video',   clips: [] },
        { id: 'o0', type: 'overlay', name: '🖼️ Overlay', clips: [] },
        { id: 't0', type: 'text',    name: '🔤 Text',    clips: [] },
        { id: 'a0', type: 'audio',   name: '🎵 Audio',   clips: [] },
    ],
    media: [],            // uploaded assets: {path, name, type, duration, w, h, has_audio}
    pxPerSec: 80,         // timeline zoom
    playhead: 0,
    selectedClipId: null,
    draggingClip: null,   // { id, mode:'move'|'trim-right'|'trim-left', startX, origStart, origDuration, origTrimOut }
    width: 1920, height: 1080, fps: 30,
};

const proProSel = (id) => document.getElementById(id);
const proUid = () => 'c_' + Date.now().toString(36) + Math.random().toString(36).slice(2, 7);

// ── toggle section ───────────────────────────────────────────────────────────
function proToggle() {
    const body = proProSel('proEditorBody');
    const icon = proProSel('proEditorToggleIcon');
    const open = body.style.display !== 'none';
    body.style.display = open ? 'none' : 'block';
    icon.textContent = open ? '▼' : '▲';
    if (!open) proRender();
}

// ── upload ──────────────────────────────────────────────────────────────────
async function proUpload(fileList) {
    const files = Array.from(fileList || []);
    if (!files.length) return;
    proSetStatus(`📤 Uploading ${files.length} file(s)…`);
    const wasEmpty = proState.media.length === 0;

    for (const f of files) {
        try {
            const isImage = f.type.startsWith('image/');
            const isAudio = f.type.startsWith('audio/');
            const fileType = isImage ? 'image' : (isAudio ? 'audio' : 'video');

            const fd = new FormData();
            fd.append('file', f);
            fd.append('type', fileType);   // ← required by /api/upload

            const r = await fetch('/api/upload', { method: 'POST', body: fd });
            const j = await r.json();
            if (!j.success) {
                proSetStatus(`❌ Upload failed for "${f.name}": ${j.error || 'unknown'}`);
                continue;
            }
            const path = j.path || j.unique_filename || j.filename;
            proSetStatus(`⏳ Reading metadata: ${f.name}…`);

            // ffprobe for metadata
            const metaResp = await fetch('/api/editor/ffprobe', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path })
            });
            const meta = metaResp.ok ? await metaResp.json() : {};

            proState.media.push({
                path: (meta.success && meta.path) ? meta.path : path,
                name: f.name,
                type: fileType,
                duration: (meta.success && meta.duration) ? meta.duration : (isImage ? 5 : 10),
                width:     meta.width  || 0,
                height:    meta.height || 0,
                fps:       meta.fps    || 30,
                has_audio: !!meta.has_audio,
            });
            proSetStatus(`✅ Added: ${f.name}`);
            proRenderMedia();   // update library after each file
        } catch (e) {
            proSetStatus(`❌ Error with "${f.name}": ${e.message}`);
        }
    }
    proSetStatus(`✅ Library: ${proState.media.length} asset(s) — click an item to add it to the timeline.`);
    proRenderMedia();
    if (wasEmpty && proState.media.length > 0) setTimeout(proFitZoom, 100);
}

function proOnDrop(ev) {
    ev.preventDefault(); ev.stopPropagation();
    const dz = proProSel('proDropZone');
    if (dz) dz.classList.remove('pro-drop-active');
    const files = ev.dataTransfer.files;
    if (files && files.length) proUpload(files);
}
function proOnDragOver(ev) {
    ev.preventDefault(); ev.stopPropagation();
    const dz = proProSel('proDropZone');
    if (dz) dz.classList.add('pro-drop-active');
}
function proOnDragLeave(ev) {
    // only clear when leaving the drop-zone itself (not a child element)
    const dz = proProSel('proDropZone');
    if (!dz) return;
    if (!dz.contains(ev.relatedTarget)) dz.classList.remove('pro-drop-active');
}

// ── add clip from media ─────────────────────────────────────────────────────
function proAddFromMedia(idx) {
    const m = proState.media[idx]; if (!m) return;
    // Choose the right track automatically based on media type
    let track;
    if (m.type === 'audio') {
        track = proState.tracks.find(t => t.type === 'audio');
    } else if (m.type === 'image') {
        track = proState.tracks.find(t => t.type === 'overlay');
    } else {
        track = proState.tracks.find(t => t.type === 'video');
    }
    if (!track) return;
    // Place at end of last clip on that track, or at playhead if empty
    const lastEnd = track.clips.reduce((s, c) => Math.max(s, c.start + c.duration), 0);
    const start = track.clips.length ? lastEnd : proState.playhead;
    const dur = Math.max(1, m.duration || (m.type === 'image' ? 4 : 5));
    track.clips.push({
        id: proUid(),
        source: m.path,
        start,
        duration: dur,
        trim_in: 0,
        name: m.name,
        trim_out: dur,
        is_image: m.type === 'image',
        props: m.type === 'image'
            ? { x: 100, y: 100, scale: 0.5 }
            : { volume: 1.0 },
    });
    proRender();
}

function proAddTextClip() {
    const track = proState.tracks.find(t => t.type === 'text'); if (!track) return;
    const start = proState.playhead;
    track.clips.push({
        id: proUid(), source: '', start, duration: 3,
        props: { text: 'New Text', x: '(w-tw)/2', y: 120, font_size: 64, color: 'white', box: true }
    });
    proRender();
}

// ── mutations ───────────────────────────────────────────────────────────────
function proDeleteSelected() {
    if (!proState.selectedClipId) return;
    for (const t of proState.tracks) {
        t.clips = t.clips.filter(c => c.id !== proState.selectedClipId);
    }
    proState.selectedClipId = null;
    proRender();
}

function proSplitAtPlayhead() {
    if (!proState.selectedClipId) return;
    const t = proState.playhead;
    for (const tr of proState.tracks) {
        const c = tr.clips.find(x => x.id === proState.selectedClipId);
        if (!c) continue;
        if (t <= c.start + 0.05 || t >= c.start + c.duration - 0.05) return;
        const offset = t - c.start;
        const right = {
            ...c, id: proUid(),
            start: t,
            duration: c.duration - offset,
            trim_in: (c.trim_in || 0) + offset,
        };
        c.duration = offset;
        c.trim_out = (c.trim_in || 0) + offset;
        tr.clips.push(right);
        break;
    }
    proRender();
}

// ── rendering ───────────────────────────────────────────────────────────────
function proRender() {
    proRenderMedia();
    proRenderTracks();
    proRenderRuler();
    proRenderInspector();
    proRenderSummary();
    proRenderPreview();
}

// ── preview: shows the selected clip's source in the player ────────────────
function proRenderPreview() {
    const clip = proGetSelectedClip();
    const vid = proProSel('proPreviewVideo');
    const img = proProSel('proPreviewImage');
    const ph  = proProSel('proPreviewPlaceholder');
    const badge = proProSel('proPreviewBadge');
    if (!vid || !img || !ph) return;

    if (!clip || !clip.source) {
        vid.style.display = 'none'; vid.src = '';
        img.style.display = 'none'; img.src = '';
        ph.style.display = 'block';
        if (badge) badge.style.display = 'none';
        return;
    }
    ph.style.display = 'none';
    const tr = proGetTrackOfClip(clip.id);
    const ttype = tr ? tr.type : '';
    const src = '/api/preview-video/' + encodeURIComponent((clip.source || '').split(/[\\/]/).pop());

    if (clip.is_image || ttype === 'text') {
        vid.style.display = 'none'; vid.pause(); vid.src = '';
        if (ttype === 'text') {
            img.style.display = 'none'; img.src = '';
            ph.style.display = 'block';
            ph.innerHTML = `<div style="font-size:40px;">🔤</div>
                <div style="font-size:${Math.min(48, (clip.props?.font_size||48))}px; color:${clip.props?.color||'white'}; margin-top:12px; font-weight:700;">
                    ${(clip.props?.text||'').replace(/</g,'&lt;')||'(empty text)'}
                </div>`;
        } else {
            img.style.display = 'block';
            if (img.dataset.srcSet !== src) { img.src = src; img.dataset.srcSet = src; }
        }
    } else {
        img.style.display = 'none';
        vid.style.display = 'block';
        if (vid.dataset.srcSet !== src) { vid.src = src; vid.dataset.srcSet = src; }
        // Seek to trim_in when (re)loading
        const seek = Math.max(0, parseFloat(clip.trim_in || 0));
        const applySeek = () => { try { vid.currentTime = seek; } catch(_) {} };
        if (vid.readyState >= 1) applySeek();
        else vid.addEventListener('loadedmetadata', applySeek, { once: true });
    }
    if (badge) {
        const icon = clip.is_image ? '🖼️' : (ttype === 'text' ? '🔤' : (ttype === 'audio' ? '🎵' : '🎬'));
        const name = ttype === 'text' ? 'Text' : (clip.name || (clip.source || '').split(/[\\/]/).pop());
        badge.style.display = 'block';
        badge.textContent = `${icon} ${name} · ${clip.duration.toFixed(2)}s`;
    }
}

// ── fit zoom: size the timeline to fill the available width ───────────────
function proFitZoom() {
    const scroll = proProSel('proTimelineScroll');
    if (!scroll) return;
    const total = Math.max(proTimelineDuration() + 2, 10);
    const trackHeadW = 100;       // sticky track-head width
    const available = Math.max(400, scroll.clientWidth - trackHeadW - 24);
    proState.pxPerSec = Math.max(10, Math.min(400, Math.floor(available / total)));
    proRender();
}

function proRenderMedia() {
    const ul = proProSel('proMediaList'); if (!ul) return;
    if (!proState.media.length) {
        ul.innerHTML = '<div style="color:#666; padding:10px; font-size:12px;">No assets yet. Drop files above.</div>';
        return;
    }
    ul.innerHTML = proState.media.map((m, i) => {
        const icon = m.type === 'image' ? '🖼️' : (m.type === 'audio' ? '🎵' : '🎬');
        const dur = m.duration ? `${m.duration.toFixed(1)}s` : '';
        const res = (m.width && m.height) ? `${m.width}×${m.height}` : '';
        return `<div class="pro-media-item" onclick="proAddFromMedia(${i})" title="Click to add to timeline">
            <div style="font-size:18px;">${icon}</div>
            <div style="flex:1; min-width:0;">
                <div style="font-size:12px; color:#e2e2f0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${m.name}</div>
                <div style="font-size:10px; color:#888;">${dur} ${res}</div>
            </div>
        </div>`;
    }).join('');
}

function proRenderRuler() {
    const ruler = proProSel('proTimelineRuler'); if (!ruler) return;
    const total = Math.max(proTimelineDuration() + 5, 20);
    const ticks = [];
    const stepSec = proState.pxPerSec >= 80 ? 1 : (proState.pxPerSec >= 30 ? 2 : 5);
    for (let s = 0; s <= total; s += stepSec) {
        const x = s * proState.pxPerSec;
        const label = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
        ticks.push(`<div class="pro-tick" style="left:${x}px;"><span>${label}</span></div>`);
    }
    ruler.style.width = (total * proState.pxPerSec) + 'px';
    ruler.innerHTML = ticks.join('');
    // position playhead
    const ph = proProSel('proPlayhead');
    if (ph) ph.style.left = (proState.playhead * proState.pxPerSec) + 'px';
}

function proRenderTracks() {
    const wrap = proProSel('proTracksWrap'); if (!wrap) return;
    const total = Math.max(proTimelineDuration() + 5, 20);
    const width = total * proState.pxPerSec;
    wrap.style.width = width + 'px';
    const phLeft = proState.playhead * proState.pxPerSec;
    wrap.innerHTML = proState.tracks.map(tr => {
        const clips = tr.clips.map(c => {
            const left = c.start * proState.pxPerSec;
            const w = Math.max(32, c.duration * proState.pxPerSec);
            const sel = proState.selectedClipId === c.id ? ' pro-clip-selected' : '';
            const rawLabel = tr.type === 'text'
                ? `🔤 ${(c.props?.text || '').substring(0, 22)}`
                : (c.name || (c.source || '').split(/[\\/]/).pop()).substring(0, 22);
            const color = proClipColor(tr.type);
            return `<div class="pro-clip${sel}" data-id="${c.id}"
                onmousedown="proClipMouseDown(event,'${c.id}','move')"
                style="left:${left}px; width:${w}px; background:${color};">
                <span class="pro-clip-label">${rawLabel}</span>
                <span class="pro-clip-handle pro-clip-handle-l" onmousedown="event.stopPropagation(); proClipMouseDown(event,'${c.id}','trim-left')"></span>
                <span class="pro-clip-handle pro-clip-handle-r" onmousedown="event.stopPropagation(); proClipMouseDown(event,'${c.id}','trim-right')"></span>
            </div>`;
        }).join('');
        return `<div class="pro-track" data-track="${tr.id}">
            <div class="pro-track-head">${tr.name}</div>
            <div class="pro-track-body" onclick="proTrackClick(event,'${tr.id}')" style="width:${width}px;">${clips}</div>
        </div>`;
    }).join('') + `<div id="proPlayhead" class="pro-playhead" style="left:${phLeft}px;"></div>`;
}

function proClipColor(type) {
    return type === 'video' ? 'linear-gradient(135deg,#4f46e5,#6366f1)'
        : type === 'overlay' ? 'linear-gradient(135deg,#ec4899,#db2777)'
        : type === 'text' ? 'linear-gradient(135deg,#f59e0b,#d97706)'
        : 'linear-gradient(135deg,#10b981,#059669)';
}

function proTimelineDuration() {
    let end = 0;
    for (const t of proState.tracks)
        for (const c of t.clips) end = Math.max(end, c.start + c.duration);
    return end;
}

function proRenderSummary() {
    const el = proProSel('proSummary'); if (!el) return;
    const dur = proTimelineDuration();
    const total = proState.tracks.reduce((s, t) => s + t.clips.length, 0);
    el.textContent = `${total} clip(s) • ${dur.toFixed(2)}s • Zoom ${proState.pxPerSec}px/s`;
}

function proRenderInspector() {
    const box = proProSel('proInspector'); if (!box) return;
    const clip = proGetSelectedClip();
    if (!clip) {
        box.innerHTML = '<div style="color:#666; font-size:12px;">Select a clip to edit its properties.</div>';
        return;
    }
    const p = clip.props || {};
    const tr = proGetTrackOfClip(clip.id);
    const ttype = tr ? tr.type : '';
    const fields = [];
    fields.push(`<label>Start (s)<input type="number" step="0.1" value="${clip.start}" onchange="proUpdateClip('${clip.id}','start',parseFloat(this.value))"></label>`);
    fields.push(`<label>Duration (s)<input type="number" step="0.1" value="${clip.duration}" onchange="proUpdateClip('${clip.id}','duration',Math.max(0.1,parseFloat(this.value)))"></label>`);
    if (ttype !== 'text' && !clip.is_image) {
        fields.push(`<label>Trim In (s)<input type="number" step="0.1" value="${clip.trim_in || 0}" onchange="proUpdateClip('${clip.id}','trim_in',parseFloat(this.value))"></label>`);
        fields.push(`<label>Trim Out (s)<input type="number" step="0.1" value="${clip.trim_out || (clip.trim_in||0) + clip.duration}" onchange="proUpdateClip('${clip.id}','trim_out',parseFloat(this.value))"></label>`);
    }
    if (ttype === 'overlay' || ttype === 'text') {
        fields.push(`<label>X<input type="text" value="${p.x ?? 0}" onchange="proUpdateProp('${clip.id}','x',this.value)"></label>`);
        fields.push(`<label>Y<input type="text" value="${p.y ?? 0}" onchange="proUpdateProp('${clip.id}','y',this.value)"></label>`);
    }
    if (ttype === 'overlay') {
        fields.push(`<label>Scale<input type="number" step="0.05" value="${p.scale ?? 1}" onchange="proUpdateProp('${clip.id}','scale',parseFloat(this.value))"></label>`);
    }
    if (ttype === 'text') {
        fields.push(`<label style="grid-column: span 2;">Text<input type="text" value="${(p.text || '').replace(/"/g,'&quot;')}" onchange="proUpdateProp('${clip.id}','text',this.value)"></label>`);
        fields.push(`<label>Size<input type="number" value="${p.font_size || 48}" onchange="proUpdateProp('${clip.id}','font_size',parseInt(this.value))"></label>`);
        fields.push(`<label>Color<input type="text" value="${p.color || 'white'}" onchange="proUpdateProp('${clip.id}','color',this.value)"></label>`);
    }
    if (ttype === 'video' || ttype === 'audio') {
        fields.push(`<label>Volume<input type="number" step="0.1" min="0" max="2" value="${p.volume ?? 1}" onchange="proUpdateProp('${clip.id}','volume',parseFloat(this.value))"></label>`);
    }
    if (ttype === 'video' || ttype === 'overlay') {
        fields.push(`<label>Speed<input type="number" step="0.1" min="0.25" max="4" value="${p.speed ?? 1}" onchange="proUpdateProp('${clip.id}','speed',parseFloat(this.value))"></label>`);
        fields.push(`<label>Fade In<input type="number" step="0.1" value="${p.fade_in ?? 0}" onchange="proUpdateProp('${clip.id}','fade_in',parseFloat(this.value))"></label>`);
        fields.push(`<label>Fade Out<input type="number" step="0.1" value="${p.fade_out ?? 0}" onchange="proUpdateProp('${clip.id}','fade_out',parseFloat(this.value))"></label>`);
    }
    box.innerHTML = `<h4 style="margin:0 0 10px; color:#a5b4fc;">Inspector</h4>
        <div class="pro-inspector-grid">${fields.join('')}</div>`;
}

function proGetSelectedClip() {
    if (!proState.selectedClipId) return null;
    for (const t of proState.tracks)
        for (const c of t.clips) if (c.id === proState.selectedClipId) return c;
    return null;
}
function proGetTrackOfClip(cid) {
    for (const t of proState.tracks)
        if (t.clips.some(c => c.id === cid)) return t;
    return null;
}
function proUpdateClip(id, key, v) {
    for (const t of proState.tracks)
        for (const c of t.clips) if (c.id === id) { c[key] = v; }
    proRender();
}
function proUpdateProp(id, key, v) {
    for (const t of proState.tracks)
        for (const c of t.clips) if (c.id === id) { c.props = c.props || {}; c.props[key] = v; }
    proRender();
}

// ── drag & drop on timeline ─────────────────────────────────────────────────
function proClipMouseDown(ev, id, mode) {
    ev.preventDefault();
    proState.selectedClipId = id;
    const clip = proGetSelectedClip(); if (!clip) return;
    proState.draggingClip = {
        id, mode, startX: ev.clientX,
        origStart: clip.start,
        origDuration: clip.duration,
        origTrimIn: clip.trim_in || 0,
        origTrimOut: clip.trim_out || 0,
    };
    document.addEventListener('mousemove', proClipMouseMove);
    document.addEventListener('mouseup', proClipMouseUp);
    proRender();
}
function proClipMouseMove(ev) {
    const d = proState.draggingClip; if (!d) return;
    const clip = proGetSelectedClip(); if (!clip) return;
    const deltaPx = ev.clientX - d.startX;
    const deltaSec = deltaPx / proState.pxPerSec;
    if (d.mode === 'move') {
        clip.start = Math.max(0, d.origStart + deltaSec);
    } else if (d.mode === 'trim-right') {
        clip.duration = Math.max(0.2, d.origDuration + deltaSec);
        if (clip.trim_out !== undefined)
            clip.trim_out = (d.origTrimIn) + clip.duration;
    } else if (d.mode === 'trim-left') {
        const newDur = Math.max(0.2, d.origDuration - deltaSec);
        const newStart = Math.max(0, d.origStart + deltaSec);
        clip.duration = newDur;
        clip.start = newStart;
        clip.trim_in = Math.max(0, d.origTrimIn + deltaSec);
    }
    proRenderTracks(); proRenderRuler(); proRenderInspector(); proRenderSummary();
}
function proClipMouseUp() {
    proState.draggingClip = null;
    document.removeEventListener('mousemove', proClipMouseMove);
    document.removeEventListener('mouseup', proClipMouseUp);
}

function proTrackClick(ev, trackId) {
    // Click empty track area → move playhead here
    if (ev.target.classList.contains('pro-clip') || ev.target.classList.contains('pro-clip-handle')
        || ev.target.classList.contains('pro-clip-label')) return;
    const rect = ev.currentTarget.getBoundingClientRect();
    const x = ev.clientX - rect.left;
    proState.playhead = Math.max(0, x / proState.pxPerSec);
    proRenderRuler();
}

function proZoom(factor) {
    proState.pxPerSec = Math.max(10, Math.min(400, Math.round(proState.pxPerSec * factor)));
    proRender();
}

// ── export ──────────────────────────────────────────────────────────────────
async function proPlan() {
    const r = await fetch('/api/editor/pro-plan', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ timeline: proBuildTimeline() })
    });
    const j = await r.json();
    if (!j.success) { proSetStatus('❌ Plan: ' + j.error); return; }
    proSetStatus(`📊 Mode: ${j.mode.toUpperCase()} — ${j.mode === 'render' ? 'filter_complex re-encode' : 'stream copy (fast)'}`);
    const dbg = proProSel('proDebugLog'); if (dbg) dbg.textContent = j.debug || '';
}

async function proExport() {
    const btn = proProSel('proExportBtn'); if (btn) { btn.disabled = true; btn.textContent = '⏳ Planning…'; }
    try {
        const r = await fetch('/api/editor/pro-export', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                timeline: proBuildTimeline(),
                preset: proProSel('proPreset')?.value || 'ultrafast',
                crf: parseInt(proProSel('proCrf')?.value || '23', 10),
            })
        });
        const j = await r.json();
        if (!j.success) { proSetStatus('❌ ' + (j.error || 'export failed')); return; }
        proSetStatus(`🚀 Exporting — job ${j.job_id.substring(0, 8)}…`);
        proPollExport(j.job_id, j.filename);
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = '🚀 Export Video'; }
    }
}

async function proPollExport(jobId, filename) {
    const bar = proProSel('proProgressBar');
    const bbox = proProSel('proProgressBox');
    if (bbox) bbox.style.display = 'block';
    const timer = setInterval(async () => {
        try {
            const r = await fetch(`/api/editor/pro-status/${jobId}`);
            const j = await r.json();
            if (!j.success) { clearInterval(timer); proSetStatus('❌ ' + j.error); return; }
            if (bar) bar.style.width = (j.progress || 0) + '%';
            proSetStatus(`🚀 ${j.status} (${j.mode || '...'}) — ${j.progress || 0}%`);
            if (j.status === 'done') {
                clearInterval(timer);
                if (bar) bar.style.width = '100%';
                proSetStatus(`✅ Done! File: ${j.output}`);
                const link = proProSel('proDownloadLink');
                if (link) {
                    link.style.display = 'inline-block';
                    link.href = `/api/preview-video/${encodeURIComponent(j.output)}`;
                    link.textContent = `⬇️ ${j.output}`;
                }
                const dbg = proProSel('proDebugLog'); if (dbg) dbg.textContent = j.log_tail || '';
            } else if (j.status === 'error') {
                clearInterval(timer);
                proSetStatus('❌ ' + (j.error || 'unknown'));
                const dbg = proProSel('proDebugLog'); if (dbg) dbg.textContent = j.log_tail || '';
            }
        } catch (e) { /* keep polling */ }
    }, 1500);
}

function proBuildTimeline() {
    return {
        width: proState.width, height: proState.height, fps: proState.fps,
        tracks: proState.tracks.map(t => ({
            id: t.id, type: t.type,
            clips: t.clips.map(c => ({
                id: c.id, source: c.source,
                start: c.start, duration: c.duration,
                trim_in: c.trim_in || 0,
                trim_out: c.trim_out || ((c.trim_in || 0) + c.duration),
                is_image: !!c.is_image,
                props: c.props || {},
            })),
        })),
    };
}

function proSetStatus(msg) {
    const el = proProSel('proStatus'); if (el) el.textContent = msg;
}

// Expose for inline handlers
window.proToggle = proToggle;
window.proUpload = proUpload;
window.proOnDrop = proOnDrop;
window.proOnDragOver = proOnDragOver;
window.proOnDragLeave = proOnDragLeave;
window.proAddFromMedia = proAddFromMedia;
window.proAddTextClip = proAddTextClip;
window.proDeleteSelected = proDeleteSelected;
window.proSplitAtPlayhead = proSplitAtPlayhead;
window.proClipMouseDown = proClipMouseDown;
window.proTrackClick = proTrackClick;
window.proZoom = proZoom;
window.proPlan = proPlan;
window.proExport = proExport;
window.proUpdateClip = proUpdateClip;
window.proUpdateProp = proUpdateProp;
window.proFitZoom = proFitZoom;

// ── init on load ─────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    // first paint so the track rows are visible immediately when the tab is open
    try { proRender(); } catch (_) {}
});
