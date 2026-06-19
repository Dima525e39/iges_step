from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_SETTINGS_PATH = Path(__file__).with_name("default_settings.json")


class SettingsManager:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else DEFAULT_SETTINGS_PATH
        self._settings = self.load()

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save(self, path: str | Path | None = None) -> None:
        target = Path(path) if path is not None else self.path
        target.write_text(
            json.dumps(self._settings, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get(self, *keys: str, default: Any = None) -> Any:
        value: Any = self._settings
        for key in keys:
            if not isinstance(value, dict) or key not in value:
                return default
            value = value[key]
        return value

    def as_dict(self) -> dict[str, Any]:
        return dict(self._settings)
