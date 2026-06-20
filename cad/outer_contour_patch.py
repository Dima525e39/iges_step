from __future__ import annotations

import sys


def install_outer_contour_patch() -> None:
    import cad.edge_classifier as edge_classifier

    if getattr(edge_classifier, "_OUTER_CONTOUR_PATCH_INSTALLED", False):
        return

    original_classify_cut_edges = edge_classifier.classify_cut_edges

    def classify_cut_edges_with_unfolded_surface(
        shape: object | None,
        *,
        summary: object,
        length_axis: str,
    ) -> object:
        result = original_classify_cut_edges(
            shape,
            summary=summary,
            length_axis=length_axis,
        )
        if shape is None:
            return result

        axis = length_axis if length_axis in edge_classifier.AXIS_INDEX else "Z"
        length_mm = edge_classifier._summary_axis_size(summary, axis)
        tolerance = edge_classifier._tolerance_from_summary(summary)
        warnings = [
            warning
            for warning in getattr(result, "warnings", ())
            if "граням в толщине изделия" not in str(warning)
            and "наружным ребрам граней толщины" not in str(warning)
        ]
        try:
            global_bounds = edge_classifier._shape_bounds(shape)
            contour_edges = _collect_unfolded_surface_cut_edges(
                edge_classifier,
                shape,
                axis=axis,
                length_mm=length_mm,
                global_bounds=global_bounds,
                tolerance=tolerance,
                warnings=warnings,
            )
        except Exception as exc:
            warnings.append(f"Расчет по развертке наружной оболочки не выполнен: {exc}")
            return edge_classifier.EdgeClassificationResult(
                cut_edges=result.cut_edges,
                all_edge_count=result.all_edge_count,
                outer_face_count=result.outer_face_count,
                thickness_faces=getattr(result, "thickness_faces", ()),
                wall_thickness_mm=getattr(result, "wall_thickness_mm", 0.0),
                cut_length_override_mm=getattr(result, "cut_length_override_mm", None),
                pierce_count_override=getattr(result, "pierce_count_override", None),
                warnings=tuple(warnings),
            )

        if not contour_edges:
            return result

        warnings.append(
            "Длина реза рассчитана как контуры на 2D-развертке наружной оболочки: "
            "внутренние контуры вырезов плюс торцы трубы."
        )
        return edge_classifier.EdgeClassificationResult(
            cut_edges=contour_edges,
            all_edge_count=result.all_edge_count,
            outer_face_count=result.outer_face_count,
            thickness_faces=getattr(result, "thickness_faces", ()),
            wall_thickness_mm=getattr(result, "wall_thickness_mm", 0.0),
            cut_length_override_mm=sum(edge.length_mm for edge in contour_edges),
            pierce_count_override=_count_cut_edge_components(
                edge_classifier,
                contour_edges,
                axis=axis,
                global_bounds=global_bounds,
                tolerance=tolerance,
            ),
            warnings=tuple(warnings),
        )

    edge_classifier.classify_cut_edges = classify_cut_edges_with_unfolded_surface
    edge_classifier._OUTER_CONTOUR_PATCH_INSTALLED = True

    analyzer = sys.modules.get("cad.analyzer")
    if analyzer is not None:
        analyzer.classify_cut_edges = classify_cut_edges_with_unfolded_surface


def _collect_unfolded_surface_cut_edges(
    edge_classifier: object,
    shape: object,
    *,
    axis: str,
    length_mm: float,
    global_bounds: object,
    tolerance: float,
    warnings: list[str],
) -> tuple[object, ...]:
    face_records = edge_classifier._collect_face_records(
        shape,
        axis=axis,
        length_mm=length_mm,
        global_bounds=global_bounds,
        tolerance=tolerance,
        warnings=warnings,
    )
    edge_records = edge_classifier._collect_edge_records(
        face_records,
        axis=axis,
        length_mm=length_mm,
        tolerance=tolerance,
        warnings=warnings,
    )
    return _select_unfolded_surface_cut_edges(
        edge_classifier,
        edge_records,
        axis=axis,
        length_mm=length_mm,
        global_bounds=global_bounds,
        tolerance=tolerance,
    )


def _select_unfolded_surface_cut_edges(
    edge_classifier: object,
    edges: tuple[object, ...] | list[object],
    *,
    axis: str,
    length_mm: float,
    global_bounds: object,
    tolerance: float,
) -> tuple[object, ...]:
    cut_edges: list[object] = []
    for edge in edges:
        reason = _surface_cut_reason(
            edge_classifier,
            edge,
            axis=axis,
            length_mm=length_mm,
            global_bounds=global_bounds,
            tolerance=tolerance,
        )
        if not reason:
            continue
        if _find_same_edge(edge_classifier, cut_edges, edge.edge) is not None:
            continue
        edge.reason = reason
        cut_edges.append(edge)
    return tuple(cut_edges)


