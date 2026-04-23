"""
Smart Exporter — Pro Multi-Track Timeline
-----------------------------------------
Converts a JSON timeline (tracks + clips) into an FFmpeg command:

- COPY MODE (stream copy): one clip, trim-only, no filters, no overlays  → `-c copy`
- COPY+CONCAT: multiple same-codec video-track clips, no overlays/effects → concat demuxer
- RENDER MODE: anything else → filter_complex via FilterGraph

Timeline JSON shape:
{
  "width": 1920, "height": 1080, "fps": 30,
  "tracks": [
    { "id":"v0", "type":"video",   "clips":[...] },
    { "id":"o0", "type":"overlay", "clips":[...] },
    { "id":"t0", "type":"text",    "clips":[...] },
    { "id":"a0", "type":"audio",   "clips":[...] }
  ]
}

Clip:
{
  "id":"c1", "source":"/abs/path.mp4",
  "start": 0,           # timeline position (seconds)
  "duration": 5.0,      # length on timeline
  "trim_in": 0,         # seconds into source to start reading
  "trim_out": 5.0,      # seconds into source to stop reading
  "props": {
    "x": 100, "y": 80, "scale": 1.0,
    "text": "...", "font_size": 48, "color":"white",
    "volume": 1.0, "speed": 1.0,
    "crop": {"w":..., "h":..., "x":..., "y":...},
    "rotate": 0,
    "brightness": 0, "contrast": 1, "saturation": 1,
    "fade_in": 0.3, "fade_out": 0.3
  },
  "is_image": false
}
"""

from __future__ import annotations
import os
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from ffmpeg_builder import FilterGraph, cmd_to_shell


# ─────────────────────────────────────────────────────────────────────────────
# Data-access helpers
# ─────────────────────────────────────────────────────────────────────────────
def _tracks_by_type(timeline: Dict[str, Any], ttype: str) -> List[Dict[str, Any]]:
    return [t for t in (timeline.get('tracks') or []) if t.get('type') == ttype]


def _all_clips(timeline: Dict[str, Any]) -> List[Dict[str, Any]]:
    clips = []
    for t in (timeline.get('tracks') or []):
        for c in (t.get('clips') or []):
            c2 = dict(c); c2['_track_type'] = t.get('type')
            clips.append(c2)
    return clips


def _clip_end(c: Dict[str, Any]) -> float:
    return float(c.get('start', 0)) + float(c.get('duration', 0))


def _timeline_duration(timeline: Dict[str, Any]) -> float:
    ends = [_clip_end(c) for c in _all_clips(timeline)]
    return max(ends) if ends else 0.0


def _has_props(c: Dict[str, Any]) -> bool:
    """True if this clip needs any per-clip filter (scale, crop, rotate, fade, etc.)."""
    p = c.get('props') or {}
    return bool(
        p.get('crop') or p.get('rotate') or
        (p.get('speed') and p['speed'] != 1.0) or
        (p.get('scale') and p['scale'] != 1.0) or
        (p.get('brightness') not in (None, 0)) or
        (p.get('contrast') not in (None, 1)) or
        (p.get('saturation') not in (None, 1)) or
        (p.get('fade_in') or 0) > 0 or (p.get('fade_out') or 0) > 0
    )


