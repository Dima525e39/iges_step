from __future__ import annotations

from dataclasses import dataclass

from cad.edge_classifier import EdgeClassificationResult, EdgeRecord


@dataclass(slots=True)
class PierceEstimate:
    pierce_count: int
    open_contour_count: int = 0
    warnings: tuple[str, ...] = ()


class PierceCounter:
    """Counts likely laser pierces as connected cut-contour components."""

    def count(self, contours: object) -> int:
        if isinstance(contours, EdgeClassificationResult):
            return count_edge_components(contours.cut_edges).pierce_count
        raise TypeError("Ожидался EdgeClassificationResult.")


def count_edge_components(edges: tuple[EdgeRecord, ...]) -> PierceEstimate:
    if not edges:
        return PierceEstimate(pierce_count=0)

    pairs = tuple((edge.start_vertex, edge.end_vertex) for edge in edges)
    return _count_components_from_pairs(pairs)


def _count_components_from_pairs(
    pairs: tuple[tuple[object | None, object | None], ...]
) -> PierceEstimate:
    if not pairs:
        return PierceEstimate(pierce_count=0)

    parent = list(range(len(pairs)))
    open_count = 0

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

    for left_index, (left_start, left_end) in enumerate(pairs):
        if left_start is None or left_end is None:
            open_count += 1
            continue
        for right_index in range(left_index + 1, len(pairs)):
            right_start, right_end = pairs[right_index]
            if right_start is None or right_end is None:
                continue
            if (
                _is_same_vertex(left_start, right_start)
                or _is_same_vertex(left_start, right_end)
                or _is_same_vertex(left_end, right_start)
                or _is_same_vertex(left_end, right_end)
            ):
                union(left_index, right_index)

    component_count = len({find(index) for index in range(len(pairs))})
    warnings: tuple[str, ...] = ()
    if open_count:
        warnings = (f"У {open_count} ребер не удалось прочитать вершины; врезки посчитаны приближенно.",)
    return PierceEstimate(
        pierce_count=component_count,
        open_contour_count=open_count,
        warnings=warnings,
    )


def _is_same_vertex(first: object, second: object) -> bool:
    try:
        return bool(first.IsSame(second))
    except Exception:
        return first is second or first == second