def _surface_cut_reason(
    edge_classifier: object,
    edge: object,
    *,
    axis: str,
    length_mm: float,
    global_bounds: object,
    tolerance: float,
) -> str:
    if edge.length_mm <= tolerance:
        return ""
    if edge.outer_face_count <= 0:
        return ""
    if edge_classifier._looks_like_longitudinal_seam(
        edge,
        axis=axis,
        length_mm=length_mm,
    ):
        return ""

    if _edge_end_side(edge_classifier, edge, axis=axis, global_bounds=global_bounds, tolerance=tolerance):
        return "unfolded tube end"
    if "inner_wire" in edge.wire_roles:
        return "unfolded inner contour"
    if "outer_wire_cut" in edge.wire_roles:
        return "unfolded outer cut contour"
    if edge.non_outer_face_count > 0:
        return "unfolded cut boundary"
    return ""


def _collect_thickness_outer_cut_edges(
    edge_classifier: object,
    records: tuple[object, ...],
    *,
    axis: str,
    length_mm: float,
    tolerance: float,
) -> tuple[object, ...]:
    cut_edges: list[object] = []
    for record in records:
        face_record = record.face
        for edge in record.edges:
            if edge.length_mm <= tolerance:
                continue
            if not edge_classifier._edge_touches_outer_face(edge, face_record):
                continue
            if edge_classifier._looks_like_longitudinal_seam(
                edge,
                axis=axis,
                length_mm=length_mm,
            ):
                continue
            if _find_same_edge(edge_classifier, cut_edges, edge.edge) is not None:
                continue
            edge.reason = "outer thickness contour"
            cut_edges.append(edge)
    return tuple(cut_edges)


def _count_cut_edge_components(
    edge_classifier: object,
    edges: tuple[object, ...],
    *,
    axis: str | None = None,
    global_bounds: object | None = None,
    tolerance: float,
) -> int:
    if not edges:
        return 0

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
            if (
                axis is not None
                and global_bounds is not None
                and _same_tube_end_side(
                    edge_classifier,
                    left,
                    edges[right_index],
                    axis=axis,
                    global_bounds=global_bounds,
                    tolerance=tolerance,
                )
            ):
                union(left_index, right_index)
                continue
            if _edge_endpoints_touch(
                edge_classifier,
                left,
                edges[right_index],
                tolerance=tolerance,
            ):
                union(left_index, right_index)

    return len({find(index) for index in range(len(edges))})


def _same_tube_end_side(
    edge_classifier: object,
    first: object,
    second: object,
    *,
    axis: str,
    global_bounds: object,
    tolerance: float,
) -> bool:
    if getattr(first, "reason", "") != "unfolded tube end":
        return False
    if getattr(second, "reason", "") != "unfolded tube end":
        return False
    first_side = _edge_end_side(
        edge_classifier,
        first,
        axis=axis,
        global_bounds=global_bounds,
        tolerance=tolerance,
    )
    if first_side is None:
        return False
    return first_side == _edge_end_side(
        edge_classifier,
        second,
        axis=axis,
        global_bounds=global_bounds,
        tolerance=tolerance,
    )


def _edge_end_side(
    edge_classifier: object,
    edge: object,
    *,
    axis: str,
    global_bounds: object,
    tolerance: float,
) -> str | None:
    bounds = getattr(edge, "bounds", None)
    if bounds is None:
        return None

    axis_index = edge_classifier.AXIS_INDEX[axis]
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


def _edge_endpoints_touch(
    edge_classifier: object,
    first: object,
    second: object,
    *,
    tolerance: float,
) -> bool:
    first_vertices = (first.start_vertex, first.end_vertex)
    second_vertices = (second.start_vertex, second.end_vertex)
    if any(
        first_vertex is not None
        and second_vertex is not None
        and edge_classifier._is_same_shape(first_vertex, second_vertex)
        for first_vertex in first_vertices
        for second_vertex in second_vertices
    ):
        return True

    first_points = (first.start_point, first.end_point)
    second_points = (second.start_point, second.end_point)
    return any(
        first_point is not None
        and second_point is not None
        and edge_classifier._points_are_close(
            first_point,
            second_point,
            tolerance=tolerance,
        )
        for first_point in first_points
        for second_point in second_points
    )


def _find_same_edge(
    edge_classifier: object,
    records: list[object],
    edge: object,
) -> object | None:
    for record in records:
        if edge_classifier._is_same_shape(record.edge, edge):
            return record
    return None