# ─────────────────────────────────────────────────────────────────────────────
# Mode decision
# ─────────────────────────────────────────────────────────────────────────────
def decide_export_mode(timeline: Dict[str, Any]) -> str:
    """Returns 'copy_single', 'copy_concat' or 'render'."""
    video_tracks = _tracks_by_type(timeline, 'video')
    overlay_tracks = _tracks_by_type(timeline, 'overlay')
    text_tracks = _tracks_by_type(timeline, 'text')
    audio_tracks = _tracks_by_type(timeline, 'audio')

    # Any overlay / text / extra audio track = render
    has_overlay_clips = any(t.get('clips') for t in overlay_tracks)
    has_text_clips = any(t.get('clips') for t in text_tracks)
    has_extra_audio = any(t.get('clips') for t in audio_tracks)
    if has_overlay_clips or has_text_clips or has_extra_audio:
        return 'render'

    if len(video_tracks) == 0:
        return 'render'

    # Must be exactly one video track for copy modes
    if len(video_tracks) > 1:
        return 'render'

    clips = video_tracks[0].get('clips') or []
    if len(clips) == 0:
        return 'render'
    # Any per-clip filter forces re-encode
    if any(_has_props(c) for c in clips):
        return 'render'
    # Gaps between clips or start-offset require re-encode
    clips_sorted = sorted(clips, key=lambda c: float(c.get('start', 0)))
    if float(clips_sorted[0].get('start', 0)) > 0.001:
        return 'render'
    for a, b in zip(clips_sorted, clips_sorted[1:]):
        if abs(_clip_end(a) - float(b.get('start', 0))) > 0.05:
            return 'render'

    if len(clips_sorted) == 1:
        return 'copy_single'
    return 'copy_concat'


# ─────────────────────────────────────────────────────────────────────────────
# Copy mode builders
# ─────────────────────────────────────────────────────────────────────────────
def build_copy_single(timeline: Dict[str, Any], out_path: str) -> List[str]:
    c = _tracks_by_type(timeline, 'video')[0]['clips'][0]
    src = c['source']
    tin = float(c.get('trim_in', 0))
    tout = float(c.get('trim_out', tin + float(c.get('duration', 0))))
    # Place -ss before -i for fast keyframe seek; -to after
    cmd = [
        'ffmpeg', '-y', '-hide_banner', '-loglevel', 'info',
        '-ss', f'{tin:.3f}',
        '-to', f'{tout:.3f}',
        '-i', src,
        '-c', 'copy',
        '-avoid_negative_ts', 'make_zero',
        '-movflags', '+faststart',
        out_path,
    ]
    return cmd


def build_copy_concat(timeline: Dict[str, Any], out_path: str,
                      workdir: str) -> Tuple[List[List[str]], str, List[str]]:
    """
    Returns (prep_cmds, final_cmd, temp_files).
    For each clip we stream-copy the trimmed segment to a temp .ts file,
    then concat them with the concat demuxer (still stream-copy).
    """
    os.makedirs(workdir, exist_ok=True)
    clips = sorted(
        _tracks_by_type(timeline, 'video')[0]['clips'],
        key=lambda c: float(c.get('start', 0)))

    prep_cmds: List[List[str]] = []
    temps: List[str] = []
    for i, c in enumerate(clips):
        seg = os.path.join(workdir, f'seg_{i:04d}.ts')
        tin = float(c.get('trim_in', 0))
        tout = float(c.get('trim_out', tin + float(c.get('duration', 0))))
        prep_cmds.append([
            'ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
            '-ss', f'{tin:.3f}', '-to', f'{tout:.3f}',
            '-i', c['source'],
            '-c', 'copy', '-bsf:v', 'h264_mp4toannexb', '-f', 'mpegts',
            seg,
        ])
        temps.append(seg)

    list_file = os.path.join(workdir, 'concat_list.txt')
    temps.append(list_file)
    with open(list_file, 'w', encoding='utf-8') as f:
        for seg in temps[:-1]:  # exclude list_file itself
            # escape single quotes in filenames
            f.write(f"file '{seg.replace(chr(39), chr(39)+chr(92)+chr(39)+chr(39))}'\n")

    final = [
        'ffmpeg', '-y', '-hide_banner', '-loglevel', 'info',
        '-f', 'concat', '-safe', '0', '-i', list_file,
        '-c', 'copy', '-movflags', '+faststart',
        out_path,
    ]
    return prep_cmds, final, temps


