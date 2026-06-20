from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from cad.importer import CadImporter
from cad.shape_summary import ShapeSummary, _count_topology, summarize_shape


@dataclass(slots=True)
class GeometryAnalysisResult:
    file_format: str
    profile_hint: str
    length_axis: str
    length_mm: float
    width_mm: float
    height_mm: float
    size_x_mm: float
    size_y_mm: float
    size_z_mm: float
    face_count: int
    edge_count: int
    solid_count: int
    shell_count: int
    warnings: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return asdict(self)

    def to_text(self) -> str:
        lines = [
            f"Формат: {self.file_format}",
            f"Тип/подсказка: {self.profile_hint}",
            f"Ось длины: {self.length_axis}",
            f"Длина: {self.length_mm:.3f} мм",
            f"Сечение по габаритам: {self.width_mm:.3f} x {self.height_mm:.3f} мм",
            (
                "Габариты XYZ: "
                f"{self.size_x_mm:.3f} x {self.size_y_mm:.3f} x {self.size_z_mm:.3f} мм"
            ),
            f"Топология: solid={self.solid_count}, shell={self.shell_count}, "
            f"faces={self.face_count}, edges={self.edge_count}",
        ]
        if self.warnings:
            lines.append("Предупреждения:")
            lines.extend(f"- {warning}" for warning in self.warnings)
        return "\n".join(lines)


class TubeAnalyzer:
    """Basic geometry analyzer for early STEP/IGES experiments."""

    def analyze(self, path: str | Path) -> GeometryAnalysisResult:
        import_result = CadImporter().import_file(path)
        return self.analyze_shape(
            import_result.shape,
            file_format=import_result.file_format,
        )

    def analyze_shape(
        self,
        shape: object,
        *,
        summary: ShapeSummary | None = None,
        file_format: str = "CAD",
    ) -> GeometryAnalysisResult:
        return analyze_shape(shape, summary=summary, file_format=file_format)


def analyze_shape(
    shape: object | None,
    *,
    summary: ShapeSummary | None = None,
    file_format: str = "CAD",
) -> GeometryAnalysisResult:
    if summary is None:
        if shape is None:
            raise ValueError("Нужна импортированная форма или готовая сводка ShapeSummary.")
        summary = summarize_shape(shape)

    sizes = {
        "X": max(0.0, float(summary.size_x_mm)),
        "Y": max(0.0, float(summary.size_y_mm)),
        "Z": max(0.0, float(summary.size_z_mm)),
    }
    length_axis, length_mm = max(sizes.items(), key=lambda item: item[1])
    cross_axes = [axis for axis in ("X", "Y", "Z") if axis != length_axis]
    cross_sizes = sorted((sizes[axis] for axis in cross_axes), reverse=True)
    width_mm = cross_sizes[0] if cross_sizes else 0.0
    height_mm = cross_sizes[1] if len(cross_sizes) > 1 else 0.0

    warnings: list[str] = []
    solid_count = 0
    shell_count = 0
    if shape is not None:
        solid_count = _count_topology_safely(shape, "TopAbs_SOLID", warnings)
        shell_count = _count_topology_safely(shape, "TopAbs_SHELL", warnings)

    profile_hint = _detect_profile_hint(length_mm, width_mm, height_mm)
    if min(sizes.values()) <= 0.0:
        warnings.append("Один из габаритов равен нулю; модель может быть поверхностной.")
    if solid_count == 0 and shell_count > 0:
        warnings.append("Найдены оболочки без solid-тела; толщину стенки пока нельзя определить надежно.")

    return GeometryAnalysisResult(
        file_format=file_format,
        profile_hint=profile_hint,
        length_axis=length_axis,
        length_mm=length_mm,
        width_mm=width_mm,
        height_mm=height_mm,
        size_x_mm=sizes["X"],
        size_y_mm=sizes["Y"],
        size_z_mm=sizes["Z"],
        face_count=int(summary.face_count),
        edge_count=int(summary.edge_count),
        solid_count=solid_count,
        shell_count=shell_count,
        warnings=tuple(warnings),
    )


def _detect_profile_hint(length_mm: float, width_mm: float, height_mm: float) -> str:
    max_cross = max(width_mm, height_mm)
    min_cross = min(width_mm, height_mm)
    if length_mm <= 0.0 or max_cross <= 0.0:
        return "Не определено"

    slender_ratio = length_mm / max_cross
    cross_ratio = abs(width_mm - height_mm) / max_cross
    if slender_ratio >= 3.0 and cross_ratio <= 0.08:
        return "Вытянутая труба/профиль с почти равным сечением"
    if slender_ratio >= 3.0:
        return "Вытянутая профильная труба/деталь"
    if min_cross / max(length_mm, max_cross) <= 0.05:
        return "Плоская деталь/лист по габаритам"
    return "Объемная деталь; тип трубы требует уточнения"


def _count_topology_safely(shape: object, top_abs_name: str, warnings: list[str]) -> int:
    try:
        import OCC.Core.TopAbs as top_abs

        shape_type = getattr(top_abs, top_abs_name)
        return _count_topology(shape, shape_type)
    except Exception as exc:
        warnings.append(f"Не удалось посчитать {top_abs_name}: {exc}")
        return 0
