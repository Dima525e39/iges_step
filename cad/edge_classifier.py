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
class EdgeRecord:
    edge: object
    length_mm: float
    bounds: Bounds | None = None
    faces: list[FaceRecord] = field(default_factory=list)
    start_vertex: object | None = None
    end_vertex: object | None = None
    reason: str = ""

    @property
    def adjacent_face_count(self) -> int:
        return len(self.faces)

    @property
    def outer_face_count(self) -> int:
        return sum(1 for face in self.faces if face.is_outer_longitudinal)


@dataclass(slots=True)
class EdgeClassificationResult:
    cut_edges: tuple[EdgeRecord, ...]
    all_edge_count: int
    outer_face_count: int
    warnings: tuple[str, ...] = ()

    @property
    def cut_edge_count(self) -> int:
        return len(self.cut_edges)

    @property
    def cut_length_mm(self) -> float:
        return sum(edge.length_mm for edge in self.cut_edges)


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
    edge_records = _collect_edge_records(face_records, warnings=warnings)

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

    if not cut_edges:
        warnings.append("Кандидаты реза не найдены. Нужна проверка через DEV-скрипт.")

    return EdgeClassificationResult(
        cut_edges=cut_edges,
        all_edge_count=len(edge_records),
        outer_face_count=outer_face_count,
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
    warnings: list[str],
) -> list[EdgeRecord]:
    from OCC.Core.TopAbs import TopAbs_EDGE

    records: list[EdgeRecord] = []
    for face_record in face_records:
        for edge in _iter_shapes(face_record.face, TopAbs_EDGE):
            record = _find_same_edge(records, edge)
            if record is None:
                record = EdgeRecord(
                    edge=edge,
                    length_mm=_edge_length(edge, warnings),
                    bounds=_safe_bounds(edge),
                )
                record.start_vertex, record.end_vertex = _edge_vertices(edge)
                records.append(record)
            record.faces.append(face_record)
    return records


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
        if edge.outer_face_count != 1:
            return False
        if _looks_like_longitudinal_seam(edge, axis=axis, length_mm=length_mm):
            return False
        edge.reason = "outer face boundary"
        return True

    if edge.adjacent_face_count <= 1 and not _looks_like_longitudinal_seam(
        edge,
        axis=axis,
        length_mm=length_mm,
    ):
        edge.reason = "open boundary fallback"
        return True
    return False


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


def _summary_axis_size(summary: ShapeSummary, axis: str) -> float:
    return {
        "X": float(summary.size_x_mm),
        "Y": float(summary.size_y_mm),
        "Z": float(summary.size_z_mm),
    }[axis]


def _tolerance_from_summary(summary: ShapeSummary) -> float:
    largest = max(float(summary.size_x_mm), float(summary.size_y_mm), float(summary.size_z_mm), 1.0)
    return max(0.01, largest * 0.001)