# ─────────────────────────────────────────────────────────────────────────────
# Render mode — full filter_complex
# ─────────────────────────────────────────────────────────────────────────────
def _apply_clip_props(g: FilterGraph, v_label: str, c: Dict[str, Any]) -> str:
    """Apply props filters (crop, scale, rotate, color, fade, speed) to a video label."""
    p = c.get('props') or {}
    if p.get('crop'):
        cr = p['crop']
        v_label = g.crop(v_label,
                         int(cr.get('w', 0)) or 100,
                         int(cr.get('h', 0)) or 100,
                         int(cr.get('x', 0)),
                         int(cr.get('y', 0)))
    if p.get('scale') and float(p['scale']) != 1.0:
        v_label = _scale_factor(g, v_label, float(p['scale']))
    if p.get('rotate'):
        v_label = g.rotate(v_label, float(p['rotate']))
    if p.get('brightness') or p.get('contrast') or p.get('saturation'):
        v_label = g.color_adjust(v_label,
                                 brightness=float(p.get('brightness', 0) or 0),
                                 contrast=float(p.get('contrast', 1) or 1),
                                 saturation=float(p.get('saturation', 1) or 1))
    if p.get('speed') and float(p['speed']) != 1.0:
        v_label = g.setpts_speed(v_label, 1.0 / float(p['speed']))
    fin = float(p.get('fade_in') or 0)
    fout = float(p.get('fade_out') or 0)
    dur = float(c.get('duration', 0))
    if fin > 0:
        v_label = g.fade_in(v_label, 0, fin)
    if fout > 0 and dur > fout:
        v_label = g.fade_out(v_label, dur - fout, fout)
    return v_label


def _scale_factor(g: FilterGraph, label: str, factor: float) -> str:
    """Scale by a factor (iw*factor : ih*factor) — helper."""
    out = f'[{g._labels.next("v")}]'
    g._filters.append(f'{label}scale=iw*{factor:.4f}:ih*{factor:.4f}{out}')
    return out


