"""
FFmpeg Filter Graph Builder
---------------------------
Clean, structured generator for FFmpeg commands.

Converts a multi-track timeline (tracks with clips) into a valid
-filter_complex graph + -map flags. Never uses raw string concat.

Usage:
    builder = FilterGraph()
    in_v = builder.add_input('/abs/path/a.mp4')       # -> 0
    in_b = builder.add_input('/abs/path/bg.mp4')      # -> 1
    v = builder.trim(in_v, 'v', 2.0, 5.0)             # -> returns label like [v0]
    b = builder.trim(in_b, 'v', 0.0, 3.0)
    b = builder.scale(b, 480, -1)
    out = builder.overlay(v, b, 100, 80)
    cmd = builder.build_command('/abs/out.mp4', preset='ultrafast', crf=23)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
import shlex


# ─────────────────────────────────────────────────────────────────────────────
# Label generator
# ─────────────────────────────────────────────────────────────────────────────
class LabelGen:
    __slots__ = ('_n',)
    def __init__(self): self._n = 0
    def next(self, prefix: str = 'x') -> str:
        self._n += 1
        return f'{prefix}{self._n}'


# ─────────────────────────────────────────────────────────────────────────────
# Escape helpers for drawtext / filter args
# ─────────────────────────────────────────────────────────────────────────────
def _esc_drawtext(text: str) -> str:
    # Escape single quotes, backslashes, colons and % for drawtext
    return (text.replace('\\', '\\\\')
                .replace("'", r"\'")
                .replace(':', r'\:')
                .replace('%', r'\%'))


def _esc_filter_arg(s: str) -> str:
    # For file paths passed as filter args (e.g. subtitles=)
    return s.replace('\\', '/').replace(':', r'\:').replace("'", r"\'")


# ─────────────────────────────────────────────────────────────────────────────
# Filter graph
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class FilterGraph:
    inputs: List[str] = field(default_factory=list)             # input file paths
    _filters: List[str] = field(default_factory=list)           # built filter strings
    _labels: 'LabelGen' = field(default_factory=LabelGen)
    video_out: Optional[str] = None                             # final [vout]
    audio_out: Optional[str] = None                             # final [aout]

    # ── inputs ──────────────────────────────────────────────────────────────
    def add_input(self, path: str, loop_image: bool = False,
                  image_duration: float = 0) -> int:
        """Returns the input index (0-based)."""
        self.inputs.append(path)
        return len(self.inputs) - 1

    def in_v(self, idx: int) -> str: return f'[{idx}:v]'
    def in_a(self, idx: int) -> str: return f'[{idx}:a]'

    # ── basic filters ───────────────────────────────────────────────────────
    def trim(self, src: str, kind: str, start: float, end: float) -> str:
        """kind: 'v' for video, 'a' for audio"""
        out = f'[{self._labels.next("v" if kind == "v" else "a")}]'
        if kind == 'v':
            self._filters.append(f'{src}trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS{out}')
        else:
            self._filters.append(f'{src}atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS{out}')
        return out

    def tpad_start(self, src: str, seconds: float) -> str:
        """Pad a video clip with black at the start so it appears later on the timeline."""
        if seconds <= 0: return src
        out = f'[{self._labels.next("v")}]'
        self._filters.append(f'{src}tpad=start_duration={seconds:.3f}:start_mode=add:color=black{out}')
        return out

    def adelay(self, src: str, ms: int) -> str:
        """Delay an audio stream by `ms` milliseconds."""
        if ms <= 0: return src
        out = f'[{self._labels.next("a")}]'
        self._filters.append(f'{src}adelay={ms}|{ms}{out}')
        return out

    def scale(self, src: str, w: int, h: int,
              force_aspect: bool = True) -> str:
        out = f'[{self._labels.next("v")}]'
        flag = ':force_original_aspect_ratio=decrease' if force_aspect and w > 0 and h > 0 else ''
        self._filters.append(f'{src}scale={w}:{h}{flag}{out}')
        return out

    def pad(self, src: str, w: int, h: int, color: str = 'black') -> str:
        out = f'[{self._labels.next("v")}]'
        self._filters.append(f'{src}pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color={color}{out}')
        return out

    def scale_cover(self, src: str, w: int, h: int) -> str:
        """Scale + center-crop so the output exactly fills w×h (no letterbox)."""
        scaled = f'[{self._labels.next("v")}]'
        self._filters.append(
            f'{src}scale={w}:{h}:force_original_aspect_ratio=increase{scaled}')
        out = f'[{self._labels.next("v")}]'
        self._filters.append(f'{scaled}crop={w}:{h}{out}')
        return out

    def crop(self, src: str, w: int, h: int, x: int = 0, y: int = 0) -> str:
        out = f'[{self._labels.next("v")}]'
        self._filters.append(f'{src}crop={w}:{h}:{x}:{y}{out}')
        return out

    def rotate(self, src: str, degrees: float) -> str:
        # Use transpose for 90/180/270 (lossless-friendly); rotate= for arbitrary
        out = f'[{self._labels.next("v")}]'
        self._filters.append(f'{src}rotate={degrees}*PI/180{out}')
        return out

    def setpts_speed(self, src: str, factor: float) -> str:
        """factor > 1.0 → slower, < 1.0 → faster (setpts multiplies PTS)."""
        out = f'[{self._labels.next("v")}]'
        self._filters.append(f'{src}setpts={factor:.4f}*PTS{out}')
        return out

    def atempo(self, src: str, factor: float) -> str:
        """factor = playback speed (0.5..2.0 per chain; chain multiples for beyond)."""
        # atempo is limited to 0.5..2.0; chain if outside
        chain: List[float] = []
        f = factor
        while f > 2.0:
            chain.append(2.0); f /= 2.0
        while f < 0.5:
            chain.append(0.5); f /= 0.5
        chain.append(f)
        parts = ','.join(f'atempo={c:.4f}' for c in chain)
        out = f'[{self._labels.next("a")}]'
        self._filters.append(f'{src}{parts}{out}')
        return out

    def fade_in(self, src: str, start: float, dur: float) -> str:
        out = f'[{self._labels.next("v")}]'
        self._filters.append(f'{src}fade=t=in:st={start:.3f}:d={dur:.3f}{out}')
        return out

    def fade_out(self, src: str, start: float, dur: float) -> str:
        out = f'[{self._labels.next("v")}]'
        self._filters.append(f'{src}fade=t=out:st={start:.3f}:d={dur:.3f}{out}')
        return out

    def afade_in(self, src: str, start: float, dur: float) -> str:
        out = f'[{self._labels.next("a")}]'
        self._filters.append(f'{src}afade=t=in:st={start:.3f}:d={dur:.3f}{out}')
        return out

    def afade_out(self, src: str, start: float, dur: float) -> str:
        out = f'[{self._labels.next("a")}]'
        self._filters.append(f'{src}afade=t=out:st={start:.3f}:d={dur:.3f}{out}')
        return out

    def volume(self, src: str, vol: float) -> str:
        out = f'[{self._labels.next("a")}]'
        self._filters.append(f'{src}volume={vol:.3f}{out}')
        return out

    def color_adjust(self, src: str, brightness: float = 0, contrast: float = 1,
                     saturation: float = 1) -> str:
        """brightness: -1..1 ; contrast: 0..2 ; saturation: 0..3"""
        out = f'[{self._labels.next("v")}]'
        self._filters.append(
            f'{src}eq=brightness={brightness:.3f}:contrast={contrast:.3f}:saturation={saturation:.3f}{out}')
        return out

    def overlay(self, base: str, top: str, x: int = 0, y: int = 0,
                enable: Optional[Tuple[float, float]] = None) -> str:
        out = f'[{self._labels.next("v")}]'
        en = ''
        if enable is not None:
            en = f":enable='between(t\\,{enable[0]:.3f}\\,{enable[1]:.3f})'"
        self._filters.append(f'{base}{top}overlay={x}:{y}{en}{out}')
        return out

    def drawtext(self, src: str, text: str, x: str = '20', y: str = '20',
                 font_size: int = 36, color: str = 'white',
                 enable: Optional[Tuple[float, float]] = None,
                 box: bool = False, box_color: str = 'black@0.5') -> str:
        out = f'[{self._labels.next("v")}]'
        t = _esc_drawtext(text)
        b = f':box=1:boxcolor={box_color}:boxborderw=8' if box else ''
        en = ''
        if enable is not None:
            en = f":enable='between(t\\,{enable[0]:.3f}\\,{enable[1]:.3f})'"
        self._filters.append(
            f"{src}drawtext=text='{t}':x={x}:y={y}:fontsize={font_size}:fontcolor={color}{b}{en}{out}")
        return out

    def subtitles(self, src: str, srt_path: str) -> str:
        out = f'[{self._labels.next("v")}]'
        p = _esc_filter_arg(srt_path)
        self._filters.append(f"{src}subtitles='{p}'{out}")
        return out

    def zoompan(self, src: str, z: str = 'min(zoom+0.0015,1.5)',
                d: int = 125, w: int = 1920, h: int = 1080) -> str:
        out = f'[{self._labels.next("v")}]'
        self._filters.append(f'{src}zoompan=z={z}:d={d}:s={w}x{h}{out}')
        return out

    def amix(self, sources: List[str], normalize: bool = False) -> str:
        if not sources:
            raise ValueError('amix requires at least one source')
        if len(sources) == 1:
            return sources[0]
        out = f'[{self._labels.next("a")}]'
        joined = ''.join(sources)
        norm = '1' if normalize else '0'
        self._filters.append(f'{joined}amix=inputs={len(sources)}:normalize={norm}:duration=longest{out}')
        return out

    def concat_video_audio(self, pairs: List[Tuple[str, Optional[str]]],
                           have_audio: bool) -> Tuple[str, Optional[str]]:
        """
        pairs: list of (video_label, audio_label_or_None). All must be same resolution.
        Returns (v_out, a_out_or_None).
        """
        if not pairs:
            raise ValueError('concat requires at least one pair')
        n = len(pairs)
        v_out = f'[{self._labels.next("v")}]'
        a_out = f'[{self._labels.next("a")}]' if have_audio else None
        joined = ''
        for (v, a) in pairs:
            joined += v
            if have_audio and a is not None:
                joined += a
        if have_audio:
            self._filters.append(f'{joined}concat=n={n}:v=1:a=1{v_out}{a_out}')
        else:
            self._filters.append(f'{joined}concat=n={n}:v=1:a=0{v_out}')
        return (v_out, a_out)

    def set_outputs(self, video_out: str, audio_out: Optional[str] = None):
        self.video_out = video_out
        self.audio_out = audio_out

    # ── command ─────────────────────────────────────────────────────────────
    def build_filter_complex(self) -> str:
        return ';'.join(self._filters)

    def build_command(self, output_path: str,
                      preset: str = 'ultrafast',
                      crf: int = 23,
                      pix_fmt: str = 'yuv420p',
                      audio_codec: str = 'aac',
                      audio_bitrate: str = '128k',
                      extra_input_flags: Optional[List[List[str]]] = None) -> List[str]:
        """
        Returns a structured argv list. extra_input_flags: per-input flags list
        (same length as self.inputs). Use for -loop 1, -framerate, -stream_loop, etc.
        """
        cmd: List[str] = ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'info']
        for i, path in enumerate(self.inputs):
            if extra_input_flags and i < len(extra_input_flags) and extra_input_flags[i]:
                cmd.extend(extra_input_flags[i])
            cmd.extend(['-i', path])
        if self._filters:
            cmd.extend(['-filter_complex', self.build_filter_complex()])
        if self.video_out:
            cmd.extend(['-map', self.video_out])
        if self.audio_out:
            cmd.extend(['-map', self.audio_out])
        cmd.extend([
            '-c:v', 'libx264',
            '-preset', preset,
            '-crf', str(crf),
            '-pix_fmt', pix_fmt,
            '-movflags', '+faststart',
        ])
        if self.audio_out:
            cmd.extend(['-c:a', audio_codec, '-b:a', audio_bitrate])
        cmd.append(output_path)
        return cmd

    def debug_str(self) -> str:
        """Human-readable dump for logs."""
        lines = [f'# inputs ({len(self.inputs)}):']
        for i, p in enumerate(self.inputs):
            lines.append(f'  [{i}] {p}')
        lines.append('# filters:')
        for f in self._filters:
            lines.append(f'  {f}')
        lines.append(f'# maps: video={self.video_out}, audio={self.audio_out}')
        return '\n'.join(lines)


def cmd_to_shell(argv: List[str]) -> str:
    """Quote an argv list into a copy-pasteable shell command (for logging only)."""
    return ' '.join(shlex.quote(a) for a in argv)
