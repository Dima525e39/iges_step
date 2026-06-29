from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from cad.debug_faces import write_debug_faces_csv
from cad.debug_edges import write_debug_edges_csv
from cad.edge_classifier import classify_cut_edges
from cad.importer import CadImporter
from cad.pierce_counter import count_edge_components
from cad.profile_detector import detect_profile_from_dimensions
from cad.shape_summary import ShapeSummary, _count_topology, summarize_shape
from cad.sheet_analyzer import SheetAnalysisResult, analyze_sheet_shape
from cad.step_text_analyzer import analyze_step_round_tube_text


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
    wall_thickness_method: str = "не определена"
    wall_thickness_confidence: str = "низкая"
    round_outer_diameter_mm: float = 0.0
    cut_length_mm: float = 0.0
    cut_end_length_mm: float = 0.0
    cut_feature_length_mm: float = 0.0
    diagnostic_edge_length_mm: float = 0.0
    pierce_count: int = 0
    cut_edge_count: int = 0
    outer_face_count: int = 0
    ignored_longitudinal_edge_count: int = 0
    ignored_profile_edge_count: int = 0
    ignored_plane_radius_edge_count: int = 0
    auxiliary_unfold_edge_count: int = 0
    uncertain_edge_count: int = 0
    debug_edges_path: str = ""
    debug_faces_path: str = ""
    warnings: tuple[str, ...] = ()
    sheet_analysis: SheetAnalysisResult | None = None

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
            f"Способ толщины: {self.wall_thickness_method}",
            f"Confidence толщины: {self.wall_thickness_confidence}",
            f"Длина реального реза: {self.cut_length_mm:.3f} мм",
            f"Длина торцевых резов: {self.cut_end_length_mm:.3f} мм",
            f"Длина вырезов/пазов: {self.cut_feature_length_mm:.3f} мм",
            f"Диагностическая сумма всех ребер: {self.diagnostic_edge_length_mm:.3f} мм",
            f"Врезки/контуры (предварительно): {self.pierce_count}",
            f"Кандидатов ребер реза: {self.cut_edge_count}",
            f"Наружных продольных граней: {self.outer_face_count}",
            f"Игнорированных продольных ребер: {self.ignored_longitudinal_edge_count}",
            f"Игнорированных профильных ребер: {self.ignored_profile_edge_count}",
            f"Игнорированных линий плоскость/радиус: {self.ignored_plane_radius_edge_count}",
            f"Вспомогательных линий развертки: {self.auxiliary_unfold_edge_count}",
            f"Сомнительных ребер: {self.uncertain_edge_count}",
        ]
        if self.sheet_analysis is not None:
            lines.append(
                "Листовые контуры: "
                f"{self.sheet_analysis.contour_count}; "
                f"размер {self.sheet_analysis.width_mm:.3f} x "
                f"{self.sheet_analysis.height_mm:.3f} мм"
            )
        if self.debug_edges_path:
            lines.append(f"debug_edges.csv: {self.debug_edges_path}")
        if self.debug_faces_path:
            lines.append(f"debug_faces.csv: {self.debug_faces_path}")
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
            import_warnings=import_result.warnings,
        )

    def analyze_shape(
        self,
        shape: object,
        *,
        summary: ShapeSummary | None = None,
        file_format: str = "CAD",
        import_warnings: tuple[str, ...] = (),
    ) -> GeometryAnalysisResult:
        return analyze_shape(
            shape,
            summary=summary,
            file_format=file_format,
            import_warnings=import_warnings,
        )


