from __future__ import annotations

from dataclasses import dataclass

from cad.edge_classifier import AUXILIARY_UNFOLD, CUT_END, CUT_FEATURE, AXIS_INDEX, Bounds
from cad.shape_summary import ShapeSummary


@dataclass(slots=True)
class UnfoldedPoint:
    x_mm: float
    y_mm: float


@dataclass(slots=True)
class UnfoldedSegment:
    start: UnfoldedPoint
    end: UnfoldedPoint
    length_mm: float
    reason: str
    component_id: int
    edge_type: str


@dataclass(slots=True)
class UnfoldingPreview:
    length_mm: float
    perimeter_mm: float
    cut_length_mm: float
    diagnostic_edge_length_mm: float
    pierce_count: int
    segments: tuple[UnfoldedSegment, ...]
    calculated_cut_segments: tuple[UnfoldedSegment, ...] = ()
    auxiliary_unfold_segments: tuple[UnfoldedSegment, ...] = ()
    ignored_longitudinal_segments: tuple[UnfoldedSegment, ...] = ()
    ignored_profile_segments: tuple[UnfoldedSegment, ...] = ()
    uncertain_segments: tuple[UnfoldedSegment, ...] = ()
    warnings: tuple[str, ...] = ()


class TubeUnfolder:
    """Builds a diagnostic 2D map of counted cut contours."""

    def unfold(
        self,
        shape: object,
        *,
        summary: ShapeSummary,
        length_axis: str,
    ) -> UnfoldingPreview:
        return build_unfolding_preview(
            shape,
            summary=summary,
            length_axis=length_axis,
        )


def build_unfolding_preview(
    shape: object | None,
    *,
    summary: ShapeSummary,
    length_axis: str,
) -> UnfoldingPreview:
    if shape is None:
        return UnfoldingPreview(
            length_mm=_summary_axis_size(summary, length_axis),
            perimeter_mm=0.0,
            cut_length_mm=0.0,
            diagnostic_edge_length_mm=0.0,
            pierce_count=0,
            segments=(),
            auxiliary_unfold_segments=(),
            warnings=("Нет формы OpenCascade для построения развертки.",),
        )

    import cad.edge_classifier as edge_classifier

    axis = length_axis if length_axis in AXIS_INDEX else "Z"
    global_bounds = edge_classifier._shape_bounds(shape)
    classification = edge_classifier.classify_cut_edges(
        shape,
        summary=summary,
        length_axis=axis,
    )
    tolerance = edge_classifier._tolerance_from_summary(summary)
    return build_unfolding_preview_from_edges(
        classification.calculated_cut_edges,
        axis=axis,
        global_bounds=global_bounds,
        cut_length_mm=classification.cut_length_mm,
        diagnostic_edge_length_mm=classification.diagnostic_edge_length_mm,
        pierce_count=classification.pierce_count or 0,
        tolerance=tolerance,
        ignored_longitudinal_edges=classification.ignored_longitudinal_edges,
        ignored_profile_edges=classification.ignored_profile_edges,
        uncertain_edges=classification.uncertain_edges,
        warnings=classification.warnings,
    )


def build_unfolding_preview_from_edges(
    edges: tuple[object, ...] | list[object],
    *,
    axis: str,
    global_bounds: Bounds,
    cut_length_mm: float,
    pierce_count: int,
    tolerance: float,
    diagnostic_edge_length_mm: float = 0.0,
    ignored_longitudinal_edges: tuple[object, ...] | list[object] = (),
    ignored_profile_edges: tuple[object, ...] | list[object] = (),
    uncertain_edges: tuple[object, ...] | list[object] = (),
    warnings: tuple[str, ...] = (),
) -> UnfoldingPreview:
    axis = axis if axis in AXIS_INDEX else "Z"
    length_mm = _axis_size(global_bounds, axis)
    perimeter_mm = _approx_profile_perimeter(global_bounds, axis)
    component_ids = _component_ids(
        edges,
        axis=axis,
        global_bounds=global_bounds,
        tolerance=tolerance,
    )
    calculated_cut_segments = _segments_from_edges(
        edges,
        axis=axis,
        global_bounds=global_bounds,
        component_ids=component_ids,
        default_edge_type=CUT_FEATURE,
    )
    auxiliary_unfold_segments = _auxiliary_unfold_segments(
        length_mm=length_mm,
        perimeter_mm=perimeter_mm,
    )
    ignored_longitudinal_segments = _segments_from_edges(
        ignored_longitudinal_edges,
        axis=axis,
        global_bounds=global_bounds,
        default_edge_type="IGNORED_LONGITUDINAL",
    )
    ignored_profile_segments = _segments_from_edges(
        ignored_profile_edges,
        axis=axis,
        global_bounds=global_bounds,
        default_edge_type="IGNORED_PROFILE",
    )
    uncertain_segments = _segments_from_edges(
        uncertain_edges,
        axis=axis,
        global_bounds=global_bounds,
        default_edge_type="UNCERTAIN",
    )

    return UnfoldingPreview(
        length_mm=length_mm,
        perimeter_mm=perimeter_mm,
        cut_length_mm=cut_length_mm,
        diagnostic_edge_length_mm=diagnostic_edge_length_mm,
        pierce_count=pierce_count,
        segments=calculated_cut_segments,
        calculated_cut_segments=calculated_cut_segments,
        auxiliary_unfold_segments=auxiliary_unfold_segments,
        ignored_longitudinal_segments=ignored_longitudinal_segments,
        ignored_profile_segments=ignored_profile_segments,
        uncertain_segments=uncertain_segments,
        warnings=warnings,
    )


