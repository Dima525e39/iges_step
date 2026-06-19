from __future__ import annotations

from pathlib import Path
from typing import Iterable

SUPPORTED_EXTENSIONS = {".step", ".stp", ".iges", ".igs"}


def is_supported_cad_file(path: str | Path) -> bool:
    return Path(path).suffix.casefold() in SUPPORTED_EXTENSIONS


def collect_supported_files(
    paths: Iterable[str | Path],
) -> tuple[list[Path], list[Path]]:
    supported: list[Path] = []
    unsupported: list[Path] = []
    seen: set[str] = set()

    for raw_path in paths:
        path = Path(raw_path).expanduser()

        if path.is_dir():
            for candidate in _iter_supported_files(path):
                key = _path_key(candidate)
                if key not in seen:
                    seen.add(key)
                    supported.append(candidate)
            continue

        if path.is_file() and is_supported_cad_file(path):
            resolved = _resolve(path)
            key = _path_key(resolved)
            if key not in seen:
                seen.add(key)
                supported.append(resolved)
        else:
            unsupported.append(path)

    supported.sort(key=lambda item: str(item).casefold())
    unsupported.sort(key=lambda item: str(item).casefold())
    return supported, unsupported


def _iter_supported_files(folder: Path) -> Iterable[Path]:
    for file_path in folder.rglob("*"):
        if file_path.is_file() and is_supported_cad_file(file_path):
            yield _resolve(file_path)


def _resolve(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path.absolute()


def _path_key(path: Path) -> str:
    return str(_resolve(path)).casefold()
