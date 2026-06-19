from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
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
            shape = self._read_shape(file_path)
        except ImportError as exc:
            raise CadImportError(
                "pythonocc-core не установлен. Для v0.2.0 используйте "
                "environment.yml или conda-forge пакет pythonocc-core."
            ) from exc

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
