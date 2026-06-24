from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from cad.shape_summary import ShapeSummary, _add_shape_to_box


AXIS_INDEX = {"X": 0, "Y": 1, "Z": 2}
CUT_FEATURE = "CUT_FEATURE"
CUT_END = "CUT_END"
AUXILIARY_UNFOLD = "AUXILIARY_UNFOLD"
IGNORED_LONGITUDINAL = "IGNORED_LONGITUDINAL"
IGNORED_PROFILE = "IGNORED_PROFILE"
IGNORED_PLANE_RADIUS = "IGNORED_PLANE_RADIUS"
UNCERTAIN = "UNCERTAIN"
CALCULATED_CUT_TYPES = {CUT_FEATURE, CUT_END}


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
    edge_type: str = ""
    cut_component_id: int = 0

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
class ThicknessEstimate:
    thickness_mm: float = 0.0
    method: str = "не определена"
    confidence: str = "низкая"
    warnings: tuple[str, ...] = ()


@dataclass(slots=True)
class CutFaceAnalysis:
    cut_edges: tuple[EdgeRecord, ...] = ()
    cut_faces: tuple[ThicknessFaceRecord, ...] = ()
    pierce_count: int = 0


@dataclass(slots=True)
class RoundTubeLoopAnalysis:
    cut_edges: tuple[EdgeRecord, ...] = ()
    pierce_count: int = 0
    selected_face: FaceRecord | None = None
    outer_radius_mm: float = 0.0


@dataclass(slots=True)
class EdgeGroups:
    calculated_cut_edges: tuple[EdgeRecord, ...] = ()
    auxiliary_unfold_edges: tuple[EdgeRecord, ...] = ()
    ignored_longitudinal_edges: tuple[EdgeRecord, ...] = ()
    ignored_profile_edges: tuple[EdgeRecord, ...] = ()
    ignored_plane_radius_edges: tuple[EdgeRecord, ...] = ()
    uncertain_edges: tuple[EdgeRecord, ...] = ()


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
    calculated_cut_edges: tuple[EdgeRecord, ...] = ()
    auxiliary_unfold_edges: tuple[EdgeRecord, ...] = ()
    ignored_longitudinal_edges: tuple[EdgeRecord, ...] = ()
    ignored_profile_edges: tuple[EdgeRecord, ...] = ()
    ignored_plane_radius_edges: tuple[EdgeRecord, ...] = ()
    uncertain_edges: tuple[EdgeRecord, ...] = ()
    diagnostic_edge_length_mm: float = 0.0
    edge_records: tuple[EdgeRecord, ...] = ()
    wall_thickness_method: str = "не определена"
    wall_thickness_confidence: str = "низкая"
    length_axis: str = "Z"
    global_bounds: Bounds | None = None
    tolerance: float = 0.01
    round_outer_diameter_mm: float = 0.0
    face_records: tuple[FaceRecord, ...] = ()

    @property
    def cut_edge_count(self) -> int:
        return len(self._active_cut_edges)

    @property
    def cut_length_mm(self) -> float:
        if self.cut_length_override_mm is not None:
            return self.cut_length_override_mm
        return sum(edge.length_mm for edge in self._active_cut_edges)

    @property
    def thickness_face_count(self) -> int:
        return len(self.thickness_faces)

    @property
    def pierce_count(self) -> int | None:
        return self.pierce_count_override

    @property
    def ignored_longitudinal_edge_count(self) -> int:
        return len(self.ignored_longitudinal_edges)

    @property
    def ignored_profile_edge_count(self) -> int:
        return len(self.ignored_profile_edges)

    @property
    def ignored_plane_radius_edge_count(self) -> int:
        return len(self.ignored_plane_radius_edges)

    @property
    def auxiliary_unfold_edge_count(self) -> int:
        return len(self.auxiliary_unfold_edges)

    @property
    def uncertain_edge_count(self) -> int:
        return len(self.uncertain_edges)

    @property
    def cut_feature_edges(self) -> tuple[EdgeRecord, ...]:
        return tuple(edge for edge in self._active_cut_edges if edge.edge_type == CUT_FEATURE)

    @property
    def cut_end_edges(self) -> tuple[EdgeRecord, ...]:
        return tuple(edge for edge in self._active_cut_edges if edge.edge_type == CUT_END)

    @property
    def cut_feature_length_mm(self) -> float:
        return sum(edge.length_mm for edge in self.cut_feature_edges)

    @property
    def cut_end_length_mm(self) -> float:
        return sum(edge.length_mm for edge in self.cut_end_edges)

    @property
    def _active_cut_edges(self) -> tuple[EdgeRecord, ...]:
        if self.calculated_cut_edges:
            return self.calculated_cut_edges
        return self.cut_edges


class EdgeClassifier:
    """Classifies likely laser cut contours on the outer tube surface."""

    def classify(
        self,
        shape: object,
        *,
        summary: ShapeSummary,
        length_axis: str,
        manual_wall_thickness_mm: float | None = None,
    ) -> EdgeClassificationResult:
        return classify_cut_edges(
            shape,
            summary=summary,
            length_axis=length_axis,
            manual_wall_thickness_mm=manual_wall_thickness_mm,
        )


