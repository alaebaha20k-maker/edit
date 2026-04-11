# Super Auto Editor v2 (Speed-First)

Production-ready modular pipeline optimized for **fast** automated assembly:

- Specific media scenes → **Brave Images** only.
- General media scenes → **Pexels Videos** only.
- Final output: **1920x1080**, **30fps**, **16:9**.
- Avatar audio is preserved end-to-end.
- Media visuals are always rendered muted.
- Fake zoom for images (no `zoompan`).

## Folder structure

- `analyze/` script analysis and scene classification (Gemini + fallback heuristics)
- `search/` Brave and Pexels integrations + ranking
- `download/` concurrent downloader with retries
- `media/` image clip and scene builders
- `timeline/` timing block loader and script segmentation
- `ffmpeg/` FFmpeg runner/probe helpers
- `cache/` search-result and asset manifest cache
- `config/` settings loader

## CLI

```bash
python backend/super_auto_editor_cli.py \
  --avatar ./input/avatar.mp4 \
  --script ./input/script.txt \
  --timeline ./input/timeline.json \
  --output ./output/final.mp4 \
  --mode ultra_fast_draft \
  --config ./backend/super_auto_editor_v2/config.example.json
```

## Timeline input

```json
[
  {"type":"avatar","start":0,"end":3},
  {"type":"media","start":3,"end":11,"script_text":"Ford Focus launch"},
  {"type":"avatar","start":11,"end":20},
  {"type":"media","start":20,"end":40,"script_text":"city at night"}
]
```

## Speed choices

- Segment-based assembly avoids expensive full-length overlays.
- Asset fetches are cached per query.
- Downloads are concurrent and deterministic.
- Image motion is fake zoom via tiny linear scale/crop transform.
- Pexels segments are one-clip trim/scale/mute pass.
- Final mux maps avatar audio once at the end.

## Runtime logs

The exporter prints exact terminal steps with elapsed time, for example:

- timeline load
- block-by-block build
- media source decision (Brave vs Pexels)
- image target count per scene
- concat and final mux phases
