# ALAR Remotion Runtime

A real editable Remotion project: React + TSX, 1080×1920, 60fps.

## GitHub Actions
Push to branch `harry/alar-remotion-runtime-20261021`. The workflow renders a 3-second MP4 via `npx remotion render` and uploads the MP4 plus an offline dependency package. The offline package is Linux x64; it does not contain a packaged browser. A compatible local Chromium installation is required for offline rendering.

## Local commands
```bash
npm install
npm run studio
npm run render
```

The GitHub runner has internet for package installation. The build results must be checked before considering the runtime proven.