def classify_cut_edges(
    shape: object | None,
    *,
    summary: ShapeSummary,
    length_axis: str,
    manual_wall_thickness_mm: float | None = None,
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

    groups = _classify_edge_groups(
        edge_records,
        axis=axis,
        length_mm=length_mm,
        global_bounds=global_bounds,
        has_outer_faces=outer_face_count > 0,
        tolerance=tolerance,
    )
    round_loop_analysis = _analyze_round_tube_outer_loops(
        face_records,
        edge_records,
        axis=axis,
        length_mm=length_mm,
        global_bounds=global_bounds,
        tolerance=tolerance,
        warnings=warnings,
    )
    cut_face_analysis = _analyze_cut_faces(
        thickness_faces,
        axis=axis,
        length_mm=length_mm,
        global_bounds=global_bounds,
        tolerance=tolerance,
    )
    round_edge_fallback_analysis = _analyze_round_tube_edge_fallback(
        edge_records,
        axis=axis,
        length_mm=length_mm,
        global_bounds=global_bounds,
        has_outer_faces=outer_face_count > 0,
        tolerance=tolerance,
    )
    use_round_loop_analysis = bool(round_loop_analysis.cut_edges)
    use_cut_face_analysis = bool(cut_face_analysis.cut_edges)
    use_round_edge_fallback = bool(round_edge_fallback_analysis.cut_edges)
    if use_round_loop_analysis:
        _suppress_legacy_cut_edges(
            edge_records,
            selected_cut_edges=round_loop_analysis.cut_edges,
        )
        groups = _groups_from_edge_records(edge_records)
        cut_edges = round_loop_analysis.cut_edges
    elif use_cut_face_analysis:
        _suppress_legacy_cut_edges(
            edge_records,
            selected_cut_edges=cut_face_analysis.cut_edges,
        )
        groups = _groups_from_edge_records(edge_records)
        cut_edges = cut_face_analysis.cut_edges
    elif use_round_edge_fallback:
        _suppress_legacy_cut_edges(
            edge_records,
            selected_cut_edges=round_edge_fallback_analysis.cut_edges,
        )
        groups = _groups_from_edge_records(edge_records)
        cut_edges = round_edge_fallback_analysis.cut_edges
    else:
        cut_edges = groups.calculated_cut_edges

    if not cut_edges:
        warnings.append(
            "Расчетные контуры CUT_FEATURE/CUT_END не найдены; "
            "внешняя рамка развертки не учитывается как рез."
        )

    cut_length_override_mm = sum(edge.length_mm for edge in cut_edges)
    if use_round_loop_analysis:
        pierce_count_override = round_loop_analysis.pierce_count
        warnings.append(
            "Круглая труба рассчитана по контурам наружной цилиндрической грани; "
            "каждый найденный EdgeLoop считается отдельной врезкой."
        )
    elif use_cut_face_analysis:
        pierce_count_override = cut_face_analysis.pierce_count
        warnings.append(
            "Длина реза рассчитана по наружным границам граней стенки реза; "
            "внутренние кромки толщины и разбиение CAD-граней не суммируются."
        )
    elif use_round_edge_fallback:
        pierce_count_override = round_edge_fallback_analysis.pierce_count
        warnings.append(
            "Наружный цилиндр не найден, но bbox похож на круглую трубу; "
            "использован fallback по замкнутым/поперечным B-Rep ребрам."
        )
    else:
        pierce_count_override = _count_cut_edge_components(
            cut_edges,
            axis=axis,
            global_bounds=global_bounds,
            tolerance=tolerance,
        )
        warnings.append(
            "Грани стенки реза не найдены; использован fallback по классификации B-Rep ребер."
        )
    thickness_estimate = estimate_wall_thickness(
        face_records,
        edge_records,
        axis=axis,
        length_mm=length_mm,
        global_bounds=global_bounds,
        tolerance=tolerance,
        manual_wall_thickness_mm=manual_wall_thickness_mm,
    )
    wall_thickness_mm = thickness_estimate.thickness_mm
    if wall_thickness_mm > tolerance:
        for face in thickness_faces:
            face.thickness_mm = wall_thickness_mm
            face.cut_length_mm = face.area_mm2 / wall_thickness_mm
    warnings.extend(thickness_estimate.warnings)
    if wall_thickness_mm <= tolerance:
        warnings.append(
            "Толщина трубы не определена надежно; задайте ручную толщину в интерфейсе."
        )
    elif thickness_estimate.confidence != "высокая":
        warnings.append(
            "Толщина трубы определена с невысокой уверенностью; при необходимости задайте ее вручную."
        )

    warnings.append(
        "Длина реза считается только по ребрам CUT_FEATURE и CUT_END; "
        "внешний контур развертки, линии профиля и продольные ребра игнорируются."
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
        calculated_cut_edges=cut_edges,
        auxiliary_unfold_edges=groups.auxiliary_unfold_edges,
        ignored_longitudinal_edges=groups.ignored_longitudinal_edges,
        ignored_profile_edges=groups.ignored_profile_edges,
        ignored_plane_radius_edges=groups.ignored_plane_radius_edges,
        uncertain_edges=groups.uncertain_edges,
        diagnostic_edge_length_mm=sum(edge.length_mm for edge in edge_records),
        edge_records=tuple(edge_records),
        wall_thickness_method=thickness_estimate.method,
        wall_thickness_confidence=thickness_estimate.confidence,
        length_axis=axis,
        global_bounds=global_bounds,
        tolerance=tolerance,
        round_outer_diameter_mm=(
            round_loop_analysis.outer_radius_mm * 2.0 if use_round_loop_analysis else 0.0
        ),
        face_records=tuple(face_records),
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

        edge_lengths = tuple(
            edge.length_mm for edge in face_edges if edge.length_mm > tolerance
        )
        thickness_mm = _estimate_face_thickness(
            face_record.bounds,
            edge_lengths,
            tolerance=tolerance,
        )

        cut_length_mm = 0.0
        if area_mm2 > tolerance and thickness_mm > tolerance:
            cut_length_mm = area_mm2 / thickness_mm

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


def estimate_wall_thickness(
    face_records: Iterable[FaceRecord],
    edge_records: Iterable[EdgeRecord],
    *,
    axis: str,
    length_mm: float,
    global_bounds: Bounds,
    tolerance: float,
    manual_wall_thickness_mm: float | None = None,
) -> ThicknessEstimate:
    manual = float(manual_wall_thickness_mm or 0.0)
    if manual > tolerance:
        return ThicknessEstimate(
            thickness_mm=manual,
            method="ручной ввод",
            confidence="высокая",
        )

    faces = tuple(face_records)
    round_estimate = _estimate_round_tube_thickness(
        faces,
        axis=axis,
        length_mm=length_mm,
        global_bounds=global_bounds,
        tolerance=tolerance,
    )
    if round_estimate.thickness_mm > tolerance and round_estimate.confidence == "высокая":
        return round_estimate

    flat_estimate = _estimate_flat_wall_thickness(
        faces,
        axis=axis,
        length_mm=length_mm,
        global_bounds=global_bounds,
        tolerance=tolerance,
    )
    if flat_estimate.thickness_mm > tolerance:
        return flat_estimate

    if round_estimate.thickness_mm > tolerance:
        return round_estimate

    return ThicknessEstimate(
        warnings=("Не удалось найти надежную пару наружного и внутреннего контура для толщины.",)
    )


def _estimate_round_tube_thickness(
    face_records: tuple[FaceRecord, ...],
    *,
    axis: str,
    length_mm: float,
    global_bounds: Bounds,
    tolerance: float,
) -> ThicknessEstimate:
    expected_outer_radius = _expected_round_outer_radius(
        axis=axis,
        global_bounds=global_bounds,
        tolerance=tolerance,
    )
    radii = sorted(
        radius
        for face in face_records
        if _looks_like_longitudinal_inner_wall(
            face.bounds,
            axis=axis,
            length_mm=length_mm,
            tolerance=tolerance,
        )
        or face.is_outer_longitudinal
        for radius in (_cylinder_radius(face.face),)
        for radius in (
            _normalize_cylinder_radius(
                radius,
                expected_outer_radius=expected_outer_radius,
                tolerance=tolerance,
            ),
        )
        if radius is not None and radius > tolerance
    )
    distinct = _distinct_sorted(radii, tolerance=tolerance)
    if len(distinct) < 2:
        return ThicknessEstimate()

    outer_radius = distinct[-1]
    inner_radius = distinct[-2]
    thickness = outer_radius - inner_radius
    if thickness <= tolerance:
        return ThicknessEstimate()

    confidence = "высокая" if len(distinct) == 2 else "средняя"
    warnings: tuple[str, ...] = ()
    if confidence != "высокая":
        warnings = ("Найдено больше двух цилиндрических радиусов; толщина круглой трубы требует проверки.",)
    return ThicknessEstimate(
        thickness_mm=thickness,
        method="цилиндры R_outer - R_inner",
        confidence=confidence,
        warnings=warnings,
    )


def _estimate_flat_wall_thickness(
    face_records: tuple[FaceRecord, ...],
    *,
    axis: str,
    length_mm: float,
    global_bounds: Bounds,
    tolerance: float,
) -> ThicknessEstimate:
    sections = [
        section
        for face in face_records
        for section in (_flat_wall_section(face, axis=axis, length_mm=length_mm, global_bounds=global_bounds, tolerance=tolerance),)
        if section is not None
    ]
    outer_sections = [section for section in sections if section["is_outer"]]
    inner_sections = [section for section in sections if not section["is_outer"]]
    values: list[float] = []

    for outer in outer_sections:
        candidates: list[float] = []
        for inner in inner_sections:
            if inner["cross_index"] != outer["cross_index"]:
                continue
            if inner["side"] != outer["side"]:
                continue
            if outer["side"] == "min":
                value = inner["coord"] - outer["coord"]
            else:
                value = outer["coord"] - inner["coord"]
            if value > tolerance:
                candidates.append(value)
        if candidates:
            values.append(min(candidates))

    if not values:
        return ThicknessEstimate()

    thickness = _median(tuple(values))
    spread = (max(values) - min(values)) if len(values) > 1 else 0.0
    relative_spread = spread / thickness if thickness > tolerance else 1.0
    if len(values) >= 2 and relative_spread <= 0.15:
        confidence = "высокая"
    elif relative_spread <= 0.30:
        confidence = "средняя"
    else:
        confidence = "низкая"

    warnings: tuple[str, ...] = ()
    if confidence != "высокая":
        warnings = (
            "Толщина профильной трубы по плоским стенкам имеет разброс; проверьте или задайте вручную.",
        )
    return ThicknessEstimate(
        thickness_mm=thickness,
        method="плоские стенки наружный/внутренний контур",
        confidence=confidence,
        warnings=warnings,
    )


def _flat_wall_section(
    face: FaceRecord,
    *,
    axis: str,
    length_mm: float,
    global_bounds: Bounds,
    tolerance: float,
) -> dict[str, object] | None:
    if length_mm <= tolerance:
        return None
    axis_index = AXIS_INDEX[axis]
    if face.bounds.sizes[axis_index] < max(length_mm * 0.45, tolerance):
        return None

    flat_tolerance = max(tolerance * 2.0, 0.05)
    cross_indexes = [index for index in range(3) if index != axis_index]
    constant_indexes = [
        index for index in cross_indexes if face.bounds.sizes[index] <= flat_tolerance
    ]
    if len(constant_indexes) != 1:
        return None

    cross_index = constant_indexes[0]
    coord = (face.bounds.mins[cross_index] + face.bounds.maxes[cross_index]) / 2.0
    global_min = global_bounds.mins[cross_index]
    global_max = global_bounds.maxes[cross_index]
    side = "min" if abs(coord - global_min) <= abs(coord - global_max) else "max"
    is_outer = (
        abs(coord - global_min) <= flat_tolerance
        or abs(coord - global_max) <= flat_tolerance
        or face.is_outer_longitudinal
    )
    return {
        "cross_index": cross_index,
        "coord": coord,
        "side": side,
        "is_outer": is_outer,
    }


def _cylinder_radius(face: object) -> float | None:
    attr_radius = getattr(face, "radius_mm", None)
    if attr_radius is None:
        attr_radius = getattr(face, "radius", None)
    if attr_radius is not None:
        try:
            return float(attr_radius)
        except (TypeError, ValueError):
            return None

    try:
        from OCC.Core.BRepAdaptor import BRepAdaptor_Surface
        from OCC.Core.GeomAbs import GeomAbs_Cylinder

        surface = BRepAdaptor_Surface(face)
        if surface.GetType() != GeomAbs_Cylinder:
            return None
        cylinder = surface.Cylinder()
        return float(cylinder.Radius())
    except Exception:
        return None


def _distinct_sorted(values: Iterable[float], *, tolerance: float) -> tuple[float, ...]:
    distinct: list[float] = []
    for value in sorted(values):
        if distinct and abs(value - distinct[-1]) <= tolerance:
            continue
        distinct.append(value)
    return tuple(distinct)


def _analyze_round_tube_outer_loops(
    face_records: tuple[FaceRecord, ...] | list[FaceRecord],
    edge_records: tuple[EdgeRecord, ...] | list[EdgeRecord],
    *,
    axis: str,
    length_mm: float,
    global_bounds: Bounds,
    tolerance: float,
    warnings: list[str],
) -> RoundTubeLoopAnalysis:
    outer_radius = _round_tube_outer_radius(
        tuple(face_records),
        axis=axis,
        length_mm=length_mm,
        global_bounds=global_bounds,
        tolerance=tolerance,
    )
    if outer_radius <= tolerance:
        return RoundTubeLoopAnalysis()

    candidates: list[tuple[float, int, FaceRecord, tuple[EdgeRecord, ...]]] = []
    for face_record in face_records:
        if not _is_round_outer_face_for_loop_sum(
            face_record,
            axis=axis,
            length_mm=length_mm,
            outer_radius=outer_radius,
            tolerance=tolerance,
        ):
            continue

        wire_records = _collect_wire_records(face_record, warnings=warnings)
        loop_groups: dict[tuple[object, ...], tuple[float, tuple[EdgeRecord, ...]]] = {}

        for wire_record in wire_records:
            loop_edges = _round_outer_loop_cut_edges(
                wire_record,
                edge_records,
                axis=axis,
                length_mm=length_mm,
                global_bounds=global_bounds,
                tolerance=tolerance,
            )
            if not loop_edges:
                continue
            loop_length = sum(edge.length_mm for edge in loop_edges)
            loop_key = _round_loop_group_key(
                loop_edges,
                axis=axis,
                global_bounds=global_bounds,
                tolerance=tolerance,
            )
            current = loop_groups.get(loop_key)
            if current is not None:
                current_length, _ = current
                if _same_round_loop_length(loop_length, current_length, tolerance=tolerance):
                    if loop_length < current_length:
                        loop_groups[loop_key] = (loop_length, loop_edges)
                    continue
            loop_groups[loop_key] = (loop_length, loop_edges)

        cut_edges: list[EdgeRecord] = []
        for component_id, (_loop_length, loop_edges) in enumerate(loop_groups.values(), start=1):
            for edge in loop_edges:
                if _find_same_edge(cut_edges, edge.edge) is not None:
                    continue
                edge.edge_type = _round_loop_edge_type(
                    edge,
                    axis=axis,
                    global_bounds=global_bounds,
                    tolerance=tolerance,
                )
                edge.reason = f"{edge.edge_type} round outer face loop"
                edge.cut_component_id = component_id
                cut_edges.append(edge)

        loop_count = len(loop_groups)
        if cut_edges and loop_count > 0:
            candidates.append(
                (
                    sum(edge.length_mm for edge in cut_edges),
                    loop_count,
                    face_record,
                    tuple(cut_edges),
                )
            )

    if not candidates:
        return RoundTubeLoopAnalysis()

    length_sum, loop_count, face_record, cut_edges = max(
        candidates,
        key=lambda item: (item[0], item[1]),
    )
    if length_sum <= tolerance:
        return RoundTubeLoopAnalysis()
    return RoundTubeLoopAnalysis(
        cut_edges=cut_edges,
        pierce_count=loop_count,
        selected_face=face_record,
        outer_radius_mm=outer_radius,
    )


def _round_loop_group_key(
    edges: tuple[EdgeRecord, ...],
    *,
    axis: str,
    global_bounds: Bounds,
    tolerance: float,
) -> tuple[object, ...]:
    loop_bounds = _combined_edge_bounds(edges)
    if loop_bounds is None:
        return ("unknown", id(edges))

    axis_index = AXIS_INDEX[axis]
    end_side = _bounds_end_side(
        loop_bounds,
        axis=axis,
        global_bounds=global_bounds,
        tolerance=tolerance,
    )
    if end_side is not None:
        return ("end", end_side)

    grid = max(tolerance * 25.0, 0.5)
    cross_indexes = [index for index in range(3) if index != axis_index]
    center_values = [
        (loop_bounds.mins[index] + loop_bounds.maxes[index]) / 2.0
        for index in (axis_index, *cross_indexes)
    ]
    span_values = [loop_bounds.sizes[index] for index in cross_indexes]
    return (
        "feature",
        *(round(value / grid) for value in center_values),
        *(round(value / grid) for value in span_values),
    )


def _same_round_loop_length(first: float, second: float, *, tolerance: float) -> bool:
    smaller = min(first, second)
    larger = max(first, second)
    if smaller <= tolerance:
        return larger <= tolerance
    return larger / smaller <= 1.25


def _combined_edge_bounds(edges: tuple[EdgeRecord, ...]) -> Bounds | None:
    bounds = [edge.bounds for edge in edges if edge.bounds is not None]
    if not bounds:
        return None
    return Bounds(
        min(item.xmin for item in bounds),
        min(item.ymin for item in bounds),
        min(item.zmin for item in bounds),
        max(item.xmax for item in bounds),
        max(item.ymax for item in bounds),
        max(item.zmax for item in bounds),
    )


def _bounds_end_side(
    bounds: Bounds,
    *,
    axis: str,
    global_bounds: Bounds,
    tolerance: float,
) -> str | None:
    axis_index = AXIS_INDEX[axis]
    bound_min = bounds.mins[axis_index]
    bound_max = bounds.maxes[axis_index]
    global_min = global_bounds.mins[axis_index]
    global_max = global_bounds.maxes[axis_index]
    end_tolerance = max(tolerance * 4.0, 0.05)
    if abs(bound_min - global_min) <= end_tolerance and abs(bound_max - global_min) <= end_tolerance:
        return "min"
    if abs(bound_min - global_max) <= end_tolerance and abs(bound_max - global_max) <= end_tolerance:
        return "max"
    return None


def _round_tube_outer_radius(
    face_records: tuple[FaceRecord, ...],
    *,
    axis: str,
    length_mm: float,
    global_bounds: Bounds,
    tolerance: float,
) -> float:
    expected_radius = _expected_round_outer_radius(
        axis=axis,
        global_bounds=global_bounds,
        tolerance=tolerance,
    )
    if expected_radius <= tolerance:
        return 0.0

    axis_index = AXIS_INDEX[axis]
    radius_tolerance = max(tolerance * 2.0, expected_radius * 0.12, 0.8)
    radii = sorted(
        radius
        for face in face_records
        if face.bounds.sizes[axis_index] >= max(length_mm * 0.02, tolerance)
        for radius in (_cylinder_radius(face.face),)
        for radius in (
            _normalize_cylinder_radius(
                radius,
                expected_outer_radius=expected_radius,
                tolerance=tolerance,
            ),
        )
        if radius is not None and radius > tolerance
    )
    distinct = _distinct_sorted(radii, tolerance=tolerance)
    if not distinct:
        return 0.0

    outer_radius = distinct[-1]
    if (
        abs(outer_radius - expected_radius) > radius_tolerance
        and abs(outer_radius * 2.0 - expected_radius) > radius_tolerance
    ):
        return 0.0
    return outer_radius


def _is_round_outer_face_for_loop_sum(
    face_record: FaceRecord,
    *,
    axis: str,
    length_mm: float,
    outer_radius: float,
    tolerance: float,
) -> bool:
    radius = _cylinder_radius(face_record.face)
    radius = _normalize_cylinder_radius(
        radius,
        expected_outer_radius=outer_radius,
        tolerance=tolerance,
    )
    if radius is None:
        return False
    radius_tolerance = max(tolerance * 2.0, outer_radius * 0.08, 0.6)
    if abs(radius - outer_radius) > radius_tolerance:
        return False

    axis_span = face_record.bounds.sizes[AXIS_INDEX[axis]]
    return axis_span >= max(length_mm * 0.02, tolerance)


def _expected_round_outer_radius(
    *,
    axis: str,
    global_bounds: Bounds,
    tolerance: float,
) -> float:
    axis_index = AXIS_INDEX[axis]
    cross_sizes = [
        global_bounds.sizes[index]
        for index in range(3)
        if index != axis_index
    ]
    if len(cross_sizes) != 2:
        return 0.0
    cross_min = min(cross_sizes)
    cross_max = max(cross_sizes)
    if cross_min <= tolerance or cross_min / cross_max < 0.75:
        return 0.0
    return (cross_min + cross_max) / 4.0


def _normalize_cylinder_radius(
    radius: float | None,
    *,
    expected_outer_radius: float,
    tolerance: float,
) -> float | None:
    if radius is None:
        return None
    radius = float(radius)
    if expected_outer_radius <= tolerance:
        return radius
    radius_tolerance = max(tolerance * 2.0, expected_outer_radius * 0.12, 0.8)
    if abs(radius - expected_outer_radius) <= radius_tolerance:
        return radius
    half_radius = radius / 2.0
    if abs(half_radius - expected_outer_radius) <= radius_tolerance:
        return half_radius
    double_radius = radius * 2.0
    if abs(double_radius - expected_outer_radius) <= radius_tolerance:
        return radius
    return radius


def _round_outer_loop_cut_edges(
    wire_record: WireRecord,
    edge_records: tuple[EdgeRecord, ...] | list[EdgeRecord],
    *,
    axis: str,
    length_mm: float,
    global_bounds: Bounds,
    tolerance: float,
) -> tuple[EdgeRecord, ...]:
    selected: list[EdgeRecord] = []
    edge_record_list = list(edge_records)
    for wire_edge in wire_record.edges:
        edge = _find_same_edge(edge_record_list, wire_edge)
        if edge is None:
            continue
        if edge.length_mm <= tolerance:
            continue
        if _looks_like_longitudinal_seam(edge, axis=axis, length_mm=length_mm):
            continue
        if _round_loop_edge_type(
            edge,
            axis=axis,
            global_bounds=global_bounds,
            tolerance=tolerance,
        ) not in CALCULATED_CUT_TYPES:
            continue
        if _find_same_edge(selected, edge.edge) is not None:
            continue
        selected.append(edge)
    return tuple(selected)


def _round_loop_edge_type(
    edge: EdgeRecord,
    *,
    axis: str,
    global_bounds: Bounds,
    tolerance: float,
) -> str:
    if _is_tube_end_edge(
        edge,
        axis=axis,
        global_bounds=global_bounds,
        tolerance=tolerance,
        allow_outer_only=True,
    ):
        return CUT_END
    return CUT_FEATURE


def _analyze_round_tube_edge_fallback(
    edge_records: tuple[EdgeRecord, ...] | list[EdgeRecord],
    *,
    axis: str,
    length_mm: float,
    global_bounds: Bounds,
    has_outer_faces: bool,
    tolerance: float,
) -> CutFaceAnalysis:
    if has_outer_faces:
        return CutFaceAnalysis()
    if not _global_bounds_looks_round_tube(
        axis=axis,
        global_bounds=global_bounds,
        tolerance=tolerance,
    ):
        return CutFaceAnalysis()

    selected: list[EdgeRecord] = []
    for edge in edge_records:
        if edge.length_mm <= tolerance:
            continue
        if _looks_like_longitudinal_seam(edge, axis=axis, length_mm=length_mm):
            continue
        if edge.bounds is not None:
            axial_span = edge.bounds.sizes[AXIS_INDEX[axis]]
            if axial_span >= max(length_mm * 0.92, length_mm - tolerance * 4.0):
                continue
        edge.edge_type = _round_loop_edge_type(
            edge,
            axis=axis,
            global_bounds=global_bounds,
            tolerance=tolerance,
        )
        edge.reason = f"{edge.edge_type} round edge fallback without detected outer cylinder"
        selected.append(edge)

    if not selected:
        return CutFaceAnalysis()

    component_ids = _cut_edge_component_ids(
        tuple(selected),
        axis=axis,
        global_bounds=global_bounds,
        tolerance=tolerance,
    )
    for index, edge in enumerate(selected):
        edge.cut_component_id = component_ids.get(index, 0)
    pierce_count = len({component for component in component_ids.values() if component > 0})
    return CutFaceAnalysis(cut_edges=tuple(selected), pierce_count=pierce_count)


def _global_bounds_looks_round_tube(
    *,
    axis: str,
    global_bounds: Bounds,
    tolerance: float,
) -> bool:
    axis_index = AXIS_INDEX[axis]
    cross_sizes = [
        global_bounds.sizes[index]
        for index in range(3)
        if index != axis_index
    ]
    if len(cross_sizes) != 2:
        return False
    cross_min = min(cross_sizes)
    cross_max = max(cross_sizes)
    return cross_min > tolerance and cross_min / cross_max >= 0.75


def _analyze_cut_faces(
    records: tuple[ThicknessFaceRecord, ...],
    *,
    axis: str,
    length_mm: float,
    global_bounds: Bounds,
    tolerance: float,
) -> CutFaceAnalysis:
    records = tuple(records)
    # Connectivity is grouped over *all* thickness faces, not only the ones
    # that carry an outer cut contour. A multi-plane cut (e.g. a 3-plane notch)
    # can have an internal facet that never reaches the outer skin; that facet
    # owns no outer edge, yet it is the only thing joining its two outer
    # neighbours. Excluding it before grouping would split a single pierce into
    # two. We therefore compute components first, then keep only the faces that
    # actually contribute an outer cut edge.
    component_ids = _thickness_face_component_ids(records, tolerance=tolerance)

    selected_records: list[ThicknessFaceRecord] = []
    selected_components: list[int] = []
    record_edges: list[tuple[EdgeRecord, ...]] = []

    for index, record in enumerate(records):
        outer_edges = _outer_cut_edges_for_thickness_face(
            record,
            axis=axis,
            length_mm=length_mm,
            tolerance=tolerance,
        )
        if not outer_edges:
            continue
        selected_records.append(record)
        selected_components.append(component_ids.get(index, 0))
        record_edges.append(outer_edges)

    if not selected_records:
        return CutFaceAnalysis()

    cut_edges: list[EdgeRecord] = []

    for record_index, edges in enumerate(record_edges):
        component_id = selected_components[record_index]
        for edge in edges:
            existing = _find_same_edge(cut_edges, edge.edge)
            if existing is not None:
                if existing.cut_component_id <= 0 and component_id > 0:
                    existing.cut_component_id = component_id
                continue

            edge_type, reason = _classify_cut_face_edge(
                edge,
                axis=axis,
                global_bounds=global_bounds,
                tolerance=tolerance,
            )
            edge.edge_type = edge_type
            edge.reason = reason
            edge.cut_component_id = component_id
            cut_edges.append(edge)

    # Count one pierce per connected group that surfaces on the outer skin.
    pierce_count = len({component for component in selected_components if component > 0})
    return CutFaceAnalysis(
        cut_edges=tuple(cut_edges),
        cut_faces=tuple(selected_records),
        pierce_count=pierce_count,
    )


def _outer_cut_edges_for_thickness_face(
    record: ThicknessFaceRecord,
    *,
    axis: str,
    length_mm: float,
    tolerance: float,
) -> tuple[EdgeRecord, ...]:
    edges: list[EdgeRecord] = []
    for edge in record.edges:
        if edge.length_mm <= tolerance:
            continue
        if not _edge_touches_outer_face(edge, record.face):
            continue
        if _looks_like_longitudinal_seam(edge, axis=axis, length_mm=length_mm):
            continue
        if _find_same_edge(edges, edge.edge) is not None:
            continue
        edges.append(edge)
    return tuple(edges)


def _classify_cut_face_edge(
    edge: EdgeRecord,
    *,
    axis: str,
    global_bounds: Bounds,
    tolerance: float,
) -> tuple[str, str]:
    if _is_tube_end_edge(
        edge,
        axis=axis,
        global_bounds=global_bounds,
        tolerance=tolerance,
    ):
        return CUT_END, "CUT_END cut-face outer contour"
    return CUT_FEATURE, "CUT_FEATURE cut-face outer contour"


def _thickness_face_component_ids(
    records: tuple[ThicknessFaceRecord, ...],
    *,
    tolerance: float,
) -> dict[int, int]:
    if not records:
        return {}

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

    root_to_component: dict[int, int] = {}
    component_ids: dict[int, int] = {}
    for index in range(len(records)):
        root = find(index)
        if root not in root_to_component:
            root_to_component[root] = len(root_to_component) + 1
        component_ids[index] = root_to_component[root]
    return component_ids


def _suppress_legacy_cut_edges(
    edges: Iterable[EdgeRecord],
    *,
    selected_cut_edges: tuple[EdgeRecord, ...],
) -> None:
    selected_ids = {id(edge) for edge in selected_cut_edges}
    for edge in edges:
        if id(edge) in selected_ids:
            continue
        if edge.edge_type in CALCULATED_CUT_TYPES:
            edge.edge_type = UNCERTAIN
            edge.reason = "ignored by cut-face component analysis"
            edge.cut_component_id = 0


def _groups_from_edge_records(edges: Iterable[EdgeRecord]) -> EdgeGroups:
    calculated_cut_edges: list[EdgeRecord] = []
    ignored_longitudinal_edges: list[EdgeRecord] = []
    ignored_profile_edges: list[EdgeRecord] = []
    ignored_plane_radius_edges: list[EdgeRecord] = []
    uncertain_edges: list[EdgeRecord] = []

    for edge in edges:
        if edge.edge_type in CALCULATED_CUT_TYPES:
            calculated_cut_edges.append(edge)
        elif edge.edge_type == IGNORED_LONGITUDINAL:
            ignored_longitudinal_edges.append(edge)
        elif edge.edge_type == IGNORED_PROFILE:
            ignored_profile_edges.append(edge)
        elif edge.edge_type == IGNORED_PLANE_RADIUS:
            ignored_plane_radius_edges.append(edge)
        elif edge.edge_type == UNCERTAIN:
            uncertain_edges.append(edge)

    return EdgeGroups(
        calculated_cut_edges=tuple(calculated_cut_edges),
        ignored_longitudinal_edges=tuple(ignored_longitudinal_edges),
        ignored_profile_edges=tuple(ignored_profile_edges),
        ignored_plane_radius_edges=tuple(ignored_plane_radius_edges),
        uncertain_edges=tuple(uncertain_edges),
    )


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


def _collect_thickness_outer_cut_edges(
    records: tuple[ThicknessFaceRecord, ...],
    *,
    axis: str,
    length_mm: float,
    tolerance: float,
) -> tuple[EdgeRecord, ...]:
    cut_edges: list[EdgeRecord] = []
    for record in records:
        for edge in record.edges:
            if edge.length_mm <= tolerance:
                continue
            if not _edge_touches_outer_face(edge, record.face):
                continue
            if _looks_like_longitudinal_seam(edge, axis=axis, length_mm=length_mm):
                continue
            existing = _find_same_edge(cut_edges, edge.edge)
            if existing is not None:
                continue
            edge.reason = "outer thickness contour"
            cut_edges.append(edge)
    return tuple(cut_edges)


def _count_cut_edge_components(
    edges: tuple[EdgeRecord, ...],
    *,
    axis: str | None = None,
    global_bounds: Bounds | None = None,
    tolerance: float,
) -> int:
    return len(
        set(
            _cut_edge_component_ids(
                edges,
                axis=axis,
                global_bounds=global_bounds,
                tolerance=tolerance,
            ).values()
        )
    )


def _cut_edge_component_ids(
    edges: tuple[EdgeRecord, ...],
    *,
    axis: str | None = None,
    global_bounds: Bounds | None = None,
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
            if (
                axis is not None
                and global_bounds is not None
                and _same_tube_end_side(
                    left,
                    right,
                    axis=axis,
                    global_bounds=global_bounds,
                    tolerance=tolerance,
                )
            ):
                union(left_index, right_index)
                continue
            if _edge_endpoints_touch(left, right, tolerance=tolerance):
                union(left_index, right_index)

    root_to_component: dict[int, int] = {}
    component_ids: dict[int, int] = {}
    for index in range(len(edges)):
        root = find(index)
        if root not in root_to_component:
            root_to_component[root] = len(root_to_component) + 1
        component_ids[index] = root_to_component[root]
    return component_ids


def _same_tube_end_side(
    first: EdgeRecord,
    second: EdgeRecord,
    *,
    axis: str,
    global_bounds: Bounds,
    tolerance: float,
) -> bool:
    if first.edge_type != CUT_END or second.edge_type != CUT_END:
        return False
    first_side = _edge_end_side(
        first,
        axis=axis,
        global_bounds=global_bounds,
        tolerance=tolerance,
    )
    if first_side is None:
        return False
    return first_side == _edge_end_side(
        second,
        axis=axis,
        global_bounds=global_bounds,
        tolerance=tolerance,
    )


def _edge_end_side(
    edge: EdgeRecord,
    *,
    axis: str,
    global_bounds: Bounds,
    tolerance: float,
) -> str | None:
    if edge.bounds is None:
        return None

    axis_index = AXIS_INDEX[axis]
    edge_min = edge.bounds.mins[axis_index]
    edge_max = edge.bounds.maxes[axis_index]
    global_min = global_bounds.mins[axis_index]
    global_max = global_bounds.maxes[axis_index]
    end_tolerance = max(tolerance * 4.0, 0.05)
    if abs(edge_min - global_min) <= end_tolerance and abs(edge_max - global_min) <= end_tolerance:
        return "min"
    if abs(edge_min - global_max) <= end_tolerance and abs(edge_max - global_max) <= end_tolerance:
        return "max"
    return None


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
    first_vertices = (first.start_vertex, first.end_vertex)
    second_vertices = (second.start_vertex, second.end_vertex)
    if any(
        first_vertex is not None
        and second_vertex is not None
        and _is_same_shape(first_vertex, second_vertex)
        for first_vertex in first_vertices
        for second_vertex in second_vertices
    ):
        return True

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


def _classify_edge_groups(
    edges: Iterable[EdgeRecord],
    *,
    axis: str,
    length_mm: float,
    global_bounds: Bounds,
    has_outer_faces: bool,
    tolerance: float,
) -> EdgeGroups:
    calculated_cut_edges: list[EdgeRecord] = []
    ignored_longitudinal_edges: list[EdgeRecord] = []
    ignored_profile_edges: list[EdgeRecord] = []
    ignored_plane_radius_edges: list[EdgeRecord] = []
    uncertain_edges: list[EdgeRecord] = []

    for edge in edges:
        edge_type, reason = _classify_single_edge(
            edge,
            axis=axis,
            length_mm=length_mm,
            global_bounds=global_bounds,
            has_outer_faces=has_outer_faces,
            tolerance=tolerance,
        )
        edge.edge_type = edge_type
        edge.reason = reason

        if edge_type in CALCULATED_CUT_TYPES:
            calculated_cut_edges.append(edge)
        elif edge_type == IGNORED_LONGITUDINAL:
            ignored_longitudinal_edges.append(edge)
        elif edge_type == IGNORED_PROFILE:
            ignored_profile_edges.append(edge)
        elif edge_type == IGNORED_PLANE_RADIUS:
            ignored_plane_radius_edges.append(edge)
        elif edge_type == UNCERTAIN:
            uncertain_edges.append(edge)

    return EdgeGroups(
        calculated_cut_edges=tuple(calculated_cut_edges),
        ignored_longitudinal_edges=tuple(ignored_longitudinal_edges),
        ignored_profile_edges=tuple(ignored_profile_edges),
        ignored_plane_radius_edges=tuple(ignored_plane_radius_edges),
        uncertain_edges=tuple(uncertain_edges),
    )


def _classify_single_edge(
    edge: EdgeRecord,
    *,
    axis: str,
    length_mm: float,
    global_bounds: Bounds,
    has_outer_faces: bool,
    tolerance: float,
) -> tuple[str, str]:
    if edge.length_mm <= tolerance:
        return "", "zero length"

    if (
        _looks_like_longitudinal_seam(edge, axis=axis, length_mm=length_mm)
        and edge.outer_face_count >= 2
    ):
        return IGNORED_PLANE_RADIUS, "ignored plane/radius transition line"

    if _looks_like_longitudinal_seam(edge, axis=axis, length_mm=length_mm):
        return IGNORED_LONGITUDINAL, "ignored longitudinal tube edge"

    if not has_outer_faces:
        if edge.adjacent_face_count <= 1:
            return UNCERTAIN, "uncertain open boundary"
        return UNCERTAIN, "uncertain edge without detected outer shell"

    if edge.outer_face_count <= 0:
        return UNCERTAIN, "edge is not on outer tube shell"

    if _is_tube_end_edge(
        edge,
        axis=axis,
        global_bounds=global_bounds,
        tolerance=tolerance,
    ):
        return CUT_END, "CUT_END tube end contour"

    if "inner_wire" in edge.wire_roles:
        return CUT_FEATURE, "CUT_FEATURE inner contour"

    if "outer_wire_cut" in edge.wire_roles:
        return CUT_FEATURE, "CUT_FEATURE outer wire cut"

    if edge.non_outer_face_count > 0:
        return CUT_FEATURE, "CUT_FEATURE outer/cut face boundary"

    return IGNORED_PROFILE, "ignored profile/unfold boundary"


def _is_tube_end_edge(
    edge: EdgeRecord,
    *,
    axis: str,
    global_bounds: Bounds,
    tolerance: float,
    allow_outer_only: bool = False,
) -> bool:
    if edge.bounds is None:
        return False
    if edge.non_outer_face_count <= 0 and not allow_outer_only:
        return False
    return _edge_end_side(edge, axis=axis, global_bounds=global_bounds, tolerance=tolerance) is not None


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
    # End-cap / cross-plane faces (axial extent ~ 0) never belong to the skin.
    if spans[axis_index] <= tolerance:
        return False

    cross_indexes = [index for index in range(3) if index != axis_index]
    # Flatness is an absolute property (a planar wall coincides with the
    # envelope to within numerical noise), so it must not scale with tube
    # length the way the position tolerance does — otherwise a thin cut wall on
    # a long tube would be mistaken for outer skin.
    flat_tol = 0.1
    corner_band = max(global_bounds.sizes[index] for index in cross_indexes) * 0.20

    touched = [
        index
        for index in cross_indexes
        if abs(bounds.mins[index] - global_bounds.mins[index]) <= tolerance
        or abs(bounds.maxes[index] - global_bounds.maxes[index]) <= tolerance
    ]
    if not touched:
        return False

    # Outer skin runs *along* the axis and lies parallel to the envelope, either
    # as a flat wall (≈ zero extent perpendicular to the side it sits on) or as
    # a corner-radius face hugging an envelope corner (small in both cross
    # directions). A cut/thickness wall instead reaches inward by ~ the wall
    # thickness, so its perpendicular extent is non-zero. This stays correct
    # when mid-span features split a wall or fillet into short axial segments.
    if any(spans[index] <= flat_tol for index in touched):
        return True
    if (
        len(touched) >= 2
        and spans[axis_index] > corner_band
        and all(spans[index] <= corner_band for index in cross_indexes)
    ):
        return True
    return False


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
