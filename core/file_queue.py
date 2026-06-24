from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from cad.supported_formats import collect_supported_files
from core.file_job import FileJob, parse_quantity_from_filename


@dataclass(slots=True)
class AddFilesResult:
    added: list[FileJob] = field(default_factory=list)
    duplicates: list[Path] = field(default_factory=list)
    unsupported: list[Path] = field(default_factory=list)


class FileQueue:
    def __init__(self) -> None:
        self._jobs: dict[str, FileJob] = {}

    def __len__(self) -> int:
        return len(self._jobs)

    def jobs(self) -> list[FileJob]:
        return list(self._jobs.values())

    def clear(self) -> None:
        self._jobs.clear()

    def add_paths(self, paths: Iterable[str | Path]) -> AddFilesResult:
        supported_files, unsupported = collect_supported_files(paths)
        result = AddFilesResult(unsupported=unsupported)

        for file_path in supported_files:
            key = self._key(file_path)
            if key in self._jobs:
                result.duplicates.append(file_path)
                continue

            job = FileJob(
                path=file_path,
                quantity=parse_quantity_from_filename(file_path),
            )
            self._jobs[key] = job
            result.added.append(job)

        return result

    def remove_paths(self, paths: Iterable[str | Path]) -> None:
        for path in paths:
            self._jobs.pop(self._key(Path(path)), None)

    def get(self, path: str | Path) -> FileJob | None:
        return self._jobs.get(self._key(Path(path)))

    def replace_jobs(self, jobs: Iterable[FileJob]) -> None:
        self._jobs = {self._key(job.path): job for job in jobs}

    @staticmethod
    def _key(path: Path) -> str:
        try:
            return str(path.resolve()).casefold()
        except OSError:
            return str(path.absolute()).casefold()