def analyze_shape(
    shape: object | None,
    *,
    summary: ShapeSummary | None = None,
    file_format: str = "CAD",
    manual_wall_thickness_mm: float | None = None,
    debug_edges_path: str | Path | None = None,
    source_path: str | Path | None = None,
    sheet_analysis: SheetAnalysisResult | None = None,
    import_warnings: tuple[str, ...] = (),
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

    warnings: list[str] = list(import_warnings)
    solid_count = 0
    shell_count = 0
    if shape is not None:
        solid_count = _count_topology_safely(shape, "TopAbs_SOLID", warnings)
        shell_count = _count_topology_safely(shape, "TopAbs_SHELL", warnings)

    profile = detect_profile_from_dimensions(length_mm, width_mm, height_mm)
    profile_hint = profile.profile_type
    cut_length_mm = 0.0
    cut_end_length_mm = 0.0
    cut_feature_length_mm = 0.0
    diagnostic_edge_length_mm = 0.0
    pierce_count = 0
    cut_edge_count = 0
    outer_face_count = 0
    wall_thickness_mm = 0.0
    wall_thickness_method = "не определена"
    wall_thickness_confidence = "низкая"
    round_outer_diameter_mm = 0.0
    ignored_longitudinal_edge_count = 0
    ignored_profile_edge_count = 0
    ignored_plane_radius_edge_count = 0
    auxiliary_unfold_edge_count = 0
    uncertain_edge_count = 0
    written_debug_edges_path = ""
    written_debug_faces_path = ""
    if min(sizes.values()) <= 0.0:
        warnings.append("Один из габаритов равен нулю; модель может быть поверхностной.")
    if solid_count == 0 and shell_count > 0:
        warnings.append("Найдены оболочки без solid-тела; толщину стенки пока нельзя определить надежно.")

    step_text_analysis = (
        analyze_step_round_tube_text(source_path)
        if source_path is not None
        else None
    )

    skip_sheet_for_surface_iges = _is_surface_only_iges_import(
        file_format=file_format,
        import_warnings=import_warnings,
    )
    if skip_sheet_for_surface_iges:
        warnings.append(
            "Листовой анализ пропущен для surface-only IGES; "
            "используется трубный анализ поверхностей."
        )

    if (
        sheet_analysis is None
        and shape is not None
        and step_text_analysis is None
        and not skip_sheet_for_surface_iges
    ):
        try:
            sheet_analysis = analyze_sheet_shape(
                shape,
                summary=summary,
                manual_thickness_mm=manual_wall_thickness_mm,
            )
        except Exception as exc:
            warnings.append(f"Листовой анализ не выполнен: {exc}")

    if sheet_analysis is not None:
        profile_hint = "листовая деталь"
        width_mm = sheet_analysis.width_mm
        height_mm = sheet_analysis.height_mm
        length_axis = "лист"
        length_mm = max(width_mm, height_mm)
        cut_length_mm = sheet_analysis.cut_length_mm
        cut_feature_length_mm = sheet_analysis.cut_length_mm
        diagnostic_edge_length_mm = sheet_analysis.cut_length_mm
        pierce_count = sheet_analysis.pierce_count
        cut_edge_count = len(sheet_analysis.segments)
        wall_thickness_mm = sheet_analysis.thickness_mm
        wall_thickness_method = (
            "ручной ввод"
            if manual_wall_thickness_mm is not None and manual_wall_thickness_mm > 0.0
            else f"листовой контур, ось толщины {sheet_analysis.thickness_axis}"
        )
        wall_thickness_confidence = "высокая" if wall_thickness_mm > 0.0 else "низкая"
        warnings.extend(sheet_analysis.warnings)
        warnings.append(
            "Листовая деталь рассчитана по 2D-контурам; внешний контур детали входит в рез."
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
            wall_thickness_method=wall_thickness_method,
            wall_thickness_confidence=wall_thickness_confidence,
            round_outer_diameter_mm=0.0,
            cut_length_mm=cut_length_mm,
            cut_end_length_mm=cut_end_length_mm,
            cut_feature_length_mm=cut_feature_length_mm,
            diagnostic_edge_length_mm=diagnostic_edge_length_mm,
            pierce_count=pierce_count,
            cut_edge_count=cut_edge_count,
            outer_face_count=outer_face_count,
            ignored_longitudinal_edge_count=ignored_longitudinal_edge_count,
            ignored_profile_edge_count=ignored_profile_edge_count,
            ignored_plane_radius_edge_count=ignored_plane_radius_edge_count,
            auxiliary_unfold_edge_count=auxiliary_unfold_edge_count,
            uncertain_edge_count=uncertain_edge_count,
            debug_edges_path=written_debug_edges_path,
            debug_faces_path=written_debug_faces_path,
            warnings=tuple(warnings),
            sheet_analysis=sheet_analysis,
        )

    if shape is not None:
        classification = classify_cut_edges(
            shape,
            summary=summary,
            length_axis=length_axis,
            manual_wall_thickness_mm=manual_wall_thickness_mm,
        )
        pierce_estimate = count_edge_components(classification.cut_edges)
        cut_length_mm = classification.cut_length_mm
        cut_end_length_mm = classification.cut_end_length_mm
        cut_feature_length_mm = classification.cut_feature_length_mm
        pierce_count = classification.pierce_count
        if pierce_count is None:
            pierce_count = pierce_estimate.pierce_count
        cut_edge_count = classification.cut_edge_count
        outer_face_count = classification.outer_face_count
        wall_thickness_mm = classification.wall_thickness_mm
        wall_thickness_method = classification.wall_thickness_method
        wall_thickness_confidence = classification.wall_thickness_confidence
        round_outer_diameter_mm = classification.round_outer_diameter_mm
        if round_outer_diameter_mm > 0.0:
            profile_hint = "Круглая труба"
            width_mm = round_outer_diameter_mm
            height_mm = round_outer_diameter_mm
        diagnostic_edge_length_mm = classification.diagnostic_edge_length_mm
        ignored_longitudinal_edge_count = classification.ignored_longitudinal_edge_count
        ignored_profile_edge_count = classification.ignored_profile_edge_count
        ignored_plane_radius_edge_count = classification.ignored_plane_radius_edge_count
        auxiliary_unfold_edge_count = 4 if classification.outer_face_count else 0
        uncertain_edge_count = classification.uncertain_edge_count
        warnings.extend(classification.warnings)
        if debug_edges_path is not None:
            try:
                debug_path = write_debug_edges_csv(
                    classification,
                    debug_edges_path,
                    source_file=str(source_path or ""),
                    length_axis=classification.length_axis,
                    global_bounds=classification.global_bounds,
                    tolerance=classification.tolerance,
                )
                written_debug_edges_path = str(debug_path)
                faces_path = debug_path.with_name("debug_faces.csv")
                written_debug_faces_path = str(
                    write_debug_faces_csv(
                        classification,
                        faces_path,
                        length_axis=classification.length_axis,
                    )
                )
            except Exception as exc:
                warnings.append(f"debug CSV не записан: {exc}")
        if classification.pierce_count is None:
            warnings.extend(pierce_estimate.warnings)
        if cut_length_mm > 0.0:
            warnings.append(
                "Длина реза рассчитана предварительно по геометрии модели; "
                "проверьте результат через DEV-скрипт."
            )

    if step_text_analysis is not None and _should_use_step_round_text_analysis(
        current_cut_length_mm=cut_length_mm,
        current_pierce_count=pierce_count,
        current_cut_feature_length_mm=cut_feature_length_mm,
        step_pierce_count=step_text_analysis.pierce_count,
    ):
        profile_hint = "Круглая труба"
        width_mm = step_text_analysis.outer_diameter_mm
        height_mm = step_text_analysis.outer_diameter_mm
        length_mm = step_text_analysis.length_mm or length_mm
        round_outer_diameter_mm = step_text_analysis.outer_diameter_mm
        wall_thickness_mm = step_text_analysis.wall_thickness_mm
        wall_thickness_method = "STEP pcurve наружный/внутренний цилиндр"
        wall_thickness_confidence = "высокая"
        cut_length_mm = step_text_analysis.cut_length_mm
        cut_end_length_mm = step_text_analysis.cut_end_length_mm
        cut_feature_length_mm = step_text_analysis.cut_feature_length_mm
        diagnostic_edge_length_mm = max(diagnostic_edge_length_mm, cut_length_mm)
        pierce_count = step_text_analysis.pierce_count
        cut_edge_count = step_text_analysis.pierce_count
        warnings.extend(step_text_analysis.warnings)

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
        wall_thickness_method=wall_thickness_method,
        wall_thickness_confidence=wall_thickness_confidence,
        round_outer_diameter_mm=round_outer_diameter_mm,
        cut_length_mm=cut_length_mm,
        cut_end_length_mm=cut_end_length_mm,
        cut_feature_length_mm=cut_feature_length_mm,
        diagnostic_edge_length_mm=diagnostic_edge_length_mm,
        pierce_count=pierce_count,
        cut_edge_count=cut_edge_count,
        outer_face_count=outer_face_count,
        ignored_longitudinal_edge_count=ignored_longitudinal_edge_count,
        ignored_profile_edge_count=ignored_profile_edge_count,
        ignored_plane_radius_edge_count=ignored_plane_radius_edge_count,
        auxiliary_unfold_edge_count=auxiliary_unfold_edge_count,
        uncertain_edge_count=uncertain_edge_count,
        debug_edges_path=written_debug_edges_path,
        debug_faces_path=written_debug_faces_path,
        warnings=tuple(warnings),
        sheet_analysis=sheet_analysis,
    )


def _count_topology_safely(shape: object, top_abs_name: str, warnings: list[str]) -> int:
    try:
        import OCC.Core.TopAbs as top_abs

        shape_type = getattr(top_abs, top_abs_name)
        return _count_topology(shape, shape_type)
    except Exception as exc:
        warnings.append(f"Не удалось посчитать {top_abs_name}: {exc}")
        return 0


def _is_surface_only_iges_import(
    *,
    file_format: str,
    import_warnings: tuple[str, ...],
) -> bool:
    if file_format.upper() != "IGES":
        return False
    return any("поверхности без B-Rep" in warning for warning in import_warnings)


def _should_use_step_round_text_analysis(
    *,
    current_cut_length_mm: float,
    current_pierce_count: int,
    current_cut_feature_length_mm: float,
    step_pierce_count: int,
) -> bool:
    if step_pierce_count <= 0:
        return False
    if current_cut_length_mm <= 0.0:
        return True
    if current_pierce_count != step_pierce_count:
        return True
    if current_cut_feature_length_mm > 0.0:
        return False
    return current_pierce_count <= step_pierce_count
