from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from cad.shape_summary import ShapeSummary, _add_shape_to_box


AXIS_INDEX = {"X": 0, "Y": 1, "Z": 2}


@dataclass(slots=True)
class Bounds:
    xmin: float
    ymin: float
    zmin: float
    xmax: float
    ymax: float
    zmax: float

    @property
    def mins(self) -> tuple[float, float, float]:
        return (self.xmin, self.ymin, self.zmin)

    @property
    def maxes(self) -> tuple[float, float, float]:
        return (self.xmax, self.ymax, self.zmax)

    @property
    def sizes(self) -> tuple[float, float, float]:
        return (
            max(0.0, self.xmax - self.xmin),
            max(0.0, self.ymax - self.ymin),
            max(0.0, self.zmax - self.zmin),
        )


@dataclass(slots=True)
class FaceRecord:
    face: object
    bounds: Bounds
    is_outer_longitudinal: bool


@dataclass(slots=True)
class WireRecord:
    wire: object
    face: FaceRecord
    edges: tuple[object, ...]
    length_mm: float
    bounds: Bounds | None = None
    is_outer_wire: bool = False


@dataclass(slots=True)
class EdgeRecord:
    edge: object
    length_mm: float
    bounds: Bounds | None = None
    faces: list[FaceRecord] = field(default_factory=list)
    start_vertex: object | None = None
    end_vertex: object | None = None
    start_point: tuple[float, float, float] | None = None
    end_point: tuple[float, float, float] | None = None
    wire_roles: set[str] = field(default_factory=set)
    reason: str = ""

    @property
    def adjacent_face_count(self) -> int:
        return len(self.faces)

    @property
    def outer_face_count(self) -> int:
        return sum(1 for face in self.faces if face.is_outer_longitudinal)

    @property
    def non_outer_face_count(self) -> int:
        return self.adjacent_face_count - self.outer_face_count


@dataclass(slots=True)
class ThicknessFaceRecord:
    face: FaceRecord
    area_mm2: float
    thickness_mm: float
    cut_length_mm: float
    edges: tuple[EdgeRecord, ...]
    reason: str = ""


@dataclass(slots=True)
class EdgeClassificationResult:
    cut_edges: tuple[EdgeRecord, ...]
    all_edge_count: int
    outer_face_count: int
    thickness_faces: tuple[ThicknessFaceRecord, ...] = ()
    wall_thickness_mm: float = 0.0
    cut_length_override_mm: float | None = None
    pierce_count_override: int | None = None
    warnings: tuple[str, ...] = ()

    @property
    def cut_edge_count(self) -> int:
        return len(self.cut_edges)

    @property
    def cut_length_mm(self) -> float:
        if self.cut_length_override_mm is not None:
            return self.cut_length_override_mm
        return sum(edge.length_mm for edge in self.cut_edges)

    @property
    def thickness_face_count(self) -> int:
        return len(self.thickness_faces)

    @property
    def pierce_count(self) -> int | None:
        return self.pierce_count_override


class EdgeClassifier:
    """Classifies likely laser cut contours on the outer tube surface."""

    def classify(
        self,
        shape: object,
        *,
        summary: ShapeSummary,
        length_axis: str,
    ) -> EdgeClassificationResult:
        return classify_cut_edges(shape, summary=summary, length_axis=length_axis)


