from __future__ import annotations

import math
from pathlib import Path

from cad.shape_summary import ShapeSummary
from cad.sheet_analyzer import SheetAnalysisResult, SheetContour, SheetPoint, build_sheet_analysis_from_contours


def read_dxf_sheet(
    path: str | Path,
    *,
    manual_thickness_mm: float | None = None,
) -> tuple[ShapeSummary, SheetAnalysisResult]:
    text = Path(path).read_text(encoding="utf-8", errors="ignore")
    pairs = _group_pairs(text)
    contours = _parse_entities(pairs)
    if not contours:
        raise ValueError("В DXF не найдены поддерживаемые 2D-контуры.")

    min_x, min_y, max_x, max_y = _contour_bounds(contours)
    normalized = tuple(_normalize_contour(contour, min_x=min_x, min_y=min_y) for contour in contours)
    width = max(0.0, max_x - min_x)
    height = max(0.0, max_y - min_y)
    thickness = float(manual_thickness_mm or 0.0)
    analysis = build_sheet_analysis_from_contours(
        normalized,
        width_mm=width,
        height_mm=height,
        thickness_mm=thickness,
        thickness_axis="DXF",
        warnings=("DXF рассчитан как 2D листовая деталь; единицы считаются миллиметрами.",),
    )
    summary = ShapeSummary(
        diagonal_mm=(width**2 + height**2 + thickness**2) ** 0.5,
        size_x_mm=width,
        size_y_mm=height,
        size_z_mm=thickness,
        face_count=1,
        edge_count=len(analysis.segments),
    )
    return summary, analysis


