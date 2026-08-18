from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

from cad.edge_classifier import AXIS_INDEX, CUT_END, CUT_FEATURE, Bounds


Point3D = tuple[float, float, float]
Vector3D = tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class _FrameProbeEdge:
    start_point: Point3D
    end_point: Point3D


@dataclass(frozen=True, slots=True)
class TubeFrame:
    """Stable local coordinate system used by the v6 geometry core."""

    origin: Point3D
    axis: Vector3D
    cross_u: Vector3D
    cross_v: Vector3D
    length_mm: float
    width_mm: float
    height_mm: float
    method: str
    confidence: str

    def local_coordinates(self, point: Point3D) -> Point3D:
        relative = tuple(value - base for value, base in zip(point, self.origin, strict=True))
        return (
            _dot(relative, self.axis),
            _dot(relative, self.cross_u),
            _dot(relative, self.cross_v),
        )

    def unfold_point(self, point: Point3D, *, round_profile: bool = False) -> tuple[float, float]:
        axial, u, v = self.local_coordinates(point)
        axial = _clamp(axial, 0.0, self.length_mm)
        if round_profile:
            center_u = self.width_mm / 2.0
            center_v = self.height_mm / 2.0
            radius = max((self.width_mm + self.height_mm) / 4.0, 0.0)
            angle = math.atan2(v - center_v, u - center_u)
            if angle < 0.0:
                angle += math.tau
            return axial, radius * angle
        return axial, _rectangular_perimeter_position(
            u,
            v,
            width=self.width_mm,
            height=self.height_mm,
        )


@dataclass(frozen=True, slots=True)
class TubeCrossSection:
    profile_type: str
    outer_width_mm: float
    outer_height_mm: float
    wall_thickness_mm: float
    perimeter_mm: float
    thickness_method: str
    thickness_confidence: str


@dataclass(frozen=True, slots=True)
class SurfaceFace:
    index: int
    bounds_min: Point3D
    bounds_max: Point3D
    is_outer_longitudinal: bool


@dataclass(frozen=True, slots=True)
class CutSegment3D:
    start: Point3D
    end: Point3D
    length_mm: float
    edge_type: str
    reason: str


@dataclass(frozen=True, slots=True)
class CutContour3D:
    component_id: int
    edge_type: str
    length_mm: float
    segments: tuple[CutSegment3D, ...]
    closed: bool
    centroid: Point3D


@dataclass(frozen=True, slots=True)
class UnfoldedPoint2D:
    x_mm: float
    y_mm: float


@dataclass(frozen=True, slots=True)
class UnfoldedSegment2D:
    start: UnfoldedPoint2D
    end: UnfoldedPoint2D
    source_length_mm: float


@dataclass(frozen=True, slots=True)
class UnfoldedContour2D:
    component_id: int
    edge_type: str
    segments: tuple[UnfoldedSegment2D, ...]


@dataclass(frozen=True, slots=True)
class ToolpathStep:
    sequence: int
    component_id: int
    edge_type: str
    approach_distance_mm: float


@dataclass(frozen=True, slots=True)
class ToolpathOrder:
    strategy: str
    steps: tuple[ToolpathStep, ...]


@dataclass(frozen=True, slots=True)
class TubeKernelModel:
    schema_version: str
    frame: TubeFrame
    cross_section: TubeCrossSection
    surfaces: tuple[SurfaceFace, ...]
    cut_contours: tuple[CutContour3D, ...]
    unfolded_contours: tuple[UnfoldedContour2D, ...]
    toolpath_order: ToolpathOrder
    reported_cut_length_mm: float
    contour_edge_length_mm: float
    reported_pierce_count: int
    warnings: tuple[str, ...] = ()


def infer_tube_frame(
    edge_records: Iterable[object],
    *,
    length_axis: str,
    global_bounds: Bounds,
    tolerance: float,
) -> TubeFrame:
    """Infer an oriented frame, with a deterministic global-axis fallback."""

    records = tuple(edge_records)
    oriented = _infer_oriented_frame(records, tolerance=tolerance)
    if oriented is not None:
        return oriented
    return _axis_aligned_frame(
        length_axis=length_axis,
        global_bounds=global_bounds,
    )


def infer_tube_frame_from_shape(
    shape: object,
    *,
    length_axis: str,
    global_bounds: Bounds,
    tolerance: float,
) -> TubeFrame:
    """Read only edge endpoints needed to establish the tube frame before classification."""

    try:
        from OCC.Core.TopAbs import TopAbs_EDGE

        from cad.edge_classifier import _edge_vertices, _iter_shapes, _vertex_point
    except Exception:
        return _axis_aligned_frame(length_axis=length_axis, global_bounds=global_bounds)

    probes: list[_FrameProbeEdge] = []
    for edge in _iter_shapes(shape, TopAbs_EDGE):
        first_vertex, last_vertex = _edge_vertices(edge)
        start = _vertex_point(first_vertex)
        end = _vertex_point(last_vertex)
        if start is not None and end is not None and _distance(start, end) > tolerance:
            probes.append(_FrameProbeEdge(start_point=start, end_point=end))
            continue
        probes.extend(_closed_edge_curve_probes(edge, tolerance=tolerance))

    return infer_tube_frame(
        probes,
        length_axis=length_axis,
        global_bounds=global_bounds,
        tolerance=tolerance,
    )


def build_tube_kernel_model(
    classification: object,
    *,
    profile_type: str,
    outer_width_mm: float,
    outer_height_mm: float,
    wall_thickness_mm: float,
    wall_thickness_method: str,
    wall_thickness_confidence: str,
    reported_cut_length_mm: float,
    reported_pierce_count: int,
) -> TubeKernelModel | None:
    global_bounds = getattr(classification, "global_bounds", None)
    if global_bounds is None:
        return None

    tolerance = max(float(getattr(classification, "tolerance", 0.01) or 0.01), 1e-6)
    length_axis = str(getattr(classification, "length_axis", "Z") or "Z")
    edge_records = tuple(getattr(classification, "edge_records", ()) or ())
    frame = getattr(classification, "tube_frame", None)
    if frame is None:
        frame = infer_tube_frame(
            edge_records,
            length_axis=length_axis,
            global_bounds=global_bounds,
            tolerance=tolerance,
        )
    width = frame.width_mm if frame.confidence == "high" else max(0.0, outer_width_mm)
    height = frame.height_mm if frame.confidence == "high" else max(0.0, outer_height_mm)
    round_profile = "круг" in profile_type.lower()
    perimeter = math.pi * ((width + height) / 2.0) if round_profile else 2.0 * (width + height)
    cross_section = TubeCrossSection(
        profile_type=profile_type,
        outer_width_mm=width,
        outer_height_mm=height,
        wall_thickness_mm=max(0.0, wall_thickness_mm),
        perimeter_mm=max(0.0, perimeter),
        thickness_method=wall_thickness_method,
        thickness_confidence=wall_thickness_confidence,
    )

    active_edges = tuple(getattr(classification, "calculated_cut_edges", ()) or ())
    if not active_edges:
        active_edges = tuple(getattr(classification, "cut_edges", ()) or ())
    active_edges = tuple(
        edge for edge in active_edges if getattr(edge, "edge_type", "") in {CUT_END, CUT_FEATURE}
    )
    contours = _build_cut_contours(active_edges, frame=frame, tolerance=tolerance)
    unfolded = _unfold_contours(contours, frame=frame, round_profile=round_profile)
    contour_length = sum(contour.length_mm for contour in contours)
    warnings: list[str] = []
    if abs(contour_length - reported_cut_length_mm) > max(tolerance, reported_cut_length_mm * 1e-4):
        warnings.append(
            "Сумма опорных 3D-ребер отличается от расчетной длины; "
            "сохранено подтвержденное значение анализатора."
        )
    if reported_pierce_count != len(contours):
        warnings.append(
            "Число собранных опорных контуров отличается от расчетного числа врезок; "
            "сохранено подтвержденное значение анализатора."
        )

    surfaces = tuple(
        SurfaceFace(
            index=index,
            bounds_min=tuple(face.bounds.mins),
            bounds_max=tuple(face.bounds.maxes),
            is_outer_longitudinal=bool(getattr(face, "is_outer_longitudinal", False)),
        )
        for index, face in enumerate(tuple(getattr(classification, "face_records", ()) or ()), start=1)
        if getattr(face, "bounds", None) is not None
    )
    return TubeKernelModel(
        schema_version="tube-kernel-v6",
        frame=frame,
        cross_section=cross_section,
        surfaces=surfaces,
        cut_contours=contours,
        unfolded_contours=unfolded,
        toolpath_order=_nearest_contour_order(contours, frame=frame),
        reported_cut_length_mm=max(0.0, reported_cut_length_mm),
        contour_edge_length_mm=contour_length,
        reported_pierce_count=max(0, int(reported_pierce_count)),
        warnings=tuple(warnings),
    )


def _infer_oriented_frame(
    edge_records: tuple[object, ...],
    *,
    tolerance: float,
) -> TubeFrame | None:
    vectors: list[tuple[float, Vector3D]] = []
    points: list[Point3D] = []
    for edge in edge_records:
        start = getattr(edge, "start_point", None)
        end = getattr(edge, "end_point", None)
        if start is None or end is None:
            continue
        start = tuple(float(value) for value in start)
        end = tuple(float(value) for value in end)
        points.extend((start, end))
        vector = tuple(end_value - start_value for start_value, end_value in zip(start, end, strict=True))
        chord = _length(vector)
        if chord > tolerance:
            vectors.append((chord, _normalize(vector)))
    if len(points) < 4 or len(vectors) < 2:
        return None

    _, axis = max(vectors, key=lambda item: item[0])
    perpendicular = tuple(item for item in vectors if abs(_dot(item[1], axis)) <= 0.10)
    if not perpendicular:
        return None
    _, candidate = max(perpendicular, key=lambda item: item[0])
    projection = _dot(candidate, axis)
    cross_u = _normalize(
        tuple(value - projection * axis_value for value, axis_value in zip(candidate, axis, strict=True))
    )
    cross_v = _normalize(_cross(axis, cross_u))
    basis = (axis, cross_u, cross_v)
    projected = tuple(
        (
            min(_dot(point, direction) for point in points),
            max(_dot(point, direction) for point in points),
        )
        for direction in basis
    )
    length = projected[0][1] - projected[0][0]
    width = projected[1][1] - projected[1][0]
    height = projected[2][1] - projected[2][0]
    if (
        min(width, height) <= tolerance
        or min(width, height) / max(width, height) < 0.50
        or length < max(width, height) * 2.0
    ):
        return None
    lows = tuple(item[0] for item in projected)
    origin = tuple(
        sum(lows[index] * basis[index][coordinate] for index in range(3))
        for coordinate in range(3)
    )
    return TubeFrame(
        origin=origin,
        axis=axis,
        cross_u=cross_u,
        cross_v=cross_v,
        length_mm=length,
        width_mm=width,
        height_mm=height,
        method="oriented-edge-frame",
        confidence="high",
    )


def _axis_aligned_frame(*, length_axis: str, global_bounds: Bounds) -> TubeFrame:
    axis_name = length_axis if length_axis in AXIS_INDEX else "Z"
    basis_by_axis: dict[str, tuple[Vector3D, Vector3D, Vector3D]] = {
        "X": ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
        "Y": ((0.0, 1.0, 0.0), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0)),
        "Z": ((0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
    }
    axis, cross_u, cross_v = basis_by_axis[axis_name]
    mins = global_bounds.mins
    maxes = global_bounds.maxes
    directions = (axis, cross_u, cross_v)
    projected = tuple(
        (
            min(_dot(point, direction) for point in _bounds_corners(mins, maxes)),
            max(_dot(point, direction) for point in _bounds_corners(mins, maxes)),
        )
        for direction in directions
    )
    lows = tuple(item[0] for item in projected)
    origin = tuple(
        sum(lows[index] * directions[index][coordinate] for index in range(3))
        for coordinate in range(3)
    )
    return TubeFrame(
        origin=origin,
        axis=axis,
        cross_u=cross_u,
        cross_v=cross_v,
        length_mm=projected[0][1] - projected[0][0],
        width_mm=projected[1][1] - projected[1][0],
        height_mm=projected[2][1] - projected[2][0],
        method=f"global-{axis_name.lower()}-axis-fallback",
        confidence="medium",
    )


def _build_cut_contours(
    edges: tuple[object, ...],
    *,
    frame: TubeFrame,
    tolerance: float,
) -> tuple[CutContour3D, ...]:
    if not edges:
        return ()
    groups: dict[int, list[object]] = {}
    next_id = max((int(getattr(edge, "cut_component_id", 0) or 0) for edge in edges), default=0) + 1
    unassigned: list[object] = []
    for edge in edges:
        component_id = int(getattr(edge, "cut_component_id", 0) or 0)
        if component_id > 0:
            groups.setdefault(component_id, []).append(edge)
        else:
            unassigned.append(edge)

    for component in _connected_edge_groups(tuple(unassigned), frame=frame, tolerance=tolerance):
        groups[next_id] = list(component)
        next_id += 1

    contours: list[CutContour3D] = []
    for component_id, component_edges in sorted(groups.items()):
        segments = _ordered_segments(tuple(component_edges), frame=frame, tolerance=tolerance)
        if not segments:
            continue
        points = tuple(point for segment in segments for point in (segment.start, segment.end))
        edge_type = CUT_FEATURE if any(segment.edge_type == CUT_FEATURE for segment in segments) else CUT_END
        contours.append(
            CutContour3D(
                component_id=component_id,
                edge_type=edge_type,
                length_mm=sum(segment.length_mm for segment in segments),
                segments=segments,
                closed=_points_close(segments[0].start, segments[-1].end, tolerance=tolerance),
                centroid=tuple(sum(point[index] for point in points) / len(points) for index in range(3)),
            )
        )
    return tuple(contours)


def _connected_edge_groups(
    edges: tuple[object, ...],
    *,
    frame: TubeFrame,
    tolerance: float,
) -> tuple[tuple[object, ...], ...]:
    remaining = list(edges)
    result: list[tuple[object, ...]] = []
    connection_tolerance = max(tolerance * 5.0, 0.05)
    while remaining:
        component = [remaining.pop(0)]
        changed = True
        while changed:
            changed = False
            for candidate in tuple(remaining):
                if any(
                    _edge_touch(candidate, existing, tolerance=connection_tolerance)
                    or _same_end_band(candidate, existing, frame=frame, tolerance=connection_tolerance)
                    for existing in component
                ):
                    component.append(candidate)
                    remaining.remove(candidate)
                    changed = True
        result.append(tuple(component))
    return tuple(result)


def _ordered_segments(
    edges: tuple[object, ...],
    *,
    frame: TubeFrame,
    tolerance: float,
) -> tuple[CutSegment3D, ...]:
    raw: list[CutSegment3D] = []
    for edge in edges:
        start = getattr(edge, "start_point", None)
        end = getattr(edge, "end_point", None)
        if start is None or end is None:
            bounds = getattr(edge, "bounds", None)
            if bounds is None:
                continue
            start = bounds.mins
            end = bounds.maxes
        raw.append(
            CutSegment3D(
                start=tuple(float(value) for value in start),
                end=tuple(float(value) for value in end),
                length_mm=max(0.0, float(getattr(edge, "length_mm", 0.0) or 0.0)),
                edge_type=str(getattr(edge, "edge_type", "") or CUT_FEATURE),
                reason=str(getattr(edge, "reason", "") or "v6 contour"),
            )
        )
    if not raw:
        return ()

    raw.sort(key=lambda segment: (*frame.local_coordinates(segment.start), *frame.local_coordinates(segment.end)))
    ordered = [raw.pop(0)]
    connection_tolerance = max(tolerance * 5.0, 0.05)
    while raw:
        endpoint = ordered[-1].end
        best_index, reverse = min(
            (
                (index, False, _distance(endpoint, segment.start))
                if _distance(endpoint, segment.start) <= _distance(endpoint, segment.end)
                else (index, True, _distance(endpoint, segment.end))
                for index, segment in enumerate(raw)
            ),
            key=lambda item: (item[2], item[0]),
        )[:2]
        segment = raw.pop(best_index)
        if reverse:
            segment = CutSegment3D(
                start=segment.end,
                end=segment.start,
                length_mm=segment.length_mm,
                edge_type=segment.edge_type,
                reason=segment.reason,
            )
        if _distance(endpoint, segment.start) > connection_tolerance:
            # Disconnected fragments stay in the same analyzer component, but retain a deterministic order.
            pass
        ordered.append(segment)
    return tuple(ordered)


def _unfold_contours(
    contours: tuple[CutContour3D, ...],
    *,
    frame: TubeFrame,
    round_profile: bool,
) -> tuple[UnfoldedContour2D, ...]:
    return tuple(
        UnfoldedContour2D(
            component_id=contour.component_id,
            edge_type=contour.edge_type,
            segments=tuple(
                UnfoldedSegment2D(
                    start=UnfoldedPoint2D(*frame.unfold_point(segment.start, round_profile=round_profile)),
                    end=UnfoldedPoint2D(*frame.unfold_point(segment.end, round_profile=round_profile)),
                    source_length_mm=segment.length_mm,
                )
                for segment in contour.segments
            ),
        )
        for contour in contours
    )


def _nearest_contour_order(
    contours: tuple[CutContour3D, ...],
    *,
    frame: TubeFrame,
) -> ToolpathOrder:
    remaining = list(contours)
    current = frame.origin
    steps: list[ToolpathStep] = []
    while remaining:
        contour = min(
            remaining,
            key=lambda item: (_distance(current, item.centroid), item.component_id),
        )
        approach = _distance(current, contour.centroid)
        steps.append(
            ToolpathStep(
                sequence=len(steps) + 1,
                component_id=contour.component_id,
                edge_type=contour.edge_type,
                approach_distance_mm=approach,
            )
        )
        current = contour.centroid
        remaining.remove(contour)
    return ToolpathOrder(strategy="nearest-contour-diagnostic", steps=tuple(steps))


def _same_end_band(first: object, second: object, *, frame: TubeFrame, tolerance: float) -> bool:
    if getattr(first, "edge_type", "") != CUT_END or getattr(second, "edge_type", "") != CUT_END:
        return False
    first_band = _edge_end_band(first, frame=frame, tolerance=tolerance)
    second_band = _edge_end_band(second, frame=frame, tolerance=tolerance)
    return first_band is not None and first_band == second_band


def _edge_end_band(edge: object, *, frame: TubeFrame, tolerance: float) -> str | None:
    points = tuple(
        point
        for point in (getattr(edge, "start_point", None), getattr(edge, "end_point", None))
        if point is not None
    )
    if not points:
        return None
    axial = tuple(frame.local_coordinates(point)[0] for point in points)
    band = max(tolerance * 4.0, 0.05)
    if max(abs(value) for value in axial) <= band:
        return "min"
    if max(abs(value - frame.length_mm) for value in axial) <= band:
        return "max"
    return None


def _edge_touch(first: object, second: object, *, tolerance: float) -> bool:
    first_points = (getattr(first, "start_point", None), getattr(first, "end_point", None))
    second_points = (getattr(second, "start_point", None), getattr(second, "end_point", None))
    return any(
        left is not None and right is not None and _points_close(left, right, tolerance=tolerance)
        for left in first_points
        for right in second_points
    )


def _rectangular_perimeter_position(u: float, v: float, *, width: float, height: float) -> float:
    u = _clamp(u, 0.0, width)
    v = _clamp(v, 0.0, height)
    side = min(
        (
            ("bottom", abs(v)),
            ("right", abs(u - width)),
            ("top", abs(v - height)),
            ("left", abs(u)),
        ),
        key=lambda item: item[1],
    )[0]
    if side == "bottom":
        return u
    if side == "right":
        return width + v
    if side == "top":
        return width + height + (width - u)
    return (2.0 * width) + height + (height - v)


def _bounds_corners(mins: Point3D, maxes: Point3D) -> tuple[Point3D, ...]:
    return tuple(
        (x, y, z)
        for x in (mins[0], maxes[0])
        for y in (mins[1], maxes[1])
        for z in (mins[2], maxes[2])
    )


def _closed_edge_curve_probes(
    edge: object,
    *,
    tolerance: float,
) -> tuple[_FrameProbeEdge, ...]:
    try:
        from OCC.Core.BRepAdaptor import BRepAdaptor_Curve

        adaptor = BRepAdaptor_Curve(edge)
        first = float(adaptor.FirstParameter())
        last = float(adaptor.LastParameter())
        if not math.isfinite(first) or not math.isfinite(last) or last <= first:
            return ()
        points = tuple(
            adaptor.Value(first + (last - first) * index / 8.0)
            for index in range(9)
        )
        coordinates = tuple(
            (float(point.X()), float(point.Y()), float(point.Z()))
            for point in points
        )
        return tuple(
            _FrameProbeEdge(start_point=start, end_point=end)
            for start, end in zip(coordinates, coordinates[1:], strict=True)
            if _distance(start, end) > tolerance
        )
    except Exception:
        return ()


def _dot(first: Point3D, second: Point3D) -> float:
    return sum(left * right for left, right in zip(first, second, strict=True))


def _cross(first: Vector3D, second: Vector3D) -> Vector3D:
    return (
        first[1] * second[2] - first[2] * second[1],
        first[2] * second[0] - first[0] * second[2],
        first[0] * second[1] - first[1] * second[0],
    )


def _length(vector: Vector3D) -> float:
    return math.sqrt(_dot(vector, vector))


def _normalize(vector: Vector3D) -> Vector3D:
    length = _length(vector)
    if length <= 1e-12:
        return (0.0, 0.0, 0.0)
    return tuple(value / length for value in vector)


def _distance(first: Point3D, second: Point3D) -> float:
    return _length(tuple(left - right for left, right in zip(first, second, strict=True)))


def _points_close(first: Point3D, second: Point3D, *, tolerance: float) -> bool:
    return _distance(first, second) <= tolerance


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))
