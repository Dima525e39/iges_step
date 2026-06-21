from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app_info import APP_NAME


DEFAULT_SETTINGS_PATH = Path(__file__).with_name("default_settings.json")


class SettingsManager:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else user_settings_path()
        self._settings = self.load()

    def load(self) -> dict[str, Any]:
        settings = _load_json(DEFAULT_SETTINGS_PATH)
        if self.path.exists() and self.path != DEFAULT_SETTINGS_PATH:
            settings = _deep_merge(settings, _load_json(self.path))
        elif self.path == DEFAULT_SETTINGS_PATH:
            settings = _load_json(self.path)
        return settings

    def save(self, path: str | Path | None = None) -> None:
        target = Path(path) if path is not None else self.path
        target.parent.mkdir(parents=True, exist_ok=True)
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

    def set(self, *keys: str, value: Any) -> None:
        if not keys:
            raise ValueError("Нужен хотя бы один ключ настройки.")
        current = self._settings
        for key in keys[:-1]:
            next_value = current.setdefault(key, {})
            if not isinstance(next_value, dict):
                next_value = {}
                current[key] = next_value
            current = next_value
        current[keys[-1]] = value

    def update_section(self, key: str, value: dict[str, Any]) -> None:
        self._settings[key] = value

    def as_dict(self) -> dict[str, Any]:
        return json.loads(json.dumps(self._settings, ensure_ascii=False))


def user_settings_path() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / APP_NAME / "settings.json"
    return Path.home() / ".config" / APP_NAME / "settings.json"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged
