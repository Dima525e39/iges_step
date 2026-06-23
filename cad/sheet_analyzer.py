from __future__ import annotations

from dataclasses import dataclass
from math import hypot

from cad.edge_classifier import Bounds
from cad.shape_summary import ShapeSummary


@dataclass(slots=True)
class SheetPoint:
    x_mm: float
    y_mm: float


@dataclass(slots=True)
class SheetSegment:
    start: SheetPoint
    end: SheetPoint
    length_mm: float
    contour_id: int
    is_outer: bool


@dataclass(slots=True)
class SheetContour:
    points: tuple[SheetPoint, ...]
    length_mm: float
    component_id: int
    is_outer: bool = False


@dataclass(slots=True)
class SheetAnalysisResult:
    width_mm: float
    height_mm: float
    thickness_mm: float
    thickness_axis: str
    cut_length_mm: float
    pierce_count: int
    contours: tuple[SheetContour, ...]
    segments: tuple[SheetSegment, ...]
    warnings: tuple[str, ...] = ()

    @property
    def contour_count(self) -> int:
        return len(self.contours)


def analyze_sheet_shape(
    shape: object | None,
    *,
    summary: ShapeSummary,
    manual_thickness_mm: float | None = None,
) -> SheetAnalysisResult | None:
    if shape is None or not looks_like_sheet(summary):
        return None

    warnings: list[str] = []
    axis, axis_index = _thickness_axis(summary)
    bounds = _shape_bounds(shape)
    projection_indexes = [index for index in range(3) if index != axis_index]
    face = _select_sheet_face(
        shape,
        axis_index=axis_index,
        projection_indexes=projection_indexes,
        tolerance=_tolerance(summary),
        warnings=warnings,
    )
    if face is None:
        warnings.append("Не найдена базовая плоская грань листовой детали.")
        return None

    contours = _extract_face_contours(
        face,
        bounds=bounds,
        projection_indexes=projection_indexes,
        warnings=warnings,
    )
    if not contours:
        warnings.append("На базовой грани листовой детали не найдены контуры.")
        return None

    contours = _mark_outer_contour(contours)
    segments = tuple(
        segment
        for contour in contours
        for segment in _segments_for_contour(contour)
    )
    thickness = float(manual_thickness_mm or 0.0)
    if thickness <= 0.0:
        thickness = _axis_size(bounds, axis_index)
    if thickness <= _tolerance(summary):
        warnings.append(
            "Толщина листовой детали близка к нулю; модель может быть поверхностной."
        )

    return SheetAnalysisResult(
        width_mm=_axis_size(bounds, projection_indexes[0]),
        height_mm=_axis_size(bounds, projection_indexes[1]),
        thickness_mm=thickness,
        thickness_axis=axis,
        cut_length_mm=sum(contour.length_mm for contour in contours),
        pierce_count=len(contours),
        contours=contours,
        segments=segments,
        warnings=tuple(warnings),
    )


def looks_like_sheet(summary: ShapeSummary) -> bool:
    sizes = sorted(
        (
            max(0.0, float(summary.size_x_mm)),
            max(0.0, float(summary.size_y_mm)),
            max(0.0, float(summary.size_z_mm)),
        )
    )
    if sizes[1] <= 0.0 or sizes[2] <= 0.0:
        return False
    return sizes[0] <= max(sizes[1] * 0.12, 0.25)


def build_sheet_analysis_from_contours(
    contours: tuple[SheetContour, ...] | list[SheetContour],
    *,
    width_mm: float,
    height_mm: float,
    thickness_mm: float,
    thickness_axis: str = "Z",
    warnings: tuple[str, ...] = (),
) -> SheetAnalysisResult:
    marked = _mark_outer_contour(tuple(contours))
    segments = tuple(
        segment for contour in marked for segment in _segments_for_contour(contour)
    )
    return SheetAnalysisResult(
        width_mm=width_mm,
        height_mm=height_mm,
        thickness_mm=thickness_mm,
        thickness_axis=thickness_axis,
        cut_length_mm=sum(contour.length_mm for contour in marked),
        pierce_count=len(marked),
        contours=marked,
        segments=segments,
        warnings=warnings,
    )


def _extract_face_contours(
    face: object,
    *,
    bounds: Bounds,
    projection_indexes: list[int],
    warnings: list[str],
) -> tuple[SheetContour, ...]:
    try:
        from OCC.Core.TopAbs import TopAbs_EDGE, TopAbs_WIRE
    except Exception as exc:
        warnings.append(f"Не удалось импортировать TopAbs для листовых контуров: {exc}")
        return ()

    from cad.edge_classifier import _edge_length, _iter_shapes

    contours: list[SheetContour] = []
    for wire in _iter_shapes(face, TopAbs_WIRE):
        points: list[SheetPoint] = []
        length_mm = 0.0
        for edge in _iter_shapes(wire, TopAbs_EDGE):
            length_mm += _edge_length(edge, warnings)
            edge_points = _sample_edge_points(
                edge,
                projection_indexes=projection_indexes,
                bounds=bounds,
            )
            if not edge_points:
                continue
            if points and _distance(points[-1], edge_points[-1]) < _distance(points[-1], edge_points[0]):
                edge_points = tuple(reversed(edge_points))
            for point in edge_points:
                if points and _distance(points[-1], point) <= 0.001:
                    continue
                points.append(point)
        if len(points) >= 2:
            if _distance(points[0], points[-1]) > 0.001:
                points.append(points[0])
            contours.append(
                SheetContour(
                    points=tuple(points),
                    length_mm=length_mm,
                    component_id=len(contours) + 1,
                )
            )
    return tuple(contours)


