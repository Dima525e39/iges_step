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
        if entity == "POLYLINE":
            contour, index = _polyline_entity(pairs, index, len(contours) + 1)
            if contour is not None:
                contours.append(contour)
            continue

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
        elif entity == "SPLINE":
            contour = _spline(entity_pairs, len(contours) + 1)
        if contour is not None:
            contours.append(contour)
        index = next_index

    return _merge_open_contours(tuple(contours))


def _lwpolyline(pairs: list[tuple[str, str]], component_id: int) -> SheetContour | None:
    points: list[SheetPoint] = []
    closed = False
    current_x: float | None = None
    for code, value in pairs:
        if code == "70":
            flag = _to_float(value)
            closed = int(flag or 0.0) & 1 == 1
        elif code == "10":
            current_x = _to_float(value)
        elif code == "20" and current_x is not None:
            y = _to_float(value)
            if y is not None:
                points.append(SheetPoint(current_x, y))
            current_x = None
    return _contour_from_points(points, component_id=component_id, closed=closed)


def _polyline_entity(
    pairs: list[tuple[str, str]],
    start_index: int,
    component_id: int,
) -> tuple[SheetContour | None, int]:
    header_end = _next_entity_index(pairs, start_index + 1)
    header_pairs = pairs[start_index + 1 : header_end]
    closed = False
    for code, value in header_pairs:
        if code == "70":
            flag = _to_float(value)
            closed = int(flag or 0.0) & 1 == 1

    points: list[SheetPoint] = []
    index = header_end
    while index < len(pairs):
        code, value = pairs[index]
        if code != "0":
            index += 1
            continue
        entity = value.upper()
        if entity == "SEQEND":
            return _contour_from_points(points, component_id=component_id, closed=closed), index + 1
        if entity != "VERTEX":
            return _contour_from_points(points, component_id=component_id, closed=closed), index

        next_index = _next_entity_index(pairs, index + 1)
        values = _entity_values(pairs[index + 1 : next_index])
        if "10" in values and "20" in values:
            points.append(SheetPoint(values["10"], values["20"]))
        index = next_index

    return _contour_from_points(points, component_id=component_id, closed=closed), index


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
    if radius <= 0.0:
        return None
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
    if values["40"] <= 0.0:
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


def _spline(pairs: list[tuple[str, str]], component_id: int) -> SheetContour | None:
    fit_points = _paired_points(pairs, x_code="11", y_code="21")
    control_points = _paired_points(pairs, x_code="10", y_code="20")
    source = fit_points if len(fit_points) >= 2 else control_points
    if len(source) < 2:
        return None

    closed = False
    for code, value in pairs:
        if code == "70":
            flag = _to_float(value)
            closed = int(flag or 0.0) & 1 == 1

    points = _sample_spline_polyline(source)
    return _contour_from_points(points, component_id=component_id, closed=closed)


def _paired_points(
    pairs: list[tuple[str, str]],
    *,
    x_code: str,
    y_code: str,
) -> list[SheetPoint]:
    points: list[SheetPoint] = []
    current_x: float | None = None
    for code, value in pairs:
        if code == x_code:
            current_x = _to_float(value)
        elif code == y_code and current_x is not None:
            y = _to_float(value)
            if y is not None:
                points.append(SheetPoint(current_x, y))
            current_x = None
    return points


def _sample_spline_polyline(points: list[SheetPoint]) -> list[SheetPoint]:
    if len(points) < 3:
        return points
    sampled: list[SheetPoint] = []
    for index in range(len(points) - 1):
        p0 = points[max(0, index - 1)]
        p1 = points[index]
        p2 = points[index + 1]
        p3 = points[min(len(points) - 1, index + 2)]
        steps = max(4, int(_distance(p1, p2) / 2.5))
        for step in range(steps):
            if sampled and step == 0:
                continue
            t = step / steps
            sampled.append(_catmull_rom(p0, p1, p2, p3, t))
    sampled.append(points[-1])
    return sampled


def _catmull_rom(
    p0: SheetPoint,
    p1: SheetPoint,
    p2: SheetPoint,
    p3: SheetPoint,
    t: float,
) -> SheetPoint:
    t2 = t * t
    t3 = t2 * t
    return SheetPoint(
        0.5
        * (
            2.0 * p1.x_mm
            + (-p0.x_mm + p2.x_mm) * t
            + (2.0 * p0.x_mm - 5.0 * p1.x_mm + 4.0 * p2.x_mm - p3.x_mm) * t2
            + (-p0.x_mm + 3.0 * p1.x_mm - 3.0 * p2.x_mm + p3.x_mm) * t3
        ),
        0.5
        * (
            2.0 * p1.y_mm
            + (-p0.y_mm + p2.y_mm) * t
            + (2.0 * p0.y_mm - 5.0 * p1.y_mm + 4.0 * p2.y_mm - p3.y_mm) * t2
            + (-p0.y_mm + 3.0 * p1.y_mm - 3.0 * p2.y_mm + p3.y_mm) * t3
        ),
    )


def _entity_values(pairs: list[tuple[str, str]]) -> dict[str, float]:
    values: dict[str, float] = {}
    for code, value in pairs:
        if code in {"10", "20", "11", "21", "40", "50", "51"}:
            number = _to_float(value)
            if number is not None:
                values[code] = number
    return values


def _to_float(value: str) -> float | None:
    try:
        return float(value.strip().replace(",", "."))
    except (AttributeError, ValueError):
        return None


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


def _merge_open_contours(contours: tuple[SheetContour, ...]) -> tuple[SheetContour, ...]:
    open_contours = [contour for contour in contours if not _is_closed_contour(contour)]
    others = [contour for contour in contours if _is_closed_contour(contour)]
    if len(open_contours) <= 1:
        return contours

    used: set[int] = set()
    merged: list[SheetContour] = list(others)
    for index, contour in enumerate(open_contours):
        if index in used:
            continue
        used.add(index)
        points = list(contour.points)
        changed = True
        while changed:
            changed = False
            for other_index, other in enumerate(open_contours):
                if other_index in used:
                    continue
                other_points = list(other.points)
                start, end = other_points[0], other_points[-1]
                if _distance(points[-1], start) <= 0.01:
                    points.extend(other_points[1:])
                elif _distance(points[-1], end) <= 0.01:
                    points.extend(reversed(other_points[:-1]))
                elif _distance(points[0], end) <= 0.01:
                    points = other_points[:-1] + points
                elif _distance(points[0], start) <= 0.01:
                    points = list(reversed(other_points[1:])) + points
                else:
                    continue
                used.add(other_index)
                changed = True
        closed = _distance(points[0], points[-1]) <= 0.01
        contour = _contour_from_points(points, component_id=len(merged) + 1, closed=closed)
        if contour is not None:
            merged.append(contour)
    return tuple(merged)


def _is_closed_contour(contour: SheetContour) -> bool:
    return len(contour.points) >= 3 and _distance(contour.points[0], contour.points[-1]) <= 0.01


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
