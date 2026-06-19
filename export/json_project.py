from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from app_info import APP_NAME, APP_VERSION
from core.file_job import FileJob


def save_project(jobs: Iterable[FileJob], target_path: str | Path) -> None:
    payload = {
        "app": APP_NAME,
        "version": APP_VERSION,
        "jobs": [job.to_dict() for job in jobs],
    }
    Path(target_path).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_project(source_path: str | Path) -> list[FileJob]:
    payload = json.loads(Path(source_path).read_text(encoding="utf-8"))
    return [FileJob.from_dict(item) for item in payload.get("jobs", [])]