def _segments_from_edges(
    edges: tuple[object, ...] | list[object],
    *,
    axis: str,
    global_bounds: Bounds,
    component_ids: dict[int, int] | None = None,
    default_edge_type: str,
) -> tuple[UnfoldedSegment, ...]:
    segments: list[UnfoldedSegment] = []
    for index, edge in enumerate(edges):
        points = _edge_points(edge, axis=axis)
        if points is None:
            continue
        start, end = points
        edge_type = str(getattr(edge, "edge_type", "") or default_edge_type)
        segments.append(
            UnfoldedSegment(
                start=_project_point(start, axis=axis, global_bounds=global_bounds),
                end=_project_point(end, axis=axis, global_bounds=global_bounds),
                length_mm=float(getattr(edge, "length_mm", 0.0) or 0.0),
                reason=str(getattr(edge, "reason", "") or edge_type),
                component_id=(component_ids or {}).get(index, -1),
                edge_type=edge_type,
            )
        )
    return tuple(segments)


def _auxiliary_unfold_segments(
    *,
    length_mm: float,
    perimeter_mm: float,
) -> tuple[UnfoldedSegment, ...]:
    if length_mm <= 0.0 or perimeter_mm <= 0.0:
        return ()
    points = (
        (UnfoldedPoint(0.0, 0.0), UnfoldedPoint(length_mm, 0.0)),
        (UnfoldedPoint(length_mm, 0.0), UnfoldedPoint(length_mm, perimeter_mm)),
        (UnfoldedPoint(length_mm, perimeter_mm), UnfoldedPoint(0.0, perimeter_mm)),
        (UnfoldedPoint(0.0, perimeter_mm), UnfoldedPoint(0.0, 0.0)),
    )
    return tuple(
        UnfoldedSegment(
            start=start,
            end=end,
            length_mm=0.0,
            reason="auxiliary unfold boundary",
            component_id=-1,
            edge_type=AUXILIARY_UNFOLD,
        )
        for start, end in points
    )


