from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class StepRoundTubeTextAnalysis:
    outer_diameter_mm: float
    inner_diameter_mm: float
    wall_thickness_mm: float
    length_mm: float
    cut_length_mm: float
    cut_end_length_mm: float
    cut_feature_length_mm: float
    pierce_count: int
    warnings: tuple[str, ...] = ()


def analyze_step_round_tube_text(path: str | Path) -> StepRoundTubeTextAnalysis | None:
    file_path = Path(path)
    if file_path.suffix.casefold() not in {".step", ".stp"}:
        return None
    try:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None

    entities = _parse_entities(text)
    cylinder_radii = _cylinder_radii(entities)
    distinct_radii = _distinct_sorted(cylinder_radii.values(), tolerance=0.01)
    if len(distinct_radii) < 2:
        return None

    outer_radius = distinct_radii[-1]
    inner_radius = distinct_radii[-2]
    thickness = outer_radius - inner_radius
    if outer_radius <= 0.0 or thickness <= 0.0:
        return None

    pcurves = _pcurves(entities)
    edge_curves = _edge_curves(entities)
    selected_lengths: list[float] = []
    axial_values: list[float] = []
    for curve_id in edge_curves:
        curve = entities.get(curve_id, "")
        if not curve.startswith("SURFACE_CURVE"):
            continue
        edge_lengths: list[float] = []
        for pcurve_id in _refs(curve)[1:]:
            surface_id, representation_id = pcurves.get(pcurve_id, (0, 0))
            if cylinder_radii.get(surface_id) != outer_radius:
                continue
            curve_ref = _representation_curve_ref(entities.get(representation_id, ""))
            points = _bspline_points(entities, curve_ref)
            if len(points) < 2:
                continue
            axial_values.extend(point[1] for point in points)
            u_values = [point[0] for point in points]
            v_values = [point[1] for point in points]
            u_span = max(u_values) - min(u_values)
            v_span = max(v_values) - min(v_values)
            if u_span < math.pi:
                continue
            if v_span > max(outer_radius * 6.0, 150.0):
                continue
            edge_lengths.append(_cylindrical_bspline_length(points, outer_radius))
        if edge_lengths:
            selected_lengths.append(max(edge_lengths))

    if len(selected_lengths) < 2:
        return None

    length_mm = max((abs(value) for value in axial_values), default=0.0)
    cut_end_length = sum(selected_lengths)
    return StepRoundTubeTextAnalysis(
        outer_diameter_mm=outer_radius * 2.0,
        inner_diameter_mm=inner_radius * 2.0,
        wall_thickness_mm=thickness,
        length_mm=length_mm,
        cut_length_mm=cut_end_length,
        cut_end_length_mm=cut_end_length,
        cut_feature_length_mm=0.0,
        pierce_count=len(selected_lengths),
        warnings=(
            "Круглая STEP-труба рассчитана по текстовым pcurve-контурам цилиндра; "
            "косой торец считается по реальной длине кривой, а не по πD.",
        ),
    )


def _parse_entities(text: str) -> dict[int, str]:
    entities: dict[int, str] = {}
    for match in re.finditer(r"#(\d+)\s*=\s*(.*?);", text, flags=re.S):
        entities[int(match.group(1))] = " ".join(match.group(2).split())
    return entities


def _cylinder_radii(entities: dict[int, str]) -> dict[int, float]:
    radii: dict[int, float] = {}
    pattern = re.compile(r"CYLINDRICAL_SURFACE\('[^']*',#\d+,({number})\)".format(number=_NUMBER))
    for entity_id, value in entities.items():
        match = pattern.search(value)
        if match:
            radii[entity_id] = float(match.group(1).replace("E", "e"))
    return radii


def _pcurves(entities: dict[int, str]) -> dict[int, tuple[int, int]]:
    result: dict[int, tuple[int, int]] = {}
    pattern = re.compile(r"PCURVE\('[^']*',#(\d+),#(\d+)\)")
    for entity_id, value in entities.items():
        match = pattern.search(value)
        if match:
            result[entity_id] = (int(match.group(1)), int(match.group(2)))
    return result


def _edge_curves(entities: dict[int, str]) -> list[int]:
    result: list[int] = []
    pattern = re.compile(r"EDGE_CURVE\('[^']*',#\d+,#\d+,#(\d+),")
    for value in entities.values():
        match = pattern.search(value)
        if match:
            result.append(int(match.group(1)))
    return result


def _representation_curve_ref(value: str) -> int:
    refs = _refs(value)
    return refs[0] if refs else 0


def _bspline_points(entities: dict[int, str], curve_id: int) -> list[tuple[float, float]]:
    curve = entities.get(curve_id, "")
    if not curve.startswith("B_SPLINE_CURVE_WITH_KNOTS"):
        return []
    points: list[tuple[float, float]] = []
    for ref in _refs(curve):
        point = entities.get(ref, "")
        if point.startswith("CARTESIAN_POINT"):
            values = _numbers(point)
            if len(values) >= 2:
                points.append((values[-2], values[-1]))
    return points


def _cylindrical_bspline_length(
    points: list[tuple[float, float]],
    radius: float,
    *,
    steps: int = 720,
) -> float:
    if len(points) == 2:
        du = points[1][0] - points[0][0]
        dv = points[1][1] - points[0][1]
        return math.hypot(radius * du, dv)

    previous = _bezier_point(points, 0.0)
    length = 0.0
    for index in range(1, steps + 1):
        current = _bezier_point(points, index / steps)
        length += math.hypot(
            radius * (current[0] - previous[0]),
            current[1] - previous[1],
        )
        previous = current
    return length


def _bezier_point(points: list[tuple[float, float]], t: float) -> tuple[float, float]:
    values = [list(point) for point in points]
    for level in range(1, len(values)):
        for index in range(len(values) - level):
            values[index][0] = (1.0 - t) * values[index][0] + t * values[index + 1][0]
            values[index][1] = (1.0 - t) * values[index][1] + t * values[index + 1][1]
    return values[0][0], values[0][1]


def _distinct_sorted(values, *, tolerance: float) -> tuple[float, ...]:
    distinct: list[float] = []
    for value in sorted(float(item) for item in values):
        if distinct and abs(value - distinct[-1]) <= tolerance:
            continue
        distinct.append(value)
    return tuple(distinct)


def _refs(value: str) -> list[int]:
    return [int(item) for item in re.findall(r"#(\d+)", value)]


def _numbers(value: str) -> list[float]:
    return [float(item.replace("E", "e")) for item in re.findall(_NUMBER, value)]


_NUMBER = r"[-+]?\d*\.?\d+(?:[Ee][-+]?\d+)?"