def _sample_edge_points(
    edge: object,
    *,
    projection_indexes: list[int],
    bounds: Bounds,
) -> tuple[SheetPoint, ...]:
    sampled = _sample_curve(edge, projection_indexes=projection_indexes, bounds=bounds)
    if sampled:
        return sampled
    return _edge_endpoint_points(edge, projection_indexes=projection_indexes, bounds=bounds)


def _sample_curve(
    edge: object,
    *,
    projection_indexes: list[int],
    bounds: Bounds,
) -> tuple[SheetPoint, ...]:
    try:
        from OCC.Core.BRepAdaptor import BRepAdaptor_Curve

        curve = BRepAdaptor_Curve(edge)
        first = float(curve.FirstParameter())
        last = float(curve.LastParameter())
        length = _safe_edge_length(edge)
        steps = max(2, min(96, int(length / 3.0) + 2))
        points: list[SheetPoint] = []
        for index in range(steps + 1):
            parameter = first + (last - first) * (index / steps)
            point = curve.Value(parameter)
            points.append(
                _project_point(
                    (float(point.X()), float(point.Y()), float(point.Z())),
                    projection_indexes=projection_indexes,
                    bounds=bounds,
                )
            )
        return tuple(points)
    except Exception:
        return ()


def _edge_endpoint_points(
    edge: object,
    *,
    projection_indexes: list[int],
    bounds: Bounds,
) -> tuple[SheetPoint, ...]:
    from cad.edge_classifier import _edge_vertices, _vertex_point

    first, last = _edge_vertices(edge)
    first_point = _vertex_point(first)
    last_point = _vertex_point(last)
    if first_point is None or last_point is None:
        return ()
    return (
        _project_point(first_point, projection_indexes=projection_indexes, bounds=bounds),
        _project_point(last_point, projection_indexes=projection_indexes, bounds=bounds),
    )


def _select_sheet_face(
    shape: object,
    *,
    axis_index: int,
    projection_indexes: list[int],
    tolerance: float,
    warnings: list[str],
) -> object | None:
    try:
        from OCC.Core.TopAbs import TopAbs_FACE
    except Exception as exc:
        warnings.append(f"Не удалось импортировать TopAbs_FACE: {exc}")
        return None

    from cad.edge_classifier import _face_area, _iter_shapes, _safe_bounds

    candidates: list[tuple[float, object]] = []
    for face in _iter_shapes(shape, TopAbs_FACE):
        face_bounds = _safe_bounds(face)
        if face_bounds is None:
            continue
        if face_bounds.sizes[axis_index] > max(tolerance * 4.0, 0.05):
            continue
        projected_area = (
            face_bounds.sizes[projection_indexes[0]]
            * face_bounds.sizes[projection_indexes[1]]
        )
        measured_area = _face_area(face, warnings)
        candidates.append((max(projected_area, measured_area), face))
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]


def _mark_outer_contour(
    contours: tuple[SheetContour, ...] | list[SheetContour],
) -> tuple[SheetContour, ...]:
    if not contours:
        return ()
    outer_index = max(
        range(len(contours)),
        key=lambda index: abs(_polygon_area(contours[index].points)),
    )
    marked: list[SheetContour] = []
    for index, contour in enumerate(contours):
        marked.append(
            SheetContour(
                points=contour.points,
                length_mm=contour.length_mm,
                component_id=index + 1,
                is_outer=index == outer_index,
            )
        )
    return tuple(marked)


def _segments_for_contour(contour: SheetContour) -> tuple[SheetSegment, ...]:
    segments: list[SheetSegment] = []
    for start, end in zip(contour.points, contour.points[1:], strict=False):
        length = _distance(start, end)
        if length <= 0.001:
            continue
        segments.append(
            SheetSegment(
                start=start,
                end=end,
                length_mm=length,
                contour_id=contour.component_id,
                is_outer=contour.is_outer,
            )
        )
    return tuple(segments)


def _shape_bounds(shape: object) -> Bounds:
    from cad.edge_classifier import _shape_bounds as edge_shape_bounds

    return edge_shape_bounds(shape)


def _safe_edge_length(edge: object) -> float:
    warnings: list[str] = []
    from cad.edge_classifier import _edge_length

    return _edge_length(edge, warnings)


def _project_point(
    point: tuple[float, float, float],
    *,
    projection_indexes: list[int],
    bounds: Bounds,
) -> SheetPoint:
    x_index, y_index = projection_indexes
    return SheetPoint(
        x_mm=float(point[x_index]) - bounds.mins[x_index],
        y_mm=float(point[y_index]) - bounds.mins[y_index],
    )


def _polygon_area(points: tuple[SheetPoint, ...]) -> float:
    if len(points) < 3:
        return 0.0
    area = 0.0
    for first, second in zip(points, points[1:], strict=False):
        area += first.x_mm * second.y_mm - second.x_mm * first.y_mm
    return area / 2.0


def _distance(first: SheetPoint, second: SheetPoint) -> float:
    return hypot(first.x_mm - second.x_mm, first.y_mm - second.y_mm)


def _thickness_axis(summary: ShapeSummary) -> tuple[str, int]:
    sizes = (
        float(summary.size_x_mm),
        float(summary.size_y_mm),
        float(summary.size_z_mm),
    )
    index = min(range(3), key=lambda item: sizes[item])
    return ("X", "Y", "Z")[index], index


def _axis_size(bounds: Bounds, axis_index: int) -> float:
    return bounds.sizes[axis_index]


def _tolerance(summary: ShapeSummary) -> float:
    return max(float(summary.diagonal_mm) * 1e-5, 0.01)