def _component_ids(
    edges: tuple[object, ...] | list[object],
    *,
    axis: str,
    global_bounds: Bounds,
    tolerance: float,
) -> dict[int, int]:
    if not edges:
        return {}

    parent = list(range(len(edges)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(first: int, second: int) -> None:
        first_root = find(first)
        second_root = find(second)
        if first_root != second_root:
            parent[second_root] = first_root

    for left_index, left in enumerate(edges):
        for right_index in range(left_index + 1, len(edges)):
            right = edges[right_index]
            if _same_tube_end_side(
                left,
                right,
                axis=axis,
                global_bounds=global_bounds,
                tolerance=tolerance,
            ) or _edges_touch(left, right, tolerance=tolerance):
                union(left_index, right_index)

    root_to_component: dict[int, int] = {}
    component_ids: dict[int, int] = {}
    for index in range(len(edges)):
        root = find(index)
        if root not in root_to_component:
            root_to_component[root] = len(root_to_component)
        component_ids[index] = root_to_component[root]
    return component_ids


def _same_tube_end_side(
    first: object,
    second: object,
    *,
    axis: str,
    global_bounds: Bounds,
    tolerance: float,
) -> bool:
    if getattr(first, "edge_type", "") != CUT_END:
        return False
    if getattr(second, "edge_type", "") != CUT_END:
        return False
    first_side = _edge_end_side(first, axis=axis, global_bounds=global_bounds, tolerance=tolerance)
    return first_side is not None and first_side == _edge_end_side(
        second,
        axis=axis,
        global_bounds=global_bounds,
        tolerance=tolerance,
    )


def _edges_touch(first: object, second: object, *, tolerance: float) -> bool:
    first_vertices = (getattr(first, "start_vertex", None), getattr(first, "end_vertex", None))
    second_vertices = (getattr(second, "start_vertex", None), getattr(second, "end_vertex", None))
    for first_vertex in first_vertices:
        for second_vertex in second_vertices:
            if first_vertex is not None and second_vertex is not None:
                try:
                    if bool(first_vertex.IsSame(second_vertex)):
                        return True
                except Exception:
                    if first_vertex is second_vertex:
                        return True

    first_points = (getattr(first, "start_point", None), getattr(first, "end_point", None))
    second_points = (getattr(second, "start_point", None), getattr(second, "end_point", None))
    return any(
        first_point is not None
        and second_point is not None
        and _points_are_close(first_point, second_point, tolerance=tolerance)
        for first_point in first_points
        for second_point in second_points
    )


def _edge_points(
    edge: object,
    *,
    axis: str,
) -> tuple[tuple[float, float, float], tuple[float, float, float]] | None:
    start_point = getattr(edge, "start_point", None)
    end_point = getattr(edge, "end_point", None)
    if start_point is not None and end_point is not None:
        return start_point, end_point

    bounds = getattr(edge, "bounds", None)
    if bounds is None:
        return None

    axis_index = AXIS_INDEX[axis]
    mins = list(bounds.mins)
    maxes = list(bounds.maxes)
    varying_indexes = [
        index
        for index, (minimum, maximum) in enumerate(zip(mins, maxes, strict=True))
        if index != axis_index and abs(maximum - minimum) > 0.0
    ]
    if not varying_indexes:
        varying_indexes = [axis_index]

    start = mins[:]
    end = mins[:]
    for index in varying_indexes:
        end[index] = maxes[index]
    return tuple(start), tuple(end)  # type: ignore[return-value]


def _project_point(
    point: tuple[float, float, float],
    *,
    axis: str,
    global_bounds: Bounds,
) -> UnfoldedPoint:
    axis_index = AXIS_INDEX[axis]
    length = point[axis_index] - global_bounds.mins[axis_index]
    return UnfoldedPoint(
        x_mm=max(0.0, min(_axis_size(global_bounds, axis), length)),
        y_mm=_cross_section_position(point, axis=axis, global_bounds=global_bounds),
    )


def _cross_section_position(
    point: tuple[float, float, float],
    *,
    axis: str,
    global_bounds: Bounds,
) -> float:
    axis_index = AXIS_INDEX[axis]
    cross_indexes = [index for index in range(3) if index != axis_index]
    u_index, v_index = cross_indexes
    min_u = global_bounds.mins[u_index]
    max_u = global_bounds.maxes[u_index]
    min_v = global_bounds.mins[v_index]
    max_v = global_bounds.maxes[v_index]
    width = max(0.0, max_u - min_u)
    height = max(0.0, max_v - min_v)
    u = max(min_u, min(max_u, point[u_index]))
    v = max(min_v, min(max_v, point[v_index]))

    side = min(
        (
            ("bottom", abs(v - min_v)),
            ("right", abs(u - max_u)),
            ("top", abs(v - max_v)),
            ("left", abs(u - min_u)),
        ),
        key=lambda item: item[1],
    )[0]

    if side == "bottom":
        return u - min_u
    if side == "right":
        return width + (v - min_v)
    if side == "top":
        return width + height + (max_u - u)
    return (2.0 * width) + height + (max_v - v)


def _edge_end_side(
    edge: object,
    *,
    axis: str,
    global_bounds: Bounds,
    tolerance: float,
) -> str | None:
    bounds = getattr(edge, "bounds", None)
    if bounds is None:
        return None

    axis_index = AXIS_INDEX[axis]
    edge_min = bounds.mins[axis_index]
    edge_max = bounds.maxes[axis_index]
    global_min = global_bounds.mins[axis_index]
    global_max = global_bounds.maxes[axis_index]
    end_tolerance = max(tolerance * 4.0, 0.05)
    if abs(edge_min - global_min) <= end_tolerance and abs(edge_max - global_min) <= end_tolerance:
        return "min"
    if abs(edge_min - global_max) <= end_tolerance and abs(edge_max - global_max) <= end_tolerance:
        return "max"
    return None


def _axis_size(bounds: Bounds, axis: str) -> float:
    return bounds.sizes[AXIS_INDEX[axis]]


def _approx_profile_perimeter(bounds: Bounds, axis: str) -> float:
    axis_index = AXIS_INDEX[axis]
    cross_sizes = [size for index, size in enumerate(bounds.sizes) if index != axis_index]
    if len(cross_sizes) != 2:
        return 0.0
    return 2.0 * (cross_sizes[0] + cross_sizes[1])


def _summary_axis_size(summary: ShapeSummary, axis: str) -> float:
    axis = axis if axis in AXIS_INDEX else "Z"
    return {
        "X": float(summary.size_x_mm),
        "Y": float(summary.size_y_mm),
        "Z": float(summary.size_z_mm),
    }[axis]


def _points_are_close(
    first: tuple[float, float, float],
    second: tuple[float, float, float],
    *,
    tolerance: float,
) -> bool:
    return all(
        abs(first_value - second_value) <= tolerance
        for first_value, second_value in zip(first, second, strict=True)
    )
