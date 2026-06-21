from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from app_info import APP_NAME, APP_VERSION
from core.file_job import FileJob


def save_project(
    jobs: Iterable[FileJob],
    target_path: str | Path,
    *,
    settings: dict[str, object] | None = None,
    purchase_rows: list[dict[str, object]] | None = None,
) -> None:
    payload = {
        "app": APP_NAME,
        "version": APP_VERSION,
        "jobs": [job.to_dict() for job in jobs],
        "settings": settings or {},
        "purchase_rows": purchase_rows or [],
    }
    Path(target_path).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_project(source_path: str | Path) -> tuple[list[FileJob], dict[str, object]]:
    payload = json.loads(Path(source_path).read_text(encoding="utf-8"))
    jobs = [FileJob.from_dict(item) for item in payload.get("jobs", [])]
    settings = payload.get("settings", {})
    return jobs, settings if isinstance(settings, dict) else {}
