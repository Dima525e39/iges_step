from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from shutil import copy2
from tempfile import TemporaryDirectory
from typing import Any

from cad.supported_formats import is_supported_cad_file


class CadImportError(RuntimeError):
    """Raised when a CAD file cannot be imported."""


@dataclass(slots=True)
class CadImportResult:
    path: Path
    shape: Any
    file_format: str


class CadImporter:
    """Imports STEP/STP/IGES/IGS files through pythonocc-core."""

    def import_file(self, path: str | Path) -> CadImportResult:
        file_path = Path(path)
        if not file_path.exists():
            raise CadImportError(f"Файл не найден: {file_path}")
        if not is_supported_cad_file(file_path):
            raise CadImportError(f"Формат файла не поддерживается: {file_path.suffix}")

        try:
            with self._path_for_opencascade(file_path) as read_path:
                shape = self._read_shape(read_path)
        except ImportError as exc:
            raise CadImportError(
                "pythonocc-core недоступен в этом запуске. "
                f"Техническая ошибка: {exc}"
            ) from exc
        except OSError as exc:
            raise CadImportError(f"Не удалось подготовить файл к импорту: {exc}") from exc

        if shape is None or shape.IsNull():
            raise CadImportError("OpenCascade вернул пустую модель.")

        return CadImportResult(
            path=file_path,
            shape=shape,
            file_format=self.detect_format(file_path),
        )

    @staticmethod
    def detect_format(path: str | Path) -> str:
        suffix = Path(path).suffix.casefold()
        if suffix in {".step", ".stp"}:
            return "STEP"
        if suffix in {".iges", ".igs"}:
            return "IGES"
        return "UNKNOWN"

    def _read_shape(self, path: Path):
        file_format = self.detect_format(path)
        if file_format == "STEP":
            return self._read_step(path)
        if file_format == "IGES":
            return self._read_iges(path)
        raise CadImportError(f"Формат файла не поддерживается: {path.suffix}")

    @staticmethod
    @contextmanager
    def _path_for_opencascade(path: Path):
        """Give OpenCascade an ASCII-only path on Windows-sensitive installs."""
        if str(path).isascii():
            yield path
            return

        with TemporaryDirectory(prefix="tubecut_cad_") as temp_dir:
            temp_path = Path(temp_dir) / f"input{path.suffix.lower()}"
            copy2(path, temp_path)
            yield temp_path

    @staticmethod
    def _read_step(path: Path):
        from OCC.Core.IFSelect import IFSelect_RetDone
        from OCC.Core.Interface import Interface_Static
        from OCC.Core.STEPControl import STEPControl_Reader

        Interface_Static.SetCVal("xstep.cascade.unit", "MM")
        reader = STEPControl_Reader()
        status = reader.ReadFile(str(path))
        if status != IFSelect_RetDone:
            raise CadImportError("STEP-файл не удалось прочитать.")

        reader.TransferRoots()
        return reader.OneShape()

    @staticmethod
    def _read_iges(path: Path):
        from OCC.Core.IFSelect import IFSelect_RetDone
        from OCC.Core.IGESControl import IGESControl_Reader
        from OCC.Core.Interface import Interface_Static

        Interface_Static.SetCVal("xstep.cascade.unit", "MM")
        reader = IGESControl_Reader()
        status = reader.ReadFile(str(path))
        if status != IFSelect_RetDone:
            raise CadImportError("IGES-файл не удалось прочитать.")

        reader.TransferRoots()
        return reader.OneShape()
