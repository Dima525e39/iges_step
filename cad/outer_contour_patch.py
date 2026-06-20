from __future__ import annotations

import sys


def install_outer_contour_patch() -> None:
    import cad.edge_classifier as edge_classifier

    if getattr(edge_classifier, "_OUTER_CONTOUR_PATCH_INSTALLED", False):
        return

    original_classify_cut_edges = edge_classifier.classify_cut_edges

    def classify_cut_edges_with_outer_contours(
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
        thickness_faces = getattr(result, "thickness_faces", ())
        if not thickness_faces:
            return result

        axis = length_axis if length_axis in edge_classifier.AXIS_INDEX else "Z"
        length_mm = edge_classifier._summary_axis_size(summary, axis)
        tolerance = edge_classifier._tolerance_from_summary(summary)
        contour_edges = _collect_thickness_outer_cut_edges(
            edge_classifier,
            thickness_faces,
            axis=axis,
            length_mm=length_mm,
            tolerance=tolerance,
        )
        if not contour_edges:
            return result

        warnings = tuple(
            warning
            for warning in getattr(result, "warnings", ())
            if "граням в толщине изделия" not in str(warning)
        ) + (
            "Длина реза рассчитана по наружным ребрам граней толщины; "
            "каждый торцевой контур считается отдельной врезкой.",
        )
        return edge_classifier.EdgeClassificationResult(
            cut_edges=contour_edges,
            all_edge_count=result.all_edge_count,
            outer_face_count=result.outer_face_count,
            thickness_faces=thickness_faces,
            wall_thickness_mm=getattr(result, "wall_thickness_mm", 0.0),
            cut_length_override_mm=sum(edge.length_mm for edge in contour_edges),
            pierce_count_override=_count_cut_edge_components(
                edge_classifier,
                contour_edges,
                tolerance=tolerance,
            ),
            warnings=warnings,
        )

    edge_classifier.classify_cut_edges = classify_cut_edges_with_outer_contours
    edge_classifier._OUTER_CONTOUR_PATCH_INSTALLED = True

    analyzer = sys.modules.get("cad.analyzer")
    if analyzer is not None:
        analyzer.classify_cut_edges = classify_cut_edges_with_outer_contours


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
            if _edge_endpoints_touch(
                edge_classifier,
                left,
                edges[right_index],
                tolerance=tolerance,
            ):
                union(left_index, right_index)

    return len({find(index) for index in range(len(edges))})


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
