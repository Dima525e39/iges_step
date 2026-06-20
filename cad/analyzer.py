from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from cad.edge_classifier import classify_cut_edges
from cad.importer import CadImporter
from cad.pierce_counter import count_edge_components
from cad.profile_detector import detect_profile_from_dimensions
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
    wall_thickness_mm: float = 0.0
    cut_length_mm: float = 0.0
    pierce_count: int = 0
    cut_edge_count: int = 0
    outer_face_count: int = 0
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
            f"Толщина стенки (предварительно): {self.wall_thickness_mm:.3f} мм",
            f"Длина реза (предварительно): {self.cut_length_mm:.3f} мм",
            f"Врезки/контуры (предварительно): {self.pierce_count}",
            f"Кандидатов ребер реза: {self.cut_edge_count}",
            f"Наружных продольных граней: {self.outer_face_count}",
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

    profile = detect_profile_from_dimensions(length_mm, width_mm, height_mm)
    profile_hint = profile.profile_type
    cut_length_mm = 0.0
    pierce_count = 0
    cut_edge_count = 0
    outer_face_count = 0
    wall_thickness_mm = 0.0
    if min(sizes.values()) <= 0.0:
        warnings.append("Один из габаритов равен нулю; модель может быть поверхностной.")
    if solid_count == 0 and shell_count > 0:
        warnings.append("Найдены оболочки без solid-тела; толщину стенки пока нельзя определить надежно.")
    if shape is not None:
        classification = classify_cut_edges(
            shape,
            summary=summary,
            length_axis=length_axis,
        )
        pierce_estimate = count_edge_components(classification.cut_edges)
        cut_length_mm = classification.cut_length_mm
        pierce_count = classification.pierce_count
        if pierce_count is None:
            pierce_count = pierce_estimate.pierce_count
        cut_edge_count = classification.cut_edge_count
        outer_face_count = classification.outer_face_count
        wall_thickness_mm = classification.wall_thickness_mm
        warnings.extend(classification.warnings)
        if classification.pierce_count is None:
            warnings.extend(pierce_estimate.warnings)
        if cut_length_mm > 0.0:
            warnings.append(
                "Длина реза рассчитана предварительно по геометрии модели; "
                "проверьте результат через DEV-скрипт."
            )

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
        wall_thickness_mm=wall_thickness_mm,
        cut_length_mm=cut_length_mm,
        pierce_count=pierce_count,
        cut_edge_count=cut_edge_count,
        outer_face_count=outer_face_count,
        warnings=tuple(warnings),
    )


def _count_topology_safely(shape: object, top_abs_name: str, warnings: list[str]) -> int:
    try:
        import OCC.Core.TopAbs as top_abs

        shape_type = getattr(top_abs, top_abs_name)
        return _count_topology(shape, shape_type)
    except Exception as exc:
        warnings.append(f"Не удалось посчитать {top_abs_name}: {exc}")
        return 0
