from __future__ import annotations

import re
from dataclasses import dataclass, field

from core.file_job import FileJob


@dataclass(slots=True)
class TubeGroup:
    material: str
    tube_type: str
    tube_size: str
    wall_thickness_mm: float
    jobs: list[FileJob] = field(default_factory=list)

    @property
    def key(self) -> tuple[str, str, str, float]:
        return (
            self.material,
            self.tube_type,
            self.tube_size,
            round(self.wall_thickness_mm, 3),
        )


def group_jobs_by_tube(jobs: list[FileJob]) -> list[TubeGroup]:
    groups: dict[tuple[str, str, str, float], TubeGroup] = {}
    for job in jobs:
        length = number_from_text(job.tube_length_mm)
        if length <= 0.0:
            continue
        thickness = number_from_text(job.wall_thickness_mm)
        key = (
            job.material or "Сталь",
            job.tube_type or "Труба",
            job.tube_size or job.tube_type or "Не определено",
            round(thickness, 3),
        )
        if key not in groups:
            groups[key] = TubeGroup(
                material=key[0],
                tube_type=key[1],
                tube_size=key[2],
                wall_thickness_mm=key[3],
            )
        groups[key].jobs.append(job)
    return list(groups.values())


def number_from_text(value: object) -> float:
    match = re.search(r"-?\d+(?:[.,]\d+)?", str(value))
    if not match:
        return 0.0
    return float(match.group(0).replace(",", "."))