def classify_cut_edges(
    shape: object | None,
    *,
    summary: ShapeSummary,
    length_axis: str,
) -> EdgeClassificationResult:
    if shape is None:
        return EdgeClassificationResult(
            cut_edges=(),
            all_edge_count=0,
            outer_face_count=0,
            warnings=("Нет формы OpenCascade для классификации ребер.",),
        )

    warnings: list[str] = []
    axis = length_axis if length_axis in AXIS_INDEX else "Z"
    length_mm = _summary_axis_size(summary, axis)
    global_bounds = _shape_bounds(shape)
    tolerance = _tolerance_from_summary(summary)

    face_records = _collect_face_records(
        shape,
        axis=axis,
        length_mm=length_mm,
        global_bounds=global_bounds,
        tolerance=tolerance,
        warnings=warnings,
    )
    edge_records = _collect_edge_records(
        face_records,
        axis=axis,
        length_mm=length_mm,
        tolerance=tolerance,
        warnings=warnings,
    )
    thickness_faces = _collect_thickness_face_records(
        face_records,
        edge_records,
        axis=axis,
        length_mm=length_mm,
        tolerance=tolerance,
        warnings=warnings,
    )

    outer_face_count = sum(1 for face in face_records if face.is_outer_longitudinal)
    if outer_face_count == 0:
        warnings.append(
            "Наружные продольные поверхности не найдены; использован fallback по открытым ребрам."
        )

    cut_edges = tuple(
        edge
        for edge in edge_records
        if _is_cut_edge_candidate(
            edge,
            axis=axis,
            length_mm=length_mm,
            has_outer_faces=outer_face_count > 0,
            tolerance=tolerance,
        )
    )

    if not cut_edges and not thickness_faces:
        warnings.append("Кандидаты реза не найдены. Нужна проверка через DEV-скрипт.")

    cut_length_override_mm = None
    pierce_count_override = None
    wall_thickness_mm = _median(
        tuple(face.thickness_mm for face in thickness_faces if face.thickness_mm > tolerance)
    )
    if thickness_faces:
        if wall_thickness_mm > tolerance:
            for face in thickness_faces:
                face.thickness_mm = wall_thickness_mm
                face.cut_length_mm = face.area_mm2 / wall_thickness_mm
        cut_length_override_mm = sum(face.cut_length_mm for face in thickness_faces)
        pierce_count_override = _count_thickness_face_components(
            thickness_faces,
            tolerance=tolerance,
        )
        warnings.append(
            "Длина реза рассчитана по граням в толщине изделия; это экспериментальный метод v0.4.3."
        )

    return EdgeClassificationResult(
        cut_edges=cut_edges,
        all_edge_count=len(edge_records),
        outer_face_count=outer_face_count,
        thickness_faces=thickness_faces,
        wall_thickness_mm=wall_thickness_mm,
        cut_length_override_mm=cut_length_override_mm,
        pierce_count_override=pierce_count_override,
        warnings=tuple(warnings),
    )


def _collect_face_records(
    shape: object,
    *,
    axis: str,
    length_mm: float,
    global_bounds: Bounds,
    tolerance: float,
    warnings: list[str],
) -> list[FaceRecord]:
    from OCC.Core.TopAbs import TopAbs_FACE

    records: list[FaceRecord] = []
    for face in _iter_shapes(shape, TopAbs_FACE):
        try:
            bounds = _shape_bounds(face)
        except Exception as exc:
            warnings.append(f"Не удалось получить bbox грани: {exc}")
            continue
        records.append(
            FaceRecord(
                face=face,
                bounds=bounds,
                is_outer_longitudinal=_is_outer_longitudinal_face(
                    bounds,
                    axis=axis,
                    length_mm=length_mm,
                    global_bounds=global_bounds,
                    tolerance=tolerance,
                ),
            )
        )
    return records


def _collect_edge_records(
    face_records: Iterable[FaceRecord],
    *,
    axis: str,
    length_mm: float,
    tolerance: float,
    warnings: list[str],
) -> list[EdgeRecord]:
    from OCC.Core.TopAbs import TopAbs_EDGE

    records: list[EdgeRecord] = []
    for face_record in face_records:
        wire_records = _collect_wire_records(face_record, warnings=warnings)
        if wire_records:
            outer_wire = _choose_outer_wire(wire_records)
            for wire_record in wire_records:
                wire_record.is_outer_wire = wire_record is outer_wire
                for edge in wire_record.edges:
                    record = _get_or_create_edge_record(records, edge, warnings)
                    _append_unique_face(record, face_record)
                    if not wire_record.is_outer_wire:
                        record.wire_roles.add("inner_wire")
                    elif _is_outer_wire_cut_segment(
                        record,
                        face_record=face_record,
                        axis=axis,
                        length_mm=length_mm,
                        tolerance=tolerance,
                    ):
                        record.wire_roles.add("outer_wire_cut")
            continue

        for edge in _iter_shapes(face_record.face, TopAbs_EDGE):
            record = _get_or_create_edge_record(records, edge, warnings)
            _append_unique_face(record, face_record)
    return records