def _group_pairs(text: str) -> list[tuple[str, str]]:
    lines = [line.strip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    pairs: list[tuple[str, str]] = []
    index = 0
    while index + 1 < len(lines):
        pairs.append((lines[index], lines[index + 1]))
        index += 2
    return pairs


def _parse_entities(pairs: list[tuple[str, str]]) -> tuple[SheetContour, ...]:
    contours: list[SheetContour] = []
    index = 0
    in_entities = False
    while index < len(pairs):
        code, value = pairs[index]
        if code == "0" and value == "SECTION":
            next_pair = pairs[index + 1] if index + 1 < len(pairs) else ("", "")
            in_entities = next_pair == ("2", "ENTITIES")
            index += 2
            continue
        if code == "0" and value == "ENDSEC":
            in_entities = False
        if not in_entities or code != "0":
            index += 1
            continue

        entity = value.upper()
        next_index = _next_entity_index(pairs, index + 1)
        entity_pairs = pairs[index + 1 : next_index]
        contour = None
        if entity == "LWPOLYLINE":
            contour = _lwpolyline(entity_pairs, len(contours) + 1)
        elif entity == "LINE":
            contour = _line(entity_pairs, len(contours) + 1)
        elif entity == "CIRCLE":
            contour = _circle(entity_pairs, len(contours) + 1)
        elif entity == "ARC":
            contour = _arc(entity_pairs, len(contours) + 1)
        if contour is not None:
            contours.append(contour)
        index = next_index

    return _merge_line_contours(tuple(contours))


def _lwpolyline(pairs: list[tuple[str, str]], component_id: int) -> SheetContour | None:
    points: list[SheetPoint] = []
    closed = False
    current_x: float | None = None
    for code, value in pairs:
        if code == "70":
            closed = int(float(value or 0)) & 1 == 1
        elif code == "10":
            current_x = float(value)
        elif code == "20" and current_x is not None:
            points.append(SheetPoint(current_x, float(value)))
            current_x = None
    return _contour_from_points(points, component_id=component_id, closed=closed)


def _line(pairs: list[tuple[str, str]], component_id: int) -> SheetContour | None:
    values = _entity_values(pairs)
    if not all(key in values for key in ("10", "20", "11", "21")):
        return None
    return _contour_from_points(
        (
            SheetPoint(values["10"], values["20"]),
            SheetPoint(values["11"], values["21"]),
        ),
        component_id=component_id,
        closed=False,
    )


def _circle(pairs: list[tuple[str, str]], component_id: int) -> SheetContour | None:
    values = _entity_values(pairs)
    if not all(key in values for key in ("10", "20", "40")):
        return None
    cx = values["10"]
    cy = values["20"]
    radius = values["40"]
    points = [
        SheetPoint(
            cx + radius * math.cos(math.tau * index / 96),
            cy + radius * math.sin(math.tau * index / 96),
        )
        for index in range(96)
    ]
    return _contour_from_points(points, component_id=component_id, closed=True)


def _arc(pairs: list[tuple[str, str]], component_id: int) -> SheetContour | None:
    values = _entity_values(pairs)
    if not all(key in values for key in ("10", "20", "40", "50", "51")):
        return None
    start = math.radians(values["50"])
    end = math.radians(values["51"])
    if end < start:
        end += math.tau
    steps = max(8, int(abs(end - start) * values["40"] / 3.0))
    points = [
        SheetPoint(
            values["10"] + values["40"] * math.cos(start + (end - start) * index / steps),
            values["20"] + values["40"] * math.sin(start + (end - start) * index / steps),
        )
        for index in range(steps + 1)
    ]
    return _contour_from_points(points, component_id=component_id, closed=False)


def _entity_values(pairs: list[tuple[str, str]]) -> dict[str, float]:
    values: dict[str, float] = {}
    for code, value in pairs:
        if code in {"10", "20", "11", "21", "40", "50", "51"}:
            values[code] = float(value)
    return values


def _contour_from_points(
    points: tuple[SheetPoint, ...] | list[SheetPoint],
    *,
    component_id: int,
    closed: bool,
) -> SheetContour | None:
    clean = list(points)
    if len(clean) < 2:
        return None
    if closed and _distance(clean[0], clean[-1]) > 0.001:
        clean.append(clean[0])
    length = sum(_distance(first, second) for first, second in zip(clean, clean[1:], strict=False))
    return SheetContour(points=tuple(clean), length_mm=length, component_id=component_id)


def _merge_line_contours(contours: tuple[SheetContour, ...]) -> tuple[SheetContour, ...]:
    open_lines = [contour for contour in contours if len(contour.points) == 2]
    others = [contour for contour in contours if len(contour.points) != 2]
    if len(open_lines) <= 1:
        return contours

    used: set[int] = set()
    merged: list[SheetContour] = list(others)
    for index, contour in enumerate(open_lines):
        if index in used:
            continue
        used.add(index)
        points = [contour.points[0], contour.points[1]]
        changed = True
        while changed:
            changed = False
            for other_index, other in enumerate(open_lines):
                if other_index in used:
                    continue
                start, end = other.points
                if _distance(points[-1], start) <= 0.01:
                    points.append(end)
                elif _distance(points[-1], end) <= 0.01:
                    points.append(start)
                elif _distance(points[0], end) <= 0.01:
                    points.insert(0, start)
                elif _distance(points[0], start) <= 0.01:
                    points.insert(0, end)
                else:
                    continue
                used.add(other_index)
                changed = True
        closed = _distance(points[0], points[-1]) <= 0.01
        contour = _contour_from_points(points, component_id=len(merged) + 1, closed=closed)
        if contour is not None:
            merged.append(contour)
    return tuple(merged)


def _next_entity_index(pairs: list[tuple[str, str]], start: int) -> int:
    index = start
    while index < len(pairs):
        if pairs[index][0] == "0":
            return index
        index += 1
    return len(pairs)


def _contour_bounds(contours: tuple[SheetContour, ...]) -> tuple[float, float, float, float]:
    points = [point for contour in contours for point in contour.points]
    return (
        min(point.x_mm for point in points),
        min(point.y_mm for point in points),
        max(point.x_mm for point in points),
        max(point.y_mm for point in points),
    )


def _normalize_contour(contour: SheetContour, *, min_x: float, min_y: float) -> SheetContour:
    points = tuple(SheetPoint(point.x_mm - min_x, point.y_mm - min_y) for point in contour.points)
    return SheetContour(
        points=points,
        length_mm=contour.length_mm,
        component_id=contour.component_id,
        is_outer=contour.is_outer,
    )


def _distance(first: SheetPoint, second: SheetPoint) -> float:
    return ((first.x_mm - second.x_mm) ** 2 + (first.y_mm - second.y_mm) ** 2) ** 0.5
