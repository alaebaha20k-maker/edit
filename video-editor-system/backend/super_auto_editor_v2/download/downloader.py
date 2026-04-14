from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from hashlib import sha1
from pathlib import Path

import requests

from super_auto_editor_v2.cache.cache_manager import CacheManager
from super_auto_editor_v2.models import DownloadedAsset


class Downloader:
    def __init__(self, cache: CacheManager, workers: int = 8, timeout: int = 20):
        self.cache = cache
        self.workers = workers
        self.timeout = timeout

    def _target_path(self, url: str) -> Path:
        ext = ".bin"
        for candidate in (".jpg", ".jpeg", ".png", ".webp", ".mp4"):
            if candidate in url.lower():
                ext = candidate
                break
        return self.cache.assets_dir / f"{sha1(url.encode('utf-8')).hexdigest()}{ext}"

    def download_many(self, tasks: list[dict]) -> list[DownloadedAsset]:
        out: list[DownloadedAsset] = []
        with ThreadPoolExecutor(max_workers=self.workers) as ex:
            futures = [ex.submit(self._download_one, t) for t in tasks]
            for fut in as_completed(futures):
                item = fut.result()
                if item:
                    out.append(item)
        return out

    def _download_one(self, task: dict) -> DownloadedAsset | None:
        url = task["url"]
        target = self._target_path(url)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "*/*",
        }
        if not target.exists():
            for _ in range(3):
                try:
                    with requests.get(url, timeout=self.timeout, stream=True, headers=headers) as r:
                        r.raise_for_status()
                        ctype = (r.headers.get("Content-Type") or "").lower()
                        source = str(task.get("source", "")).lower()
                        if source in ("brave", "serper") and "image" not in ctype:
                            continue
                        if source == "pexels" and "video" not in ctype and "octet-stream" not in ctype:
                            continue
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with target.open("wb") as f:
                            for chunk in r.iter_content(chunk_size=65536):
                                if chunk:
                                    f.write(chunk)
                        if target.stat().st_size < 10 * 1024:
                            target.unlink(missing_ok=True)
                            continue
                    break
                except Exception:
                    continue
        if not target.exists():
            return None

        asset = DownloadedAsset(
            scene_id=task["scene_id"],
            asset_id=task["asset_id"],
            source=task["source"],
            query=task["query"],
            path=target,
            metadata=task.get("metadata", {}),
        )
        self.cache.append_manifest(
            {
                "scene_id": asset.scene_id,
                "asset_id": asset.asset_id,
                "source": asset.source,
                "query": asset.query,
                "path": str(asset.path),
            }
        )
        return asset