def _collect_thickness_face_records(
    face_records: Iterable[FaceRecord],
    edge_records: Iterable[EdgeRecord],
    *,
    axis: str,
    length_mm: float,
    tolerance: float,
    warnings: list[str],
) -> tuple[ThicknessFaceRecord, ...]:
    records: list[ThicknessFaceRecord] = []
    for face_record in face_records:
        face_edges = tuple(
            edge for edge in edge_records if _edge_has_face(edge, face_record)
        )
        if not _is_thickness_face_candidate(
            face_record,
            face_edges,
            axis=axis,
            length_mm=length_mm,
            tolerance=tolerance,
        ):
            continue

        area_mm2 = _face_area(face_record.face, warnings)
        if area_mm2 <= tolerance:
            continue

        edge_lengths = tuple(
            edge.length_mm for edge in face_edges if edge.length_mm > tolerance
        )
        thickness_mm = _estimate_face_thickness(
            face_record.bounds,
            edge_lengths,
            tolerance=tolerance,
        )
        if thickness_mm <= tolerance:
            continue

        cut_length_mm = area_mm2 / thickness_mm
        if cut_length_mm <= tolerance:
            continue

        records.append(
            ThicknessFaceRecord(
                face=face_record,
                area_mm2=area_mm2,
                thickness_mm=thickness_mm,
                cut_length_mm=cut_length_mm,
                edges=face_edges,
                reason="touches outer face through material thickness",
            )
        )
    return tuple(records)


def _is_thickness_face_candidate(
    face_record: FaceRecord,
    face_edges: tuple[EdgeRecord, ...],
    *,
    axis: str,
    length_mm: float,
    tolerance: float,
) -> bool:
    if face_record.is_outer_longitudinal:
        return False
    if not face_edges:
        return False
    if _looks_like_longitudinal_inner_wall(
        face_record.bounds,
        axis=axis,
        length_mm=length_mm,
        tolerance=tolerance,
    ):
        return False
    return any(_edge_touches_outer_face(edge, face_record) for edge in face_edges)


def _edge_has_face(edge: EdgeRecord, face_record: FaceRecord) -> bool:
    return any(_is_same_shape(face.face, face_record.face) for face in edge.faces)


def _edge_touches_outer_face(edge: EdgeRecord, face_record: FaceRecord) -> bool:
    return any(
        not _is_same_shape(face.face, face_record.face) and face.is_outer_longitudinal
        for face in edge.faces
    )


def _looks_like_longitudinal_inner_wall(
    bounds: Bounds,
    *,
    axis: str,
    length_mm: float,
    tolerance: float,
) -> bool:
    if length_mm <= 0:
        return False
    axis_size = bounds.sizes[AXIS_INDEX[axis]]
    return axis_size >= max(length_mm * 0.65, tolerance)


