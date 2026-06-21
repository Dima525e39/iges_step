from __future__ import annotations

from pathlib import Path
from typing import Any


def logo_path_from_settings(settings: dict[str, Any]) -> str:
    logo = settings.get("logo", {})
    if not isinstance(logo, dict):
        return ""
    path = str(logo.get("path", ""))
    if not path:
        return ""
    return path if Path(path).exists() else ""
