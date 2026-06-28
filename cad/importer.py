from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from shutil import copy2
from tempfile import TemporaryDirectory
from typing import Any

from cad.supported_formats import is_supported_cad_file

# IGES is a surface format: adjacent faces usually carry their own copy of the
# shared boundary curve instead of a single common edge. Sewing rebuilds that
# shared topology so cut-contour grouping (pierce counting) can tell that the
# planes of one multi-plane cut belong together. The tolerance is the maximum
# gap that is still treated as a coincident edge.
IGES_SEW_TOLERANCE_MM = 0.01
IGES_BREP_ENTITY_TYPES = frozenset({186, 502, 504, 508, 510, 514})
IGES_SURFACE_ENTITY_TYPES = frozenset(
    {
        114,
        118,
        120,
        122,
        128,
        140,
        143,
        144,
        190,
        192,
        194,
        196,
        198,
    }
)


class CadImportError(RuntimeError):
    """Raised when a CAD file cannot be imported."""


@dataclass(slots=True)
class CadImportResult:
    path: Path
    shape: Any
    file_format: str
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class IgesEntitySummary:
    entity_count: int
    entity_counts: dict[int, int]

    @property
    def has_brep_topology(self) -> bool:
        return any(
            self.entity_counts.get(entity_type, 0)
            for entity_type in IGES_BREP_ENTITY_TYPES
        )

    @property
    def has_surfaces(self) -> bool:
        return any(
            self.entity_counts.get(entity_type, 0)
            for entity_type in IGES_SURFACE_ENTITY_TYPES
        )

    @property
    def is_surface_only_model(self) -> bool:
        return self.has_surfaces and not self.has_brep_topology

    def warning(self) -> str:
        return (
            "IGES содержит поверхности без B-Rep solid/shell; "
            "автоматическая сшивка пропущена, используется анализ поверхностей."
        )


class CadImporter:
    """Imports STEP/STP/IGES/IGS files through pythonocc-core."""

    def import_file(self, path: str | Path) -> CadImportResult:
        file_path = Path(path)
        if not file_path.exists():
            raise CadImportError(f"Файл не найден: {file_path}")
        if not is_supported_cad_file(file_path):
            raise CadImportError(f"Формат файла не поддерживается: {file_path.suffix}")

        file_format = self.detect_format(file_path)
        iges_summary = scan_iges_entity_summary(file_path) if file_format == "IGES" else None

        try:
            with self._path_for_opencascade(file_path) as read_path:
                shape = self._read_shape(read_path, iges_summary=iges_summary)
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
            file_format=file_format,
            warnings=(
                (iges_summary.warning(),)
                if iges_summary is not None and iges_summary.is_surface_only_model
                else ()
            ),
        )

    @staticmethod
    def detect_format(path: str | Path) -> str:
        suffix = Path(path).suffix.casefold()
        if suffix in {".step", ".stp"}:
            return "STEP"
        if suffix in {".iges", ".igs"}:
            return "IGES"
        return "UNKNOWN"

    def _read_shape(self, path: Path, *, iges_summary: IgesEntitySummary | None = None):
        file_format = self.detect_format(path)
        if file_format == "STEP":
            return self._read_step(path)
        if file_format == "IGES":
            return self._read_iges(path, iges_summary=iges_summary)
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
    def _read_iges(path: Path, *, iges_summary: IgesEntitySummary | None = None):
        last_error: CadImportError | None = None
        candidates = [path]
        temp_dir_context = None

        if _iges_has_non_ascii_bytes(path):
            temp_dir_context = TemporaryDirectory(prefix="tubecut_iges_ascii_")
            sanitized_path = Path(temp_dir_context.name) / "input.igs"
            _copy_iges_ascii_sanitized(path, sanitized_path)
            candidates.append(sanitized_path)

        try:
            for candidate in candidates:
                try:
                    shape = CadImporter._read_iges_once(candidate)
                except CadImportError as exc:
                    last_error = exc
                    continue
                if not _shape_is_null(shape):
                    if iges_summary is not None and iges_summary.is_surface_only_model:
                        return shape
                    return _sew_iges_shape(shape)
                last_error = CadImportError("OpenCascade вернул пустую IGES-модель.")
        finally:
            if temp_dir_context is not None:
                temp_dir_context.cleanup()

        if len(candidates) > 1:
            raise CadImportError(
                "IGES-файл не удалось прочитать даже после очистки не-ASCII заголовка."
            ) from last_error
        raise last_error or CadImportError("IGES-файл не удалось прочитать.")

    @staticmethod
    def _read_iges_once(path: Path):
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


def _sew_iges_shape(shape: object) -> object:
    """Sew free IGES surfaces into a shell with shared edges and vertices.

    Returns the sewed shape on success, or the original shape unchanged on any
    failure (missing dependency, untopologized input, OpenCascade error) so an
    IGES import never regresses to an error because of healing.
    """
    if shape is None:
        return shape

    try:
        from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_Sewing

        sewing = BRepBuilderAPI_Sewing(IGES_SEW_TOLERANCE_MM)
        sewing.Add(shape)
        sewing.Perform()
        sewed = sewing.SewedShape()
    except Exception:
        return shape

    if sewed is None:
        return shape
    try:
        if sewed.IsNull():
            return shape
    except Exception:
        return shape
    return sewed


def scan_iges_entity_summary(path: str | Path) -> IgesEntitySummary:
    """Read the IGES directory section without OpenCascade.

    This is intentionally lightweight: it only inspects fixed-width D-section
    records and counts entity types. Surface-only IGES files can then skip
    expensive automatic sewing.
    """
    entity_counts: dict[int, int] = {}
    try:
        lines = Path(path).read_bytes().splitlines()
    except OSError:
        return IgesEntitySummary(entity_count=0, entity_counts={})

    directory_lines = [
        line
        for line in lines
        if len(line) >= 73 and line[72:73] == b"D"
    ]
    for line in directory_lines[::2]:
        try:
            entity_type = int(line[:8].strip())
        except ValueError:
            continue
        entity_counts[entity_type] = entity_counts.get(entity_type, 0) + 1
    return IgesEntitySummary(
        entity_count=sum(entity_counts.values()),
        entity_counts=entity_counts,
    )


def _iges_has_non_ascii_bytes(path: Path) -> bool:
    try:
        return any(byte > 0x7F for byte in path.read_bytes())
    except OSError:
        return False


def _copy_iges_ascii_sanitized(source: Path, target: Path) -> None:
    target.write_bytes(_sanitize_iges_ascii_bytes(source.read_bytes()))


def _sanitize_iges_ascii_bytes(data: bytes) -> bytes:
    table = bytes.maketrans(
        bytes(range(256)),
        bytes(byte if byte <= 0x7F else ord("_") for byte in range(256)),
    )
    return data.translate(table)


def _shape_is_null(shape: object) -> bool:
    if shape is None:
        return True
    try:
        return bool(shape.IsNull())
    except Exception:
        return False