def _estimate_face_thickness(
    bounds: Bounds,
    edge_lengths: tuple[float, ...],
    *,
    tolerance: float,
) -> float:
    lengths = sorted(length for length in edge_lengths if length > tolerance)
    if lengths:
        index = min(len(lengths) - 1, max(0, len(lengths) // 4))
        return lengths[index]

    non_zero_sizes = sorted(size for size in bounds.sizes if size > tolerance)
    if non_zero_sizes:
        return non_zero_sizes[0]
    return 0.0


def _count_thickness_face_components(
    records: tuple[ThicknessFaceRecord, ...],
    *,
    tolerance: float,
) -> int:
    if not records:
        return 0

    parent = list(range(len(records)))

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

    for left_index, left in enumerate(records):
        for right_index in range(left_index + 1, len(records)):
            if _thickness_faces_touch(left, records[right_index], tolerance=tolerance):
                union(left_index, right_index)

    return len({find(index) for index in range(len(records))})


def _thickness_faces_touch(
    first: ThicknessFaceRecord,
    second: ThicknessFaceRecord,
    *,
    tolerance: float,
) -> bool:
    for first_edge in first.edges:
        for second_edge in second.edges:
            if _is_same_shape(first_edge.edge, second_edge.edge):
                return True
            if _edge_endpoints_touch(first_edge, second_edge, tolerance=tolerance):
                return True
    return False


def _edge_endpoints_touch(
    first: EdgeRecord,
    second: EdgeRecord,
    *,
    tolerance: float,
) -> bool:
    first_points = (first.start_point, first.end_point)
    second_points = (second.start_point, second.end_point)
    return any(
        first_point is not None
        and second_point is not None
        and _points_are_close(first_point, second_point, tolerance=tolerance)
        for first_point in first_points
        for second_point in second_points
    )


def _collect_wire_records(
    face_record: FaceRecord,
    *,
    warnings: list[str],
) -> list[WireRecord]:
    try:
        from OCC.Core.TopAbs import TopAbs_EDGE, TopAbs_WIRE
    except Exception as exc:
        warnings.append(f"Не удалось импортировать TopAbs_WIRE: {exc}")
        return []

    records: list[WireRecord] = []
    for wire in _iter_shapes(face_record.face, TopAbs_WIRE):
        edges: list[object] = []
        length_mm = 0.0
        for edge in _iter_shapes(wire, TopAbs_EDGE):
            if any(_is_same_shape(edge, existing) for existing in edges):
                continue
            edges.append(edge)
            length_mm += _edge_length(edge, warnings)
        if edges:
            records.append(
                WireRecord(
                    wire=wire,
                    face=face_record,
                    edges=tuple(edges),
                    length_mm=length_mm,
                    bounds=_safe_bounds(wire),
                )
            )
    return records


def _choose_outer_wire(wire_records: list[WireRecord]) -> WireRecord:
    return max(wire_records, key=lambda wire: wire.length_mm)


def _get_or_create_edge_record(
    records: list[EdgeRecord],
    edge: object,
    warnings: list[str],
) -> EdgeRecord:
    record = _find_same_edge(records, edge)
    if record is not None:
        return record

    record = EdgeRecord(
        edge=edge,
        length_mm=_edge_length(edge, warnings),
        bounds=_safe_bounds(edge),
    )
    record.start_vertex, record.end_vertex = _edge_vertices(edge)
    record.start_point = _vertex_point(record.start_vertex)
    record.end_point = _vertex_point(record.end_vertex)
    records.append(record)
    return record


def _append_unique_face(record: EdgeRecord, face_record: FaceRecord) -> None:
    if any(_is_same_shape(face_record.face, existing.face) for existing in record.faces):
        return
    record.faces.append(face_record)


def _is_cut_edge_candidate(
    edge: EdgeRecord,
    *,
    axis: str,
    length_mm: float,
    has_outer_faces: bool,
    tolerance: float,
) -> bool:
    if edge.length_mm <= tolerance:
        return False

    if has_outer_faces:
        if edge.outer_face_count <= 0:
            return False
        if _looks_like_longitudinal_seam(edge, axis=axis, length_mm=length_mm):
            return False
        if edge.non_outer_face_count > 0:
            edge.reason = "outer/cut face boundary"
            return True
        if "inner_wire" in edge.wire_roles:
            edge.reason = "inner face wire"
            return True
        if "outer_wire_cut" in edge.wire_roles:
            edge.reason = "outer wire cut segment"
            return True
        return False

    if edge.adjacent_face_count <= 1 and not _looks_like_longitudinal_seam(
        edge,
        axis=axis,
        length_mm=length_mm,
    ):
        edge.reason = "open boundary fallback"
        return True
    return False


def _is_outer_wire_cut_segment(
    edge: EdgeRecord,
    *,
    face_record: FaceRecord,
    axis: str,
    length_mm: float,
    tolerance: float,
) -> bool:
    if edge.bounds is None:
        return False
    if _looks_like_longitudinal_seam(edge, axis=axis, length_mm=length_mm):
        return False
    return not _looks_like_natural_face_frame_edge(
        edge,
        face_record=face_record,
        axis=axis,
        tolerance=tolerance,
    )


def _looks_like_natural_face_frame_edge(
    edge: EdgeRecord,
    *,
    face_record: FaceRecord,
    axis: str,
    tolerance: float,
) -> bool:
    if edge.bounds is None:
        return False
    axis_index = AXIS_INDEX[axis]
    face_sizes = face_record.bounds.sizes
    edge_sizes = edge.bounds.sizes
    cross_indexes = [index for index in range(3) if index != axis_index]

    at_length_end = (
        abs(edge.bounds.mins[axis_index] - face_record.bounds.mins[axis_index]) <= tolerance
        or abs(edge.bounds.maxes[axis_index] - face_record.bounds.maxes[axis_index]) <= tolerance
    )
    if at_length_end and any(
        edge_sizes[index] >= max(face_sizes[index] * 0.75, tolerance)
        for index in cross_indexes
    ):
        return True

    return any(
        (
            abs(edge.bounds.mins[index] - face_record.bounds.mins[index]) <= tolerance
            or abs(edge.bounds.maxes[index] - face_record.bounds.maxes[index]) <= tolerance
        )
        and edge_sizes[axis_index] >= max(face_sizes[axis_index] * 0.75, tolerance)
        for index in cross_indexes
    )


def _is_outer_longitudinal_face(
    bounds: Bounds,
    *,
    axis: str,
    length_mm: float,
    global_bounds: Bounds,
    tolerance: float,
) -> bool:
    axis_index = AXIS_INDEX[axis]
    spans = bounds.sizes
    if length_mm > 0 and spans[axis_index] < max(length_mm * 0.45, tolerance):
        return False

    cross_indexes = [index for index in range(3) if index != axis_index]
    return any(
        abs(bounds.mins[index] - global_bounds.mins[index]) <= tolerance
        or abs(bounds.maxes[index] - global_bounds.maxes[index]) <= tolerance
        for index in cross_indexes
    )


def _looks_like_longitudinal_seam(
    edge: EdgeRecord,
    *,
    axis: str,
    length_mm: float,
) -> bool:
    if edge.bounds is None or length_mm <= 0:
        return False
    axis_size = edge.bounds.sizes[AXIS_INDEX[axis]]
    return axis_size >= length_mm * 0.60


def _iter_shapes(shape: object, shape_type: int):
    from OCC.Core.TopExp import TopExp_Explorer

    explorer = TopExp_Explorer(shape, shape_type)
    while explorer.More():
        yield explorer.Current()
        explorer.Next()


def _shape_bounds(shape: object) -> Bounds:
    from OCC.Core.Bnd import Bnd_Box

    box = Bnd_Box()
    _add_shape_to_box(shape, box)
    return Bounds(*box.Get())


def _safe_bounds(shape: object) -> Bounds | None:
    try:
        return _shape_bounds(shape)
    except Exception:
        return None


def _edge_length(edge: object, warnings: list[str]) -> float:
    try:
        from OCC.Core.GProp import GProp_GProps

        props = GProp_GProps()
        _linear_properties(edge, props)
        return float(props.Mass())
    except Exception as exc:
        warnings.append(f"Не удалось измерить длину ребра: {exc}")
        return 0.0


def _face_area(face: object, warnings: list[str]) -> float:
    try:
        from OCC.Core.GProp import GProp_GProps

        props = GProp_GProps()
        _surface_properties(face, props)
        return float(props.Mass())
    except Exception as exc:
        warnings.append(f"Не удалось измерить площадь грани: {exc}")
        return 0.0


def _linear_properties(edge: object, props: object) -> None:
    import OCC.Core.BRepGProp as brep_gprop

    brepgprop = getattr(brep_gprop, "brepgprop", None)
    if brepgprop is not None:
        for method_name in ("LinearProperties", "LinearProperties_s"):
            method = getattr(brepgprop, method_name, None)
            if method is not None:
                method(edge, props)
                return

    method = getattr(brep_gprop, "brepgprop_LinearProperties", None)
    if method is not None:
        method(edge, props)
        return

    raise AttributeError("BRepGProp LinearProperties не найден.")


def _surface_properties(face: object, props: object) -> None:
    import OCC.Core.BRepGProp as brep_gprop

    brepgprop = getattr(brep_gprop, "brepgprop", None)
    if brepgprop is not None:
        for method_name in ("SurfaceProperties", "SurfaceProperties_s"):
            method = getattr(brepgprop, method_name, None)
            if method is not None:
                method(face, props)
                return

    method = getattr(brep_gprop, "brepgprop_SurfaceProperties", None)
    if method is not None:
        method(face, props)
        return

    raise AttributeError("BRepGProp SurfaceProperties не найден.")


def _edge_vertices(edge: object) -> tuple[object | None, object | None]:
    try:
        import OCC.Core.TopExp as top_exp

        for owner in (getattr(top_exp, "topexp", None), top_exp):
            if owner is None:
                continue
            first_vertex = getattr(owner, "FirstVertex", None)
            last_vertex = getattr(owner, "LastVertex", None)
            if first_vertex is not None and last_vertex is not None:
                return first_vertex(edge), last_vertex(edge)
    except Exception:
        pass
    return None, None


def _vertex_point(vertex: object | None) -> tuple[float, float, float] | None:
    if vertex is None:
        return None
    try:
        import OCC.Core.BRep as brep

        methods = []
        brep_tool = getattr(brep, "BRep_Tool", None)
        if brep_tool is not None:
            methods.extend(
                method
                for method in (
                    getattr(brep_tool, "Pnt", None),
                    getattr(brep_tool, "Pnt_s", None),
                )
                if method is not None
            )
        breptool = getattr(brep, "breptool", None)
        if breptool is not None:
            methods.extend(
                method
                for method in (
                    getattr(breptool, "Pnt", None),
                    getattr(breptool, "Pnt_s", None),
                )
                if method is not None
            )
        breptool_pnt = getattr(brep, "breptool_Pnt", None)
        if breptool_pnt is not None:
            methods.append(breptool_pnt)

        for method in methods:
            point = method(vertex)
            return (float(point.X()), float(point.Y()), float(point.Z()))
    except Exception:
        return None
    return None


def _find_same_edge(records: list[EdgeRecord], edge: object) -> EdgeRecord | None:
    for record in records:
        if _is_same_shape(record.edge, edge):
            return record
    return None


def _is_same_shape(first: object, second: object) -> bool:
    try:
        return bool(first.IsSame(second))
    except Exception:
        return first is second


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


def _summary_axis_size(summary: ShapeSummary, axis: str) -> float:
    return {
        "X": float(summary.size_x_mm),
        "Y": float(summary.size_y_mm),
        "Z": float(summary.size_z_mm),
    }[axis]


def _tolerance_from_summary(summary: ShapeSummary) -> float:
    largest = max(float(summary.size_x_mm), float(summary.size_y_mm), float(summary.size_z_mm), 1.0)
    return max(0.01, largest * 0.001)


def _median(values: tuple[float, ...]) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    middle = len(sorted_values) // 2
    if len(sorted_values) % 2:
        return sorted_values[middle]
    return (sorted_values[middle - 1] + sorted_values[middle]) / 2.0
