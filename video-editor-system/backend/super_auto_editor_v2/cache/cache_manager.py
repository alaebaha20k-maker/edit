from __future__ import annotations

import json
import threading
from hashlib import sha1
from pathlib import Path
from typing import Any


class CacheManager:
    def __init__(self, root: Path):
        self.root = root
        self.search_dir = root / "search"
        self.assets_dir = root / "assets"
        self.generated_dir = root / "generated"
        self.manifest_path = root / "manifest.json"
        self._manifest_lock = threading.Lock()
        self.root.mkdir(parents=True, exist_ok=True)
        self.search_dir.mkdir(parents=True, exist_ok=True)
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        self.generated_dir.mkdir(parents=True, exist_ok=True)
        if not self.manifest_path.exists():
            self.manifest_path.write_text("[]", encoding="utf-8")

    def cache_key(self, *parts: str) -> str:
        return sha1("::".join(parts).encode("utf-8")).hexdigest()

    def load_search(self, provider: str, query: str) -> Any | None:
        key = self.cache_key(provider, query)
        p = self.search_dir / f"{key}.json"
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))

    def save_search(self, provider: str, query: str, payload: Any) -> None:
        key = self.cache_key(provider, query)
        p = self.search_dir / f"{key}.json"
        p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def append_manifest(self, item: dict[str, Any]) -> None:
        with self._manifest_lock:
            data = self._safe_load_manifest()
            data.append(item)
            self.manifest_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _safe_load_manifest(self) -> list[dict[str, Any]]:
        try:
            raw = self.manifest_path.read_text(encoding="utf-8").strip()
            if not raw:
                return []
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            # Recover from previously corrupted concurrent writes.
            backup = self.manifest_path.with_suffix(".corrupt.json")
            try:
                self.manifest_path.replace(backup)
            except Exception:
                pass
            return []
