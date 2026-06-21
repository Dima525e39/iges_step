from __future__ import annotations

import csv
from pathlib import Path

from cad.edge_classifier import (
    CALCULATED_CUT_TYPES,
    CUT_END,
    Bounds,
    EdgeClassificationResult,
    EdgeRecord,
    _edge_endpoints_touch,
    _same_tube_end_side,
)


def write_debug_edges_csv(
    classification: EdgeClassificationResult,
    path: str | Path,
    *,
    source_file: str = "",
    length_axis: str | None = None,
    global_bounds: Bounds | None = None,
    tolerance: float = 0.01,
) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    component_ids = _cut_component_ids(
        classification.calculated_cut_edges,
        axis=length_axis,
        global_bounds=global_bounds,
        tolerance=tolerance,
    )
    calculated_ids = {id(edge) for edge in classification.calculated_cut_edges}

    with target.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            (
                "source_file",
                "edge_index",
                "length_mm",
                "edge_type",
                "included_in_cut",
                "cut_component_id",
                "reason",
                "adjacent_faces",
                "outer_faces",
                "non_outer_faces",
                "wire_roles",
                "bounds",
            )
        )
        for index, edge in enumerate(classification.edge_records, start=1):
            included = id(edge) in calculated_ids and edge.edge_type in CALCULATED_CUT_TYPES
            writer.writerow(
                (
                    source_file,
                    index,
                    f"{edge.length_mm:.6f}",
                    edge.edge_type,
                    "yes" if included else "no",
                    component_ids.get(id(edge), ""),
                    edge.reason,
                    edge.adjacent_face_count,
                    edge.outer_face_count,
                    edge.non_outer_face_count,
                    "|".join(sorted(edge.wire_roles)),
                    _format_bounds(edge.bounds),
                )
            )
    return target


def _cut_component_ids(
    edges: tuple[EdgeRecord, ...],
    *,
    axis: str | None,
    global_bounds: Bounds | None,
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
            same_tube_end = (
                axis is not None
                and global_bounds is not None
                and left.edge_type == CUT_END
                and right.edge_type == CUT_END
                and _same_tube_end_side(
                    left,
                    right,
                    axis=axis,
                    global_bounds=global_bounds,
                    tolerance=tolerance,
                )
            )
            if same_tube_end or _edge_endpoints_touch(left, right, tolerance=tolerance):
                union(left_index, right_index)

    root_to_component: dict[int, int] = {}
    ids: dict[int, int] = {}
    for index, edge in enumerate(edges):
        root = find(index)
        if root not in root_to_component:
            root_to_component[root] = len(root_to_component) + 1
        ids[id(edge)] = root_to_component[root]
    return ids


def _format_bounds(bounds: Bounds | None) -> str:
    if bounds is None:
        return ""
    return (
        f"{bounds.xmin:.6f};{bounds.ymin:.6f};{bounds.zmin:.6f};"
        f"{bounds.xmax:.6f};{bounds.ymax:.6f};{bounds.zmax:.6f}"
    )