def build_render(timeline: Dict[str, Any], out_path: str,
                 preset: str = 'ultrafast', crf: int = 23) -> List[str]:
    W = int(timeline.get('width', 1920))
    H = int(timeline.get('height', 1080))
    FPS = int(timeline.get('fps', 30))
    total = max(_timeline_duration(timeline), 0.1)

    g = FilterGraph()

    # ── base canvas: black for the whole duration ─────────────────────────
    base_in = g.add_input(f'color=c=black:s={W}x{H}:r={FPS}:d={total:.3f}')
    # This input uses -f lavfi. We'll signal that via extra_input_flags.
    extra: List[List[str]] = [['-f', 'lavfi']]
    base = g.in_v(base_in)

    audio_labels: List[str] = []

    # ── video + overlay tracks ────────────────────────────────────────────
    # Lower-index video tracks render FIRST (below), higher-index on top.
    video_like = (
        _tracks_by_type(timeline, 'video') +
        _tracks_by_type(timeline, 'overlay')
    )

    for track in video_like:
        for clip in (track.get('clips') or []):
            src = clip['source']
            is_image = bool(clip.get('is_image'))
            props = clip.get('props') or {}

            if is_image:
                idx = g.add_input(src)
                # image inputs need -loop 1 -t duration so they decode as video
                extra.append(['-loop', '1', '-t', f'{float(clip.get("duration", 3)):.3f}'])
                v_src = g.in_v(idx)
            else:
                idx = g.add_input(src)
                extra.append([])
                v_src = g.in_v(idx)

            tin = float(clip.get('trim_in', 0))
            tout = float(clip.get('trim_out', tin + float(clip.get('duration', 0))))
            v = g.trim(v_src, 'v', tin, tout) if not is_image else v_src
            v = _apply_clip_props(g, v, clip)

            # Fit into canvas (overlay tracks may be smaller → scale by scale factor)
            if track.get('type') == 'video':
                # Fit-to-canvas with letterbox
                v = g.scale(v, W, H, force_aspect=True)
                v = g.pad(v, W, H)

            # delay on timeline
            start = float(clip.get('start', 0))
            v = g.tpad_start(v, start)

            x = int(props.get('x', 0))
            y = int(props.get('y', 0))
            base = g.overlay(base, v, x, y,
                             enable=(start, start + float(clip.get('duration', 0))))

            # Extract audio from non-image video clips, delay to match timeline
            if not is_image and not clip.get('mute'):
                a = g.trim(g.in_a(idx), 'a', tin, tout)
                vol = float(props.get('volume', 1.0))
                if vol != 1.0:
                    a = g.volume(a, vol)
                if start > 0:
                    a = g.adelay(a, int(start * 1000))
                audio_labels.append(a)

    # ── text tracks (drawtext) ─────────────────────────────────────────────
    for track in _tracks_by_type(timeline, 'text'):
        for clip in (track.get('clips') or []):
            p = clip.get('props') or {}
            text = p.get('text') or clip.get('source') or ''
            if not text: continue
            start = float(clip.get('start', 0))
            dur = float(clip.get('duration', 2))
            base = g.drawtext(
                base, text,
                x=str(p.get('x', 20)),
                y=str(p.get('y', 20)),
                font_size=int(p.get('font_size', 48)),
                color=str(p.get('color', 'white')),
                enable=(start, start + dur),
                box=bool(p.get('box', False)),
                box_color=str(p.get('box_color', 'black@0.5')))

    # ── audio tracks ───────────────────────────────────────────────────────
    for track in _tracks_by_type(timeline, 'audio'):
        for clip in (track.get('clips') or []):
            idx = g.add_input(clip['source'])
            extra.append([])
            tin = float(clip.get('trim_in', 0))
            tout = float(clip.get('trim_out', tin + float(clip.get('duration', 0))))
            a = g.trim(g.in_a(idx), 'a', tin, tout)
            vol = float((clip.get('props') or {}).get('volume', 1.0))
            if vol != 1.0:
                a = g.volume(a, vol)
            start = float(clip.get('start', 0))
            if start > 0:
                a = g.adelay(a, int(start * 1000))
            audio_labels.append(a)

    # Final video output
    g.set_outputs(base, g.amix(audio_labels) if audio_labels else None)

    return g.build_command(
        out_path, preset=preset, crf=crf,
        extra_input_flags=extra,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Run helpers
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class ExportPlan:
    mode: str                       # 'copy_single' | 'copy_concat' | 'render'
    prep_cmds: List[List[str]]      # commands to run first (for copy_concat)
    final_cmd: List[str]            # final command
    temp_files: List[str]           # cleanup after success
    debug: str                      # human-readable log


def plan_export(timeline: Dict[str, Any], out_path: str, workdir: str,
                preset: str = 'ultrafast', crf: int = 23) -> ExportPlan:
    mode = decide_export_mode(timeline)
    if mode == 'copy_single':
        cmd = build_copy_single(timeline, out_path)
        return ExportPlan('copy_single', [], cmd, [], cmd_to_shell(cmd))
    if mode == 'copy_concat':
        preps, final, temps = build_copy_concat(timeline, out_path, workdir)
        dbg = '\n'.join([cmd_to_shell(c) for c in preps]) + '\n' + cmd_to_shell(final)
        return ExportPlan('copy_concat', preps, final, temps, dbg)
    # render
    cmd = build_render(timeline, out_path, preset=preset, crf=crf)
    return ExportPlan('render', [], cmd, [], cmd_to_shell(cmd))


def run_export(plan: ExportPlan, on_log=None) -> Tuple[bool, str]:
    """Executes the plan. Returns (ok, combined_log)."""
    logs: List[str] = [f'# Mode: {plan.mode}', plan.debug, '']
    try:
        for i, c in enumerate(plan.prep_cmds):
            logs.append(f'[prep {i+1}/{len(plan.prep_cmds)}] {cmd_to_shell(c)}')
            r = subprocess.run(c, capture_output=True, text=True, timeout=1800)
            if r.returncode != 0:
                logs.append(r.stderr[-2000:])
                return False, '\n'.join(logs)
        logs.append(f'[final] {cmd_to_shell(plan.final_cmd)}')
        r = subprocess.run(plan.final_cmd, capture_output=True, text=True, timeout=3600)
        if r.returncode != 0:
            logs.append(r.stderr[-4000:])
            return False, '\n'.join(logs)
        logs.append('✅ export complete')
        return True, '\n'.join(logs)
    finally:
        for t in plan.temp_files:
            try:
                if os.path.exists(t): os.remove(t)
            except Exception:
                pass
