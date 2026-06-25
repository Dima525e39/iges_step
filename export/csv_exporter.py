from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from core.file_job import FileJob


CSV_HEADERS = [
    "Файл",
    "Материал",
    "Размер",
    "Толщина",
    "Длина",
    "Длина реза",
    "Врезки",
    "Количество",
    "Цена",
]


def export_jobs_to_csv(jobs: Iterable[FileJob], target_path: str | Path) -> None:
    with Path(target_path).open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(CSV_HEADERS)
        for job in jobs:
            writer.writerow(job.to_table_row())
